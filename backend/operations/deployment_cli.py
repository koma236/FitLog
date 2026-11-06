"""Local-only by default. Real-AWS modes require an explicit operator opt-in."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from operations.deployment_assets import upload
from operations.deployment_aws import Api, Gateway, collect, preflight, task_definition
from operations.deployment_contract import (
    STEPS,
    DeploymentError,
    Manifest,
    canonical,
    require,
    write_evidence,
)
from operations.deployment_step import Parser

PREVIOUS = {'bootstrap': 'bootstrap-inspect', 'migrate': 'bootstrap', 'seed': 'migrate',
            'check': 'seed', 'verify': 'check'}


def identity(manifest: Manifest) -> str:
    """Allow reviewed task revisions/expiry updates without changing the deployment."""
    data = json.loads(canonical(manifest.data))
    del data['approval']
    del data['resources']['backend_task'], data['resources']['bootstrap_task']
    return hashlib.sha256(canonical(data)).hexdigest()


def save_private(path: Path, data: object) -> None:
    require(not path.is_symlink())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical(data))
        stream.flush()
        os.fsync(stream.fileno())


def predecessor(folder: Path, manifest: Manifest, step: str) -> None:
    if step not in PREVIOUS:
        return
    name = PREVIOUS[step]
    path = folder / f"{manifest.data['run_id']}-{name}.json"
    require(not path.is_symlink())
    result = json.loads(path.read_text())
    require(result.get('schema_version') == 2 and result.get('deployment_identity') == identity(manifest))
    require(result['run_id'] == manifest.data['run_id'] and result['step'] == name
            and result['status'] == 'pass' and result['source_revision'] == manifest.data['source_revision']
            and result['image_digest'] == manifest.data['image_digest'])


def task_command(manifest: Manifest, step: str) -> list[str]:
    if step.startswith('bootstrap'):
        command = ['python', '-m', 'operations.bootstrap', '--expected-account-id',
                   manifest.data['account'], '--environment', manifest.environment,
                   '--db-instance-identifier', manifest.environment, '--application-secret-arn',
                   manifest.resources['application_secret'], '--distribution-id',
                   manifest.resources['distribution'], '--operation-id', manifest.data['bootstrap_id']]
        if step == 'bootstrap':
            command.append('--initialize')
        return command
    require(step in ('migrate', 'seed', 'check', 'verify'))
    return ['python', '-m', 'operations.deployment_step', '--step', step, '--run-id',
            manifest.data['run_id'], '--expected-host', manifest.resources['database_host'],
            '--environment', manifest.environment]


def execute(
    api: Api, manifest: Manifest, folder: Path, step: str, phase: str,
    verify_input: dict[str, Any] | None = None, resume_task: str | None = None,
) -> str:
    """Intent is durable before RunTask. An unknown outcome requires reconciliation."""
    if step != 'verify':
        require(phase == 'private' and verify_input is None)
    else:
        require(verify_input is not None)
        assert verify_input is not None
        validate_verify_input(manifest, phase, verify_input)
    predecessor(folder, manifest, step)
    if verify_input is not None and verify_input['mode'] == 'ip':
        baseline = folder / f"{manifest.data['run_id']}-verify-public-ip-baseline.json"
        require(not baseline.is_symlink())
        record = json.loads(baseline.read_text())
        require(record['status'] == 'pass' and record.get('deployment_identity') == identity(manifest))
        require(record.get('parameters_sha256') ==
                hashlib.sha256(canonical(verify_input['parameters'])).hexdigest())
    network = preflight(api, manifest, phase)
    command = task_command(manifest, step)
    override: dict[str, Any] = {'name': 'backend', 'command': command}
    if verify_input is not None:
        override['environment'] = [{'name': 'FITLOG_VERIFY_INPUT',
                                    'value': canonical(verify_input).decode()}]
    token = str(uuid.uuid5(uuid.UUID(manifest.data['run_id']),
                           manifest.fingerprint + step + phase + canonical(verify_input).decode()))
    label = step_label(step, phase, verify_input)
    intent = {'manifest_sha256': manifest.fingerprint, 'token': token,
              'deployment_identity': identity(manifest),
              'definition': task_definition(manifest, step), 'step': step, 'phase': phase,
              'overrides_sha256': hashlib.sha256(canonical(override)).hexdigest()}
    # Repeating an invocation is deliberately refused, even if RunTask timed out.
    # Inspect ECS startedBy/task overrides, reconcile, then use collect-only.
    intent_path = folder / f"{manifest.data['run_id']}-{label}.intent"
    if resume_task is None:
        save_private(intent_path, intent)
        manifest.authorize(datetime.now(UTC))
        result = api.call('ecs', 'run_task', cluster=manifest.environment,
                          taskDefinition=task_definition(manifest, step), count=1,
                          launchType='FARGATE', platformVersion='1.4.0',
                          startedBy=manifest.data['run_id'], clientToken=token,
                          enableExecuteCommand=False,
                          networkConfiguration={'awsvpcConfiguration': network},
                          overrides={'containerOverrides': [override]})
        require(not result.get('failures') and len(result.get('tasks', [])) == 1)
        task = result['tasks'][0]['taskArn']
        save_private(folder / f"{manifest.data['run_id']}-{label}.task", {'task': task})
    else:
        require(not intent_path.is_symlink())
        stored = json.loads(intent_path.read_text())
        require(set(stored) == set(intent))
        require(all(stored[key] == intent[key] for key in (
            'deployment_identity', 'definition', 'step', 'phase', 'overrides_sha256')))
        require(isinstance(stored['manifest_sha256'], str)
                and len(stored['manifest_sha256']) == 64
                and all(c in '0123456789abcdef' for c in stored['manifest_sha256']))
        expected_token = str(uuid.uuid5(uuid.UUID(manifest.data['run_id']),
                                       stored['manifest_sha256'] + step + phase
                                       + canonical(verify_input).decode()))
        require(stored['token'] == expected_token)
        actual = api.call('ecs', 'describe_tasks', cluster=manifest.environment,
                          tasks=[resume_task])['tasks']
        require(len(actual) == 1 and actual[0]['taskArn'] == resume_task
                and actual[0]['startedBy'] == manifest.data['run_id']
                and actual[0]['overrides']['containerOverrides'] == [override])
        task = resume_task
    try:
        collect(api, manifest, step, task)
    except Exception:
        # Stop only the validated task from this response, never a service or an
        # unrelated task. STOPPED confirmation is required before returning.
        result = api.call('ecs', 'describe_tasks', cluster=manifest.environment, tasks=[task])
        require(not result.get('failures') and len(result['tasks']) == 1)
        actual = result['tasks'][0]
        require(actual['taskArn'] == task and actual['startedBy'] == manifest.data['run_id']
                and actual['taskDefinitionArn'] == task_definition(manifest, step))
        if actual['lastStatus'] != 'STOPPED':
            api.call('ecs', 'stop_task', cluster=manifest.environment, task=task,
                     reason='FitLog deployment verification failed')
            for _ in range(20):
                import time
                time.sleep(3)
                current = api.call('ecs', 'describe_tasks', cluster=manifest.environment,
                                   tasks=[task])['tasks']
                if len(current) == 1 and current[0]['taskArn'] == task \
                        and current[0]['lastStatus'] == 'STOPPED':
                    break
            else:
                raise DeploymentError() from None
        raise DeploymentError() from None
    return str(task)


def step_label(step: str, phase: str, verify_input: dict[str, Any] | None) -> str:
    if step != 'verify':
        return step
    require(verify_input is not None)
    assert verify_input is not None
    return f"verify-{phase}-{verify_input['mode']}"


def validate_verify_input(manifest: Manifest, phase: str, data: dict[str, Any]) -> None:
    require(isinstance(data, dict) and set(data) == {'mode', 'parameters'})
    mode, params = data['mode'], data['parameters']
    require(mode in ('database', 'permissions', 'ip', 'ip-baseline') and isinstance(params, dict)
            and phase in ('backend', 'public')
            and (phase == 'public' or mode == 'database'))
    if mode == 'database':
        require(not params)
    elif mode == 'permissions':
        require(params == {'account': manifest.data['account'],
                           'application_secret': manifest.resources['application_secret'],
                           'master_secret': manifest.resources['master_secret'],
                           'version': manifest.data['bootstrap_id'], 'fixture_verified': True})
    else:
        require(set(params) == {'expected_ip', 'spoof_ip', 'window', 'before', 'spoof_before'})
        for name in ('expected_ip', 'spoof_ip'):
            require(str(ipaddress.ip_address(params[name])) == params[name])
        window = datetime.fromisoformat(params['window'])
        require(window.tzinfo is not None and window.second == 0 and window.microsecond == 0)
        require(type(params['before']) is int and 0 <= params['before'] < 10
                and type(params['spoof_before']) is int and params['spoof_before'] >= 0)


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description='Offline deployment manifest validation by default', allow_abbrev=False)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--aws-approved', action='store_true')
    parser.add_argument('--step', choices=('inspect', 'bootstrap-inspect', 'bootstrap', 'migrate',
                                          'seed', 'check', 'verify', 'static'), default='inspect')
    parser.add_argument('--phase', choices=('private', 'backend', 'public'), default='private')
    parser.add_argument('--verify-input', type=Path)
    parser.add_argument('--collect-task', help='Reconcile an existing intent; never launches a task')
    parser.add_argument('--static-root', type=Path)
    parser.add_argument('--assets', type=Path)
    lock: Path | None = None
    manifest: Manifest | None = None
    args = None
    started_at = datetime.now(UTC).isoformat()
    logging.disable(logging.CRITICAL)
    try:
        args = parser.parse_args(argv)
        manifest = Manifest.parse(json.loads(args.manifest.read_text()))
        if not args.aws_approved:
            require(args.step == 'inspect' and args.evidence is None and args.verify_input is None)
            print(json.dumps({'event': 'deployment_manifest_validated',
                              'manifest_sha256': manifest.fingerprint}))
            return 0
        manifest.authorize(datetime.now(UTC))
        require(args.evidence is not None)
        args.evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(not args.evidence.is_symlink() and args.evidence.stat().st_mode & 0o777 == 0o700)
        candidate = args.evidence / 'deployment.lock'
        candidate.mkdir()  # Do not steal another operator's lock.
        lock = candidate
        api = Gateway.connect()
        task = None
        verify_input = None
        if args.step == 'inspect':
            preflight(api, manifest, args.phase)
        elif args.step == 'static':
            require(args.static_root is not None and args.assets is not None and args.phase == 'private')
            preflight(api, manifest, 'private')
            upload(api, manifest, args.static_root, json.loads(args.assets.read_text()))
            # Static inventory is artifact evidence, not a task state transition.
            save_private(args.evidence / f"{manifest.data['run_id']}-static.json",
                         {'manifest_sha256': manifest.fingerprint, 'status': 'pass'})
            return 0
        else:
            verify_input = json.loads(args.verify_input.read_text()) if args.verify_input else None
            task = execute(api, manifest, args.evidence, args.step, args.phase, verify_input,
                           args.collect_task)
        label = step_label(args.step, args.phase, verify_input)
        parameters_hash = (hashlib.sha256(canonical(verify_input['parameters'])).hexdigest()
                           if verify_input is not None else None)
        write_evidence(args.evidence, manifest, label, 'pass', task, 0 if task else None, started_at,
                       deployment_identity=identity(manifest), parameters_sha256=parameters_hash,
                       allow_existing=args.collect_task is not None)
    except (Exception, SystemExit):
        if lock is not None and manifest is not None and args is not None:
            try:
                save_private(args.evidence / (manifest.data['run_id'] + '-attempt-'
                             + str(uuid.uuid4()) + '.json'),
                             {'status': 'fail', 'step': args.step if args.step in STEPS else 'inspect',
                              'run_id': manifest.data['run_id'], 'manifest_sha256': manifest.fingerprint,
                              'started_at': started_at, 'finished_at': datetime.now(UTC).isoformat()})
            except OSError:
                print('{"event":"deployment_evidence_failed"}', file=sys.stderr)
        print('{"event":"deployment_failed"}', file=sys.stderr)
        return 2
    finally:
        if lock is not None:
            lock.rmdir()
    print('{"event":"deployment_completed"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Offline C handoff: aggregate bound observations, never certify an unrun test."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from operations.deployment_artifacts import digest, read_private, timestamp, validate_artifacts
from operations.deployment_cli import identity
from operations.deployment_contract import LIVE_EVIDENCE_STEPS, REGION, Manifest, matches, require

REQUIRED = ('inspect', 'static', 'bootstrap-inspect', 'bootstrap', 'migrate', 'seed',
            'check', 'backend', 'verify-backend-database', 'public-health')
REMOTE = ('bootstrap-inspect', 'bootstrap', 'migrate', 'seed', 'check',
          'verify-backend-database', 'verify-public-permissions', 'verify-public-ip',
          'verify-public-ip-baseline')


def observation(folder: Path, manifest: Manifest, step: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Read a validated receipt and return only an allowlisted reference/hash."""
    path = folder / f"{manifest.data['run_id']}-{step}.json"
    data = read_private(path)
    require(isinstance(data, dict) and data.get('schema_version') == 2
            and data.get('status') == 'pass' and data.get('step') == step
            and data.get('deployment_identity') == identity(manifest))
    for key in ('run_id', 'source_revision', 'image_digest', 'frontend_sha256'):
        require(data.get(key) == manifest.data[key])
    require(matches(r'[a-f0-9]{64}', data.get('manifest_sha256')))
    if step in LIVE_EVIDENCE_STEPS:
        require(data.get('backend_task') == manifest.resources['backend_task'])
    require(timestamp(data['started_at']) <= timestamp(data['finished_at']) <= datetime.now(UTC))
    if step in REMOTE:
        prefix = f"arn:aws:ecs:{REGION}:{manifest.data['account']}:task/{manifest.environment}/"
        task = data.get('task')
        require(isinstance(task, str) and task.startswith(prefix)
                and matches(r'[a-f0-9]{32}', task[len(prefix):]) and data.get('exit_code') == 0)
    return data, {'step': step, 'path': str(path), 'sha256': digest(data)}


def handoff(manifest: Manifest, artifacts: Any, folder: Path, window: Any) -> dict[str, Any]:
    """Create a ready_for_c summary; the actual C acceptance remains independent."""
    manifest.authorize(datetime.now(UTC), 'inspect')
    artifacts = validate_artifacts(artifacts, manifest)
    require(isinstance(window, dict) and set(window) == {'starts_at', 'ends_at', 'approval_reference'}
            and window['approval_reference'] == manifest.data['approval']['reference'])
    start, end = timestamp(window['starts_at']), timestamp(window['ends_at'])
    require(start < end <= timestamp(manifest.data['approval']['expires_at'])
            and datetime.now(UTC) < end)
    references = []
    observations = {}
    for step in REQUIRED:
        record, ref = observation(folder, manifest, step)
        observations[step] = record
        references.append(ref)
    origin = observations['public-health'].get('origin')
    require(matches(r'https://[a-z0-9]+\.cloudfront\.net', origin)
            and observations['backend'].get('origin') == origin
            and timestamp(observations['public-health']['finished_at']) <= start)
    probes = {}
    for mode in ('permissions', 'ip'):
        label = 'verify-public-' + mode
        path = folder / f"{manifest.data['run_id']}-{label}.json"
        if not path.exists() and not path.is_symlink():
            probes[mode] = 'not_run'
            continue
        record, ref = observation(folder, manifest, label)
        require(matches(r'[a-f0-9]{64}', record.get('parameters_sha256')))
        if mode == 'ip':
            baseline, baseline_ref = observation(folder, manifest, 'verify-public-ip-baseline')
            require(baseline['parameters_sha256'] == record['parameters_sha256'])
            references.append(baseline_ref)
        references.append(ref)
        probes[mode] = 'pass'
    return {'schema_version': 1, 'status': 'ready_for_c', 'account': manifest.data['account'],
            'region': REGION, 'environment': manifest.environment,
            'run_id': manifest.data['run_id'], 'bootstrap_id': manifest.data['bootstrap_id'],
            'source_revision': manifest.data['source_revision'], 'image_digest': manifest.data['image_digest'],
            'frontend_sha256': manifest.data['frontend_sha256'], 'artifact_sha256': digest(artifacts),
            'manifest_sha256': manifest.fingerprint, 'origin': origin, 'window': dict(window),
            'evidence': references, 'probes': probes}

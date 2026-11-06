"""Non-secret deployment manifest and append-only evidence; no AWS imports."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

REGION = 'ap-northeast-1'
STEPS = ('inspect', 'bootstrap-inspect', 'bootstrap', 'migrate', 'seed', 'check',
         'backend', 'verify', 'verify-backend-database', 'verify-public-database',
         'verify-public-permissions', 'verify-public-ip',
         'verify-public-ip-baseline',
         'capture', 'destroy', 'rebuild', 'destroy-again')


class DeploymentError(Exception):
    """Fixed error boundary: upstream messages must never be displayed."""

    def __init__(self) -> None:
        super().__init__('deployment_failed')


def require(condition: bool) -> None:
    if not condition:
        raise DeploymentError()


def matches(pattern: str, value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


@dataclass(frozen=True)
class Manifest:
    """Validated metadata; authorize separately immediately before AWS operations."""

    data: dict[str, Any]

    @classmethod
    def parse(cls, data: Any) -> Manifest:
        require(isinstance(data, dict) and set(data) == {
            'schema_version', 'run_id', 'account', 'region', 'environment', 'source_revision',
            'image_digest', 'frontend_sha256', 'bootstrap_id', 'approval', 'resources',
        })
        require(data['schema_version'] == 1 and data['region'] == REGION)
        require(matches(r'[0-9]{12}', data['account']))
        env = data['environment']
        require(matches(r'fitlog-demo-[a-z0-9]+(?:-[a-z0-9]+)*', env) and len(env) <= 24)
        for name in ('run_id', 'bootstrap_id'):
            require(isinstance(data[name], str) and str(uuid.UUID(data[name])) == data[name])
        require(matches(r'[a-f0-9]{40}', data['source_revision']))
        require(matches(r'sha256:[a-f0-9]{64}', data['image_digest']))
        require(matches(r'[a-f0-9]{64}', data['frontend_sha256']))
        approval = data['approval']
        require(isinstance(approval, dict) and set(approval) == {
            'reference', 'budget_usd', 'expires_at',
        })
        require(matches(r'[a-zA-Z0-9_.:/#-]{1,160}', approval['reference']))
        require(matches(r'[0-9]{1,6}\.[0-9]{2}', approval['budget_usd'])
                and Decimal(approval['budget_usd']) > 0)
        expiry = datetime.fromisoformat(approval['expires_at'])
        require(expiry.tzinfo is not None)
        resources = data['resources']
        require(isinstance(resources, dict) and set(resources) == {
            'distribution', 'database_host', 'application_secret', 'master_secret',
            'backend_task', 'bootstrap_task', 'subnets', 'security_group',
        })
        account = data['account']
        require(matches(r'[A-Z0-9]{1,32}', resources['distribution']))
        require(matches(r'[a-z0-9.-]+\.ap-northeast-1\.rds\.amazonaws\.com',
                        resources['database_host']))
        prefix = f'arn:aws:secretsmanager:{REGION}:{account}:secret:'
        require(matches(re.escape(prefix + env + '/application-') + r'[A-Za-z0-9]{6}',
                        resources['application_secret']))
        require(matches(re.escape(prefix) + r'rds!db-[A-Za-z0-9-]+', resources['master_secret']))
        for role in ('backend', 'bootstrap'):
            require(matches(re.escape(f'arn:aws:ecs:{REGION}:{account}:task-definition/{env}-')
                            + role + r':[1-9][0-9]*', resources[role + '_task']))
        require(isinstance(resources['subnets'], list) and len(resources['subnets']) == 2
                and all(matches(r'subnet-[a-f0-9]{17}', v) for v in resources['subnets'])
                and len(set(resources['subnets'])) == 2)
        require(matches(r'sg-[a-f0-9]{17}', resources['security_group']))
        return cls(json.loads(canonical(data)))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical(self.data)).hexdigest()

    @property
    def environment(self) -> str:
        return str(self.data['environment'])

    @property
    def resources(self) -> dict[str, Any]:
        return dict(self.data['resources'])

    def authorize(self, now: datetime) -> None:
        require(now.tzinfo is not None
                and now < datetime.fromisoformat(self.data['approval']['expires_at']))


def write_evidence(
    folder: Path, manifest: Manifest, step: str, status: str,
    task: str | None = None, exit_code: int | None = None, started_at: str | None = None,
    deployment_identity: str | None = None, parameters_sha256: str | None = None,
    allow_existing: bool = False,
) -> Path:
    """Only allowlisted metadata, exclusive creation and restrictive permissions."""
    require(step in STEPS and status in ('pass', 'fail', 'not_run'))
    require(task is None or matches(
        re.escape(f"arn:aws:ecs:{REGION}:{manifest.data['account']}:task/{manifest.environment}/")
        + r'[a-f0-9]{32}', task))
    require(exit_code is None or type(exit_code) is int)
    require(deployment_identity is None or matches(r'[a-f0-9]{64}', deployment_identity))
    require(parameters_sha256 is None or matches(r'[a-f0-9]{64}', parameters_sha256))
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not folder.is_symlink() and folder.stat().st_mode & 0o777 == 0o700)
    directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = f"{manifest.data['run_id']}-{step}.json"
    record = {'schema_version': 2, 'run_id': manifest.data['run_id'],
              'manifest_sha256': manifest.fingerprint, 'source_revision': manifest.data['source_revision'],
              'image_digest': manifest.data['image_digest'], 'step': step, 'status': status,
              'deployment_identity': deployment_identity or manifest.fingerprint,
              'parameters_sha256': parameters_sha256,
              'started_at': started_at or datetime.now(UTC).isoformat(),
              'finished_at': datetime.now(UTC).isoformat(), 'task': task, 'exit_code': exit_code}
    temporary = '.evidence-' + uuid.uuid4().hex + '.tmp'
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=directory)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(record))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Link publishes a complete fsynced record without replacing an
            # existing success. A crash cannot publish half a JSON document.
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False)
            os.fsync(directory)
        except FileExistsError:
            require(allow_existing)
            existing_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(existing_fd) as stream:
                existing = json.load(stream)
            # Current approval metadata/timestamps can change during recovery;
            # immutable deployment/task/step bindings cannot.
            keys = ('schema_version', 'run_id', 'source_revision', 'image_digest',
                    'step', 'status', 'deployment_identity', 'parameters_sha256', 'task', 'exit_code')
            require(all(existing.get(key) == record[key] for key in keys))
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)
    return folder / name

"""Non-secret deployment manifest and append-only evidence; no AWS imports."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any

REGION = 'ap-northeast-1'
OPERATIONS = ('inspect', 'static', 'bootstrap-inspect', 'bootstrap', 'migrate', 'seed',
              'check', 'verify')
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


def _fields(value: Any, names: set[str], draft: bool) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) <= names
            and (draft or set(value) == names))
    assert isinstance(value, dict)
    return value


def _field(data: dict[str, Any], name: str, draft: bool,
           check: Callable[[Any], bool]) -> None:
    value = data.get(name)
    if value is None:
        require(draft)
    else:
        require(check(value))


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _absolute_path(value: Any) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 4096 and '\x00' not in value
            and Path(value).is_absolute() and '..' not in Path(value).parts)


@dataclass(frozen=True)
class Manifest:
    """Validated metadata; authorize separately immediately before AWS operations."""

    data: dict[str, Any]
    draft: bool = False

    @classmethod
    def parse(cls, data: Any, *, draft: bool = False) -> Manifest:
        data = _fields(data, {
            'schema_version', 'run_id', 'account', 'region', 'environment', 'source_revision',
            'image_digest', 'frontend_sha256', 'bootstrap_id', 'approval', 'resources', 'state',
        }, draft)
        _field(data, 'schema_version', draft, lambda v: type(v) is int and v == 1)
        _field(data, 'region', draft, lambda v: v == REGION)
        _field(data, 'account', draft, lambda v: matches(r'[0-9]{12}', v))
        _field(data, 'environment', draft, lambda v:
               matches(r'fitlog-demo-[a-z0-9]+(?:-[a-z0-9]+)*', v) and len(v) <= 24)
        for name in ('run_id', 'bootstrap_id'):
            _field(data, name, draft, lambda v:
                   matches(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', v))
        for name, pattern in (('source_revision', r'[a-f0-9]{40}'),
                              ('image_digest', r'sha256:[a-f0-9]{64}'),
                              ('frontend_sha256', r'[a-f0-9]{64}')):
            _field(data, name, draft, partial(matches, pattern))
        if data.get('approval') is not None or not draft:
            approval = _fields(data.get('approval'), {
                'reference', 'budget_usd', 'expires_at', 'steps'}, draft)
            _field(approval, 'reference', draft, lambda v: matches(r'[a-zA-Z0-9_.:/#-]{1,160}', v))
            _field(approval, 'budget_usd', draft, lambda v:
                   matches(r'[0-9]{1,6}\.[0-9]{2}', v) and Decimal(v) > 0)
            _field(approval, 'expires_at', draft, _timestamp)
            _field(approval, 'steps', draft, lambda v:
                   isinstance(v, list) and 0 < len(v) <= len(OPERATIONS)
                   and all(isinstance(step, str) and step in OPERATIONS for step in v)
                   and len(set(v)) == len(v))
        if data.get('state') is not None or not draft:
            state = _fields(data.get('state'), {'path', 'sha256'}, draft)
            _field(state, 'path', draft, _absolute_path)
            _field(state, 'sha256', draft, lambda v: matches(r'[a-f0-9]{64}', v))
        if data.get('resources') is None and draft:
            return cls(json.loads(canonical(data)), draft=True)
        resources = _fields(data.get('resources'), {
            'distribution', 'database_host', 'application_secret', 'master_secret',
            'backend_task', 'bootstrap_task', 'subnets', 'security_group',
        }, draft)
        account = re.escape(data['account']) if data.get('account') else r'[0-9]{12}'
        env = (re.escape(data['environment']) if data.get('environment')
               else r'fitlog-demo-[a-z0-9]+(?:-[a-z0-9]+)*')
        _field(resources, 'distribution', draft, lambda v: matches(r'[A-Z0-9]{1,32}', v))
        _field(resources, 'database_host', draft, lambda v:
               matches(r'[a-z0-9.-]+\.ap-northeast-1\.rds\.amazonaws\.com', v))
        prefix = f'arn:aws:secretsmanager:{REGION}:{account}:secret:'
        _field(resources, 'application_secret', draft, lambda v:
               matches(prefix + env + r'/application-[A-Za-z0-9]{6}', v))
        _field(resources, 'master_secret', draft, lambda v:
               matches(prefix + r'rds!db-[A-Za-z0-9-]+', v))
        for role in ('backend', 'bootstrap'):
            pattern = f'arn:aws:ecs:{REGION}:{account}:task-definition/{env}-{role}:[1-9][0-9]*'
            _field(resources, role + '_task', draft, partial(matches, pattern))
        _field(resources, 'subnets', draft, lambda v:
               isinstance(v, list) and len(v) == 2
               and all(matches(r'subnet-[a-f0-9]{17}', item) for item in v) and len(set(v)) == 2)
        _field(resources, 'security_group', draft, lambda v: matches(r'sg-[a-f0-9]{17}', v))
        return cls(json.loads(canonical(data)), draft=draft)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical(self.data)).hexdigest()

    @property
    def environment(self) -> str:
        return str(self.data['environment'])

    @property
    def resources(self) -> dict[str, Any]:
        return dict(self.data['resources'])

    def authorize(self, now: datetime, step: str | None = None) -> None:
        require(not self.draft and now.tzinfo is not None
                and now < datetime.fromisoformat(self.data['approval']['expires_at']))
        if step is not None:
            require(step in self.data['approval']['steps'])

    def validate_state(self) -> None:
        """Bind the protected local artifact without displaying/parsing secret state."""
        require(not self.draft)
        path = Path(self.data['state']['path'])
        require(path == path.resolve(strict=True)
                and path.parent.stat().st_mode & 0o777 == 0o700
                and path.parent.stat().st_uid == os.getuid())
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid()
                    and stat.S_IMODE(metadata.st_mode) in (0o400, 0o600))
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(digest == self.data['state']['sha256'])


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

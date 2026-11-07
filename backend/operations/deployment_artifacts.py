"""Offline artifact bindings and private metadata I/O. Never discovers credentials."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from operations.deployment_contract import REGION, Manifest, canonical, matches, require


def digest(data: object) -> str:
    """Hash canonical non-secret metadata."""
    return hashlib.sha256(canonical(data)).hexdigest()


def private_path(path: Path) -> None:
    """Require a canonical, operator-owned directory without symlink ancestors."""
    require(path.is_absolute() and path.parent == path.parent.resolve(strict=True)
            and path.parent.stat().st_uid == os.getuid()
            and stat.S_IMODE(path.parent.stat().st_mode) == 0o700)


def read_private(path: Path) -> Any:
    """Read only an owned, protected regular JSON file; no raw error printing."""
    private_path(path)
    require(not path.is_symlink())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid()
                and stat.S_IMODE(metadata.st_mode) in (0o400, 0o600))
        return json.load(stream)


def publish_private(path: Path, data: object) -> None:
    """Publish a complete, fsynced JSON record without replacing another record."""
    private_path(path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.metadata-' + uuid.uuid4().hex
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(data))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory,
                follow_symlinks=False)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)


def timestamp(value: Any) -> datetime:
    """Parse an offset-qualified time, normalized for window comparisons."""
    require(isinstance(value, str))
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None)
    return result.astimezone(UTC)


def validate_artifacts(data: Any, manifest: Manifest) -> dict[str, Any]:
    """Bind the operator's build record to one source, registry and static inventory."""
    require(not manifest.draft and isinstance(data, dict) and set(data) == {
        'schema_version', 'run_id', 'source_revision', 'source_tree', 'backend',
        'frontend_sha256', 'started_at', 'finished_at', 'commands'})
    require(type(data['schema_version']) is int and data['schema_version'] == 1)
    for key in ('run_id', 'source_revision', 'frontend_sha256'):
        require(data[key] == manifest.data[key])
    require(matches(r'[a-f0-9]{40}', data['source_tree']))
    require(timestamp(data['started_at']) <= timestamp(data['finished_at']))
    backend = data['backend']
    require(isinstance(backend, dict) and set(backend) == {
        'repository', 'tag', 'local_image_id', 'registry_digest', 'platform', 'revision_label'})
    require(backend['repository'] ==
            f"{manifest.data['account']}.dkr.ecr.{REGION}.amazonaws.com/{manifest.environment}/backend"
            and backend['tag'] == manifest.data['source_revision'] + '-' + manifest.data['run_id']
            and backend['registry_digest'] == manifest.data['image_digest']
            and backend['revision_label'] == manifest.data['source_revision']
            and backend['platform'] == 'linux/amd64'
            and matches(r'sha256:[a-f0-9]{64}', backend['local_image_id']))
    commands = data['commands']
    require(isinstance(commands, list) and len(commands) == 2)
    require(all(isinstance(item, dict) and set(item) == {'kind', 'exit_code'}
                and type(item['exit_code']) is int and item['exit_code'] == 0 for item in commands))
    require([item['kind'] for item in commands] == ['frontend', 'backend'])
    return dict(data)


def check_source(root: Path, revision: str) -> str:
    """Check clean commit/tree before exporting a build; do not inspect other repos."""
    require(matches(r'[a-f0-9]{40}', revision))

    def git(*args: str) -> str:
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                              text=True, timeout=30).stdout.strip()

    require(git('rev-parse', 'HEAD') == revision
            and not git('status', '--porcelain=v1', '--untracked-files=all'))
    require(not any(line.startswith('160000 ') for line in git('ls-tree', '-r', 'HEAD').splitlines()))
    # Both configured filters and committed LFS pointers require a separate export procedure.
    for name in git('ls-files', '*.gitattributes', '.gitattributes').splitlines():
        require('filter=lfs' not in git('show', 'HEAD:' + name))
    for pattern in ('^version https://git-lfs.github.com/spec/v1$',):
        result = subprocess.run(['git', '-C', str(root), 'grep', '-l', '-e', pattern, 'HEAD'],
                                capture_output=True, timeout=30)
        require(result.returncode == 1)
    tree = git('rev-parse', 'HEAD^{tree}')
    require(matches(r'[a-f0-9]{40}', tree))
    return tree

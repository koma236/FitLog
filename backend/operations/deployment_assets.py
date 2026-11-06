"""Content-addressed static inventory; no AWS calls until the complete list matches."""
from __future__ import annotations

import hashlib
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from operations.deployment_aws import Api
from operations.deployment_contract import REGION, Manifest, canonical, matches, require


def bundle(root: Path) -> dict[str, Any]:
    require(root.is_dir() and not root.is_symlink())
    entries = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink())
        if path.is_dir():
            continue
        key = path.relative_to(root).as_posix()
        require(matches(r'[A-Za-z0-9_./-]+', key) and '..' not in key.split('/'))
        content = path.read_bytes()
        entries.append({'key': key, 'sha256': hashlib.sha256(content).hexdigest(),
                        'size': len(content),
                        'content_type': mimetypes.guess_type(key)[0] or 'application/octet-stream'})
    require(any(item['key'] == 'index.html' for item in entries))
    return {'files': entries, 'sha256': hashlib.sha256(canonical(entries)).hexdigest()}


def upload(api: Api, manifest: Manifest, root: Path, assets: dict[str, Any]) -> None:
    require(bundle(root) == assets and assets['sha256'] == manifest.data['frontend_sha256'])
    bucket = f"{manifest.environment}-static-{manifest.data['account']}-{REGION}"
    api.call('s3', 'head_bucket', Bucket=bucket, ExpectedBucketOwner=manifest.data['account'])
    # Read and verify each object again immediately before sending it. A source
    # mutation fails this run; it cannot silently deploy a different artifact.
    for item in assets['files']:
        manifest.authorize(datetime.now(UTC))
        path = root / item['key']
        require(not path.is_symlink())
        content = path.read_bytes()
        require(hashlib.sha256(content).hexdigest() == item['sha256'])
        api.call('s3', 'put_object', Bucket=bucket, Key=item['key'], Body=content,
                 ContentType=item['content_type'], CacheControl='no-store',
                 ExpectedBucketOwner=manifest.data['account'], ServerSideEncryption='AES256')

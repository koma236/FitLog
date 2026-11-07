"""Offline-only, strict C test contracts. No SDK, credentials or network."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid


class Invalid(ValueError):
    def __init__(self):
        super().__init__('AWS_CONTRACT_INVALID')


B_START = ('inspect', 'static', 'bootstrap-inspect', 'bootstrap', 'migrate', 'seed',
           'check', 'backend', 'verify-backend-database', 'public-health')
EXTERNAL_PROBES = ('alb-normal', 'alb-host', 'task', 's3-static', 's3-media', 'other-distribution', 'viewer-headers')
FINAL_PROBES = EXTERNAL_PROBES
IDENTITY = ('account', 'region', 'environment', 'run_id', 'bootstrap_id', 'source',
            'image_digest', 'frontend_sha256', 'origin')
FIELDS = {*IDENTITY, 'schema_version', 'test_run', 'starts_at', 'expires_at', 'approval',
          'lease_id', 'evidence', 'campaign_id', 'handoff'}


def require(condition):
    if not condition:
        raise Invalid()


def identity(data):
    return {key: data[key] for key in IDENTITY}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_handoff(data):
    ref = data['handoff']
    require(set(ref) == {'path', 'sha256'})
    p = protected(ref['path'])
    require(sha256(p) == ref['sha256'])
    handoff = load(p)
    require(handoff['schema_version'] == 1 and handoff['status'] == 'ready_for_c')
    for key in IDENTITY:
        require(handoff['source_revision' if key == 'source' else key] == data[key])
    window = handoff['window']
    require(timestamp(window['starts_at'], external=True) <= timestamp(data['starts_at'])
            and timestamp(data['expires_at']) <= timestamp(window['ends_at'], external=True)
            and window['approval_reference'] == data['approval']['reference'])
    require(set(handoff['probes']) == {'permissions', 'ip'}
            and all(value in ('pass', 'not_run') for value in handoff['probes'].values()))
    seen = set(); binding = set()
    for item in handoff['evidence']:
        require(set(item) == {'step', 'path', 'sha256'} and item['step'] not in seen)
        seen.add(item['step'])
        record = load(item['path'])
        require(canonical_hash(record) == item['sha256'])
        require(record['schema_version'] == 2 and record['step'] == item['step'] and record['status'] == 'pass')
        for key in ('run_id', 'image_digest', 'frontend_sha256'):
            require(record[key] == data[key])
        require(record['source_revision'] == data['source'])
        require(bool(re.fullmatch(r'[a-f0-9]{64}', record['deployment_identity'])))
        binding.add(record['deployment_identity'])
        if item['step'] in ('backend', 'public-health'): require(record['origin'] == data['origin'])
    require(set(B_START) <= seen and len(binding) == 1)
    for mode in ('permissions', 'ip'):
        if handoff['probes'][mode] == 'pass':
            require('verify-public-' + mode in seen)
            if mode == 'ip': require('verify-public-ip-baseline' in seen)
    return handoff


def protected(path, directory=False):
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p)
    s = p.lstat()
    require(s.st_uid == os.getuid() and not stat.S_ISLNK(s.st_mode))
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink == 1)
    require(stat.S_IMODE(s.st_mode) == 0o700 if directory else stat.S_IMODE(s.st_mode) in (0o600, 0o400))
    if not directory:
        protected(p.parent, True)
        require(s.st_size <= 1024 * 1024)
    return p


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    try:
        return json.loads(protected(path).read_text(), object_pairs_hook=unique)
    except (OSError, ValueError, TypeError):
        raise Invalid() from None


def exclusive_json(path, data):
    p = Path(path)
    protected(p.parent, True)
    try:
        with open(p, 'x', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            json.dump(data, stream, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError):
        # A partial intent remains consumed, never auto-repair or refund.
        raise Invalid() from None


def timestamp(value, external=False):
    ending = r'(?:\.\d{1,6})?(?:Z|\+00:00)' if external else 'Z'
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d' + ending, value))
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def validate(data, now=None):
    try:
        require(isinstance(data, dict) and set(data) == FIELDS)
        require(type(data['schema_version']) is int and data['schema_version'] == 1)
        for key in ('run_id', 'bootstrap_id', 'campaign_id'):
            require(str(uuid.UUID(data[key])) == data[key])
        require(bool(re.fullmatch(r'[a-f0-9]{12}', data['test_run'])))
        require(bool(re.fullmatch(r'[0-9]{12}', data['account'])))
        require(data['region'] == 'ap-northeast-1')
        require(bool(re.fullmatch(r'[a-z][a-z0-9-]{2,30}', data['environment'])))
        require(bool(re.fullmatch(r'[a-f0-9]{40}', data['source'])))
        require(bool(re.fullmatch(r'sha256:[a-f0-9]{64}', data['image_digest'])))
        require(bool(re.fullmatch(r'[a-f0-9]{64}', data['frontend_sha256'])))
        require(bool(re.fullmatch(r'https://[a-z0-9]{1,63}\.cloudfront\.net', data['origin'])))
        require(bool(re.fullmatch(r'[A-Za-z0-9_-]{8,80}', data['lease_id'])))
        approval = data['approval']
        require(set(approval) == {'reference', 'steps', 'budget_usd'})
        require(bool(re.fullmatch(r'[A-Za-z0-9_:#./-]{8,160}', approval['reference'])))
        require(approval['steps'] == ['journey', 'capture', 'performance', 'cleanup'])
        require(bool(re.fullmatch(r'[0-9]{1,6}(\.[0-9]{1,2})?', approval['budget_usd'])))
        require(float(approval['budget_usd']) > 0)
        start, end = timestamp(data['starts_at']), timestamp(data['expires_at'])
        require(start <= (now or datetime.now(timezone.utc)) < end)
        require(300 < (end - start).total_seconds() <= 2700)
        validate_handoff(data)
        require(isinstance(data['evidence'], list))
        require(boundary_status(data)['status'] != 'fail')
        return data
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise Invalid() from None


def boundary_status(data):
    # Lazy import keeps the common private-file helpers independent of C04.
    from aws_boundary import boundary_status as evaluate
    return evaluate(data)


def final_ready(data):
    """Readiness of boundary/storage evidence, never overall AWS acceptance."""
    handoff = validate_handoff(data)
    return boundary_status(data)['status'] == 'pass' and all(v == 'pass' for v in handoff['probes'].values())


def init_campaign(folder, first, second, campaign_id=None):
    require(first != second and all(re.fullmatch(r'[a-z][a-z0-9-]{2,30}', v) for v in (first, second)))
    exclusive_json(Path(folder) / 'campaign.json', {'schema_version': 1,
                   'campaign_id': campaign_id or fixture()['campaign_id'], 'environments': [first, second]})


def claim(folder, data):
    folder = protected(folder, True)
    campaign = load(folder / 'campaign.json')
    require(set(campaign) == {'schema_version', 'campaign_id', 'environments'})
    require(campaign['schema_version'] == 1 and campaign['campaign_id'] == data['campaign_id'])
    require(len(campaign['environments']) == 2 and len(set(campaign['environments'])) == 2)
    require(data['environment'] in campaign['environments'])
    slot = campaign['environments'].index(data['environment'])
    require(slot == 0 or (folder / 'attempt-0.json').exists())
    exclusive_json(folder / f'attempt-{slot}.json', {'environment': data['environment'],
                   'test_run': data['test_run'], 'identity': identity(data), 'status': 'consumed'})


def fixture():
    """Public, incomplete synthetic input; never constitutes approval."""
    return {'schema_version': 1, 'account': '123456789012', 'region': 'ap-northeast-1',
            'environment': 'aws-one', 'run_id': '00000000-0000-4000-8000-000000000001',
            'bootstrap_id': '00000000-0000-4000-8000-000000000002',
            'campaign_id': '00000000-0000-4000-8000-000000000003', 'test_run': 'aaaaaaaaaaaa',
            'source': 'a' * 40, 'image_digest': 'sha256:' + 'b' * 64, 'frontend_sha256': 'c' * 64,
            'origin': 'https://dexample.cloudfront.net', 'lease_id': 'test-window-001',
            'starts_at': '2026-11-07T07:59:00Z', 'expires_at': '2026-11-07T08:40:00Z',
            'approval': {'reference': 'chat:example-not-approved', 'steps': ['journey', 'capture', 'performance', 'cleanup'],
                         'budget_usd': '1.00'}, 'evidence': [], 'handoff': None}

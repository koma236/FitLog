"""Offline boundary receipts. Hashes bind operator observations, not AWS signatures."""
import hashlib
import ipaddress
import json
from pathlib import Path
import re

from aws_contract import (IDENTITY, FINAL_PROBES, Invalid, canonical_hash, identity,
                          protected, require, timestamp, validate_handoff)

MAX_BODY = 16 * 1024
HEALTH = b'{"status":"ok"}'
TARGETS = {'alb', 'task', 'static', 'media', 'distribution', 'other', 'function'}
PROBE_TARGETS = {
    'alb-normal': {'alb'}, 'alb-host': {'alb'}, 'task': {'task', 'alb'},
    's3-static': {'static'}, 's3-media': {'media'},
    'other-distribution': {'static', 'distribution', 'other'},
    'viewer-headers': {'alb', 'distribution', 'function'},
}


class Missing(Exception):
    """A reference is present but its observation has not been collected."""


def shape(value, fields):
    require(isinstance(value, dict) and set(value) == set(fields))


def matches(pattern, value):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_ref(ref, sources):
    shape(ref, ('path', 'sha256'))
    matches(r'[a-f0-9]{64}', ref['sha256'])
    try:
        path = protected(ref['path'])
    except FileNotFoundError:
        # An unsafe spelling is invalid even if that path does not exist.
        path = Path(ref['path'])
        require(path.is_absolute() and path.resolve() == path)
        raise Missing() from None
    raw = path.read_bytes()
    require(len(raw) <= 1024 * 1024 and digest(raw) == ref['sha256'])
    sources[str(path)] = ref['sha256']

    def unique(pairs):
        row = {}
        for key, value in pairs:
            require(key not in row)
            row[key] = value
        return row

    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Invalid()))


def envelope(row, data, fields):
    shape(row, {'schema_version', 'identity', 'observed_at', *fields})
    require(type(row['schema_version']) is int and row['schema_version'] == 1)
    shape(row['identity'], IDENTITY)
    require(row['identity'] == identity(data))
    require(timestamp(data['starts_at']) <= timestamp(row['observed_at']) < timestamp(data['expires_at']))


def ingress(row, port, source_type, source):
    require(isinstance(row, list) and len(row) == 1)
    shape(row[0], ('protocol', 'from_port', 'to_port', 'source_type', 'source'))
    require(row[0] == {'protocol': 'tcp', 'from_port': port, 'to_port': port,
                       'source_type': source_type, 'source': source})
    require(type(row[0]['from_port']) is int and type(row[0]['to_port']) is int)


def inventory(ref, data, sources):
    inv = read_ref(ref, sources)
    envelope(inv, data, ('approval_reference', 'starts_at', 'expires_at', 'targets'))
    require(inv['approval_reference'] == data['approval']['reference'])
    require(timestamp(inv['starts_at']) <= timestamp(data['starts_at'])
            and timestamp(data['expires_at']) <= timestamp(inv['expires_at']))
    shape(inv['targets'], TARGETS)
    targets, missing = {}, set()
    for kind, target in inv['targets'].items():
        require(isinstance(target, dict) and 'original' in target)
        facts = {k: v for k, v in target.items() if k != 'original'}
        targets[kind] = facts
        try:
            original = read_ref(target['original'], sources)
            envelope(original, data, ('kind', 'facts'))
            require(original['kind'] == kind and original['facts'] == facts)
        except Missing:
            missing.add(kind)
    account, region = data['account'], data['region']
    alb, task, function = targets['alb'], targets['task'], targets['function']
    shape(alb, ('arn', 'dns', 'port', 'security_groups', 'ingress', 'prefix_list'))
    matches(r'arn:aws:elasticloadbalancing:' + region + ':' + account + r':loadbalancer/app/[a-zA-Z0-9-]{1,32}/[a-f0-9]{16}', alb['arn'])
    matches(r'[a-z0-9-]{1,80}\.' + re.escape(region) + r'\.elb\.amazonaws\.com', alb['dns'])
    require(type(alb['port']) is int and alb['port'] == 80)
    require(isinstance(alb['security_groups'], list) and len(alb['security_groups']) == 1)
    matches(r'sg-[a-f0-9]{8,17}', alb['security_groups'][0])
    shape(alb['prefix_list'], ('id', 'name', 'owner'))
    matches(r'pl-[a-f0-9]{8,17}', alb['prefix_list']['id'])
    require(alb['prefix_list']['name'] == 'com.amazonaws.global.cloudfront.origin-facing'
            and alb['prefix_list']['owner'] == 'AWS')
    ingress(alb['ingress'], 80, 'prefix-list', alb['prefix_list']['id'])
    shape(task, ('arn', 'eni', 'public_ip', 'port', 'security_groups', 'ingress'))
    matches(r'arn:aws:ecs:' + region + ':' + account + ':task/' + re.escape(data['environment']) + r'/[a-f0-9]{32}', task['arn'])
    matches(r'eni-[a-f0-9]{8,17}', task['eni'])
    require(str(ipaddress.IPv4Address(task['public_ip'])) == task['public_ip'])
    require(type(task['port']) is int and task['port'] == 8000)
    require(isinstance(task['security_groups'], list) and len(task['security_groups']) == 1)
    matches(r'sg-[a-f0-9]{8,17}', task['security_groups'][0])
    require(task['security_groups'] != alb['security_groups'])
    ingress(task['ingress'], 8000, 'security-group', alb['security_groups'][0])
    for kind in ('static', 'media'):
        obj = targets[kind]
        shape(obj, ('arn', 'key', 'sha256', 'size', 'region', 'owner'))
        require(obj['arn'] == f'arn:aws:s3:::{data["environment"]}-{kind}-{account}-{region}')
        require(obj['region'] == region and obj['owner'] == account)
        matches(r'[A-Za-z0-9_./-]{1,200}', obj['key'])
        require(not obj['key'].startswith('/') and '..' not in obj['key'])
        matches(r'[a-f0-9]{64}', obj['sha256'])
        require(type(obj['size']) is int and 0 < obj['size'] <= MAX_BODY)
    shape(function, ('arn', 'stage', 'sha256'))
    matches(r'arn:aws:cloudfront::' + account + ':function/' + re.escape(data['environment']) + r'-[a-zA-Z0-9_-]{1,64}', function['arn'])
    require(function['stage'] == 'LIVE')
    require(function['sha256'] == digest((Path(__file__).parents[1] / 'terraform/functions/client-ip.js').read_bytes()))
    for kind in ('distribution', 'other'):
        dist = targets[kind]
        shape(dist, {'id', 'dns', 'bucket_arn', 'origin_path', 'path_pattern', 'oac', *({'api'} if kind == 'distribution' else set())})
        matches(r'[A-Z0-9]{1,32}', dist['id'])
        matches(r'[a-z0-9]{1,63}\.cloudfront\.net', dist['dns'])
        require(dist['bucket_arn'] == targets['static']['arn'] and dist['origin_path'] == '' and dist['path_pattern'] == '*')
        shape(dist['oac'], ('id', 'origin_type', 'signing_behavior', 'signing_protocol'))
        matches(r'[A-Z0-9]{1,32}', dist['oac']['id'])
        require(dist['oac']['origin_type'] == 's3' and dist['oac']['signing_behavior'] == 'always' and dist['oac']['signing_protocol'] == 'sigv4')
    require('https://' + targets['distribution']['dns'] == data['origin'])
    require(targets['distribution']['id'] != targets['other']['id'] and targets['distribution']['dns'] != targets['other']['dns'])
    require(targets['distribution']['api'] == {'alb_arn': alb['arn'], 'origin_verify': 'configured',
                                            'forwarded_proto': 'https', 'function_arn': function['arn']})
    return targets, missing


def expected_request(targets, target, *, host_header='target', headers='none', health=False):
    obj = targets[target]
    if target == 'alb': host, port, scheme = obj['dns'], 80, 'http'
    elif target == 'task': host, port, scheme = obj['public_ip'], 8000, 'http'
    elif target in ('static', 'media'):
        host, port, scheme = obj['arn'].split(':::')[1] + '.s3.' + obj['region'] + '.amazonaws.com', 443, 'https'
    else: host, port, scheme = obj['dns'], 443, 'https'
    key = obj.get('key', targets['static']['key'])
    return {'target': target, 'host': host, 'port': port, 'scheme': scheme, 'method': 'GET',
            'path': '/api/health/live' if health else '/' + key, 'host_header': host_header, 'headers': headers}


def result_http(row, status, classification, body=None, size=None, body_hash=None):
    shape(row, ('transport', 'status', 'response_class', 'body_bytes', 'body_sha256'))
    require(row['transport'] == 'http' and type(row['status']) is int and row['status'] == status
            and row['response_class'] == classification)
    require(type(row['body_bytes']) is int and 0 < row['body_bytes'] <= MAX_BODY)
    matches(r'[a-f0-9]{64}', row['body_sha256'])
    if body is not None: size, body_hash = len(body), digest(body)
    if size is not None: require(row['body_bytes'] == size and row['body_sha256'] == body_hash)


def timeout(row):
    require(row == {'transport': 'timeout', 'status': None, 'response_class': 'none', 'body_bytes': 0, 'body_sha256': None})
    require(type(row['body_bytes']) is int)


def observation_attempts(probe, observation, data):
    """Reject independently known failures even without an available inventory."""
    envelope(observation, data, ('probe_id', 'attempts'))
    require(observation['probe_id'] == probe)
    attempts = observation['attempts']
    require(isinstance(attempts, list) and len(attempts) == (2 if probe in ('other-distribution', 'viewer-headers') else 1))
    for attempt in attempts:
        shape(attempt, ('request', 'result'))
        shape(attempt['request'], ('target', 'host', 'port', 'scheme', 'method', 'path', 'host_header', 'headers'))
        require(attempt['request']['method'] == 'GET' and attempt['request']['headers'] in ('none', 'spoofed'))
    if probe in ('alb-normal', 'alb-host', 'task'):
        result = attempts[0]['result']
        if probe != 'task' and result.get('transport') == 'http': result_http(result, 403, 'alb-denied', body=b'Forbidden')
        else: timeout(result)
    elif probe in ('s3-static', 's3-media'):
        result_http(attempts[0]['result'], 403, 'access-denied')
    elif probe == 'other-distribution':
        result_http(attempts[0]['result'], 200, 'object')
        result_http(attempts[1]['result'], 403, 'access-denied')
    elif probe == 'viewer-headers':
        for attempt in attempts: result_http(attempt['result'], 200, 'health', body=HEALTH)
    return attempts


def evaluate(probe, attempts, targets, data):
    if probe in ('alb-normal', 'alb-host', 'task'):
        target = 'task' if probe == 'task' else 'alb'
        host = 'task' if probe == 'task' else 'alb' if probe == 'alb-normal' else 'canonical'
        require(attempts[0]['request'] == expected_request(targets, target, host_header=host, health=True))
        result = attempts[0]['result']
        return 'http-denied' if result['transport'] == 'http' else 'sg-restricted'
    if probe in ('s3-static', 's3-media'):
        target = probe.removeprefix('s3-')
        require(attempts[0]['request'] == expected_request(targets, target))
    elif probe == 'other-distribution':
        for attempt, target in zip(attempts, ('distribution', 'other')):
            require(attempt['request'] == expected_request(targets, target))
        obj = targets['static']
        result_http(attempts[0]['result'], 200, 'object', size=obj['size'], body_hash=obj['sha256'])
    elif probe == 'viewer-headers':
        for attempt, headers in zip(attempts, ('none', 'spoofed')):
            require(attempt['request'] == expected_request(targets, 'distribution', host_header='canonical', headers=headers, health=True))
        handoff = validate_handoff(data)
        if handoff['probes']['ip'] != 'pass': raise Missing()
        # The existing B collector records the real baseline/counter experiment.
        from aws_contract import load
        records = {ref['step']: load(ref['path']) for ref in handoff['evidence']}
        baseline, spoofed = (records[step] for step in ('verify-public-ip-baseline', 'verify-public-ip'))
        matches(r'[a-f0-9]{64}', baseline.get('parameters_sha256'))
        require(baseline['parameters_sha256'] == spoofed.get('parameters_sha256'))
    return 'http-denied' if probe != 'viewer-headers' else 'protected-viewer'


def boundary_status(data):
    """Classify all supplied facts; an invalid probe dominates missing evidence."""
    probes = {probe: {'status': 'not_run', 'classification': 'missing'} for probe in FINAL_PROBES}
    sources = {}
    seen = set()
    inventories = set()
    malformed = False
    try:
        require(isinstance(data['evidence'], list))
        for ref in data['evidence']:
            probe = None
            try:
                shape(ref, ('probe_id', 'path', 'sha256'))
                probe = ref['probe_id']
                require(probe in probes and probe not in seen)
                seen.add(probe)
                receipt = read_ref({k: ref[k] for k in ('path', 'sha256')}, sources)
                require(identity(receipt) == identity(data) and receipt['probe_id'] == probe)
                if 'schema_version' not in receipt:
                    shape(receipt, {*IDENTITY, 'probe_id', 'status'})
                    require(receipt['status'] == 'pass')
                    probes[probe] = {'status': 'not_run', 'classification': 'legacy-summary'}
                    continue
                shape(receipt, {*IDENTITY, 'schema_version', 'probe_id', 'inventory', 'observation'})
                require(type(receipt['schema_version']) is int and receipt['schema_version'] == 2)
                inventories.add(canonical_hash(receipt['inventory']))
                # Missing dependencies do not skip the other, available facts.
                attempts, targets = None, None
                try:
                    attempts = observation_attempts(probe, read_ref(receipt['observation'], sources), data)
                except Missing:
                    pass  # Still inspect the inventory and its available originals.
                missing = set(PROBE_TARGETS[probe])
                try:
                    targets, missing = inventory(receipt['inventory'], data, sources)
                except Missing:
                    pass  # Known response failures were already checked above.
                if attempts is None or targets is None: raise Missing()
                classification = evaluate(probe, attempts, targets, data)
                if missing & PROBE_TARGETS[probe]: raise Missing()
                probes[probe] = {'status': 'pass', 'classification': classification}
            except Missing:
                if probe in probes: probes[probe] = {'status': 'not_run', 'classification': 'missing-original'}
                else: malformed = True
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                if probe in probes: probes[probe] = {'status': 'fail', 'classification': 'invalid-observation'}
                malformed = True
        require(len(inventories) <= 1)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        malformed = True
    states = {row['status'] for row in probes.values()}
    status = 'fail' if malformed or 'fail' in states else 'not_run' if 'not_run' in states else 'pass'
    return {'status': status, 'probes': probes, 'fingerprint': canonical_hash(sources)}

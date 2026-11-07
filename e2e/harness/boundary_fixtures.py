"""Handwritten synthetic facts, never evidence of an AWS execution."""
import copy
import hashlib
import json
from pathlib import Path

import aws_contract as contract


def write(root, name, value):
    path = root / (name + '.json')
    path.write_text(json.dumps(value, separators=(',', ':')))
    path.chmod(0o600)
    return {'path': str(path), 'sha256': contract.sha256(path)}


def complete(root, data):
    ident = contract.identity(data)
    account, region = data['account'], data['region']
    alb = f'arn:aws:elasticloadbalancing:{region}:{account}:loadbalancer/app/aws-one-api/1234567890abcdef'
    task = f'arn:aws:ecs:{region}:{account}:task/aws-one/' + '1' * 32
    function = f'arn:aws:cloudfront::{account}:function/aws-one-client-ip'
    code_hash = hashlib.sha256((Path(__file__).parents[2] / 'terraform/functions/client-ip.js').read_bytes()).hexdigest()
    rule = lambda port, kind, source: {'protocol': 'tcp', 'from_port': port, 'to_port': port, 'source_type': kind, 'source': source}
    targets = {
        'alb': {'arn': alb, 'dns': 'aws-one-api-123.ap-northeast-1.elb.amazonaws.com', 'port': 80,
                'security_groups': ['sg-11111111'], 'ingress': [rule(80, 'prefix-list', 'pl-11111111')],
                'prefix_list': {'id': 'pl-11111111', 'name': 'com.amazonaws.global.cloudfront.origin-facing', 'owner': 'AWS'}},
        'task': {'arn': task, 'eni': 'eni-11111111', 'public_ip': '198.51.100.10', 'port': 8000,
                 'security_groups': ['sg-22222222'], 'ingress': [rule(8000, 'security-group', 'sg-11111111')]},
        'function': {'arn': function, 'stage': 'LIVE', 'sha256': code_hash},
    }
    for kind in ('static', 'media'):
        targets[kind] = {'arn': f'arn:aws:s3:::aws-one-{kind}-{account}-{region}', 'key': 'boundary-fixture.txt',
                         'sha256': hashlib.sha256(b'boundary fixture').hexdigest(), 'size': 16,
                         'region': region, 'owner': account}
    for kind, distribution, dns in [('distribution', 'EDISTRIBUTION1', 'dexample'), ('other', 'EDISTRIBUTION2', 'dother')]:
        targets[kind] = {'id': distribution, 'dns': dns + '.cloudfront.net', 'bucket_arn': targets['static']['arn'],
                         'origin_path': '', 'path_pattern': '*',
                         'oac': {'id': 'EOAC1', 'origin_type': 's3', 'signing_behavior': 'always', 'signing_protocol': 'sigv4'}}
        if kind == 'distribution':
            targets[kind]['api'] = {'alb_arn': alb, 'origin_verify': 'configured', 'forwarded_proto': 'https', 'function_arn': function}
    inventory = {'schema_version': 1, 'identity': ident, 'approval_reference': data['approval']['reference'],
                 'starts_at': data['starts_at'], 'expires_at': data['expires_at'],
                 'observed_at': '2026-11-07T08:00:00Z', 'targets': {}}
    for kind, facts in targets.items():
        original = {'schema_version': 1, 'identity': ident, 'observed_at': inventory['observed_at'], 'kind': kind, 'facts': facts}
        inventory['targets'][kind] = {**copy.deepcopy(facts), 'original': write(root, 'original-' + kind, original)}
    inventory_ref = write(root, 'inventory', inventory)

    def request(target, host, port, scheme, path, host_header, headers='none'):
        return {'target': target, 'host': host, 'port': port, 'scheme': scheme, 'method': 'GET',
                'path': path, 'host_header': host_header, 'headers': headers}

    def http(status, classification, body):
        return {'transport': 'http', 'status': status, 'response_class': classification,
                'body_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest()}

    timeout = {'transport': 'timeout', 'status': None, 'response_class': 'none', 'body_bytes': 0, 'body_sha256': None}
    health = http(200, 'health', b'{"status":"ok"}')
    cases = {}
    for probe, host_header in [('alb-normal', 'alb'), ('alb-host', 'canonical')]:
        cases[probe] = [{'request': request('alb', targets['alb']['dns'], 80, 'http', '/api/health/live', host_header), 'result': timeout}]
    cases['task'] = [{'request': request('task', targets['task']['public_ip'], 8000, 'http', '/api/health/live', 'task'), 'result': timeout}]
    for kind in ('static', 'media'):
        bucket = targets[kind]['arn'].split(':::')[1]
        cases['s3-' + kind] = [{'request': request(kind, bucket + '.s3.' + region + '.amazonaws.com', 443, 'https', '/boundary-fixture.txt', 'target'),
                               'result': http(403, 'access-denied', b'<Error><Code>AccessDenied</Code></Error>')}]
    cases['other-distribution'] = [
        {'request': request('distribution', targets['distribution']['dns'], 443, 'https', '/boundary-fixture.txt', 'target'),
         'result': http(200, 'object', b'boundary fixture')},
        {'request': request('other', targets['other']['dns'], 443, 'https', '/boundary-fixture.txt', 'target'),
         'result': http(403, 'access-denied', b'<Error><Code>AccessDenied</Code></Error>')}]
    cases['viewer-headers'] = [{'request': request('distribution', targets['distribution']['dns'], 443, 'https', '/api/health/live', 'canonical', headers), 'result': health}
                               for headers in ('none', 'spoofed')]
    data['evidence'] = []
    for probe, attempts in cases.items():
        observation = {'schema_version': 1, 'identity': ident, 'probe_id': probe,
                       'observed_at': inventory['observed_at'], 'attempts': attempts}
        receipt = {**ident, 'schema_version': 2, 'probe_id': probe, 'inventory': inventory_ref,
                   'observation': write(root, 'observation-' + probe, observation)}
        data['evidence'].append({'probe_id': probe, **write(root, 'receipt-' + probe, receipt)})
    handoff = contract.load(data['handoff']['path'])
    handoff['evidence'] = [ref for ref in handoff['evidence'] if ref['step'] in contract.B_START]
    for step in ('verify-public-permissions', 'verify-public-ip-baseline', 'verify-public-ip'):
        record = {**contract.load(handoff['evidence'][0]['path']), 'step': step,
                  'parameters_sha256': 'f' * 64, 'origin': data['origin']}
        ref = write(root, step, record)
        handoff['evidence'].append({'step': step, 'path': ref['path'], 'sha256': contract.canonical_hash(record)})
    handoff['probes'] = {'permissions': 'pass', 'ip': 'pass'}
    data['handoff'] = write(root, 'handoff', handoff)
    return data


def mutate_observation(root, data, probe, change):
    ref = next(item for item in data['evidence'] if item['probe_id'] == probe)
    receipt = contract.load(ref['path'])
    observation = contract.load(receipt['observation']['path'])
    change(observation)
    receipt['observation'] = write(root, 'observation-' + probe, observation)
    ref.update(write(root, 'receipt-' + probe, receipt))


def mutate_inventory(root, data, change, sync_original=True):
    inventory = contract.load(root / 'inventory.json')
    change(inventory)
    if sync_original:
        for kind, target in inventory['targets'].items():
            facts = {k: v for k, v in target.items() if k != 'original'}
            original = {'schema_version': 1, 'identity': inventory['identity'], 'observed_at': inventory['observed_at'], 'kind': kind, 'facts': facts}
            target['original'] = write(root, 'original-' + kind, original)
    inventory_ref = write(root, 'inventory', inventory)
    for ref in data['evidence']:
        receipt = contract.load(ref['path']); receipt['inventory'] = inventory_ref
        ref.update(write(root, 'receipt-' + ref['probe_id'], receipt))

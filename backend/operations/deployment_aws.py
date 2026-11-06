"""Bounded AWS adapter and independent metadata/completion checks.

This module does not connect at import time. SDK values are untrusted at the
adapter boundary; only validated, allowlisted metadata reaches evidence.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from operations.deployment_contract import REGION, Manifest, matches, require


class Api(Protocol):
    def call(self, service: str, operation: str, **kwargs: Any) -> dict[str, Any]: ...


@dataclass
class Gateway:
    clients: dict[str, Any]

    @classmethod
    def connect(cls) -> Gateway:
        import boto3
        import botocore.session
        from botocore.config import Config

        core = botocore.session.get_session()
        core.set_config_variable('ignore_configured_endpoint_urls', True)
        session = boto3.Session(region_name=REGION, botocore_session=core)
        endpoints: dict[Literal['sts', 'rds', 'ecs', 'logs', 's3', 'ecr', 'ec2',
                                'secretsmanager', 'elbv2'], str] = {
            'sts': 'sts', 'rds': 'rds', 'ecs': 'ecs', 'logs': 'logs',
            's3': 's3', 'ecr': 'api.ecr', 'ec2': 'ec2',
            'secretsmanager': 'secretsmanager', 'elbv2': 'elasticloadbalancing',
        }
        clients: dict[str, Any] = {}
        for service, endpoint in endpoints.items():
            clients[service] = session.client(
                service, endpoint_url=f'https://{endpoint}.{REGION}.amazonaws.com',
                config=Config(region_name=REGION, connect_timeout=5, read_timeout=10,
                              retries={'total_max_attempts': 1}),
            )
        clients['cloudfront'] = session.client(
            'cloudfront', endpoint_url='https://cloudfront.amazonaws.com',
            config=Config(region_name='us-east-1', connect_timeout=5, read_timeout=10,
                          retries={'total_max_attempts': 1}),
        )
        return cls(clients)

    def call(self, service: str, operation: str, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = getattr(self.clients[service], operation)(**kwargs)
        return result


def tagged(tags: list[dict[str, str]], manifest: Manifest, lower: bool = False) -> None:
    actual = {item['key' if lower else 'Key']: item['value' if lower else 'Value'] for item in tags}
    require(actual.get('Project') == 'FitLog'
            and actual.get('Environment') == manifest.environment)


def preflight(api: Api, manifest: Manifest, phase: str) -> dict[str, Any]:
    """Operator-only AWS inspection, with phase-specific stop/live guards."""
    manifest.authorize(datetime.now(UTC))
    require(phase in ('private', 'backend', 'public'))
    env, account, res = manifest.environment, manifest.data['account'], manifest.resources
    require(api.call('sts', 'get_caller_identity')['Account'] == account)
    result = api.call('ecs', 'describe_services', cluster=env, services=[env + '-backend'],
                      include=['TAGS'])
    require(not result.get('failures') and len(result['services']) == 1)
    service = result['services'][0]
    require(service['status'] == 'ACTIVE' and service['serviceName'] == env + '-backend'
            and service['clusterArn'] == f'arn:aws:ecs:{REGION}:{account}:cluster/{env}'
            and service['taskDefinition'] == res['backend_task'])
    tagged(service['tags'], manifest, lower=True)
    counts = tuple(service[name] for name in ('desiredCount', 'runningCount', 'pendingCount'))
    require(counts == ((0, 0, 0) if phase == 'private' else (1, 1, 0)))
    network = service['networkConfiguration']['awsvpcConfiguration']
    require(set(network['subnets']) == set(res['subnets'])
            and network['securityGroups'] == [res['security_group']]
            and network['assignPublicIp'] == 'ENABLED')
    dbs = api.call('rds', 'describe_db_instances', DBInstanceIdentifier=env)['DBInstances']
    require(len(dbs) == 1)
    db = dbs[0]
    require(db['DBInstanceArn'] == f'arn:aws:rds:{REGION}:{account}:db:{env}'
            and db['DBInstanceIdentifier'] == env and db['DBInstanceStatus'] == 'available'
            and db['Engine'] == 'postgres' and db['EngineVersion'].startswith('17.')
            and db['MasterUsername'] == 'fitlog_admin' and db['DBName'] == 'fitlog'
            and not db['PubliclyAccessible'] and db['Endpoint']['Port'] == 5432
            and db['Endpoint']['Address'] == res['database_host']
            and db['MasterUserSecret']['SecretArn'] == res['master_secret'])
    tagged(db['TagList'], manifest)
    secret = api.call('secretsmanager', 'describe_secret', SecretId=res['application_secret'])
    require(secret['ARN'] == res['application_secret'] and 'DeletedDate' not in secret
            and secret['Name'] == env + '/application')
    tagged(secret['Tags'], manifest)
    for kind in ('backend', 'bootstrap'):
        definition = api.call('ecs', 'describe_task_definition',
                              taskDefinition=res[kind + '_task'])['taskDefinition']
        require(definition['taskDefinitionArn'] == res[kind + '_task']
                and definition['status'] == 'ACTIVE' and definition['networkMode'] == 'awsvpc'
                and definition['runtimePlatform'] == {'cpuArchitecture': 'X86_64',
                                                      'operatingSystemFamily': 'LINUX'})
        role = env + ('-task' if kind == 'backend' else '-bootstrap')
        execution = env + ('-execution' if kind == 'backend' else '-bootstrap-exec')
        require(definition['taskRoleArn'] == f'arn:aws:iam::{account}:role/{role}'
                and definition['executionRoleArn'] == f'arn:aws:iam::{account}:role/{execution}')
        containers = definition['containerDefinitions']
        require(len(containers) == 1 and containers[0]['name'] == 'backend')
        container = containers[0]
        expected_image = f'{account}.dkr.ecr.{REGION}.amazonaws.com/{env}/backend@'
        require(container['image'] == expected_image + manifest.data['image_digest'])
        if kind == 'bootstrap':
            require(not container.get('secrets'))
        else:
            actual = {item['name']: item['value'] for item in container['environment']}
            require(all(actual.get(key) == value for key, value in {
                'POSTGRES_HOST': res['database_host'], 'POSTGRES_DB': 'fitlog',
                'POSTGRES_USER': 'fitlog_app', 'POSTGRES_PORT': '5432',
                'FITLOG_APP_VERSION': manifest.data['source_revision'],
                'FITLOG_TRUST_PROXY': '0' if phase == 'private' else '1',
                'FITLOG_AUTH_CLIENT_IP_SOURCE': 'remote_addr' if phase == 'private' else 'cloudfront',
            }.items()))
            require({item['name']: item['valueFrom'] for item in container['secrets']} == {
                key: f"{res['application_secret']}:{key}::" for key in (
                    'DJANGO_SECRET_KEY', 'AUTH_RATE_LIMIT_HMAC_KEY', 'POSTGRES_PASSWORD')})
    dist_arn = f"arn:aws:cloudfront::{account}:distribution/{res['distribution']}"
    tagged(api.call('cloudfront', 'list_tags_for_resource', Resource=dist_arn)['Tags']['Items'],
           manifest)
    distribution = api.call('cloudfront', 'get_distribution', Id=res['distribution'])['Distribution']
    require(distribution['ARN'] == dist_arn and distribution['Status'] == 'Deployed')
    config = distribution['DistributionConfig']
    require(config['Enabled'] is (phase == 'public'))
    balancers = api.call('elbv2', 'describe_load_balancers', Names=[env + '-api'])['LoadBalancers']
    require(len(balancers) == 1)
    balancer = balancers[0]
    require(balancer['LoadBalancerArn'].startswith(
        f'arn:aws:elasticloadbalancing:{REGION}:{account}:loadbalancer/app/'))
    tagged(api.call('elbv2', 'describe_tags', ResourceArns=[balancer['LoadBalancerArn']])[
        'TagDescriptions'][0]['Tags'], manifest)
    require([o['DomainName'] for o in config['Origins']['Items'] if o['Id'] == 'api']
            == [balancer['DNSName']])
    # Origin headers are never returned, logged, or persisted.
    return dict(network)


def task_definition(manifest: Manifest, step: str) -> str:
    return str(manifest.resources['bootstrap_task' if step.startswith('bootstrap') else 'backend_task'])


def collect(
    api: Api, manifest: Manifest, step: str, task: str, timeout: float = 900,
    log_timeout: float = 180,
) -> int:
    """RunTask acceptance alone is never completion. No synthetic success events."""
    require(matches(re.escape(f"arn:aws:ecs:{REGION}:{manifest.data['account']}:task/"
                              f'{manifest.environment}/') + r'[a-f0-9]{32}', task))
    deadline = time.monotonic() + timeout
    while True:
        manifest.authorize(datetime.now(UTC), step)
        result = api.call('ecs', 'describe_tasks', cluster=manifest.environment, tasks=[task])
        require(not result.get('failures') and len(result['tasks']) == 1)
        actual = result['tasks'][0]
        require(actual['taskArn'] == task and actual['startedBy'] == manifest.data['run_id']
                and actual['taskDefinitionArn'] == task_definition(manifest, step))
        if actual['lastStatus'] == 'STOPPED':
            break
        require(time.monotonic() < deadline)
        time.sleep(min(3, max(0, deadline - time.monotonic())))
    containers = actual['containers']
    require(len(containers) == 1 and containers[0]['name'] == 'backend'
            and containers[0].get('exitCode') == 0
            and containers[0].get('imageDigest') == manifest.data['image_digest'])
    bootstrap = step.startswith('bootstrap')
    prefix = 'bootstrap' if bootstrap else 'backend'
    expected = ({'event': 'bootstrap_inspected' if step == 'bootstrap-inspect' else 'bootstrap_verified',
                 'operation': manifest.data['bootstrap_id']} if bootstrap else
                {'event': 'deployment_step_completed', 'step': step, 'run_id': manifest.data['run_id']})
    until = time.monotonic() + (log_timeout if timeout else 0)
    token: str | None = None
    seen: set[str] = set()
    while True:
        args: dict[str, Any] = {
            'logGroupName': f'/fitlog/{manifest.environment}/{prefix}',
            'logStreamName': f'{prefix}/backend/{task.rsplit("/", 1)[1]}',
            'startFromHead': True,
        }
        if token:
            args['nextToken'] = token
        try:
            page = api.call('logs', 'get_log_events', **args)
        except Exception as error:
            require(getattr(error, 'response', {}).get('Error', {}).get('Code')
                    == 'ResourceNotFoundException' and time.monotonic() < until)
            time.sleep(min(3, max(0, until - time.monotonic())))
            continue
        for event in page.get('events', []):
            try:
                parsed = json.loads(event['message'])
            except (ValueError, TypeError):
                continue
            if parsed == expected:
                return 0
        next_token = page.get('nextForwardToken')
        if next_token and next_token != token:
            require(next_token not in seen)
            seen.add(next_token)
            token = next_token
        require(time.monotonic() < until)
        time.sleep(min(3, max(0, until - time.monotonic())))

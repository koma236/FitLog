"""Operator-only, bounded service health observation; no AWS mutation or HTTP probes."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from operations.deployment_aws import Api, preflight
from operations.deployment_contract import REGION, Manifest, matches, require


@dataclass
class BoundedObservation:
    """Check approval/deadline around every read, including paginated responses."""

    api: Api
    manifest: Manifest
    deadline: float

    def check(self) -> None:
        self.manifest.authorize(datetime.now(UTC), 'inspect')
        require(time.monotonic() <= self.deadline)

    def call(self, service: str, operation: str, **kwargs: Any) -> dict[str, Any]:
        self.check()
        result = self.api.call(service, operation, **kwargs)
        self.check()
        return result


def service_tasks(api: Api, manifest: Manifest) -> list[dict[str, Any]]:
    """Enumerate this service only, refusing pagination cycles and missing tasks."""
    arns: list[str] = []
    token: str | None = None
    seen: set[str] = set()
    while True:
        args: dict[str, Any] = {'cluster': manifest.environment,
                                'serviceName': manifest.environment + '-backend',
                                'desiredStatus': 'RUNNING'}
        if token:
            args['nextToken'] = token
        page = api.call('ecs', 'list_tasks', **args)
        require(isinstance(page.get('taskArns'), list))
        arns.extend(page['taskArns'])
        token = page.get('nextToken')
        if not token:
            break
        require(isinstance(token, str) and token not in seen)
        seen.add(token)
    require(len(arns) == len(set(arns)))
    tasks = []
    prefix = f"arn:aws:ecs:{REGION}:{manifest.data['account']}:task/{manifest.environment}/"
    for start in range(0, len(arns), 100):
        selected = arns[start:start + 100]
        require(all(isinstance(arn, str) and arn.startswith(prefix)
                    and matches(r'[a-f0-9]{32}', arn[len(prefix):]) for arn in selected))
        page = api.call('ecs', 'describe_tasks', cluster=manifest.environment, tasks=selected)
        require(not page.get('failures') and len(page['tasks']) == len(selected)
                and {task['taskArn'] for task in page['tasks']} == set(selected))
        tasks.extend(page['tasks'])
    return tasks


def observe(api: Api, manifest: Manifest, phase: str) -> tuple[bool, str]:
    """Validate immutable boundaries first; return pending only for rollout state."""
    preflight(api, manifest, phase, wait_live=True)
    env = manifest.environment
    response = api.call('ecs', 'describe_services', cluster=env, services=[env + '-backend'])
    require(not response.get('failures') and len(response['services']) == 1)
    svc = response['services'][0]
    require(svc['taskDefinition'] == manifest.resources['backend_task']
            and svc['serviceName'] == env + '-backend' and svc['status'] == 'ACTIVE')
    deployments = svc['deployments']
    require(deployments and all(item.get('rolloutState') != 'FAILED' for item in deployments))
    primary = [item for item in deployments if item['status'] == 'PRIMARY']
    require(len(primary) == 1 and primary[0]['taskDefinition'] == manifest.resources['backend_task'])
    stable = (len(deployments) == 1 and primary[0].get('rolloutState') == 'COMPLETED'
              and tuple(svc[key] for key in ('desiredCount', 'runningCount', 'pendingCount')) == (1, 1, 0))
    lbs = svc['loadBalancers']
    require(len(lbs) == 1 and lbs[0]['containerName'] == 'backend' and lbs[0]['containerPort'] == 8000)
    tg_arn = lbs[0]['targetGroupArn']
    require(tg_arn.startswith(f"arn:aws:elasticloadbalancing:{REGION}:{manifest.data['account']}:targetgroup/"))
    balancers = api.call('elbv2', 'describe_load_balancers', Names=[env + '-api'])['LoadBalancers']
    require(len(balancers) == 1)
    groups = api.call('elbv2', 'describe_target_groups', TargetGroupArns=[tg_arn])['TargetGroups']
    require(len(groups) == 1)
    group = groups[0]
    require(group['TargetGroupArn'] == tg_arn and group['TargetType'] == 'ip'
            and group['Port'] == 8000 and group['Protocol'] == 'HTTP'
            and group['VpcId'] == balancers[0]['VpcId']
            and group['LoadBalancerArns'] == [balancers[0]['LoadBalancerArn']]
            and group['HealthCheckPath'] == '/api/health/live')
    tasks = service_tasks(api, manifest)
    expected_ip = None
    if stable and len(tasks) == 1:
        task = tasks[0]
        require(task['clusterArn'] == svc['clusterArn']
                and task['group'] == 'service:' + env + '-backend')
        stable = (task['taskDefinitionArn'] == manifest.resources['backend_task']
                  and task['lastStatus'] == 'RUNNING')
        if stable:
            containers = task['containers']
            require(len(containers) == 1 and containers[0]['name'] == 'backend'
                    and containers[0].get('imageDigest') == manifest.data['image_digest'])
            interfaces = containers[0]['networkInterfaces']
            require(len(interfaces) == 1)
            expected_ip = interfaces[0]['privateIpv4Address']
    else:
        stable = False
    targets = api.call('elbv2', 'describe_target_health', TargetGroupArn=tg_arn)['TargetHealthDescriptions']
    healthy = (len(targets) == 1 and targets[0]['Target']['Id'] == expected_ip
               and targets[0]['Target']['Port'] == 8000 and targets[0]['TargetHealth']['State'] == 'healthy')
    dist = api.call('cloudfront', 'get_distribution', Id=manifest.resources['distribution'])['Distribution']
    require(dist['ARN'] == f"arn:aws:cloudfront::{manifest.data['account']}:distribution/{manifest.resources['distribution']}"
            and dist['Status'] == 'Deployed' and dist['DistributionConfig']['Enabled'] is (phase == 'public')
            and matches(r'[a-z0-9]+\.cloudfront\.net', dist['DomainName']))
    return stable and healthy, 'https://' + dist['DomainName']


def health(api: Api, manifest: Manifest, phase: str, timeout: float = 900,
           interval: float = 3) -> str:
    """Wait for the expected deployment; failure never enables public traffic."""
    require(phase in ('backend', 'public'))
    deadline = time.monotonic() + timeout
    bounded = BoundedObservation(api, manifest, deadline)
    while True:
        bounded.check()
        ready, origin = observe(bounded, manifest, phase)
        bounded.check()
        if ready:
            return origin
        require(time.monotonic() < deadline)
        time.sleep(min(interval, max(0, deadline - time.monotonic())))

"""Service/task/ENI/target health oracles from AWS B design §4."""
import copy
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from test_contract import fixture
from test_remote import TASK, EnvironmentApi

from operations.deployment_contract import DeploymentError, Manifest

TG = 'arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:targetgroup/test/123'


class HealthApi(EnvironmentApi):
    def __init__(self, pending=0, failure=None, public=False):
        super().__init__()
        self.pending = pending
        self.failure = failure
        self.public = public

    def call(self, service, operation, **kwargs):
        if operation == 'list_tasks':
            self.calls.append((service, operation, kwargs))
            return {'taskArns': [TASK]}
        if operation == 'describe_tasks':
            self.calls.append((service, operation, kwargs))
            task = {'taskArn': TASK, 'lastStatus': 'RUNNING',
                    'taskDefinitionArn': fixture()['resources']['backend_task'],
                    'group': 'service:fitlog-demo-test-backend',
                    'clusterArn': 'arn:aws:ecs:ap-northeast-1:123456789012:cluster/fitlog-demo-test',
                    'containers': [{'name': 'backend', 'imageDigest': fixture()['image_digest'],
                                    'networkInterfaces': [{'privateIpv4Address': '10.42.0.8'}]}]}
            if self.failure == 'digest':
                task['containers'][0]['imageDigest'] = 'sha256:' + 'f' * 64
            return {'tasks': [task]}
        if operation == 'describe_target_groups':
            self.calls.append((service, operation, kwargs))
            return {'TargetGroups': [{'TargetGroupArn': TG, 'TargetType': 'ip', 'Port': 8000,
                    'Protocol': 'HTTP', 'VpcId': 'vpc-00000000000000001',
                    'HealthCheckPath': '/api/health/live',
                    'LoadBalancerArns': ['arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:loadbalancer/app/test/123']}]}
        if operation == 'describe_target_health':
            self.calls.append((service, operation, kwargs))
            return {'TargetHealthDescriptions': [{'Target': {'Id': '10.42.0.8', 'Port': 8000},
                    'TargetHealth': {'State': 'unhealthy' if self.failure == 'target' else 'healthy'}}]}
        result = copy.deepcopy(super().call(service, operation, **kwargs))
        if operation == 'describe_services':
            svc = result['services'][0]
            svc.update(desiredCount=1, runningCount=0 if self.pending else 1,
                       pendingCount=1 if self.pending else 0,
                       loadBalancers=[{'targetGroupArn': TG, 'containerName': 'backend', 'containerPort': 8000}],
                       deployments=[{'status': 'PRIMARY', 'taskDefinition': svc['taskDefinition'],
                                     'rolloutState': 'FAILED' if self.failure == 'rollback' else
                                     'IN_PROGRESS' if self.pending else 'COMPLETED'}])
            if self.pending:
                self.pending -= 1
        elif operation == 'describe_task_definition' and kwargs['taskDefinition'].endswith('-backend:1'):
            for item in result['taskDefinition']['containerDefinitions'][0]['environment']:
                if item['name'] == 'FITLOG_TRUST_PROXY':
                    item['value'] = '1'
                elif item['name'] == 'FITLOG_AUTH_CLIENT_IP_SOURCE':
                    item['value'] = 'cloudfront'
        elif operation == 'get_distribution':
            result['Distribution']['DomainName'] = 'dtest.cloudfront.net'
            result['Distribution']['DistributionConfig']['Enabled'] = self.public
        elif operation == 'describe_load_balancers':
            result['LoadBalancers'][0]['VpcId'] = 'vpc-00000000000000001'
        return result


class HealthTests(unittest.TestCase):
    def test_old_task_from_same_service_is_pending_until_new_revision_is_observed(self):
        from operations.deployment_health import health
        class EventuallyConsistent(HealthApi):
            old = True
            def call(self, service, operation, **kwargs):
                result = super().call(service, operation, **kwargs)
                if operation == 'describe_tasks' and self.old:
                    self.old = False
                    result['tasks'][0]['taskDefinitionArn'] = fixture()['resources']['backend_task'][:-1] + '9'
                return result
        api = EventuallyConsistent()
        self.assertEqual(health(api, Manifest.parse(fixture()), 'backend', timeout=1, interval=0),
                         'https://dtest.cloudfront.net')
        self.assertEqual(sum(op == 'describe_tasks' for _, op, _ in api.calls), 2)

    def test_read_response_after_deadline_or_approval_expiry_cannot_certify_health(self):
        from operations.deployment_health import health
        for limit in ('deadline', 'approval'):
            data = fixture()
            now = datetime.now(UTC)
            data['approval']['expires_at'] = (now + timedelta(seconds=1)).isoformat()
            with self.subTest(limit=limit), patch('operations.deployment_health.time.monotonic', return_value=0) as timer, \
                    patch('operations.deployment_health.datetime') as wall:
                wall.now.return_value = now
                class Delayed(HealthApi):
                    def call(self, service, operation, **kwargs):
                        result = super().call(service, operation, **kwargs)
                        if operation == 'get_distribution':
                            if limit == 'deadline':
                                timer.return_value = 901
                            else:
                                wall.now.return_value = now + timedelta(seconds=2)
                        return result
                with self.assertRaises(DeploymentError):
                    health(Delayed(), Manifest.parse(data), 'backend', timeout=900)

    def test_rollout_overlap_clears_before_success_and_pagination_cycles_fail(self):
        from operations.deployment_health import health
        class Rolling(HealthApi):
            overlap = 2
            def call(self, service, operation, **kwargs):
                result = super().call(service, operation, **kwargs)
                if operation == 'describe_services' and self.overlap:
                    self.overlap -= 1
                    result['services'][0]['deployments'].append({
                        'status': 'ACTIVE', 'taskDefinition': 'old-revision', 'rolloutState': 'COMPLETED'})
                return result
        self.assertEqual(health(Rolling(), Manifest.parse(fixture()), 'backend', timeout=1, interval=0),
                         'https://dtest.cloudfront.net')
        class Cycling(HealthApi):
            def call(self, service, operation, **kwargs):
                result = super().call(service, operation, **kwargs)
                if operation == 'list_tasks':
                    result['nextToken'] = 'repeated'
                return result
        with self.assertRaises(DeploymentError):
            health(Cycling(), Manifest.parse(fixture()), 'backend', timeout=0.01, interval=0)

    def test_unrelated_target_group_and_extra_task_do_not_pass(self):
        from operations.deployment_health import health
        for mutation in ('vpc', 'extra-task', 'empty-target', 'wrong-ip'):
            class Altered(HealthApi):
                def call(self, service, operation, **kwargs):
                    result = super().call(service, operation, **kwargs)
                    if operation == 'describe_target_groups' and mutation == 'vpc':
                        result['TargetGroups'][0]['VpcId'] = 'unrelated'
                    if operation == 'list_tasks' and mutation == 'extra-task':
                        result['taskArns'].append(TASK[:-32] + 'e' * 32)
                    if operation == 'describe_tasks' and mutation == 'extra-task':
                        extra = copy.deepcopy(result['tasks'][0])
                        extra['taskArn'] = TASK[:-32] + 'e' * 32
                        result['tasks'].append(extra)
                    if operation == 'describe_target_health':
                        if mutation == 'empty-target':
                            result['TargetHealthDescriptions'] = []
                        if mutation == 'wrong-ip':
                            result['TargetHealthDescriptions'][0]['Target']['Id'] = '10.42.0.99'
                    return result
            with self.subTest(mutation=mutation), self.assertRaises(DeploymentError):
                health(Altered(), Manifest.parse(fixture()), 'backend', timeout=0.01, interval=0)

    def test_starting_service_waits_then_binds_task_to_target(self):
        from operations.deployment_health import health
        api = HealthApi(pending=3)
        result = health(api, Manifest.parse(fixture()), 'backend', timeout=1, interval=0)
        self.assertEqual(result, 'https://dtest.cloudfront.net')
        self.assertGreater(sum(op == 'describe_services' for _, op, _ in api.calls), 3)
        self.assertFalse(any(op in ('run_task', 'update_service', 'put_object') for _, op, _ in api.calls))

    def test_rollback_digest_and_persistently_unhealthy_target_never_pass(self):
        from operations.deployment_health import health
        for failure in ('rollback', 'digest', 'target'):
            with self.subTest(failure=failure), self.assertRaises(DeploymentError):
                health(HealthApi(failure=failure), Manifest.parse(fixture()), 'backend', timeout=0.01, interval=0)

    def test_public_origin_is_from_expected_distribution_only(self):
        from operations.deployment_health import health
        api = HealthApi(public=True)
        self.assertEqual(health(api, Manifest.parse(fixture()), 'public', timeout=1),
                         'https://dtest.cloudfront.net')
        with self.assertRaises(DeploymentError):
            health(HealthApi(), Manifest.parse(fixture()), 'public', timeout=0.01, interval=0)

"""Task completion requires ECS and same-task log evidence independently."""
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_contract import fixture

from operations.deployment_aws import collect, preflight
from operations.deployment_cli import execute, identity, validate_verify_input
from operations.deployment_contract import DeploymentError, Manifest, write_evidence

TASK = 'arn:aws:ecs:ap-northeast-1:123456789012:task/fitlog-demo-test/' + 'd' * 32


class Fake:
    def __init__(self, code=0, digest=None, event=None):
        self.calls = []
        self.code = code
        self.digest = digest or fixture()['image_digest']
        self.event = event or {'event': 'deployment_step_completed', 'step': 'migrate',
                               'run_id': fixture()['run_id']}

    def call(self, service, operation, **kwargs):
        self.calls.append((service, operation, kwargs))
        if operation == 'describe_tasks':
            return {'tasks': [{'taskArn': TASK, 'lastStatus': 'STOPPED',
                               'taskDefinitionArn': fixture()['resources']['backend_task'],
                               'startedBy': fixture()['run_id'],
                               'overrides': {'containerOverrides': [{'name': 'backend', 'command':
                                   ['python', '-m', 'operations.deployment_step', '--step', 'migrate',
                                    '--run-id', fixture()['run_id'], '--expected-host',
                                    fixture()['resources']['database_host'], '--environment',
                                    fixture()['environment']]}]},
                               'containers': [{'name': 'backend', 'exitCode': self.code,
                                               'imageDigest': self.digest}]}]}
        if operation == 'get_log_events':
            return {'events': [{'message': json.dumps(self.event)}]}
        if operation == 'get_caller_identity':
            return {'Account': '999999999999'}
        raise AssertionError(operation)


class RemoteTests(unittest.TestCase):
    def test_same_task_event_and_digest_required(self):
        manifest = Manifest.parse(fixture())
        self.assertEqual(collect(Fake(), manifest, 'migrate', TASK, timeout=0), 0)
        for api in (Fake(code=1), Fake(digest='sha256:' + 'f' * 64),
                    Fake(event={'event': 'deployment_step_completed', 'step': 'migrate',
                                'run_id': '33333333-3333-4333-8333-333333333333'})):
            with self.subTest(api=api), self.assertRaises(DeploymentError):
                collect(api, manifest, 'migrate', TASK, timeout=0)

    def test_preflight_wrong_account_cannot_reach_mutation(self):
        api = Fake()
        with self.assertRaises(DeploymentError):
            preflight(api, Manifest.parse(fixture()), 'private')
        self.assertEqual([(s, op) for s, op, args in api.calls], [('sts', 'get_caller_identity')])


class EnvironmentApi(Fake):
    """Independent fixture of the B4/B6 metadata contract, no secret values."""
    def call(self, service, operation, **kwargs):
        data = fixture()
        env, account, res = data['environment'], data['account'], data['resources']
        tags = [{'Key': 'Project', 'Value': 'FitLog'}, {'Key': 'Environment', 'Value': env}]
        self.calls.append((service, operation, kwargs))
        if operation == 'get_caller_identity':
            return {'Account': account}
        if operation == 'describe_services':
            return {'services': [{'status': 'ACTIVE', 'serviceName': env + '-backend',
                    'clusterArn': f'arn:aws:ecs:ap-northeast-1:{account}:cluster/{env}',
                    'taskDefinition': res['backend_task'], 'desiredCount': 0, 'runningCount': 0,
                    'pendingCount': 0, 'tags': [{'key': t['Key'], 'value': t['Value']} for t in tags],
                    'networkConfiguration': {'awsvpcConfiguration': {'subnets': res['subnets'],
                        'securityGroups': [res['security_group']], 'assignPublicIp': 'ENABLED'}}}]}
        if operation == 'describe_db_instances':
            return {'DBInstances': [{'DBInstanceArn': f'arn:aws:rds:ap-northeast-1:{account}:db:{env}',
                    'DBInstanceIdentifier': env, 'DBInstanceStatus': 'available', 'Engine': 'postgres',
                    'EngineVersion': '17.6', 'MasterUsername': 'fitlog_admin', 'DBName': 'fitlog',
                    'PubliclyAccessible': False, 'Endpoint': {'Port': 5432, 'Address': res['database_host']},
                    'MasterUserSecret': {'SecretArn': res['master_secret']}, 'TagList': tags}]}
        if operation == 'describe_secret':
            return {'ARN': res['application_secret'], 'Name': env + '/application', 'Tags': tags}
        if operation == 'describe_task_definition':
            bootstrap = kwargs['taskDefinition'] == res['bootstrap_task']
            suffix = '-bootstrap' if bootstrap else '-task'
            exec_suffix = '-bootstrap-exec' if bootstrap else '-execution'
            container = {'name': 'backend', 'image': f'{account}.dkr.ecr.ap-northeast-1.amazonaws.com/{env}/backend@' + data['image_digest']}
            if not bootstrap:
                container['environment'] = [{'name': k, 'value': v} for k, v in {
                    'POSTGRES_HOST': res['database_host'], 'POSTGRES_DB': 'fitlog', 'POSTGRES_USER': 'fitlog_app',
                    'POSTGRES_PORT': '5432', 'FITLOG_APP_VERSION': data['source_revision'],
                    'FITLOG_TRUST_PROXY': '0', 'FITLOG_AUTH_CLIENT_IP_SOURCE': 'remote_addr'}.items()]
                container['secrets'] = [{'name': k, 'valueFrom': res['application_secret'] + ':' + k + '::'}
                    for k in ('DJANGO_SECRET_KEY', 'AUTH_RATE_LIMIT_HMAC_KEY', 'POSTGRES_PASSWORD')]
            return {'taskDefinition': {'taskDefinitionArn': kwargs['taskDefinition'], 'status': 'ACTIVE',
                    'networkMode': 'awsvpc', 'runtimePlatform': {'cpuArchitecture': 'X86_64', 'operatingSystemFamily': 'LINUX'},
                    'taskRoleArn': f'arn:aws:iam::{account}:role/{env}{suffix}',
                    'executionRoleArn': f'arn:aws:iam::{account}:role/{env}{exec_suffix}', 'containerDefinitions': [container]}}
        if operation == 'list_tags_for_resource':
            return {'Tags': {'Items': tags}}
        if operation == 'get_distribution':
            return {'Distribution': {'ARN': f'arn:aws:cloudfront::{account}:distribution/EFITLOGTEST',
                    'Status': 'Deployed', 'DistributionConfig': {'Enabled': False,
                    'Origins': {'Items': [{'Id': 'api', 'DomainName': 'fixture.elb.amazonaws.com'}]}}}}
        if operation == 'describe_load_balancers':
            return {'LoadBalancers': [{'LoadBalancerArn': f'arn:aws:elasticloadbalancing:ap-northeast-1:{account}:loadbalancer/app/test/123',
                                     'DNSName': 'fixture.elb.amazonaws.com'}]}
        if operation == 'describe_tags':
            return {'TagDescriptions': [{'Tags': tags}]}
        if operation == 'run_task':
            return {'tasks': [{'taskArn': TASK}]}
        return super().call(service, operation, **kwargs)


class ExecutionTests(unittest.TestCase):
    def test_success_and_duplicate_intent_never_launches_second_task(self):
        manifest = Manifest.parse(fixture())
        api = EnvironmentApi()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_evidence(root, manifest, 'bootstrap', 'pass', deployment_identity=identity(manifest))
            self.assertEqual(execute(api, manifest, root, 'migrate', 'private'), TASK)
            with self.assertRaises(FileExistsError):
                execute(api, manifest, root, 'migrate', 'private')
        self.assertEqual(sum(op == 'run_task' for s, op, args in api.calls), 1)

    def test_secret_looking_verify_input_rejected_before_api(self):
        manifest = Manifest.parse(fixture())
        for data in ({'mode': 'database', 'parameters': {'password': 'PRIVATE'}},
                     {'mode': 'permissions', 'parameters': {'version': 'PRIVATE'}}):
            with self.assertRaises(DeploymentError):
                validate_verify_input(manifest, 'public', data)

    def test_private_database_verify_rejected_before_task_or_inspection(self):
        manifest = Manifest.parse(fixture())
        api = EnvironmentApi()
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(DeploymentError):
            execute(api, manifest, Path(folder), 'verify', 'private',
                    {'mode': 'database', 'parameters': {}})
        self.assertEqual(api.calls, [])

    def test_collect_after_approval_expiry_extension_never_launches_again(self):
        data = fixture()
        manifest = Manifest.parse(data)
        api = EnvironmentApi()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_evidence(root, manifest, 'bootstrap', 'pass', deployment_identity=identity(manifest))
            self.assertEqual(execute(api, manifest, root, 'migrate', 'private'), TASK)
            data['approval']['expires_at'] = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
            updated = Manifest.parse(data)
            self.assertNotEqual(manifest.fingerprint, updated.fingerprint)
            self.assertEqual(identity(manifest), identity(updated))
            self.assertEqual(execute(api, updated, root, 'migrate', 'private', resume_task=TASK), TASK)
        self.assertEqual(sum(op == 'run_task' for s, op, args in api.calls), 1)

    def test_run_task_response_loss_can_resume_after_new_approval(self):
        class LostResponse(EnvironmentApi):
            def call(self, service, operation, **kwargs):
                result = super().call(service, operation, **kwargs)
                if operation == 'run_task':
                    raise TimeoutError('response lost')
                return result
        data = fixture()
        manifest = Manifest.parse(data)
        api = LostResponse()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_evidence(root, manifest, 'bootstrap', 'pass', deployment_identity=identity(manifest))
            with self.assertRaises(TimeoutError):
                execute(api, manifest, root, 'migrate', 'private')
            data['approval']['expires_at'] = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
            self.assertEqual(execute(api, Manifest.parse(data), root, 'migrate', 'private',
                                     resume_task=TASK), TASK)
        self.assertEqual(sum(op == 'run_task' for s, op, args in api.calls), 1)

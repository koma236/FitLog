"""Initial provisioning contracts, independent of Django and live AWS."""
import json
import unittest
from unittest.mock import Mock

from operations.contract import BootstrapError, Request, SecretValues

ACCOUNT = '123456789012'
ENV = 'fitlog-demo-test'
ARN = f'arn:aws:secretsmanager:ap-northeast-1:{ACCOUNT}:secret:{ENV}/application-AbCdEf'
TOKEN = '01234567-0123-4123-8123-0123456789ab'


class ContractTests(unittest.TestCase):
    def test_request_names_and_account_boundary(self) -> None:
        request = Request(ACCOUNT, ENV, ENV, ARN, 'E123456789ABCD', TOKEN)
        self.assertEqual(request.service, 'fitlog-demo-test-backend')
        for account, env, db, arn, token in (
            ('999999999999', ENV, ENV, ARN, TOKEN),
            (ACCOUNT, ENV, 'fitlog-demo-other', ARN, TOKEN),
            (ACCOUNT, 'wrong', 'wrong', ARN, TOKEN),
            (ACCOUNT, ENV, ENV, ARN.replace('ap-northeast-1', 'us-east-1'), TOKEN),
            (ACCOUNT, ENV, ENV, ARN, 'not-a-uuid'),
        ):
            with self.subTest(account=account, env=env, db=db, token=token):
                with self.assertRaises(BootstrapError):
                    Request(account, env, db, arn, 'E123456789ABCD', token)

    def test_generated_values_are_distinct_private_and_serializable(self) -> None:
        values = SecretValues.generate()
        payload = json.loads(values.encode())
        self.assertEqual(set(payload), {
            'DJANGO_SECRET_KEY', 'AUTH_RATE_LIMIT_HMAC_KEY', 'POSTGRES_PASSWORD',
        })
        self.assertEqual(len(set(payload.values())), 3)
        for value in payload.values():
            self.assertRegex(value, r'^[A-Za-z0-9_-]{64}$')
            self.assertNotIn(value, repr(values))
        self.assertEqual(SecretValues.decode(values.encode()).encode(), values.encode())

    def test_malformed_or_equal_secrets_are_rejected_without_echo(self) -> None:
        for raw in ('secret-sentinel', '{}', '[]', json.dumps({
            'DJANGO_SECRET_KEY': 'S' * 64,
            'AUTH_RATE_LIMIT_HMAC_KEY': 'S' * 64,
            'POSTGRES_PASSWORD': 'P' * 64,
        })):
            with self.subTest(raw=raw):
                with self.assertRaises(BootstrapError) as error:
                    SecretValues.decode(raw)
                self.assertNotIn(raw, str(error.exception))


class SecretStoreTests(unittest.TestCase):
    def test_initial_and_resume_are_same_version_without_second_write(self) -> None:
        from unittest.mock import Mock

        from operations.aws import SecretStore

        client = Mock()
        client.list_secret_version_ids.return_value = {'Versions': []}
        values = SecretValues.generate()
        client.put_secret_value.return_value = {'ARN': ARN, 'VersionId': TOKEN}
        client.get_secret_value.return_value = {
            'ARN': ARN, 'VersionId': TOKEN, 'VersionStages': ['AWSCURRENT'],
            'SecretString': values.encode(),
        }
        store = SecretStore(client, Request(ACCOUNT, ENV, ENV, ARN, 'E123456789ABCD', TOKEN))
        # Generate fixture through the external CSPRNG boundary.
        from unittest.mock import patch
        with patch('operations.contract.secrets.token_urlsafe',
                   side_effect=[values.django, values.hmac, values.password]):
            first = store.load_or_create(lambda: None)
        self.assertEqual(first.encode(), values.encode())
        self.assertEqual(client.put_secret_value.call_count, 1)
        client.list_secret_version_ids.return_value = {'Versions': [
            {'VersionId': TOKEN, 'VersionStages': ['AWSCURRENT']},
        ]}
        self.assertEqual(store.load_or_create(lambda: None).encode(), first.encode())
        self.assertEqual(client.put_secret_value.call_count, 1)

    def test_second_page_unknown_version_is_rejected(self) -> None:
        from unittest.mock import Mock

        from operations.aws import SecretStore

        client = Mock()
        client.list_secret_version_ids.side_effect = [
            {'Versions': [{'VersionId': TOKEN, 'VersionStages': ['AWSCURRENT']}],
             'NextToken': 'second'},
            {'Versions': [{'VersionId': 'unknown', 'VersionStages': []}]},
        ]
        with self.assertRaises(BootstrapError):
            SecretStore(client, Request(ACCOUNT, ENV, ENV, ARN, 'E1', TOKEN)).load_or_create(lambda: None)
        client.put_secret_value.assert_not_called()
        client.get_secret_value.assert_not_called()


class DatabaseBoundaryTests(unittest.TestCase):
    def test_connection_options_cannot_be_replaced_by_environment(self) -> None:
        from operations.database import connection_options
        options = connection_options('demo.rds.amazonaws.com', 'fitlog_admin', 'hidden', '/ca.pem')
        self.assertEqual(options['sslmode'], 'verify-full')
        self.assertEqual(options['sslrootcert'], '/ca.pem')
        self.assertEqual(options['dbname'], 'fitlog')
        self.assertEqual(options['port'], 5432)
        self.assertEqual(options['user'], 'fitlog_admin')

    def test_busy_lock_never_reaches_secret_write(self) -> None:
        from unittest.mock import Mock

        from operations.database import Database
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = (False,)
        with self.assertRaises(BootstrapError):
            Database(connection).acquire()


class CommandTests(unittest.TestCase):
    def test_help_has_no_credential_lookup(self) -> None:
        import os
        import subprocess
        import sys
        environment = {**os.environ, 'AWS_EC2_METADATA_DISABLED': 'false',
                       'AWS_ENDPOINT_URL': 'http://127.0.0.1:1'}
        result = subprocess.run([sys.executable, '-m', 'operations.bootstrap', '--help'],
                                env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--initialize', result.stdout)
        self.assertIn('--distribution-id', result.stdout)

    def test_invalid_input_is_not_echoed(self) -> None:
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-m', 'operations.bootstrap',
                                 '--password', 'private-sentinel'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('private-sentinel', result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)


class MetadataTests(unittest.TestCase):
    def fixture(self) -> Mock:
        from unittest.mock import Mock

        from operations.aws import Aws
        aws = Mock(spec=Aws)
        for name in ("sts", "rds", "ecs", "secrets", "cloudfront", "elbv2"):
            setattr(aws, name, Mock())
        aws.inspect.side_effect = lambda request: Aws.inspect(aws, request)
        aws.tags.side_effect = Aws.tags
        tags = [{'Key': 'Project', 'Value': 'FitLog'}, {'Key': 'Environment', 'Value': ENV}]
        master = f'arn:aws:secretsmanager:ap-northeast-1:{ACCOUNT}:secret:rds!master-AbCdEf'
        aws.sts.get_caller_identity.return_value = {'Account': ACCOUNT}
        aws.rds.describe_db_instances.return_value = {'DBInstances': [{
            'DBInstanceIdentifier': ENV,
            'DBInstanceArn': f'arn:aws:rds:ap-northeast-1:{ACCOUNT}:db:{ENV}',
            'Engine': 'postgres', 'EngineVersion': '17.11', 'DBName': 'fitlog',
            'MasterUsername': 'fitlog_admin', 'PubliclyAccessible': False,
            'DBInstanceStatus': 'available', 'Endpoint': {'Address': 'db.example', 'Port': 5432},
            'TagList': tags, 'MasterUserSecret': {'SecretArn': master},
        }]}
        aws.secrets.describe_secret.return_value = {'ARN': ARN, 'Name': ENV + '/application',
                                                   'Tags': tags}
        aws.ecs.describe_services.return_value = {'services': [{
            'serviceName': ENV + '-backend', 'status': 'ACTIVE',
            'clusterArn': f'arn:aws:ecs:ap-northeast-1:{ACCOUNT}:cluster/{ENV}',
            'desiredCount': 0, 'runningCount': 0, 'pendingCount': 0,
            'tags': [{'key': tag['Key'], 'value': tag['Value']} for tag in tags],
            'taskDefinition': 'definition',
        }]}
        aws.ecs.describe_task_definition.return_value = {'taskDefinition': {
            'taskDefinitionArn': f'arn:aws:ecs:ap-northeast-1:{ACCOUNT}:task-definition/{ENV}-backend:1',
            'containerDefinitions': [{'name': 'backend', 'environment': [
                {'name': key, 'value': value} for key, value in {
                    'POSTGRES_HOST': 'db.example', 'POSTGRES_PORT': '5432',
                    'POSTGRES_DB': 'fitlog', 'POSTGRES_USER': 'fitlog_app',
                }.items()], 'secrets': [{'name': key, 'valueFrom': ARN + ':' + key + '::'} for key in
                    ('DJANGO_SECRET_KEY', 'AUTH_RATE_LIMIT_HMAC_KEY', 'POSTGRES_PASSWORD')]}],
        }}
        aws.elbv2.describe_load_balancers.return_value = {'LoadBalancers': [{
            'LoadBalancerArn': f'arn:aws:elasticloadbalancing:ap-northeast-1:{ACCOUNT}:loadbalancer/app/demo/1',
            'DNSName': 'alb.example',
        }]}
        aws.elbv2.describe_tags.return_value = {'TagDescriptions': [{'Tags': tags}]}
        aws.cloudfront.list_tags_for_resource.return_value = {'Tags': {'Items': tags}}
        aws.cloudfront.get_distribution.return_value = {'Distribution': {
            'ARN': f'arn:aws:cloudfront::{ACCOUNT}:distribution/E1', 'Status': 'Deployed',
            'DistributionConfig': {'Enabled': False, 'Origins': {'Items': [
                {'Id': 'api', 'DomainName': 'alb.example', 'CustomHeaders': {'private': 'sentinel'}},
            ]}},
        }}
        return aws

    def test_read_only_does_not_connect_or_get_private_values(self) -> None:
        from operations.bootstrap import run
        aws = self.fixture()
        self.assertEqual(run(Request(ACCOUNT, ENV, ENV, ARN, 'E1', TOKEN), False, aws),
                         'bootstrap_inspected')
        aws.secrets.get_secret_value.assert_not_called()
        aws.secrets.put_secret_value.assert_not_called()

    def test_wrong_account_and_running_service_are_rejected(self) -> None:
        aws = self.fixture()
        aws.sts.get_caller_identity.return_value = {'Account': '999999999999'}
        with self.assertRaises(BootstrapError):
            aws.inspect(Request(ACCOUNT, ENV, ENV, ARN, 'E1', TOKEN))
        aws.rds.describe_db_instances.assert_not_called()
        for field in ('desiredCount', 'runningCount', 'pendingCount'):
            aws = self.fixture()
            aws.ecs.describe_services.return_value['services'][0][field] = 1
            with self.assertRaises(BootstrapError):
                aws.inspect(Request(ACCOUNT, ENV, ENV, ARN, 'E1', TOKEN))
            aws.secrets.get_secret_value.assert_not_called()

    def test_wrong_host_secret_origin_and_enabled_distribution_rejected(self) -> None:
        for case in ('host', 'secret', 'origin', 'enabled', 'tag'):
            aws = self.fixture()
            if case == 'host':
                aws.rds.describe_db_instances.return_value['DBInstances'][0]['Endpoint'][
                    'Address'] = 'another.example'
            elif case == 'secret':
                aws.ecs.describe_task_definition.return_value['taskDefinition'][
                    'containerDefinitions'][0]['secrets'][0]['valueFrom'] = 'another-secret'
            elif case == 'origin':
                aws.cloudfront.get_distribution.return_value['Distribution'][
                    'DistributionConfig']['Origins']['Items'][0]['DomainName'] = 'another-alb'
            elif case == 'enabled':
                aws.cloudfront.get_distribution.return_value['Distribution'][
                    'DistributionConfig']['Enabled'] = True
            else:
                aws.secrets.describe_secret.return_value['Tags'] = []
            with self.subTest(case=case), self.assertRaises(BootstrapError):
                aws.inspect(Request(ACCOUNT, ENV, ENV, ARN, 'E1', TOKEN))


class SdkBoundaryTests(unittest.TestCase):
    def test_environment_endpoint_overrides_cannot_redirect_clients(self) -> None:
        from unittest.mock import patch

        from operations.aws import Aws
        with patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'fixture',
                                      'AWS_SECRET_ACCESS_KEY': 'fixture',
                                      'AWS_ENDPOINT_URL': 'http://127.0.0.1:1',
                                      'AWS_ENDPOINT_URL_RDS': 'http://127.0.0.1:2',
                                      'AWS_EC2_METADATA_DISABLED': 'true'}):
            aws = Aws.connect()
        for client, domain in ((aws.sts, 'sts.ap-northeast-1'),
                               (aws.rds, 'rds.ap-northeast-1'),
                               (aws.ecs, 'ecs.ap-northeast-1'),
                               (aws.secrets, 'secretsmanager.ap-northeast-1'),
                               (aws.cloudfront, 'cloudfront'),
                               (aws.elbv2, 'elasticloadbalancing.ap-northeast-1')):
            self.assertEqual(client.meta.endpoint_url, f'https://{domain}.amazonaws.com')

    def test_real_sdk_parses_fixed_version_without_network(self) -> None:
        import boto3
        from botocore.stub import Stubber

        from operations.aws import SecretStore
        client = boto3.client('secretsmanager', region_name='ap-northeast-1',
                              aws_access_key_id='fixture', aws_secret_access_key='fixture')
        values = SecretValues.generate()
        with Stubber(client) as stub:
            stub.add_response('list_secret_version_ids', {'Versions': [
                {'VersionId': TOKEN, 'VersionStages': ['AWSCURRENT']},
            ]}, {'SecretId': ARN, 'IncludeDeprecated': True})
            stub.add_response('get_secret_value', {'ARN': ARN, 'VersionId': TOKEN,
                'VersionStages': ['AWSCURRENT'], 'SecretString': values.encode()},
                {'SecretId': ARN, 'VersionId': TOKEN, 'VersionStage': 'AWSCURRENT'})
            result = SecretStore(client, Request(ACCOUNT, ENV, ENV, ARN, 'E1', TOKEN)).load_or_create(lambda: None)
            self.assertEqual(result.encode(), values.encode())
            stub.assert_no_pending_responses()

    def test_private_upstream_exception_never_reaches_command_output(self) -> None:
        import logging
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from operations.bootstrap import main
        self.addCleanup(logging.disable, logging.root.manager.disable)
        output, error = StringIO(), StringIO()
        with patch('operations.bootstrap.Aws.connect', side_effect=RuntimeError(
            'private-password SCRAM-SHA-256$verifier upstream-traceback')):
            with redirect_stdout(output), redirect_stderr(error):
                code = main(['--expected-account-id', ACCOUNT, '--environment', ENV,
                             '--db-instance-identifier', ENV, '--application-secret-arn', ARN,
                             '--distribution-id', 'E1', '--operation-id', TOKEN])
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(error.getvalue(), '{"event":"bootstrap_failed"}\n')


class CredentialChainBoundaryTests(unittest.TestCase):
    def test_web_identity_internal_sts_ignores_endpoint_overrides(self) -> None:
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from botocore.client import BaseClient

        from operations.aws import Aws
        observed: list[str] = []

        def credential_response(client: BaseClient, operation: str,
                                params: dict[str, object]) -> dict[str, object]:
            self.assertIn(operation, ('AssumeRoleWithWebIdentity', 'AssumeRole'))
            if operation == 'AssumeRoleWithWebIdentity':
                self.assertEqual(params['WebIdentityToken'], 'public-web-identity-fixture')
            observed.append(client.meta.endpoint_url)
            return {'Credentials': {'AccessKeyId': 'A' * 20, 'SecretAccessKey': 'S' * 40,
                                    'SessionToken': 'public-session-fixture',
                                    'Expiration': '2099-01-01T00:00:00Z'}}

        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / 'token'
            token.write_text('public-web-identity-fixture')
            config = Path(folder) / 'config'
            config.write_text('[profile fixture]\nrole_arn = arn:aws:iam::' + ACCOUNT +
                              ':role/fixture\nsource_profile = source\nregion = ap-northeast-1\n')
            credentials = Path(folder) / 'credentials'
            credentials.write_text('[source]\naws_access_key_id = public-fixture\n'
                                   'aws_secret_access_key = public-fixture\n')
            for mode in ('web', 'role'):
                env = {'AWS_ENDPOINT_URL_STS': 'http://127.0.0.1:19999',
                       'AWS_CONFIG_FILE': str(config),
                       'AWS_SHARED_CREDENTIALS_FILE': str(credentials),
                       'AWS_EC2_METADATA_DISABLED': 'true'}
                if mode == 'web':
                    env.update(AWS_ROLE_ARN=f'arn:aws:iam::{ACCOUNT}:role/fixture',
                               AWS_WEB_IDENTITY_TOKEN_FILE=str(token))
                else:
                    env['AWS_PROFILE'] = 'fixture'
                with self.subTest(mode=mode), patch.dict(os.environ, env, clear=True):
                    with patch.object(BaseClient, '_make_api_call', new=credential_response):
                        aws = Aws.connect()
                        aws.sts.generate_presigned_url('get_caller_identity', Params={})
        self.assertEqual(observed, ['https://sts.ap-northeast-1.amazonaws.com'] * 2)


class LeaseGuardTests(unittest.TestCase):
    def test_lost_lease_before_put_does_not_write(self) -> None:
        from operations.aws import SecretStore
        client = Mock()
        client.list_secret_version_ids.return_value = {'Versions': []}
        guard = Mock(side_effect=[None, BootstrapError()])
        with self.assertRaises(BootstrapError):
            SecretStore(client, Request(ACCOUNT, ENV, ENV, ARN, 'E1', TOKEN)).load_or_create(guard)
        client.put_secret_value.assert_not_called()
        client.get_secret_value.assert_not_called()


class SignatureScopeTests(unittest.TestCase):
    def test_fixed_endpoints_sign_for_each_service_region_without_network(self) -> None:
        import re
        from unittest.mock import patch

        from botocore.awsrequest import AWSPreparedRequest

        from operations.aws import Aws

        class SendCaptured(Exception):
            pass

        scopes: list[tuple[str, str]] = []

        def capture(request: AWSPreparedRequest, **kwargs: object) -> None:
            assert request.headers is not None
            authorization = request.headers.get('Authorization')
            assert isinstance(authorization, (str, bytes))
            text = authorization.decode() if isinstance(authorization, bytes) else authorization
            matched = re.search(r'Credential=[^/]+/[0-9]{8}/([^/]+)/([^/]+)/aws4_request', text)
            assert matched is not None
            scopes.append((matched.group(1), matched.group(2)))
            raise SendCaptured()

        with patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'public-fixture',
                                      'AWS_SECRET_ACCESS_KEY': 'public-fixture',
                                      'AWS_EC2_METADATA_DISABLED': 'true',
                                      'AWS_ENDPOINT_URL': 'http://127.0.0.1:1',
                                      'AWS_ENDPOINT_URL_CLOUDFRONT': 'http://127.0.0.1:2'},
                        clear=True):
            aws = Aws.connect()
            cases = (
                (aws.sts, lambda: aws.sts.get_caller_identity(), 'ap-northeast-1', 'sts'),
                (aws.rds, lambda: aws.rds.describe_db_instances(DBInstanceIdentifier=ENV),
                 'ap-northeast-1', 'rds'),
                (aws.ecs, lambda: aws.ecs.describe_services(cluster=ENV, services=[ENV + '-backend']),
                 'ap-northeast-1', 'ecs'),
                (aws.secrets, lambda: aws.secrets.describe_secret(SecretId=ARN),
                 'ap-northeast-1', 'secretsmanager'),
                (aws.cloudfront, lambda: aws.cloudfront.list_tags_for_resource(
                    Resource=f'arn:aws:cloudfront::{ACCOUNT}:distribution/E1'),
                 'us-east-1', 'cloudfront'),
                (aws.elbv2, lambda: aws.elbv2.describe_load_balancers(Names=[ENV + '-api']),
                 'ap-northeast-1', 'elasticloadbalancing'),
            )
            for client, invoke, region, service in cases:
                with self.subTest(service=service):
                    client.meta.events.register('before-send.*.*', capture)
                    before = len(scopes)
                    with self.assertRaises(SendCaptured):
                        invoke()
                    self.assertEqual(len(scopes), before + 1)
                    self.assertEqual(scopes[-1], (region, service))

"""Negative authorization results must be actual denials, not missing objects."""
import unittest

from test_contract import fixture

from operations.deployment_contract import DeploymentError
from operations.deployment_verify import denied, permission_probes


class ApiError(Exception):
    def __init__(self, code):
        self.response = {'Error': {'Code': code}}


class Api:
    def __init__(self, code='AccessDeniedException'):
        self.code = code
        self.calls = []

    def call(self, service, operation, **kwargs):
        self.calls.append((service, operation, kwargs))
        if self.code:
            raise ApiError(self.code)
        return {'SecretString': 'PRIVATE-UNEXPECTED-SUCCESS'}


class VerifyTests(unittest.TestCase):
    def test_only_access_denied_counts_as_authorization_rejection(self):
        denied(Api(), 'secretsmanager', 'get_secret_value', SecretId='fixture')
        for code in ('ResourceNotFoundException', 'Timeout', None):
            with self.subTest(code=code), self.assertRaises(DeploymentError):
                denied(Api(code), 'secretsmanager', 'get_secret_value', SecretId='fixture')

    def test_real_secret_write_probe_uses_existing_uuid_without_stage_changes(self):
        data = fixture()
        args = {'account': data['account'], 'application_secret': data['resources']['application_secret'],
                'master_secret': data['resources']['master_secret'],
                'version': data['bootstrap_id'], 'fixture_verified': True}
        api = Api()
        permission_probes(api, data['environment'], args)
        put = [call for call in api.calls if call[1] == 'put_secret_value'][0][2]
        self.assertEqual(put['ClientRequestToken'], data['bootstrap_id'])
        self.assertEqual(put['SecretId'], args['application_secret'])
        self.assertNotIn('VersionStages', put)
        api = Api()
        args['fixture_verified'] = False
        with self.assertRaises(DeploymentError):
            permission_probes(api, data['environment'], args)
        self.assertEqual(api.calls, [])

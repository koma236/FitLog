"""Offline contract oracles from the approved FL-09B7 design, not AWS outputs."""
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from operations.deployment_contract import DeploymentError, Manifest, write_evidence


def fixture():
    return {
        'schema_version': 1, 'run_id': '11111111-1111-4111-8111-111111111111',
        'account': '123456789012', 'region': 'ap-northeast-1', 'environment': 'fitlog-demo-test',
        'source_revision': 'b' * 40, 'image_digest': 'sha256:' + 'a' * 64,
        'frontend_sha256': 'c' * 64,
        'bootstrap_id': '22222222-2222-4222-8222-222222222222',
        'state': {'path': '/protected/terraform.tfstate', 'sha256': 'd' * 64},
        'approval': {'reference': 'chat-aws-approval-1', 'budget_usd': '20.00',
                     'steps': ['inspect', 'static', 'bootstrap-inspect', 'bootstrap',
                               'migrate', 'seed', 'check', 'verify'],
                     'expires_at': (datetime.now(UTC) + timedelta(hours=2)).isoformat()},
        'resources': {
            'distribution': 'EFITLOGTEST', 'database_host': 'fixture.ap-northeast-1.rds.amazonaws.com',
            'application_secret': 'arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fitlog-demo-test/application-AbCdEf',
            'master_secret': 'arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:rds!db-fixture-AbCdEf',
            'backend_task': 'arn:aws:ecs:ap-northeast-1:123456789012:task-definition/fitlog-demo-test-backend:1',
            'bootstrap_task': 'arn:aws:ecs:ap-northeast-1:123456789012:task-definition/fitlog-demo-test-bootstrap:1',
            'subnets': ['subnet-00000000000000001', 'subnet-00000000000000002'],
            'security_group': 'sg-00000000000000001',
        },
    }


def protected_state(data, root):
    directory = root.resolve() / 'state'
    directory.mkdir(mode=0o700)
    path = directory / 'terraform.tfstate'
    content = b'{"version":4,"fixture":"LOCAL-STATE-MUST-NOT-LEAK"}'
    path.write_bytes(content)
    path.chmod(0o600)
    data['state'] = {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest()}
    return path


class ContractTests(unittest.TestCase):
    def test_valid_and_expired_approval(self):
        data = fixture()
        manifest = Manifest.parse(data)
        manifest.authorize(datetime.now(UTC))
        data['approval']['expires_at'] = '2020-01-01T00:00:00+00:00'
        with self.assertRaises(DeploymentError):
            Manifest.parse(data).authorize(datetime.now(UTC))

    def test_cross_account_unknown_fields_and_secret_inputs_rejected(self):
        for key, value in [('account', '999999999999'), ('region', 'us-east-1'),
                           ('password', 'DO-NOT-LOG-ME'), ('image_digest', 'latest')]:
            data = fixture()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(DeploymentError):
                Manifest.parse(data)

    def test_evidence_append_only_private_and_fixed_fields(self):
        manifest = Manifest.parse(fixture())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'evidence'
            path = write_evidence(target, manifest, 'inspect', 'pass')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(path.read_text())['manifest_sha256'], manifest.fingerprint)
            with self.assertRaises(DeploymentError):
                write_evidence(target, manifest, 'inspect', 'pass')
            with self.assertRaises(DeploymentError):
                write_evidence(target, manifest, 'password=DO-NOT-LOG-ME', 'pass')

    def test_atomic_success_record_contains_all_bindings_and_can_be_recollected(self):
        manifest = Manifest.parse(fixture())
        binding = 'd' * 64
        parameters = 'e' * 64
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'evidence'
            with patch('operations.deployment_contract.os.link', side_effect=OSError('fixture')):
                with self.assertRaises(OSError):
                    write_evidence(target, manifest, 'verify-public-ip-baseline', 'pass',
                                   deployment_identity=binding, parameters_sha256=parameters)
            self.assertEqual(list(target.iterdir()), [])
            path = write_evidence(target, manifest, 'verify-public-ip-baseline', 'pass',
                                  deployment_identity=binding, parameters_sha256=parameters)
            record = json.loads(path.read_text())
            self.assertEqual(record['deployment_identity'], binding)
            self.assertEqual(record['parameters_sha256'], parameters)
            same = write_evidence(target, manifest, 'verify-public-ip-baseline', 'pass',
                                  deployment_identity=binding, parameters_sha256=parameters,
                                  allow_existing=True)
            self.assertEqual(path, same)
            with self.assertRaises(DeploymentError):
                write_evidence(target, manifest, 'verify-public-ip-baseline', 'pass',
                               deployment_identity='f' * 64, parameters_sha256=parameters,
                               allow_existing=True)

    def test_response_loss_after_atomic_publish_can_be_recollected(self):
        import os
        original = os.link
        def publish_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('injected loss after publish')
        manifest = Manifest.parse(fixture())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'evidence'
            with patch('operations.deployment_contract.os.link', side_effect=publish_then_fail):
                with self.assertRaises(OSError):
                    write_evidence(target, manifest, 'migrate', 'pass', deployment_identity='d' * 64)
            path = write_evidence(target, manifest, 'migrate', 'pass',
                                  deployment_identity='d' * 64, allow_existing=True)
            self.assertEqual(json.loads(path.read_text())['deployment_identity'], 'd' * 64)
            self.assertEqual(len(list(target.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()

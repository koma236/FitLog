"""Approved draft/state/operation boundaries exercised without AWS credentials."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from test_contract import fixture, protected_state
from test_remote import EnvironmentApi

from operations.deployment_assets import bundle, upload
from operations.deployment_cli import execute, identity, main
from operations.deployment_contract import DeploymentError, Manifest


class ManifestGuardTests(unittest.TestCase):
    def invoke(self, data, root, *arguments):
        source = root / 'manifest.json'
        source.write_text(json.dumps(data))
        output, error = io.StringIO(), io.StringIO()
        with patch('operations.deployment_cli.Gateway.connect', return_value=EnvironmentApi()) as gateway, \
                redirect_stdout(output), redirect_stderr(error):
            result = main(['--manifest', str(source), *arguments])
        return result, output.getvalue(), error.getvalue(), gateway

    def test_partial_draft_is_offline_and_never_executable(self):
        data = {'schema_version': 1, 'region': 'ap-northeast-1', 'account': None,
                'approval': {'steps': ['inspect']}, 'resources': {'backend_task': None}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result, output, error, gateway = self.invoke(data, root, '--draft')
            self.assertEqual((result, error), (0, ''))
            self.assertEqual(json.loads(output)['event'], 'deployment_manifest_draft_validated')
            gateway.assert_not_called()
            result, _, _, gateway = self.invoke(data, root, '--draft', '--aws-approved')
            self.assertEqual(result, 2)
            gateway.assert_not_called()
        with self.assertRaises(DeploymentError):
            Manifest.parse(fixture(), draft=True).authorize(datetime.now(UTC), 'inspect')

    def test_draft_checks_supplied_values_and_unknown_nested_fields(self):
        for data in ({'account': 'invalid'}, {'approval': {'password': 'PRIVATE'}},
                     {'resources': {'backend_task': 'arn:aws:ecs:us-east-1:123456789012:task-definition/x:1'}},
                     {'state': {'path': '../state'}}, {'schema_version': 99},
                     {'approval': {'steps': ['shell']}},
                     {'account': '999999999999', 'resources': fixture()['resources']}):
            with self.subTest(data=data), self.assertRaises(DeploymentError):
                Manifest.parse(data, draft=True)

    def test_full_manifest_requires_all_fields_and_nonempty_unique_known_steps(self):
        data = fixture()
        Manifest.parse(data)
        for key in ('image_digest', 'state', 'approval'):
            for missing in (True, False):
                invalid = fixture()
                if missing:
                    del invalid[key]
                else:
                    invalid[key] = None
                with self.subTest(key=key, missing=missing), self.assertRaises(DeploymentError):
                    Manifest.parse(invalid)
        for steps in ([], ['inspect', 'inspect'], ['shell'], '*', None):
            invalid = fixture()
            invalid['approval']['steps'] = steps
            with self.subTest(steps=steps), self.assertRaises(DeploymentError):
                Manifest.parse(invalid)

    def test_permitted_inspect_succeeds_with_verified_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = fixture()
            protected_state(data, root)
            data['approval']['steps'] = ['inspect']
            result, output, error, gateway = self.invoke(
                data, root, '--aws-approved', '--evidence', str(root / 'evidence'))
            self.assertEqual((result, error), (0, ''))
            self.assertEqual(json.loads(output)['event'], 'deployment_completed')
            self.assertEqual(gateway.call_count, 1)
            receipt = json.loads(next((root / 'evidence').glob('*-inspect.json')).read_text())
            self.assertEqual(receipt['status'], 'pass')

    def test_unapproved_steps_and_collection_rejected_before_aws(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = fixture()
            protected_state(data, root)
            data['approval']['steps'] = ['inspect']
            for step in ('bootstrap', 'migrate', 'static', 'verify'):
                for collect in ([], ['--collect-task', 'untrusted-task']):
                    result, _, _, gateway = self.invoke(data, root, '--aws-approved',
                        '--evidence', str(root / 'evidence'), '--step', step, *collect)
                    self.assertEqual(result, 2)
                    gateway.assert_not_called()
            api = EnvironmentApi()
            with self.assertRaises(DeploymentError):
                execute(api, Manifest.parse(data), root, 'migrate', 'private')
            self.assertEqual(api.calls, [])

    def test_state_hash_permissions_missing_and_symlink_fail_before_aws(self):
        for failure in ('hash', 'file-mode', 'directory-mode', 'missing', 'symlink', 'parent-symlink'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                data = fixture()
                state = protected_state(data, root)
                if failure == 'hash':
                    state.write_text('CHANGED-STATE-MUST-NOT-LEAK')
                elif failure == 'file-mode':
                    state.chmod(0o644)
                elif failure == 'directory-mode':
                    state.parent.chmod(0o755)
                elif failure == 'missing':
                    state.unlink()
                elif failure == 'symlink':
                    link = state.parent / 'link'
                    link.symlink_to(state)
                    data['state']['path'] = str(link)
                else:
                    link = root.resolve() / 'link'
                    link.symlink_to(state.parent, target_is_directory=True)
                    data['state']['path'] = str(link / state.name)
                result, output, error, gateway = self.invoke(data, root, '--aws-approved',
                                                           '--evidence', str(root / 'evidence'))
                self.assertEqual(result, 2)
                self.assertNotIn('MUST-NOT-LEAK', output + error)
                gateway.assert_not_called()

    def test_state_hash_can_track_apply_but_path_stays_bound_to_run(self):
        data = fixture()
        original = identity(Manifest.parse(data))
        data['state']['sha256'] = 'e' * 64
        self.assertEqual(identity(Manifest.parse(data)), original)
        data['state']['path'] = '/protected/other.tfstate'
        self.assertNotEqual(identity(Manifest.parse(data)), original)

    def test_static_upload_also_requires_its_own_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'index.html').write_text('fixture')
            assets = bundle(root)
            data = fixture()
            data['frontend_sha256'] = assets['sha256']
            data['approval']['steps'] = ['inspect']
            api = EnvironmentApi()
            with self.assertRaises(DeploymentError):
                upload(api, Manifest.parse(data), root, assets)
            self.assertEqual(api.calls, [])

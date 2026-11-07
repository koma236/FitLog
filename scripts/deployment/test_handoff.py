"""Offline handoff must not convert mixed or missing observations to a pass."""
import copy
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_artifacts import artifact_fixture, private_json
from test_contract import fixture
from test_remote import TASK

from operations.deployment_cli import identity
from operations.deployment_contract import DeploymentError, Manifest, write_evidence


def records(root, manifest):
    steps = ('inspect', 'static', 'bootstrap-inspect', 'bootstrap', 'migrate', 'seed',
             'check', 'backend', 'verify-backend-database', 'public-health')
    for step in steps:
        remote = step in ('bootstrap-inspect', 'bootstrap', 'migrate', 'seed', 'check',
                          'verify-backend-database')
        write_evidence(root, manifest, step, 'pass', TASK if remote else None,
                       0 if remote else None, deployment_identity=identity(manifest),
                       origin='https://dtest.cloudfront.net' if step in ('backend', 'public-health') else None)


class HandoffTests(unittest.TestCase):
    def test_new_backend_revision_cannot_reuse_old_health_or_database_receipts(self):
        from operations.deployment_handoff import handoff
        from operations.deployment_cli import predecessor
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest, folder, window = self.setup_bundle(root)
            data = copy.deepcopy(manifest.data)
            data['resources']['backend_task'] = data['resources']['backend_task'][:-1] + '2'
            updated = Manifest.parse(data)
            # Private migration/seed/check history legitimately predates proxy activation.
            predecessor(folder, updated, 'backend')
            with self.assertRaises(DeploymentError):
                handoff(updated, artifact_fixture(data), folder, window)
            with self.assertRaises(DeploymentError):
                predecessor(folder, updated, 'verify', 'backend')

    def setup_bundle(self, root):
        data = fixture()
        manifest = Manifest.parse(data)
        folder = root / 'evidence'
        records(folder, manifest)
        now = datetime.now(UTC)
        window = {'starts_at': (now + timedelta(minutes=1)).isoformat(),
                  'ends_at': (now + timedelta(minutes=10)).isoformat(),
                  'approval_reference': data['approval']['reference']}
        return manifest, folder, window

    def test_ready_for_c_does_not_certify_unexecuted_permissions_or_ip(self):
        from operations.deployment_handoff import handoff
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest, folder, window = self.setup_bundle(root)
            result = handoff(manifest, artifact_fixture(manifest.data), folder, window)
            self.assertEqual(result['status'], 'ready_for_c')
            self.assertEqual(result['origin'], 'https://dtest.cloudfront.net')
            self.assertEqual(result['probes'], {'permissions': 'not_run', 'ip': 'not_run'})
            self.assertEqual(len(result['evidence']), 10)
            self.assertNotIn('state', result)

    def test_mixed_frontend_failed_records_and_bad_window_rejected(self):
        from operations.deployment_handoff import handoff
        for mutation in ('frontend', 'status', 'missing', 'origin', 'window'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                manifest, folder, window = self.setup_bundle(root)
                path = folder / (manifest.data['run_id'] + '-public-health.json')
                import json
                saved = json.loads(path.read_text())
                if mutation == 'window':
                    window['ends_at'] = '2099-01-01T00:00:00Z'
                elif mutation == 'missing':
                    path.unlink()
                else:
                    saved[{'frontend': 'frontend_sha256', 'status': 'status', 'origin': 'origin'}[mutation]] = {
                        'frontend': 'f' * 64, 'status': 'fail', 'origin': 'https://attacker.invalid'}[mutation]
                    private_json(path, saved)
                with self.assertRaises((DeploymentError, FileNotFoundError)):
                    handoff(manifest, artifact_fixture(manifest.data), folder, copy.deepcopy(window))

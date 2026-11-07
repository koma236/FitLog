"""Missing predecessors cannot reach AWS mutations (approved design §4)."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_artifacts import artifact_fixture, private_json
from test_contract import fixture, protected_state

from operations.deployment_cli import identity, main
from operations.deployment_contract import Manifest, write_evidence


class SequenceTests(unittest.TestCase):
    def test_bootstrap_inspect_requires_inspect_even_when_static_record_remains(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            data = fixture()
            protected_state(data, root)
            manifest = private_json(root / 'manifest.json', data)
            artifacts = private_json(root / 'artifacts.json', artifact_fixture(data))
            parsed = Manifest.parse(data)
            evidence = root / 'evidence'
            write_evidence(evidence, parsed, 'static', 'pass', deployment_identity=identity(parsed))
            with patch('operations.deployment_cli.Gateway.connect') as gateway, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = main(['--manifest', str(manifest), '--artifacts', str(artifacts),
                               '--aws-approved', '--evidence', str(evidence), '--step', 'bootstrap-inspect'])
            self.assertEqual(result, 2)
            gateway.assert_not_called()

    def test_source_record_tamper_never_connects_and_never_echoes_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            data = fixture()
            protected_state(data, root)
            manifest = private_json(root / 'manifest.json', data)
            record = artifact_fixture(data)
            record['backend']['revision_label'] = 'PRIVATE-SENTINEL'
            artifacts = private_json(root / 'artifacts.json', record)
            out, err = io.StringIO(), io.StringIO()
            with patch('operations.deployment_cli.Gateway.connect') as gateway, \
                    redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(['--manifest', str(manifest), '--artifacts', str(artifacts),
                                       '--aws-approved', '--evidence', str(root / 'evidence')]), 2)
            gateway.assert_not_called()
            self.assertNotIn('PRIVATE-SENTINEL', out.getvalue() + err.getvalue())

    def test_missing_artifact_refused_before_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            data = fixture()
            protected_state(data, root)
            manifest = private_json(root / 'manifest.json', data)
            with patch('operations.deployment_cli.Gateway.connect') as gateway, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--manifest', str(manifest), '--aws-approved',
                                       '--evidence', str(root / 'evidence')]), 2)
            gateway.assert_not_called()

    def test_predecessors_checked_before_gateway_for_static_bootstrap_and_health(self):
        for step, phase in [('static', 'private'), ('bootstrap-inspect', 'private'),
                            ('inspect', 'backend'), ('inspect', 'public')]:
            with self.subTest(step=step, phase=phase), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                data = fixture()
                protected_state(data, root)
                manifest = private_json(root / 'manifest.json', data)
                artifacts = private_json(root / 'artifacts.json', artifact_fixture(data))
                with patch('operations.deployment_cli.Gateway.connect') as gateway, \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = main(['--manifest', str(manifest), '--artifacts', str(artifacts),
                                   '--aws-approved', '--evidence', str(root / 'evidence'),
                                   '--step', step, '--phase', phase])
                self.assertEqual(result, 2)
                gateway.assert_not_called()

    def test_record_frontend_and_origin_are_bound_without_raw_responses(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as folder:
            record = write_evidence(Path(folder), Manifest.parse(data), 'public-health', 'pass',
                deployment_identity=identity(Manifest.parse(data)), origin='https://dtest.cloudfront.net')
            saved = json.loads(record.read_text())
            self.assertEqual(saved['frontend_sha256'], data['frontend_sha256'])
            self.assertEqual(saved['origin'], 'https://dtest.cloudfront.net')

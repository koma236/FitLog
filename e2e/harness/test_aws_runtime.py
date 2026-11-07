"""No real AWS endpoints: child/process boundaries are replaced with fakes."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import time
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('aws_runtime', Path(__file__).parents[1] / 'aws-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class AwsRuntimeTests(unittest.TestCase):
    def test_default_entry_only_validates_and_never_creates_a_client(self):
        with patch.object(runtime, 'load', return_value={}), patch.object(runtime, 'validate', return_value={}), patch.object(runtime, 'execute') as execute:
            self.assertEqual(runtime.main(['--contract', '/fixture/input']), 0)
        execute.assert_not_called()

    def test_invalid_contract_prevents_execution(self):
        with patch.object(runtime, 'load', side_effect=runtime.Invalid()), patch.object(runtime, 'execute') as execute:
            self.assertEqual(runtime.main(['--contract', '/fixture/input', '--execute-aws', '--campaign', '/fixture/campaign']), 1)
        execute.assert_not_called()

    def test_no_container_or_server_command_in_aws_lifecycle(self):
        # Exercise fake runtime directly, including failing browser outcome.
        driver = object.__new__(runtime.AwsDriver)
        driver.lock = Mock(owner={'run_id': 'aaaaaaaaaaaa'})
        driver.output = Path('/fixture/output')
        driver.data = {'test_run': 'aaaaaaaaaaaa'}
        driver.report = {}
        driver.command = Mock(side_effect=RuntimeError('COMMAND_FAILED'))
        driver.safe = True
        with self.assertRaises(RuntimeError): driver.exercise()
        argv = driver.command.call_args.args[1]
        self.assertEqual(argv[0], 'node')
        self.assertIn('--config=e2e/aws.playwright.config.ts', argv)
        # No browser receipt: even a stopped fake Node is not proof of Chromium.
        self.assertFalse(driver.stop_owned())

    def test_spawn_failure_retains_uncertain_stop_and_does_not_expose_raw_error(self):
        driver = object.__new__(runtime.AwsDriver)
        driver.lock = Mock(owned=Mock(return_value=True))
        driver.report = {'operations': []}; driver.safe = True; driver.persist = Mock()
        driver.deadline = time.monotonic() + 100
        driver.data = {'expires_at': '2030-01-01T00:00:00Z'}
        driver.output = Path('/fixture/nonexistent'); driver.browser_attempted = False
        driver.lock.owner = {'run_id': 'aaaaaaaaaaaa'}
        with patch.object(runtime.subprocess, 'Popen', side_effect=OSError('secret-canary')):
            with self.assertRaises(OSError): driver.command('browser', ['node', 'fixture'])
        self.assertFalse(driver.stop_owned())
        self.assertNotIn('secret-canary', str(driver.report))

    def test_pending_storage_evidence_is_not_promoted_by_successful_http_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = object.__new__(runtime.AwsDriver)
            driver.output = Path(directory).resolve()
            videos = driver.output / 'videos-quarantine'; videos.mkdir()
            for name in ('a.webm', 'b.webm'): (videos / name).write_bytes(b'fixture-not-real-video')
            driver.data = {'test_run': 'aaaaaaaaaaaa'}
            driver.report = {}; driver.command = Mock(return_value='')
            rows = {key: {'status': 'pass'} for key in ('C01', 'C02', 'C05', 'C06')}
            rows['C03'] = {'status': 'not_run'}
            with patch.object(runtime.local, 'validate_browser_result'), patch.object(runtime, 'load', side_effect=[
                rows, {'public_http_health': 'pass', 's3_reference': 'not_run'},
                {'status': 'aws_capture_pending_playback'},
            ]):
                driver.exercise()
            self.assertEqual(rows['C03']['status'], 'not_run')
            self.assertNotIn('acceptance', driver.report)

    def test_parent_refuses_a_browser_command_after_its_stop_reserve(self):
        driver = object.__new__(runtime.AwsDriver)
        driver.lock = Mock(owned=Mock(return_value=True))
        driver.safe = True; driver.deadline = time.monotonic() - 1
        driver.data = {'expires_at': '2030-01-01T00:00:00Z'}
        with patch.object(runtime.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError, 'AWS_DEADLINE'):
                driver.command('aws-browser', ['node', 'fixture'], 1200)
        spawn.assert_not_called()

"""No real AWS endpoints: child/process boundaries are replaced with fakes."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import time
import copy
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('aws_runtime', Path(__file__).parents[1] / 'aws-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class AwsRuntimeTests(unittest.TestCase):
    def run_fake_lifecycle(self, *, stopped, exercise_failed=False, owner=True, changed_source=False, stop_raises=False):
        """Run the real coordinator with client/lock boundaries replaced only."""
        data = {'source': 'a' * 40, 'test_run': 'aaaaaaaaaaaa', 'lease_id': 'fixture-window'}
        before = {'commit': data['source'], 'dirty_paths': [], 'source_sha256': 'b' * 64}
        after = {**before, 'source_sha256': 'c' * 64} if changed_source else before
        lock = Mock(owner={}); lock.owned.return_value = owner
        driver = Mock(report={})
        driver.stop_owned.return_value = stopped
        if stop_raises: driver.stop_owned.side_effect = RuntimeError('PRIVATE-STOP-CANARY')
        if exercise_failed: driver.exercise.side_effect = RuntimeError('PRIVATE-ERROR-CANARY')
        saved = []
        driver.save.side_effect = lambda: saved.append(copy.deepcopy(driver.report))
        lock.release.side_effect = lambda: self.assertTrue(all(item['status'] == 'fail' for item in saved))
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runtime.local.shared, 'git_context', return_value=(runtime.local.EXPECTED_COMMON, 'test/aws-verification-60')), \
                 patch.object(runtime.local, 'snapshot', side_effect=[before, after]), \
                 patch.object(runtime.local.shared, 'RuntimeLock', return_value=lock), \
                 patch.object(runtime, 'protected', return_value=Path(directory).resolve()), \
                 patch.object(runtime, 'validate'), patch.object(runtime, 'claim'), \
                 patch.object(runtime, 'AwsDriver', return_value=driver):
                code = runtime.execute(data, Path(directory).resolve())
        return code, driver.report, saved, lock

    def test_successful_exercise_with_unconfirmed_stop_fails_and_retains_lock(self):
        code, report, saved, lock = self.run_fake_lifecycle(stopped=False)
        self.assertNotEqual(code, 0)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['error'], 'STOP_UNCONFIRMED')
        self.assertFalse(report['client_stop_confirmed'])
        self.assertFalse(report['lease_returned'])
        self.assertTrue(all(item['status'] != 'pass' for item in saved))
        lock.release.assert_not_called()

    def test_success_requires_stop_source_and_lock_return_and_preserves_earlier_failure(self):
        for options in ({'stopped': True}, {'stopped': True, 'exercise_failed': True},
                        {'stopped': True, 'owner': False}, {'stopped': True, 'changed_source': True}):
            with self.subTest(options=options):
                code, report, saved, lock = self.run_fake_lifecycle(**options)
                success = options == {'stopped': True}
                self.assertEqual(code == 0, success)
                self.assertEqual(report['status'], 'pass' if success else 'fail')
                self.assertNotIn('PRIVATE-ERROR-CANARY', str(saved))
                if not options.get('owner', True): lock.release.assert_not_called()
                else: lock.release.assert_called_once()

    def test_stop_exception_is_a_failed_result_with_no_raw_details_or_lock_release(self):
        code, report, saved, lock = self.run_fake_lifecycle(stopped=True, stop_raises=True)
        self.assertNotEqual(code, 0)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['error'], 'STOP_UNCONFIRMED')
        self.assertFalse(report['lease_returned'])
        self.assertNotIn('PRIVATE-STOP-CANARY', str(saved))
        lock.release.assert_not_called()

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

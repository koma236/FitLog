"""Offline contracts and client lifecycle; no AWS credentials or product requests."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'e2e'))
import aws_contract as base


def fixture(folder):
    data = base.fixture()
    data.pop('campaign_id')
    data.update(environment='fitlog-demo-day70', evidence=[])
    data['approval']['steps'] = ['journey', 'cleanup']
    refs = []
    for step in base.B_START:
        record = {'schema_version': 2, 'step': step, 'status': 'pass',
                  'run_id': data['run_id'], 'source_revision': data['source'],
                  'image_digest': data['image_digest'], 'frontend_sha256': data['frontend_sha256'],
                  'deployment_identity': 'e' * 64,
                  'origin': data['origin'] if step in ('backend', 'public-health') else None}
        path = folder / ('b-' + step + '.json')
        base.exclusive_json(path, record)
        refs.append({'step': step, 'path': str(path), 'sha256': base.canonical_hash(record)})
    handoff = {**base.identity(data), 'source_revision': data['source'], 'schema_version': 1,
               'status': 'ready_for_c', 'probes': {'permissions': 'not_run', 'ip': 'not_run'},
               'evidence': refs, 'window': {'starts_at': data['starts_at'],
               'ends_at': data['expires_at'], 'approval_reference': data['approval']['reference']}}
    handoff.pop('source')
    path = folder / 'handoff.json'
    base.exclusive_json(path, handoff)
    data['handoff'] = {'path': str(path), 'sha256': base.sha256(path)}
    return data


class Day70Tests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'scripts/day70/runtime.py').is_file(), 'day70 entry missing')
        from scripts.day70 import runtime
        self.runtime = runtime
        self.contract = runtime.contract
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.folder.chmod(0o700)
        self.data = fixture(self.folder)
        self.now = datetime(2026, 11, 7, 8, tzinfo=timezone.utc)

    def test_single_environment_without_recording_or_second_campaign_is_valid(self):
        result = self.contract.validate(self.data, self.now)
        self.assertEqual(result['approval']['steps'], ['journey', 'cleanup'])
        self.assertNotIn('campaign_id', result)
        self.assertFalse(base.final_ready(result))

    def test_capture_performance_or_extra_steps_are_refused(self):
        for steps in (['journey', 'capture', 'performance', 'cleanup'], ['journey'],
                      ['journey', 'cleanup', 'capture']):
            data = copy.deepcopy(self.data)
            data['approval']['steps'] = steps
            with self.subTest(steps=steps), self.assertRaises(base.Invalid):
                self.contract.validate(data, self.now)

    def test_budget_and_binding_fields_are_strict(self):
        for key, value in [('schema_version', True), ('campaign_id', 'unused'),
                           ('origin', 'http://dexample.cloudfront.net'),
                           ('origin', 'https://dexample.cloudfront.net:443'),
                           ('origin', 'https://user@dexample.cloudfront.net'),
                           ('origin', 'https://other.cloudfront.net'),
                           ('environment', 'day70'), ('run_id', 'x'), ('source', 'a' * 39),
                           ('unknown', 'PRIVATE-CANARY')]:
            data = copy.deepcopy(self.data)
            data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(base.Invalid):
                self.contract.validate(data, self.now)
        for budget in ('0', '5.01', '-1', True, 5, 'NaN', '1e0'):
            data = copy.deepcopy(self.data)
            data['approval']['budget_usd'] = budget
            with self.subTest(budget=budget), self.assertRaises(base.Invalid):
                self.contract.validate(data, self.now)

    def test_window_boundaries_and_expired_inputs_are_refused(self):
        for key, value in [('expires_at', '2026-11-07T08:00:00Z'),
                           ('starts_at', '2026-11-07T08:01:00Z'),
                           ('starts_at', '2026-11-07T07:59:00+00:00'),
                           ('expires_at', '2026-11-07T08:45:01Z')]:
            data = copy.deepcopy(self.data)
            data[key] = value
            with self.subTest(key=key), self.assertRaises(base.Invalid):
                self.contract.validate(data, self.now)

    def test_handoff_original_change_is_rejected(self):
        handoff = base.load(self.data['handoff']['path'])
        Path(handoff['evidence'][0]['path']).write_text('{"status":"pass"}')
        with self.assertRaises(base.Invalid):
            self.contract.validate(self.data, self.now)

    def test_one_environment_ledger_does_not_refund_a_failed_attempt(self):
        ledger = self.folder / 'ledger'
        ledger.mkdir(mode=0o700)
        self.contract.initialize(ledger, self.data)
        self.contract.claim(ledger, self.data)
        for key, value in [('test_run', 'bbbbbbbbbbbb'), ('environment', 'fitlog-demo-other'),
                           ('run_id', '00000000-0000-4000-8000-000000000099')]:
            data = copy.deepcopy(self.data)
            data[key] = value
            with self.subTest(key=key), self.assertRaises(base.Invalid):
                self.contract.claim(ledger, data)
        with self.assertRaises(base.Invalid):
            self.contract.initialize(ledger, self.data)
        self.assertTrue((ledger / 'attempt.json').is_file())

    def make_driver(self):
        driver = object.__new__(self.runtime.Day70Driver)
        driver.data = self.data
        driver.output = self.folder
        driver.report = {}
        driver.command = Mock()
        driver.browser_attempted = False
        return driver

    def exercise(self, driver, rows=None, capture='not_run', storage=None):
        rows = rows or {key: {'status': 'pass' if key in ('C01', 'C02') else 'not_run'}
                        for key in ('C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07')}
        story = {'capture_status': capture}
        with patch.object(self.runtime.local, 'validate_browser_result'), \
             patch.object(self.runtime.base, 'load', side_effect=[rows, story, storage or {'public_http_health': 'pass'}]):
            driver.exercise()

    def test_exercise_reuses_guarded_journey_with_capture_disabled(self):
        driver = self.make_driver()
        self.exercise(driver)
        args, kwargs = driver.command.call_args
        self.assertEqual(args[1][0], 'node')
        self.assertIn('--config=e2e/aws.playwright.config.ts', args[1])
        self.assertEqual(kwargs['env']['FITLOG_E2E_CAPTURE'], '0')
        self.assertTrue(driver.browser_attempted)
        self.assertEqual(driver.report['capture'], 'not_run')
        self.assertEqual(driver.report['performance'], 'not_run')
        self.assertNotIn('acceptance', driver.report)

    def test_capture_performance_and_incomplete_observations_fail(self):
        for changed, status in [('C01', 'not_run'), ('C02', 'not_run'), ('C03', 'fail'),
                                ('C05', 'pass'), ('C06', 'pass'), ('C07', 'pass')]:
            rows = {key: {'status': 'pass' if key in ('C01', 'C02') else 'not_run'}
                    for key in ('C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07')}
            rows[changed]['status'] = status
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                self.exercise(self.make_driver(), rows)
        with self.assertRaises(RuntimeError):
            self.exercise(self.make_driver(), capture='pass')
        (self.folder / 'videos-quarantine').mkdir()
        with self.assertRaises(RuntimeError):
            self.exercise(self.make_driver())

    def test_missing_health_and_forbidden_artifacts_cannot_hide_behind_pass(self):
        with self.assertRaises(RuntimeError):
            self.exercise(self.make_driver(), storage={'public_http_health': 'not_run'})
        for name in ('performance.json', 'capture-safe.json', 'secret-screen.png'):
            path = self.folder / name
            path.write_text('{}')
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                self.exercise(self.make_driver())
            path.unlink()

    def test_preparation_preserves_original_approval_without_fake_capture(self):
        driver = self.make_driver()
        with patch.object(self.contract, 'validate', return_value=self.data):
            driver.prepare()
        value = base.load(self.folder / 'runtime-input.json')
        self.assertEqual(value['contract']['approval']['steps'], ['journey', 'cleanup'])
        self.assertEqual(value['mode'], 'aws')
        self.assertFalse(value['final_evidence_ready'])

    def run_lifecycle(self, stopped=True, owned=True, exercise_failure=False, changed=False,
                      release_failure=False, mutate_handoff=False):
        runtime = self.runtime
        ledger = self.folder / 'ledger'
        ledger.mkdir(mode=0o700)
        before = {'commit': self.data['source'], 'source_sha256': 'a' * 64, 'dirty_paths': []}
        after = {**before, 'source_sha256': 'b' * 64} if changed else before
        lock = Mock(owner={})
        lock.owned.return_value = owned
        if release_failure:
            lock.release.side_effect = RuntimeError('PRIVATE-RELEASE-CANARY')
        driver = Mock(report={})
        driver.stop_owned.return_value = stopped
        if exercise_failure:
            driver.exercise.side_effect = RuntimeError('PRIVATE-EXERCISE-CANARY')
        if mutate_handoff:
            handoff = base.load(self.data['handoff']['path'])
            receipt = Path(handoff['evidence'][0]['path'])
            original = receipt.read_bytes()
            self.addCleanup(receipt.write_bytes, original)
            driver.exercise.side_effect = lambda: receipt.write_text('{"status":"pass"}')
        saved = []
        driver.save.side_effect = lambda: saved.append(copy.deepcopy(driver.report))
        def release():
            self.assertTrue(saved)
            self.assertTrue(all(row['status'] == 'fail' for row in saved))
        if not release_failure:
            lock.release.side_effect = release
        with patch.object(runtime.local.shared, 'git_context', return_value=(runtime.local.EXPECTED_COMMON, 'ops/aws-demo-day-70')), \
             patch.object(runtime.local.shared, 'RuntimeLock', return_value=lock), \
             patch.object(runtime.local, 'snapshot', side_effect=[before, after]), \
             patch.object(runtime.contract, 'validate'), patch.object(runtime.contract, 'claim'), \
             patch.object(runtime, 'Day70Driver', return_value=driver):
            result = runtime.execute(self.data, ledger)
        return result, saved, lock, driver

    def test_success_requires_client_stop_and_source_owner_and_lock_return(self):
        result, saved, lock, driver = self.run_lifecycle()
        self.assertEqual(result, 0)
        self.assertEqual(saved[-1]['status'], 'pass')
        self.assertTrue(saved[-1]['lease_returned'])
        lock.release.assert_called_once()
        driver.verify_boundary.assert_called_once()

    def test_failure_cannot_be_overwritten_by_a_later_success(self):
        for options in ({'stopped': False}, {'owned': False}, {'exercise_failure': True},
                        {'changed': True}, {'release_failure': True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temp:
                old = self.folder
                self.folder = Path(temp).resolve()
                self.folder.chmod(0o700)
                result, saved, lock, driver = self.run_lifecycle(**options)
                self.folder = old
                self.assertNotEqual(result, 0)
                self.assertTrue(all(row['status'] == 'fail' for row in saved))
                self.assertNotIn('PRIVATE-', str(saved))
                if options.get('stopped') is False or options.get('owned') is False:
                    lock.release.assert_not_called()

    def test_changed_source_or_handoff_original_retains_lock_and_lease(self):
        # Plan §3 requires all three proofs before return: stop, source, evidence.
        for options, code in (({'changed': True}, 'SOURCE_CHANGED'),
                              ({'mutate_handoff': True}, 'DAY70_EVIDENCE_INVALID')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temp:
                old = self.folder
                self.folder = Path(temp).resolve()
                self.folder.chmod(0o700)
                result, saved, lock, driver = self.run_lifecycle(**options)
                self.folder = old
                self.assertEqual(result, 1)
                lock.release.assert_not_called()
                self.assertTrue(all(row['status'] == 'fail' for row in saved))
                self.assertFalse(saved[-1]['lease_returned'])
                self.assertFalse(saved[-1]['lock_released'])
                self.assertEqual(saved[-1]['error'], code)
                if options.get('mutate_handoff'):
                    self.assertFalse(saved[-1]['final_evidence_ready'])

    def test_default_entry_is_offline_and_does_not_spawn_or_claim(self):
        with patch.object(self.runtime.base, 'load', return_value=self.data), \
             patch.object(self.contract, 'validate', return_value=self.data), \
             patch.object(self.runtime, 'execute') as execute:
            self.assertEqual(self.runtime.main(['--contract', '/fixture/contract']), 0)
        execute.assert_not_called()

    def test_invalid_contract_blocks_client_creation_and_sanitizes_errors(self):
        with patch.object(self.runtime.base, 'load', side_effect=ValueError('PRIVATE-CONTRACT-CANARY')), \
             patch.object(self.runtime, 'execute') as execute, patch('builtins.print') as output:
            self.assertEqual(self.runtime.main(['--contract', '/fixture/contract', '--execute-aws', '--ledger', '/fixture/ledger']), 1)
        execute.assert_not_called()
        self.assertNotIn('PRIVATE-CONTRACT-CANARY', str(output.call_args))


if __name__ == '__main__':
    unittest.main()

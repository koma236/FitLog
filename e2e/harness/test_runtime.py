"""Runner lifecycle oracles: never stop someone else's resources or release early."""
import importlib.util
import copy
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("e2e_runtime", Path(__file__).parents[1] / "runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class Driver:
    def __init__(self, failure=None, safe=True):
        self.events = []
        self.failure = failure
        self.safe = safe

    def prepare(self):
        self.events.append("prepare")

    def exercise(self):
        self.events.append("exercise")
        if self.failure:
            raise self.failure

    def stop_owned(self):
        self.events.append("stop-owned")
        return self.safe


class LifecycleTests(unittest.TestCase):
    def test_network_fixture_busy_ports_do_not_hold_an_empty_lock_or_stop_other_resources(self):
        fixture_spec = importlib.util.spec_from_file_location("network_fixture", Path(__file__).with_name("network_browser.py"))
        fixture = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = fixture.runtime.shared.RuntimeLock(root, root, "test/fl-10a-e2e-54", "fixture")
            driver = fixture.FixtureDriver(lock, root / "output")
            with patch.object(driver, "containers", return_value=[]), patch.object(fixture.runtime, "port_open", return_value=True), patch.object(driver, "command", side_effect=AssertionError("No resource commands allowed")):
                session = fixture.runtime.RuntimeSession(lock, driver)
                self.assertFalse(session.run())
            self.assertTrue(session.report["lock_released"])
            self.assertFalse(driver.fixture_started)

    def session(self, directory, driver):
        root = Path(directory)
        lock = runtime.shared.RuntimeLock(root, root, "test/fl-10a-e2e-54", "fixture")
        return runtime.RuntimeSession(lock, driver), lock

    def test_lock_conflict_does_not_start_or_stop_any_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = Driver()
            session, lock = self.session(directory, driver)
            lock.path.mkdir()
            (lock.path / "owner.json").write_text('{"other":"owner"}')
            self.assertFalse(session.run())
            self.assertEqual(driver.events, [])
            self.assertTrue(lock.path.exists())

    def test_timeout_stops_owned_resources_before_releasing(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = Driver(TimeoutError("SECRET"))
            session, lock = self.session(directory, driver)
            self.assertFalse(session.run())
            self.assertEqual(driver.events, ["prepare", "exercise", "stop-owned"])
            self.assertFalse(lock.path.exists())
            self.assertNotIn("SECRET", str(session.report))

    def test_success_requires_confirmed_stop_and_lock_release(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = Driver()
            session, lock = self.session(directory, driver)
            self.assertTrue(session.run())
            self.assertEqual(driver.events, ["prepare", "exercise", "stop-owned"])
            self.assertFalse(lock.path.exists())
            self.assertTrue(session.report["lock_released"])

    def test_unconfirmed_stop_retains_lock_and_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            session, lock = self.session(directory, Driver(safe=False))
            self.assertFalse(session.run())
            self.assertTrue(lock.path.exists())
            self.assertFalse(session.report["lock_released"])

    def test_owner_change_prevents_cleanup_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = Driver()
            session, lock = self.session(directory, driver)
            def replace_owner():
                driver.events.append("exercise")
                (lock.path / "owner.json").write_text('{"other":"owner"}')
            driver.exercise = replace_owner
            self.assertFalse(session.run())
            self.assertEqual(driver.events, ["prepare", "exercise"])
            self.assertTrue(lock.path.exists())

    def test_cleanup_still_executes_when_result_disk_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = runtime.shared.RuntimeLock(root, root, "test/fl-10a-e2e-54", "fixture")
            lock.acquire()
            try:
                driver = runtime.LocalDriver(lock, root / "output")
                driver.cleaning = True
                def failed_save():
                    raise OSError("disk full SECRET")
                driver.save = failed_save
                marker = root / "stopped"
                driver.command("stop-fixture", [sys.executable, "-c", "from pathlib import Path; Path(__import__('sys').argv[1]).write_text('stopped')", str(marker)])
                self.assertEqual(marker.read_text(), "stopped")
                self.assertTrue(driver.persistence_failed)
                self.assertNotIn("SECRET", str(driver.report))
            finally:
                lock.release()

    def test_approved_run_limit_keeps_history_and_does_not_start_a_tenth_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / 'e2e/.artifacts'
            artifacts.mkdir(parents=True)
            journal = artifacts / 'attempts.json'
            history = '["one","two","three","four","five","six","seven","eight","nine"]'
            journal.write_text(history)
            lock = runtime.shared.RuntimeLock(root, root, "test/fl-10a-e2e-54", "tenth")
            driver = runtime.LocalDriver(lock, artifacts / 'tenth')
            with patch.object(runtime, 'ROOT', root), patch.object(driver, 'command', side_effect=AssertionError('Browser must not start')):
                with self.assertRaisesRegex(RuntimeError, 'SESSION_RUN_LIMIT'):
                    driver.exercise()
            self.assertEqual(journal.read_text(), history)

    def test_browser_exit_zero_still_requires_all_cases_and_owned_cleanup_evidence(self):
        base = {
            'run_id': 'fixture',
            'steps': [{'id': f'E{i:02}', 'status': 'pass', 'started': 'start', 'finished': 'end'} for i in range(1, 11)],
            'cleanup': [{'action': 'A-owned-ui-cleanup', 'status': 'pass'}, {'action': 'B-owned-ui-cleanup', 'status': 'pass'}],
            'resources': {'users': ['a7bc207c-c555-4f52-bd0e-f4118e463776', 'd8b63ea9-a940-4220-937f-86bd1f7431b9'], 'posts': [], 'comments': []},
        }
        runner = {'status': 'passed', 'worker_error': False, 'tests': [{'status': 'passed'}]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'BROWSER_RESULT_INVALID'):
                runtime.validate_browser_result(output, 'fixture')
            for scenario in ['partial', 'not-run', 'cleanup', 'stale', 'leftovers', 'duplicate-user', 'no-test', 'failed-test']:
                with self.subTest(scenario=scenario):
                    story, result = copy.deepcopy(base), copy.deepcopy(runner)
                    if scenario == 'partial': story['steps'].pop()
                    elif scenario == 'not-run': story['steps'][0]['status'] = 'not_run'
                    elif scenario == 'cleanup': story['cleanup'][0]['status'] = 'fail'
                    elif scenario == 'stale': story['run_id'] = 'different'
                    elif scenario == 'leftovers': story['resources']['posts'] = ['leftover']
                    elif scenario == 'duplicate-user': story['resources']['users'][1] = story['resources']['users'][0]
                    elif scenario == 'no-test': result['tests'] = []
                    elif scenario == 'failed-test': result['tests'][0]['status'] = 'failed'
                    (output / 'journey.json').write_text(json.dumps(story))
                    (output / 'runner.json').write_text(json.dumps(result))
                    with self.assertRaisesRegex(RuntimeError, 'BROWSER_RESULT_INVALID'):
                        runtime.validate_browser_result(output, 'fixture')
            (output / 'journey.json').write_text(json.dumps(base))
            (output / 'runner.json').write_text(json.dumps(runner))
            self.assertIsNone(runtime.validate_browser_result(output, 'fixture'))

    def test_readiness_deadline_also_applies_to_non_error_http_status(self):
        class Response:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Opener:
            calls = 0
            def open(self, *args, **kwargs):
                self.calls += 1
                if self.calls > 3:
                    raise AssertionError('Readiness loop exceeded its deadline')
                return Response()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = runtime.shared.RuntimeLock(root, root, 'test/fl-10a-e2e-54', 'fixture')
            driver = runtime.LocalDriver(lock, root / 'output')
            driver.containers = lambda: []
            driver.command = lambda *args, **kwargs: ''
            driver.migrations = lambda phase: None
            with patch.object(runtime, 'port_open', return_value=False), patch.object(runtime.urllib.request, 'build_opener', return_value=Opener()), patch.object(runtime.time, 'monotonic', side_effect=range(0, 1000, 30)), patch.object(runtime.time, 'sleep'):
                with self.assertRaises(TimeoutError):
                    driver.prepare()


if __name__ == "__main__":
    unittest.main()

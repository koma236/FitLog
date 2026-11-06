import contextlib
import json
import signal
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from perf import runner, runtime


class FakeProcess:
    def __init__(self, fail=None, unstoppable=False):
        self.pid = None
        self.exitcode = None
        self.alive = False
        self.fail = fail
        self.unstoppable = unstoppable
        self.stops = 0
        self.joins = 0

    def start(self):
        if self.fail:
            raise self.fail
        self.pid, self.alive = 123, True

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.stops += 1
        self.alive = self.unstoppable

    kill = terminate

    def join(self, timeout=None):
        self.joins += 1


class LifecycleTests(unittest.TestCase):
    def test_partial_start_failure_reaps_started_workers(self):
        for error in (OSError("no resources"), KeyboardInterrupt()):
            first, second, events = FakeProcess(), FakeProcess(error), Mock()
            context = SimpleNamespace(Queue=lambda events=events: events, Process=Mock(side_effect=[first, second]))
            with self.subTest(error=type(error).__name__), patch.object(runner.multiprocessing, "get_context", return_value=context):
                result = runner.bounded_jobs(None, [(), ()])
            self.assertGreater(first.stops, 0)
            self.assertGreater(first.joins, 0)
            self.assertTrue(result["workers_stopped"])
            self.assertTrue(result["errors"])
            events.close.assert_called_once()

    def test_unconfirmed_worker_stop_is_reported(self):
        first, second, events = FakeProcess(unstoppable=True), FakeProcess(OSError()), Mock()
        context = SimpleNamespace(Queue=lambda: events, Process=Mock(side_effect=[first, second]))
        with patch.object(runner.multiprocessing, "get_context", return_value=context):
            result = runner.bounded_jobs(None, [(), ()])
        self.assertFalse(result["workers_stopped"])

    def test_creation_intent_survives_lost_docker_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            run = runtime.Runtime(Path(directory) / "run")
            created = []
            def call(argv):
                if "ls" in argv:
                    return ""
                created.append(argv[-1])
                raise TimeoutError("daemon created; reply lost")
            run.call = call
            with self.assertRaises(TimeoutError):
                run.create("volume", "media", [])
            record = json.loads((run.folder / "ownership.json").read_text())
            self.assertEqual(record["resources"], [["volume", created[0]]])
            self.assertEqual(record["resource_states"][created[0]], "unknown")

    def test_cleanup_interrupt_retains_lock_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {"release": True, "owned": lambda: True}
            @contextlib.contextmanager
            def lock(task):
                yield state
            run = SimpleNamespace(folder=Path(directory), run_id="abc", resources=[("volume", "perf_abc_media")],
                                  started=time.monotonic(), stats=[], sampling_stop=Mock(),
                                  resource_states={}, prepare=Mock(side_effect=RuntimeError("preparation failed")))
            with patch.object(runtime, "runtime_lock", lock), patch.object(runtime, "Runtime", return_value=run), patch.object(runtime, "existing_resources", create=True, return_value=run.resources), patch.object(runtime, "owned_cleanup", side_effect=KeyboardInterrupt()), patch("sys.argv", ["runtime", "smoke"]):
                code = runtime.main()
            self.assertNotEqual(code, 0)
            self.assertFalse(state["release"])
            result = json.loads((run.folder / "results.json").read_text())
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["cleanup"], "KeyboardInterrupt")

    def test_unknown_creation_absence_cannot_claim_cleanup_success(self):
        with self.assertRaises(ValueError):
            runtime.existing_resources(lambda argv: "", "abc", [("volume", "perf_abc_media")], {"perf_abc_media": "unknown"})

    def test_unknown_creation_is_reconciled_and_only_owned_object_removed(self):
        names = {"perf_abc_media"}
        def call(argv):
            if "ls" in argv:
                return "\n".join(names)
            if "inspect" in argv:
                return json.dumps([{"Labels": {"fitlog.perf.run": "abc", "fitlog.perf.worktree": str(runtime.ROOT)}}])
            if "rm" in argv:
                names.remove(argv[-1])
                return ""
            raise AssertionError("unexpected mutation")
        present = runtime.existing_resources(call, "abc", [("volume", "perf_abc_media")], {"perf_abc_media": "unknown"})
        runtime.owned_cleanup(call, "abc", present)
        self.assertEqual(names, set())

    def test_cleanup_defers_actual_sigterm_and_restores_handler(self):
        previous = signal.getsignal(signal.SIGTERM)
        with runner.cleanup_signals() as deferred:
            signal.raise_signal(signal.SIGTERM)
        self.assertEqual(deferred, [signal.SIGTERM])
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_unconfirmed_workers_block_runtime_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {"release": True, "owned": lambda: True}
            @contextlib.contextmanager
            def lock(task):
                yield state
            run = SimpleNamespace(folder=Path(directory), run_id="abc", resources=[], resource_states={},
                                  started=time.monotonic(), stats=[], sampling_stop=Mock(), prepare=Mock(return_value={}))
            with patch.object(runtime, "runtime_lock", lock), patch.object(runtime, "Runtime", return_value=run), patch.object(runtime, "owned_cleanup") as cleanup, patch.object(runner, "run_load", return_value={"workers_stopped": False, "summary": {"status": "fail"}}), patch("sys.argv", ["runtime", "smoke"]):
                self.assertNotEqual(runtime.main(), 0)
            self.assertFalse(state["release"])
            cleanup.assert_not_called()

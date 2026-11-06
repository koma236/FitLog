"""Exercise the OS-spawn / Process-handle registration boundary in a subprocess."""
import json
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from perf.runner import bounded_jobs


def sleeper(events, actor):
    time.sleep(30)


def probe(kind):
    from multiprocessing.popen_spawn_posix import Popen

    original, children = Popen._launch, []

    def interrupt(number, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)

    def launch(popen, process):
        original(popen, process)
        children.append(popen)
        if len(children) == 2:
            if kind == "unknown":
                raise OSError("OS child exists but handle registration failed")
            signal.raise_signal(getattr(signal, kind))

    try:
        with patch.object(Popen, "_launch", launch):
            result = bounded_jobs(sleeper, [(0,), (1,)], total=2)
        print(json.dumps({"result": result, "exitcodes": [p.poll() for p in children]}), flush=True)
    finally:
        # The probe owns these children, including deliberately unregistered handles.
        for child in children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)


class SpawnBoundaryTests(unittest.TestCase):
    def invoke(self, kind):
        process = subprocess.run([sys.executable, "-B", "-m", "perf.test_spawn", kind],
                                 capture_output=True, text=True, timeout=20, check=True)
        return json.loads(process.stdout)

    def test_actual_signals_after_os_spawn_reap_all_children(self):
        for kind in ("SIGINT", "SIGTERM"):
            with self.subTest(signal=kind):
                observed = self.invoke(kind)
                self.assertEqual(len(observed["exitcodes"]), 2)
                self.assertNotIn(None, observed["exitcodes"], "live child at completion")
                self.assertTrue(observed["result"]["workers_stopped"])
                self.assertTrue(observed["result"]["errors"], "interrupted run cannot pass")

    def test_unknown_start_result_cannot_prove_all_children_stopped(self):
        observed = self.invoke("unknown")
        self.assertFalse(observed["result"]["workers_stopped"])
        self.assertIn("worker_cleanup_unconfirmed", observed["result"]["errors"])


if __name__ == "__main__":
    probe(sys.argv[1])

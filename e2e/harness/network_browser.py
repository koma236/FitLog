"""Run controlled redirect fixtures on the two fixed ports under the shared lock."""
import importlib.util
import json
import signal
import uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location("e2e_runtime", Path(__file__).parents[1] / "runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class FixtureDriver(runtime.LocalDriver):
    fixture_started = False

    def preflight(self):
        # Controlled fixture never consumes a product attempt.
        pass

    def prepare(self):
        records = self.containers()
        if any(row["Service"] != "postgres" and row["State"] not in {"exited", "dead", "created"} for row in records):
            raise RuntimeError("RUNTIME_BUSY")
        if any(runtime.port_open(port) for port in (15173, 18080)):
            raise RuntimeError("RUNTIME_BUSY")

    def exercise(self):
        self.fixture_started = True
        self.command("network-browser-fixture", ["node", "e2e/harness/network-browser.mjs"], 60,
                     {"FITLOG_GUARD_FIXTURE_RUN": self.lock.owner["run_id"]})
        result = json.loads((self.output / "fixture.json").read_text())
        if result.get("passed") is not True or result.get("forbidden_reads") != 0 or result.get("credential_reads") != 0:
            raise RuntimeError("FIXTURE_FAILED")

    def stop_owned(self):
        # LocalDriver.command reaps its complete child group, including Chromium.
        safe = self.safe and (not self.fixture_started or not any(runtime.port_open(port) for port in (15173, 18080)))
        self.report["cleanup"] = {"stop_confirmed": safe, "product_services_changed": False}
        return safe


def main():
    common, branch = runtime.shared.git_context(runtime.ROOT)
    if common.resolve() != runtime.EXPECTED_COMMON.resolve():
        raise RuntimeError("WORKTREE_MISMATCH")
    run = "network-fixture-" + uuid.uuid4().hex[:12]
    output = runtime.ROOT / "e2e/.artifacts" / run
    lock = runtime.shared.RuntimeLock(common, runtime.ROOT, branch, run)
    driver = FixtureDriver(lock, output)
    session = runtime.RuntimeSession(lock, driver)
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        passed = session.run()
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    driver.report["lifecycle"] = session.report
    driver.save()
    print(json.dumps({"run_id": run, "passed": passed, "lock_released": session.report["lock_released"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

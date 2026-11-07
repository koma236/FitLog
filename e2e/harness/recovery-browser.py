"""Read-only product components, controlled HTTP only; never starts product services."""
import importlib.util
import json
import hashlib
import signal
import uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location('network_fixture', Path(__file__).with_name('network_browser.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
runtime = fixture.runtime


class RecoveryDriver(fixture.FixtureDriver):
    def preflight(self):
        # Reuse the exact frontend lock in an ignored fixture-only dependency tree.
        for name in ('package.json', 'package-lock.json'):
            original = (runtime.ROOT / 'frontend' / name).read_bytes()
            installed = (runtime.ROOT / 'e2e/.artifacts/frontend-deps' / name).read_bytes()
            if original != installed:
                raise RuntimeError('FIXTURE_DEPENDENCIES_MISMATCH')
        self.report['frontend_lock_sha256'] = hashlib.sha256(original).hexdigest()

    def exercise(self):
        self.fixture_started = True
        self.command('recovery-browser-fixture', ['node', 'e2e/harness/recovery-browser.mjs'], 180,
                     {'FITLOG_RECOVERY_FIXTURE_RUN': self.lock.owner['run_id']})
        result = json.loads((self.output / 'fixture.json').read_text())
        if result.get('passed') is not True or result.get('product_requests') != 0 or result.get('users_created') != 0:
            raise RuntimeError('FIXTURE_FAILED')


def main():
    common, branch = runtime.shared.git_context(runtime.ROOT)
    if common.resolve() != runtime.EXPECTED_COMMON.resolve():
        raise RuntimeError('WORKTREE_MISMATCH')
    run = 'recovery-fixture-' + uuid.uuid4().hex[:12]
    lock = runtime.shared.RuntimeLock(common, runtime.ROOT, branch, run)
    driver = RecoveryDriver(lock, runtime.ROOT / 'e2e/.artifacts' / run)
    driver.report['source_before'] = runtime.snapshot()
    session = runtime.RuntimeSession(lock, driver)
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        passed = session.run()
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    driver.report.update(lifecycle=session.report, source_after=runtime.snapshot())
    if driver.report['source_before'] != driver.report['source_after']:
        passed = False
        driver.report['source_changed'] = True
    driver.save()
    print(json.dumps({'run_id': run, 'passed': passed, 'lock_released': session.report['lock_released']}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

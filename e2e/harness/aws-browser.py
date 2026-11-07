"""Controlled HTTPS/proxy fixtures only; no AWS, product or data writes."""
import importlib.util
import json
from pathlib import Path
import signal
import uuid

spec = importlib.util.spec_from_file_location('network_fixture', Path(__file__).with_name('network_browser.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
runtime = fixture.runtime
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from browser_ownership import stop_browsers


class AwsFixtureDriver(fixture.FixtureDriver):
    def stop_owned(self):
        stopped = stop_browsers(self.output, self.lock.owner['run_id'], required=self.fixture_started)
        return super().stop_owned() and stopped

    def exercise(self):
        self.fixture_started = True
        self.output.chmod(0o700)
        config = self.output / 'openssl.cnf'
        config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n'
                          '[dn]\nCN=dexample.cloudfront.net\n[ext]\nsubjectAltName=DNS:dexample.cloudfront.net\n'
                          'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,digitalSignature,keyEncipherment\n')
        config.chmod(0o600)
        self.command('fixture-cert', ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                     '-config', str(config), '-keyout', str(self.output / 'key.pem'), '-out', str(self.output / 'cert.pem')])
        (self.output / 'key.pem').chmod(0o600)
        (self.output / 'cert.pem').chmod(0o600)
        self.command('aws-guard-fixture', ['node', 'e2e/harness/aws-browser.mjs'], 90,
                     {'FITLOG_GUARD_FIXTURE_RUN': self.lock.owner['run_id'],
                      'NODE_EXTRA_CA_CERTS': str(self.output / 'cert.pem')})
        result = json.loads((self.output / 'fixture.json').read_text())
        if result.get('passed') is not True or result.get('forbidden_reads') != 0:
            raise RuntimeError('FIXTURE_FAILED')
        expected_exit = False
        try:
            self.command('orphan-browser-fixture', ['node', 'e2e/harness/browser-orphan.mjs'], 15,
                         {'FITLOG_GUARD_FIXTURE_RUN': self.lock.owner['run_id']})
        except RuntimeError:
            expected_exit = self.report['operations'][-1]['exit_code'] == -9
        if not expected_exit or not stop_browsers(self.output, self.lock.owner['run_id'], required=True):
            raise RuntimeError('ORPHAN_BROWSER_STOP_UNCONFIRMED')
        self.report['orphan_browser_stop'] = 'pass'


def main():
    common, branch = runtime.shared.git_context(runtime.ROOT)
    if common.resolve() != runtime.EXPECTED_COMMON.resolve(): raise RuntimeError('WORKTREE_MISMATCH')
    run = 'aws-fixture-' + uuid.uuid4().hex[:12]
    lock = runtime.shared.RuntimeLock(common, runtime.ROOT, branch, run)
    driver = AwsFixtureDriver(lock, runtime.ROOT / 'e2e/.artifacts' / run)
    def interrupted(_signum, _frame): raise KeyboardInterrupt()
    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try: passed = runtime.RuntimeSession(lock, driver).run()
    finally:
        for sig, handler in handlers.items(): signal.signal(sig, handler)
    driver.save()
    print(json.dumps({'run_id': run, 'passed': passed, 'product_requests': 0, 'aws': 'not_run'}))
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())

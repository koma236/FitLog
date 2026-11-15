"""Recording-free single-environment journey. Offline unless --execute-aws is explicit."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'e2e'))
import aws_contract as base
from scripts.day70 import contract

spec = importlib.util.spec_from_file_location('fitlog_day70_aws_runtime', ROOT / 'e2e/aws-runtime.py')
aws_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aws_runtime)
local = aws_runtime.local


class Day70Driver(aws_runtime.AwsDriver):
    """Reuse guarded browser/process ownership, without the old capture contract."""

    def __init__(self, lock, output, data):
        local.LocalDriver.__init__(self, lock, output, capture=False)
        self.data = data
        self.deadline = time.monotonic() + (base.timestamp(data['expires_at']) - datetime.now(timezone.utc)).total_seconds() - 30
        self.browser_attempted = False
        self.initial_boundary = base.boundary_status(data)
        self.report.update(environment='aws', mode='day70', acceptance='not_run',
                           lease_returned=False, capture='not_run', performance='not_run', rebuild='not_run')

    def preflight(self):
        contract.validate(self.data)

    def prepare(self):
        contract.validate(self.data)
        handoff = base.validate_handoff(self.data)
        base.exclusive_json(self.output / 'runtime-input.json', {
            'mode': 'aws', 'test_run': self.data['test_run'], 'origin': self.data['origin'],
            'contract': self.data,
            'storage_evidence_ready': handoff['probes']['permissions'] == 'pass',
            'final_evidence_ready': base.final_ready(self.data),
        })

    def exercise(self):
        self.browser_attempted = True
        self.command('day70-browser', ['node', 'e2e/node_modules/@playwright/test/cli.js', 'test',
                     '--config=e2e/aws.playwright.config.ts'], 1200, env={
                         'FITLOG_E2E_RUN_ID': self.data['test_run'], 'FITLOG_E2E_CAPTURE': '0',
                         'FITLOG_AWS_INPUT': str(self.output / 'runtime-input.json'),
                         'FITLOG_AWS_OUTPUT': str(self.output),
                     })
        local.validate_browser_result(self.output, self.data['test_run'])
        rows = base.load(self.output / 'aws-results.json')
        story = base.load(self.output / 'journey.json')
        storage = base.load(self.output / 'storage-evidence.json')
        forbidden = ('*.webm', '*.har', 'trace.zip', '*.png', '*.jpg', '*.jpeg',
                     'capture-safe.json', 'performance.json', 'performance-requests.json')
        if (any(rows.get(key, {}).get('status') != 'pass' for key in ('C01', 'C02'))
                or rows.get('C03', {}).get('status') not in ('pass', 'not_run')
                or storage.get('public_http_health') != 'pass'
                or any(rows.get(key, {}).get('status') != 'not_run' for key in ('C05', 'C06', 'C07'))
                or story.get('capture_status') != 'not_run'
                or (self.output / 'videos-quarantine').exists()
                or any(any(self.output.rglob(pattern)) for pattern in forbidden)):
            raise RuntimeError('DAY70_OBSERVATIONS_INVALID')
        self.report.update(observed_browser_cases='pass', capture='not_run', performance='not_run', rebuild='not_run')


def execute(data, ledger):
    """Stop clients and recheck evidence before releasing the shared runtime lease."""
    common, branch = local.shared.git_context(ROOT)
    base.require(common.resolve() == local.EXPECTED_COMMON.resolve())
    before = local.snapshot()
    base.require(not before['dirty_paths'] and before['commit'] == data['source'])
    ledger = base.protected(ledger, True)
    base.require(not ledger.is_relative_to(ROOT))
    lock = local.shared.RuntimeLock(common, ROOT, branch, data['test_run'])
    lock.owner['resources'] = ['day70 AWS clients; no recording or lifecycle', data['lease_id']]
    lock.acquire()
    driver = None
    passed = False
    try:
        contract.validate(data)
        contract.claim(ledger, data)
        driver = Day70Driver(lock, ledger / ('run-' + data['test_run']), data)
        driver.report['source_before'] = before
        driver.preflight()
        driver.prepare()
        driver.exercise()
        passed = True
    except (Exception, KeyboardInterrupt):
        if driver:
            driver.report['error'] = 'DAY70_RUN_FAILED'
    finally:
        handlers = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            try:
                stopped = driver is None or driver.stop_owned()
            except (Exception, KeyboardInterrupt):
                stopped = False
            owned = lock.owned()
            after = local.snapshot()
            source_unchanged = after == before
            evidence_unchanged = True
            passed = passed and stopped and owned and source_unchanged
            if driver:
                driver.report.update(source_after=after, status='fail', client_stop_confirmed=bool(stopped),
                                     lease_returned=False, lock_released=False, ended_at=local.shared.now())
                if not stopped:
                    driver.report['error'] = 'STOP_UNCONFIRMED'
                elif not owned:
                    driver.report['error'] = 'OWNER_CHANGED'
                elif after != before:
                    driver.report['error'] = 'SOURCE_CHANGED'
                try:
                    # Also reopens the original B handoff; missing/changed evidence fails closed.
                    base.validate_handoff(data)
                    driver.verify_boundary()
                except Exception:
                    passed = False
                    evidence_unchanged = False
                    driver.report.update(error='DAY70_EVIDENCE_INVALID', final_evidence_ready=False)
                driver.save()
            released = False
            if stopped and owned and source_unchanged and evidence_unchanged:
                try:
                    lock.release()
                    released = True
                except Exception:
                    passed = False
            passed = passed and released
            if driver:
                driver.report.update(status='pass' if passed else 'fail',
                                     lease_returned=bool(stopped and released), lock_released=released)
                driver.save()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--initialize-ledger', action='store_true')
    parser.add_argument('--execute-aws', action='store_true')
    args = parser.parse_args(argv)
    try:
        data = contract.validate(base.load(args.contract))
        if args.initialize_ledger:
            base.require(args.ledger is not None and not args.execute_aws)
            contract.initialize(args.ledger, data)
            result = 0
        elif args.execute_aws:
            base.require(args.ledger is not None and not any(os.environ.get(key)
                         for key in ('DEBUG', 'PWDEBUG', 'NODE_DEBUG', 'NODE_OPTIONS')))
            os.umask(0o077)

            def interrupted(_signum, _frame):
                raise KeyboardInterrupt()

            handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
            try:
                result = execute(data, args.ledger)
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
        else:
            result = 0
        print(json.dumps({'mode': 'day70', 'status': 'pass' if result == 0 else 'fail',
                          'aws': 'executed' if args.execute_aws else 'not_run',
                          'capture': 'not_run', 'performance': 'not_run', 'acceptance': 'not_run'}))
        return result
    except (Exception, KeyboardInterrupt):
        print('{"status":"fail","code":"DAY70_RUN_REFUSED"}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

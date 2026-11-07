"""C runner: offline by default; explicit separately approved AWS execution only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aws_contract import Invalid, boundary_status, claim, exclusive_json, final_ready, init_campaign, load, protected, sha256, validate, validate_handoff

spec = importlib.util.spec_from_file_location('fitlog_local_runtime', Path(__file__).with_name('runtime.py'))
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)
sys.path.insert(0, str(local.ROOT))
from perf.runner import cleanup_signals
from browser_ownership import stop_browsers


class AwsDriver(local.LocalDriver):
    def __init__(self, lock, output, data):
        super().__init__(lock, output, capture=True)
        self.data = data
        self.deadline = time.monotonic() + (datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds() - 30
        self.browser_attempted = False
        self.initial_boundary = boundary_status(data)
        self.report.update(environment='aws', lease_returned=False, final_evidence_ready=final_ready(data),
                           manual_playback='not_run', after_destroy_playback='not_run')

    def preflight(self):
        validate(self.data)

    def verify_boundary(self):
        """Re-read originals after clients stop; consumed evidence cannot disappear."""
        self.report.update(c04='fail', final_evidence_ready=False, boundary_reason='BOUNDARY_EVIDENCE_INVALID')
        current = boundary_status(self.data)
        self.report['boundary'] = current
        if current['fingerprint'] != self.initial_boundary['fingerprint'] or current['status'] == 'fail':
            raise RuntimeError('BOUNDARY_EVIDENCE_CHANGED')
        ready = final_ready(self.data)
        self.report.update(c04=current['status'], final_evidence_ready=ready,
                           boundary_reason='BOUNDARY_OBSERVED' if current['status'] == 'pass' else 'BOUNDARY_EVIDENCE_INCOMPLETE')

    def command(self, name, argv, timeout=90, env=None):
        """Reuse group-stop primitives with spawn registration protected from signals."""
        if not self.lock.owned(): raise RuntimeError('OWNER_CHANGED')
        remaining = min(self.deadline - time.monotonic(),
                        (datetime.fromisoformat(self.data['expires_at'].replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds() - 30)
        if remaining <= 0: raise RuntimeError('AWS_DEADLINE')
        timeout = min(timeout, remaining)
        entry = {'id': name, 'started_at': local.shared.now(), 'exit_code': None}
        self.report['operations'].append(entry)
        self.persist()
        child = None
        previous = self.safe
        self.safe = False
        try:
            child_env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'PLAYWRIGHT_BROWSERS_PATH')}
            child_env.update(env or {})
            with cleanup_signals() as deferred:
                child = subprocess.Popen(argv, cwd=local.ROOT, env=child_env, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, start_new_session=True)
            if deferred: raise KeyboardInterrupt()
            operation_end = time.monotonic() + timeout
            while True:
                left = min(operation_end - time.monotonic(), self.deadline - time.monotonic(),
                           (datetime.fromisoformat(self.data['expires_at'].replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds() - 30)
                if left <= 0: raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    stdout, _ = child.communicate(timeout=min(.2, left))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if local.shared.group_exists(child.pid):
                local.shared.stop_group(child)
                raise ChildProcessError('DESCENDANT_REMAINED')
            self.safe = previous
            entry['exit_code'] = child.returncode
            if child.returncode: raise RuntimeError('COMMAND_FAILED')
            return stdout.decode(errors='replace')
        except BaseException:
            if child is not None:
                local.shared.stop_group(child)
                self.safe = previous
            # A Popen failure without a registered child remains uncertain.
            raise
        finally:
            entry['ended_at'] = local.shared.now()
            self.persist()

    def prepare(self):
        validate(self.data)
        exclusive_json(self.output / 'runtime-input.json', {'mode': 'aws', 'test_run': self.data['test_run'],
                       'origin': self.data['origin'], 'contract': self.data,
                       'storage_evidence_ready': validate_handoff(self.data)['probes']['permissions'] == 'pass',
                       'final_evidence_ready': final_ready(self.data)})

    def exercise(self):
        self.browser_attempted = True
        self.command('aws-browser', ['node', 'e2e/node_modules/@playwright/test/cli.js', 'test', '--config=e2e/aws.playwright.config.ts'],
                     1200, {'FITLOG_E2E_RUN_ID': self.data['test_run'], 'FITLOG_E2E_CAPTURE': '1',
                            'FITLOG_AWS_INPUT': str(self.output / 'runtime-input.json'), 'FITLOG_AWS_OUTPUT': str(self.output)})
        local.validate_browser_result(self.output, self.data['test_run'])
        result = load(self.output / 'aws-results.json')
        if any(result.get(key, {}).get('status') != 'pass' for key in ('C01', 'C02', 'C05', 'C06')):
            raise RuntimeError('AWS_RESULTS_INCOMPLETE')
        if (result.get('C03', {}).get('status') not in ('pass', 'not_run')
                or load(self.output / 'storage-evidence.json').get('public_http_health') != 'pass'):
            raise RuntimeError('AWS_STORAGE_OBSERVATION_INCOMPLETE')
        capture = load(self.output / 'capture-safe.json')
        if capture.get('status') != 'aws_capture_pending_playback':
            raise RuntimeError('AWS_CAPTURE_INCOMPLETE')
        videos = list((self.output / 'videos-quarantine').glob('*.webm'))
        if len(videos) != 2:
            raise RuntimeError('CAPTURE_COUNT_MISMATCH')
        self.report['videos'] = []
        for i, video in enumerate(videos):
            video.chmod(0o600)
            self.command('decode-' + str(i), ['ffmpeg', '-v', 'error', '-i', str(video), '-f', 'null', '-'], 60)
            self.report['videos'].append({'name': video.name, 'sha256': sha256(video), 'decode': 'pass', 'visual': 'not_run'})
        self.report['observed_browser_cases'] = 'pass'

    def stop_owned(self):
        # command() verifies process-group death before returning, on every exit.
        # No Compose/DB/remote AWS lifecycle operation is reachable here.
        browsers_stopped = stop_browsers(self.output, self.lock.owner['run_id'], required=self.browser_attempted)
        safe = self.safe and browsers_stopped
        self.report['client_stop_confirmed'] = safe
        self.report['lease_returned'] = safe
        return safe


def execute(data, campaign):
    common, branch = local.shared.git_context(local.ROOT)
    if common.resolve() != local.EXPECTED_COMMON.resolve():
        raise Invalid()
    snapshot = local.snapshot()
    if snapshot['dirty_paths'] or snapshot['commit'] != data['source']:
        raise Invalid()
    campaign = protected(campaign, True)
    if campaign.is_relative_to(local.ROOT):
        raise Invalid()
    output = campaign / ('run-' + data['test_run'])
    lock = local.shared.RuntimeLock(common, local.ROOT, branch, data['test_run'])
    lock.owner['resources'] = ['AWS test clients (no Compose/DB lifecycle)', data['lease_id']]
    lock.acquire()
    driver = None
    passed = False
    try:
        # Irreversible accounting precedes every child/client, never refunded.
        validate(data)
        claim(campaign, data)
        driver = AwsDriver(lock, output, data)
        driver.report['source_before'] = snapshot
        driver.preflight(); driver.prepare(); driver.exercise()
        passed = True
    except (Exception, KeyboardInterrupt):
        if driver:
            driver.report['error'] = 'AWS_RUN_FAILED'
    finally:
        handlers = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
        released = False
        try:
            try:
                stopped = driver is None or driver.stop_owned()
            except (Exception, KeyboardInterrupt):
                stopped = False
            # Capture once: a later successful read must not erase an observed
            # ownership failure. release() still performs its own final check.
            owned = lock.owned()
            if driver:
                after = local.snapshot()
                passed = passed and stopped and after == snapshot and owned
                if not stopped:
                    driver.report['error'] = 'STOP_UNCONFIRMED'
                elif not owned:
                    driver.report['error'] = 'OWNER_CHANGED'
                elif after != snapshot:
                    driver.report['error'] = 'SOURCE_CHANGED'
                # Persist a conservative outcome before attempting lock return.
                # A failed save/release must never leave a success record behind.
                driver.report.update(source_after=after, status='fail',
                                     client_stop_confirmed=bool(stopped), lease_returned=False,
                                     lock_released=False,
                                     acceptance='not_run', ended_at=local.shared.now())
                try:
                    driver.verify_boundary()
                except Exception:
                    passed = False
                    driver.report.update(c04='fail', final_evidence_ready=False,
                                         boundary_reason='BOUNDARY_EVIDENCE_INVALID', error='BOUNDARY_EVIDENCE_INVALID')
                driver.save()
            if stopped and owned:
                lock.release()
                released = True
            passed = passed and released
            if driver:
                driver.report.update(status='pass' if passed else 'fail',
                                     lease_returned=bool(stopped and released), lock_released=released)
                driver.save()
        finally:
            for sig, handler in handlers.items(): signal.signal(sig, handler)
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--campaign', type=Path)
    parser.add_argument('--execute-aws', action='store_true')
    parser.add_argument('--init-campaign', nargs=2, metavar=('INITIAL', 'REBUILD'))
    args = parser.parse_args(argv)
    try:
        data = validate(load(args.contract))
        if args.init_campaign:
            if args.execute_aws or not args.campaign: raise Invalid()
            init_campaign(args.campaign, *args.init_campaign, campaign_id=data['campaign_id'])
            result = 0
        elif args.execute_aws:
            if not args.campaign or any(os.environ.get(k) for k in ('DEBUG', 'PWDEBUG', 'NODE_DEBUG', 'NODE_OPTIONS')): raise Invalid()
            os.umask(0o077)
            def interrupted(_signum, _frame): raise KeyboardInterrupt()
            handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
            try: result = execute(data, args.campaign)
            finally:
                for sig, handler in handlers.items(): signal.signal(sig, handler)
        else:
            result = 0
        print(json.dumps({'contract': 'pass', 'aws': 'executed' if args.execute_aws else 'not_run',
                          'status': 'pass' if result == 0 else 'fail',
                          'boundary': boundary_status(data), 'final_evidence_ready': final_ready(data)}))
        return result
    except (Exception, KeyboardInterrupt):
        print('{"status":"fail","code":"AWS_RUN_REFUSED"}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

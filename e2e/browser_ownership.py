"""Stop only CDP-identified Chromium groups bound to this test run and birth."""
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from aws_contract import exclusive_json, load


def group_exists(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False


def process_identity(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'pgid='],
                            capture_output=True, text=True, timeout=2, env={**os.environ, 'LC_ALL': 'C', 'TZ': 'UTC'})
    match = re.fullmatch(r'(.+?)\s+(\d+)', result.stdout.strip())
    if result.returncode or not match:
        raise RuntimeError('BROWSER_IDENTITY_UNKNOWN')
    return match[1].strip(), int(match[2])


def stop_browsers(folder, run, *, required=False, exists=group_exists, identity=process_identity, kill=os.killpg):
    records = list(Path(folder).glob('browser-worker-*.json'))
    safe = (bool(records) if required else True) and len(records) <= 4
    for path in records[:4]:
        try:
            row = load(path)
            if (row['schema_version'] != 1 or row['run_id'] != run or row['phase'] != 'launched'
                    or type(row['pid']) is not int or row['pid'] <= 1 or row['pgid'] != row['pid']
                    or not isinstance(row['birth'], str) or not row['birth']):
                raise RuntimeError('BROWSER_IDENTITY_UNKNOWN')
            group = row['pgid']
            if not exists(group): continue
            if identity(row['pid']) != (row['birth'], group):
                raise RuntimeError('BROWSER_IDENTITY_CHANGED')
            # Node's graceful close has already had its opportunity. Cancel a
            # remaining owned network client now, inside the stop reserve.
            kill(group, signal.SIGKILL)
            end = time.monotonic() + 2
            while exists(group) and time.monotonic() < end: time.sleep(.05)
            if exists(group): raise RuntimeError('BROWSER_STOP_UNCONFIRMED')
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
            safe = False
    return safe

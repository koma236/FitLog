"""Run with the shared runtime lease; no AWS, public port, or shared database."""
import subprocess
from pathlib import Path
from unittest.mock import patch

from tests import production_tls_smoke as tls
from tests.production_smoke import docker as original

IMAGE = 'fitlog-fl09b7-production-52'


def main() -> None:
    source = Path(__file__).with_name('bootstrap_probe.py').read_text()
    sentinel = "    print('Bootstrap:"
    assert source.count(sentinel) == 1
    source = source.replace(sentinel, '    probe(values)\n' + sentinel)

    def docker(*args: str, source: str | None = None) -> str:
        if source is None:
            return original(*args)
        combined = source + '\n' + probe_source
        safe = ('import sys, traceback\ntry:\n exec(compile(' + repr(combined)
                + ', "deployment_fixture", "exec"))\nexcept BaseException as error:\n'
                ' print(type(error).__name__, file=sys.stderr)\n'
                ' for frame in traceback.extract_tb(error.__traceback__):\n'
                '  print(frame.filename, frame.lineno, frame.name, file=sys.stderr)\n'
                ' sys.exit(1)\n')
        result = subprocess.run(['docker', *args], input=safe,
                                capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, 'Owned deployment TLS fixture failed: ' + result.stderr
        return result.stdout

    # Production intentionally excludes tests; transmit this public fixture over
    # stdin, just like the existing bootstrap probe, instead of importing tests.
    probe_source = Path(__file__).with_name('deployment_probe.py').read_text() + '\n' + source
    with patch.object(tls, 'IMAGE', IMAGE), patch.object(tls, 'docker', docker):
        tls.main()


if __name__ == '__main__':
    main()

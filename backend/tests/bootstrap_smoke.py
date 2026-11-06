"""Reuse the isolated TLS fixture; append the non-superuser provisioning oracle.

Run under the shared runtime lease after building fitlog-fl09b6-production-48.
No AWS access, shared DB writes, published ports, or persistent volumes.
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

from tests import production_tls_smoke as tls
from tests.production_smoke import docker as original

IMAGE = 'fitlog-fl09b6-production-48'


def main() -> None:
    flow = Path(__file__).with_name('bootstrap_flow_probe.py').read_text()
    probe = Path(__file__).with_name('bootstrap_probe.py').read_text()

    setting = ''

    def docker(*args: str, source: str | None = None) -> str:
        if source is not None:
            source += '\nimport os\nos.environ["BOOTSTRAP_SELF_GRANT"] = ' + repr(setting) + '\n' + flow + '\n' + probe
            result = subprocess.run(['docker', *args], input=source, text=True,
                                    capture_output=True, timeout=180)
            if result.returncode:
                raise RuntimeError('Bootstrap fixture failed: ' + result.stderr)
            return result.stdout
        return original(*args, source=source)

    with patch.object(tls, "IMAGE", IMAGE), patch.object(tls, "docker", docker):
        for setting in ("", "inherit,set"):
            print("createrole_self_grant fixture:", repr(setting), flush=True)
            tls.main()


if __name__ == '__main__':
    main()

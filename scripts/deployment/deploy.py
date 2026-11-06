"""Repository entry point; uses the locked backend Python environment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from operations.deployment_cli import main

if __name__ == '__main__':
    raise SystemExit(main())

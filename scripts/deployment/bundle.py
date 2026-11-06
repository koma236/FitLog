"""Generate an offline static manifest before filling frontend_sha256."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from operations.deployment_assets import bundle
from operations.deployment_cli import save_private

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    save_private(args.output, bundle(args.root))

"""Validate a protected build record offline; never builds, pushes or contacts AWS."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from operations.deployment_artifacts import (
    check_source,
    publish_private,
    read_private,
    validate_artifacts,
)
from operations.deployment_contract import Manifest, require
from operations.deployment_step import Parser


def main(argv=None):
    parser = Parser(allow_abbrev=False)
    for flag in ('manifest', 'record', 'assets', 'source', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        manifest = Manifest.parse(read_private(args.manifest))
        record = validate_artifacts(read_private(args.record), manifest)
        require(check_source(args.source, manifest.data['source_revision']) == record['source_tree'])
        assets = read_private(args.assets)
        from operations.deployment_assets import validate_inventory
        validate_inventory(assets, manifest.data['frontend_sha256'])
        publish_private(args.output, record)
    except (Exception, SystemExit):
        print('{"event":"deployment_failed"}', file=sys.stderr)
        return 2
    print('{"event":"deployment_artifacts_validated"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

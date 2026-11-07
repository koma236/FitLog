"""Build a private, non-secret C handoff offline; no AWS or browser connections."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from operations.deployment_artifacts import publish_private, read_private
from operations.deployment_contract import Manifest
from operations.deployment_handoff import handoff
from operations.deployment_step import Parser


def main(argv=None):
    parser = Parser(allow_abbrev=False)
    for flag in ('manifest', 'artifacts', 'evidence', 'window', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        result = handoff(Manifest.parse(read_private(args.manifest)), read_private(args.artifacts),
                         args.evidence, read_private(args.window))
        result['manifest'] = {'path': str(args.manifest), 'sha256': result['manifest_sha256']}
        result['artifacts'] = {'path': str(args.artifacts), 'sha256': result['artifact_sha256']}
        publish_private(args.output, result)
    except (Exception, SystemExit):
        print('{"event":"deployment_failed"}', file=sys.stderr)
        return 2
    print('{"event":"deployment_handoff_created"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

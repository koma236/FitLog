"""Check an initial ECR-only saved plan without displaying its secret content."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def check(data):
    changes = [entry for entry in data.get('resource_changes', [])
               if entry['change']['actions'] != ['no-op']]
    return len(changes) == 1 and changes[0]['address'] == 'aws_ecr_repository.backend' \
        and changes[0]['change']['actions'] == ['create']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = subprocess.run(['terraform', '-chdir=terraform', 'show', '-json', str(args.plan.resolve())],
                                capture_output=True, timeout=60, check=True)
        passed = check(json.loads(result.stdout))
    except Exception:
        passed = False
    print('ecr_plan_verified' if passed else 'ecr_plan_rejected')
    sys.exit(0 if passed else 2)

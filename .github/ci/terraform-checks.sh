#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$root"
task_home="$(mktemp -d)"
trap 'rm -rf -- "$task_home"' EXIT
# Start a clean shell too: no BASH_ENV, exported functions, AWS or TF overrides.
env -i PATH="$PATH" HOME="$task_home" CHECKPOINT_DISABLE=1 \
  TF_CLI_CONFIG_FILE=/dev/null TF_IN_AUTOMATION=1 \
  AWS_EC2_METADATA_DISABLED=true AWS_SHARED_CREDENTIALS_FILE=/dev/null \
  AWS_CONFIG_FILE=/dev/null bash --noprofile --norc <<'CHECKS'
set -euo pipefail
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform init -backend=false -input=false -lockfile=readonly
terraform -chdir=terraform validate
python3 -B -m unittest discover -s terraform/tests -p 'test_*.py'
terraform -chdir=terraform test -no-color
node --test terraform/functions/client-ip.test.cjs
CHECKS

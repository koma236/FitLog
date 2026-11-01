#!/usr/bin/env bash
set -euo pipefail
script="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/required-status.sh"
check() {
  local expected="$1" actual
  shift
  if bash "$script" "$@" >/dev/null 2>&1; then actual=0; else actual=$?; fi
  if [[ "$actual" != "$expected" ]]; then
    printf 'Expected exit %s, got %s for %s\n' "$expected" "$actual" "$*" >&2
    exit 1
  fi
}
# The oracle is a fixed table: only success/success may authorize merging.
while read -r backend frontend expected; do
  check "$expected" "$backend" "$frontend"
done <<'CASES'
success success 0
success failure 1
success cancelled 1
success skipped 1
failure success 1
failure failure 1
failure cancelled 1
failure skipped 1
cancelled success 1
cancelled failure 1
cancelled cancelled 1
cancelled skipped 1
skipped success 1
skipped failure 1
skipped cancelled 1
skipped skipped 1
CASES
check 2
check 2 success
check 2 success success success
check 2 '' success
check 2 success unknown
check 2 'success; exit 0' success
printf 'required-status: 16 states and 6 invalid-input cases passed\n'

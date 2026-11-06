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
# Oracle: the single accepted row is fixed; enumerate all 4^3 result states.
for backend in success failure cancelled skipped; do
  for frontend in success failure cancelled skipped; do
    for terraform in success failure cancelled skipped; do
      expected=1
      if [[ "$backend/$frontend/$terraform" == success/success/success ]]; then expected=0; fi
      check "$expected" "$backend" "$frontend" "$terraform"
    done
  done
done
check 2
check 2 success
check 2 success success
check 2 success success success success
check 2 '' success success
check 2 success unknown success
check 2 success success unknown
check 2 'success; exit 0' success success
printf 'required-status: 64 states and 8 invalid-input cases passed\n'

#!/usr/bin/env bash
set -euo pipefail
if [[ "$#" -ne 2 ]]; then
  printf 'Expected backend and frontend job results\n' >&2
  exit 2
fi
for result in "$@"; do
  case "$result" in
    success|failure|cancelled|skipped) ;;
    *) printf 'Invalid job result\n' >&2; exit 2 ;;
  esac
done
if [[ "$1" == success && "$2" == success ]]; then
  printf 'All required checks passed\n'
else
  printf 'Required checks did not succeed: backend=%s frontend=%s\n' "$1" "$2" >&2
  exit 1
fi

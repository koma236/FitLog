"""Reuse nearest-rank/failure accounting for the 180-slot AWS limited probe."""
import json
import sys
from perf.report import summarize


def report(rows):
    return summarize(rows, 180, required={'all GET', 'following GET', 'detail GET'}, minimum=60)


if __name__ == '__main__':
    try:
        value = json.load(sys.stdin)
        result = report(value)
        print(json.dumps(result))
        sys.exit(0 if result['status'] == 'pass' else 1)
    except (ValueError, KeyError, TypeError):
        print('{"status":"fail"}')
        sys.exit(1)

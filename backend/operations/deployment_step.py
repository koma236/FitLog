"""Fixed remote deployment steps; never expose Django/SDK output or exceptions."""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Never

from operations.deployment_contract import DeploymentError, matches, require


@dataclass(frozen=True)
class StepContext:
    run_id: str
    expected_host: str
    environment: str


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise DeploymentError()


def database_guard(context: StepContext) -> None:
    """Check the actual DB identity and transport without broadening Web AWS IAM."""
    from django.conf import settings
    from django.db import connection

    require(settings.FITLOG_ENV == 'production'
            and os.environ.get('DJANGO_SETTINGS_MODULE') == 'config.production')
    require(connection.settings_dict['HOST'] == context.expected_host
            and connection.settings_dict['NAME'] == 'fitlog'
            and connection.settings_dict['USER'] == 'fitlog_app')
    with connection.cursor() as cursor:
        cursor.execute('SELECT session_user, current_database(), ssl FROM pg_stat_ssl '
                       'WHERE pid = pg_backend_pid()')
        require(cursor.fetchone() == ('fitlog_app', 'fitlog', True))


def run_step(step: str, context: StepContext) -> None:
    """No arbitrary commands, import paths, SQL, or shell evaluation."""
    import django
    from django.core.management import call_command

    django.setup()
    database_guard(context)
    if step == 'migrate':
        call_command('migrate', interactive=False, verbosity=0)
    elif step == 'check':
        call_command('migrate', check_unapplied=True, interactive=False, verbosity=0)
    elif step == 'seed':
        from operations.demo_seed import seed
        seed()
    else:
        from operations.deployment_verify import verify_from_environment
        verify_from_environment(context)


def main(
    argv: list[str] | None = None,
    runner: Callable[[str, StepContext], None] = run_step,
) -> int:
    parser = Parser(allow_abbrev=False)
    for name in ('step', 'run-id', 'expected-host', 'environment'):
        parser.add_argument('--' + name, required=True)
    try:
        args = parser.parse_args(argv)
        require(args.step in ('migrate', 'seed', 'check', 'verify'))
        require(str(uuid.UUID(args.run_id)) == args.run_id)
        require(matches(r'[a-z0-9.-]+\.ap-northeast-1\.rds\.amazonaws\.com', args.expected_host))
        require(matches(r'fitlog-demo-[a-z0-9]+(?:-[a-z0-9]+)*', args.environment)
                and len(args.environment) <= 24)
        context = StepContext(args.run_id, args.expected_host, args.environment)
        # A dedicated process, like B6. Restore logging for in-process unit tests.
        disabled = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), \
                    contextlib.redirect_stderr(sink):
                runner(args.step, context)
        finally:
            logging.disable(disabled)
    except (Exception, SystemExit):
        print('{"event":"deployment_step_failed"}', file=sys.stderr)
        return 2
    print(json.dumps({'event': 'deployment_step_completed', 'step': args.step,
                      'run_id': context.run_id}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

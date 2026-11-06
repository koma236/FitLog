"""Explicit, initial-only operator command. Defaults to metadata inspection."""
import argparse
import json
import logging
import os
import sys
from typing import Never

import psycopg

from operations.aws import Aws, SecretStore
from operations.contract import BootstrapError, Request, require
from operations.database import Database, connection_options, verify_login


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse's usual message echoes unrecognized secret-looking arguments.
        raise BootstrapError()


def run(request: Request, initialize: bool, aws: Aws) -> str:
    target = aws.inspect(request)
    if not initialize:
        return "bootstrap_inspected"
    secret = aws.secrets.get_secret_value(SecretId=target.administrator_secret,
                                         VersionStage="AWSCURRENT")
    require(secret["ARN"] == target.administrator_secret)
    data: object = json.loads(secret["SecretString"])
    require(isinstance(data, dict))
    if not isinstance(data, dict):
        raise BootstrapError()
    password = data.get("password")
    require(data.get("username") == "fitlog_admin" and isinstance(password, str) and bool(password))
    if not isinstance(password, str):
        raise BootstrapError()
    del secret, data
    with psycopg.connect(**connection_options(target.host, "fitlog_admin", password),
                         autocommit=True) as connection:
        del password
        database = Database(connection)
        database.acquire()
        completed = database.before(request)
        require(aws.inspect(request) == target)
        database.asserted_lock()
        store = SecretStore(aws.secrets, request)
        if not database.claimed():
            store.require_empty()
            database.asserted_lock()
            database.reserve(request)
        values = store.load_or_create(lambda: database.check_reservation(request))
        require(aws.inspect(request) == target)
        database.check_reservation(request)
        if not completed:
            database.initialize(request, values)
        database.verify(request)
        verify_login(target.host, values)
    return "bootstrap_verified"


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)
    parser = Parser(description="Inspect or initialize a stopped FitLog environment",
                    allow_abbrev=False)
    for flag in ("expected-account-id", "environment", "db-instance-identifier",
                 "application-secret-arn", "distribution-id", "operation-id"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--initialize", action="store_true")
    try:
        args = parser.parse_args(argv)
        request = Request(args.expected_account_id, args.environment, args.db_instance_identifier,
                          args.application_secret_arn, args.distribution_id, args.operation_id)
        # This is a dedicated process. No libpq environment option may override the contract.
        for key in tuple(os.environ):
            if key.startswith("PG"):
                del os.environ[key]
        result = run(request, args.initialize, Aws.connect())
    except Exception:
        # Deliberate final boundary: all SDK/SQL/validation failures are private.
        print('{"event":"bootstrap_failed"}', file=sys.stderr)
        return 2
    print(json.dumps({"event": result, "operation": request.operation}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Exercise the real orchestration and PG transactions with a deterministic AWS boundary."""
import json
from collections.abc import Callable
from dataclasses import replace
from unittest.mock import Mock, patch

import psycopg
from psycopg import sql

from operations import bootstrap
from operations.aws import Aws, DatabaseTarget
from operations.contract import BootstrapError, Request, SecretValues
from operations.database import Database, connection_options

FLOW_CA = '/fixtures/ca.pem'
FLOW_PASSWORD = 'bootstrap-public-fixture'
FLOW_MASTER = 'arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:master-AbCdEf'


def flow_main() -> None:
    # The caller provides the same isolated TLS fixture as bootstrap_probe.py.
    request = Request('123456789012', 'fitlog-demo-test', 'fitlog-demo-test',
        'arn:aws:secretsmanager:ap-northeast-1:123456789012:'
        'secret:fitlog-demo-test/application-AbCdEf', 'E1',
        '01234567-0123-4123-8123-0123456789ab')
    other = replace(request, operation='11234567-0123-4123-8123-0123456789ab')
    original_connect = psycopg.connect
    active: list[psycopg.Connection[tuple[object, ...]]] = []

    def fail(action: Callable[[], object]) -> None:
        try:
            action()
        except (BootstrapError, psycopg.OperationalError, TimeoutError, RuntimeError):
            return
        raise AssertionError('Injected failure or conflicting operation unexpectedly succeeded')

    def connect(*, host: str, user: str, password: str, port: int = 5432,
                dbname: str = 'fitlog', sslmode: str = 'verify-full',
                sslrootcert: str = FLOW_CA, connect_timeout: int = 5,
                passfile: str = '/dev/null', options: str = '',
                autocommit: bool = False) -> psycopg.Connection[tuple[object, ...]]:
        connection = original_connect(host=host, user=user, password=password, port=port,
            dbname=dbname, sslmode=sslmode, sslrootcert=FLOW_CA, connect_timeout=connect_timeout,
            passfile=passfile, options=options, autocommit=autocommit)
        if user == 'fitlog_admin':
            active.append(connection)
        return connection

    with original_connect(host='db-valid', dbname='postgres', user='postgres',
            password='tls-public-fixture', sslmode='verify-full', sslrootcert=FLOW_CA,
            autocommit=True) as root:
        def reset(create_admin: bool = True) -> None:
            root.execute('DROP DATABASE fitlog WITH (FORCE)')
            root.execute('DROP ROLE IF EXISTS fitlog_app')
            root.execute('DROP ROLE IF EXISTS fitlog_admin')
            if create_admin:
                root.execute(sql.SQL('CREATE ROLE fitlog_admin LOGIN NOSUPERUSER CREATEROLE '
                    'CREATEDB INHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}').format(
                        sql.Literal(FLOW_PASSWORD)))
                root.execute('CREATE DATABASE fitlog OWNER fitlog_admin')
            else:
                root.execute('CREATE DATABASE fitlog OWNER postgres')

        def run_scenario(scenario: str) -> None:
            reset()
            active.clear()
            aws = Mock(spec=Aws)
            aws.secrets = Mock()
            saved: dict[str, str] = {}
            writes: list[str] = []
            inspect_calls = 0
            injection = True

            def inspect(target: Request) -> DatabaseTarget:
                nonlocal inspect_calls
                inspect_calls += 1
                if scenario == 'lease_lost' and inspect_calls == 2:
                    active[-1].close()
                return DatabaseTarget('db-valid', FLOW_MASTER)

            def get_secret(*, SecretId: str, VersionStage: str,
                           VersionId: str = "") -> dict[str, object]:
                if SecretId == FLOW_MASTER:
                    return {'ARN': FLOW_MASTER, 'SecretString': json.dumps({
                        'username': 'fitlog_admin', 'password': FLOW_PASSWORD})}
                return {'ARN': request.application_arn, 'VersionId': request.operation,
                    'VersionStages': ['AWSCURRENT'], 'SecretString': saved[request.operation]}

            def versions(*, SecretId: str, IncludeDeprecated: bool,
                         NextToken: str = "") -> dict[str, object]:
                return {'Versions': [{'VersionId': key, 'VersionStages': ['AWSCURRENT']}
                                     for key in saved]}

            def put(*, SecretId: str, ClientRequestToken: str, SecretString: str,
                    VersionStages: list[str]) -> dict[str, str]:
                nonlocal injection
                version, payload = ClientRequestToken, SecretString
                writes.append(version)
                if scenario == 'late_old_put' and injection:
                    injection = False
                    active[-1].close()
                    fail(lambda: bootstrap.run(other, True, aws))
                    bootstrap.run(request, True, aws)
                if version in saved and saved[version] != payload:
                    raise RuntimeError('Immutable version rejected different payload')
                saved[version] = payload
                if scenario == 'put_timeout' and injection:
                    injection = False
                    raise TimeoutError('Persisted response lost')
                if scenario == 'old_put_first' and injection:
                    injection = False
                    active[-1].close()
                    fail(lambda: bootstrap.run(other, True, aws))
                    bootstrap.run(request, True, aws)
                return {'ARN': request.application_arn, 'VersionId': version}

            aws.inspect.side_effect = inspect
            aws.secrets.get_secret_value.side_effect = get_secret
            aws.secrets.list_secret_version_ids.side_effect = versions
            aws.secrets.put_secret_value.side_effect = put
            with patch.object(psycopg, 'connect', new=connect):
                if scenario == 'claim_only':
                    with connect(**connection_options('db-valid', 'fitlog_admin', FLOW_PASSWORD),
                                 autocommit=True) as admin:
                        database = Database(admin)
                        database.acquire()
                        database.reserve(request)
                    fail(lambda: bootstrap.run(other, True, aws))
                    assert writes == []
                elif scenario in ('claim_commit_unknown', 'completion_unknown'):
                    name = 'reserve' if scenario == 'claim_commit_unknown' else 'initialize'
                    original_reserve = Database.reserve
                    original_initialize = Database.initialize

                    def unknown_reserve(self: Database, target: Request) -> None:
                        original_reserve(self, target)
                        raise psycopg.OperationalError('Committed response lost')

                    def unknown_initialize(self: Database, target: Request,
                                           values: SecretValues) -> None:
                        original_initialize(self, target, values)
                        raise psycopg.OperationalError('Committed response lost')

                    inject = unknown_reserve if name == 'reserve' else unknown_initialize
                    with patch.object(Database, name, new=inject):
                        fail(lambda: bootstrap.run(request, True, aws))
                    if scenario == 'claim_commit_unknown':
                        assert writes == []
                    fail(lambda: bootstrap.run(other, True, aws))
                elif scenario == 'login_failure':
                    with patch.object(bootstrap, 'verify_login', side_effect=
                                      psycopg.OperationalError('Injected login failure')):
                        fail(lambda: bootstrap.run(request, True, aws))
                elif scenario == 'secret_without_claim':
                    saved[request.operation] = SecretValues.generate().encode()
                    fail(lambda: bootstrap.run(request, True, aws))
                    with connect(**connection_options('db-valid', 'fitlog_admin', FLOW_PASSWORD),
                                 autocommit=True) as admin:
                        assert Database(admin).claimed() is False
                    assert writes == []
                    return
                elif scenario in ('put_timeout', 'lease_lost', 'late_old_put', 'old_put_first'):
                    fail(lambda: bootstrap.run(request, True, aws))
                    if scenario == 'lease_lost':
                        assert writes == []
                assert bootstrap.run(request, True, aws) == 'bootstrap_verified'
                before = len(writes)
                fail(lambda: bootstrap.run(other, True, aws))
                assert len(writes) == before
                values = SecretValues.decode(saved[request.operation])
                with connect(**connection_options('db-valid', 'fitlog_app', values.password)) as app:
                    assert app.execute('SELECT session_user::text').fetchone() == ('fitlog_app',)
                assert set(saved) == {request.operation}
            print('Orchestration fixture:', scenario, 'OK')
        for scenario in ('claim_only', 'put_timeout', 'claim_commit_unknown',
                         'completion_unknown', 'login_failure', 'lease_lost',
                         'late_old_put', 'old_put_first', 'secret_without_claim'):
            run_scenario(scenario)
        reset(create_admin=False)
    print('Orchestration: durable claim, lease loss, delayed writes and real recovery: OK')


if __name__ == '__main__':
    flow_main()

"""Real PG17 oracle, run only inside the isolated TLS smoke client."""
import os
import subprocess
import sys
from collections.abc import Callable
from functools import partial

import psycopg
from psycopg import sql

from operations.contract import BootstrapError, Request, SecretValues
from operations.database import Database, connection_options, verify_login

CA = '/fixtures/ca.pem'
PASSWORD = 'bootstrap-public-fixture'
TOKEN = '01234567-0123-4123-8123-0123456789ab'
REQUEST = Request('123456789012', 'fitlog-demo-test', 'fitlog-demo-test',
                  'arn:aws:secretsmanager:ap-northeast-1:123456789012:'
                  'secret:fitlog-demo-test/application-AbCdEf', 'E1', TOKEN)


def rejected(action: Callable[[], object]) -> None:
    try:
        action()
    except (BootstrapError, psycopg.errors.InsufficientPrivilege):
        return
    raise AssertionError('Operation that must be rejected succeeded')


def connect(user: str, password: str) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(**connection_options('db-valid', user, password, CA), autocommit=True)


def main() -> None:
    with connect('postgres', 'tls-public-fixture') as root:
        root.execute(sql.SQL('CREATE ROLE fitlog_admin NOSUPERUSER LOGIN CREATEROLE CREATEDB '
                             'INHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}').format(
                                 sql.Literal(PASSWORD)))
        root.execute('ALTER DATABASE fitlog OWNER TO fitlog_admin')
    with connect('fitlog_admin', PASSWORD) as admin:
        assert admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname=session_user").fetchone() == (False,)
        admin.execute("SELECT set_config('createrole_self_grant', %s, false)",
                      (os.environ.get('BOOTSTRAP_SELF_GRANT', ''),))
        database = Database(admin)
        database.acquire()
        assert database.before(REQUEST) is False
        with connect('fitlog_admin', PASSWORD) as other:
            rejected(Database(other).acquire)
        admin.execute('CREATE FUNCTION public.sentinel() RETURNS integer LANGUAGE SQL AS $$SELECT 1$$')
        rejected(database.empty)
        admin.execute('DROP FUNCTION public.sentinel()')
        admin.execute("CREATE TYPE public.sentinel AS ENUM ('x')")
        rejected(database.empty)
        admin.execute('DROP TYPE public.sentinel')
        database.reserve(REQUEST)
        assert database.before(REQUEST) is False
        from dataclasses import replace
        rejected(lambda: database.before(replace(
            REQUEST, operation='11234567-0123-4123-8123-0123456789ab')))
        # Rollback leaves the durable claim but no role or completion marker.
        values = SecretValues.generate()
        try:
            with admin.transaction():
                database.initialize(REQUEST, values)
                raise RuntimeError('injected transaction failure')
        except RuntimeError:
            pass
        assert database.role_exists() is False
        assert database.before(REQUEST) is False
        database.initialize(REQUEST, values)
        assert database.before(REQUEST) is True
        database.verify(REQUEST)
        verify_login('db-valid', values, CA)
        with connect('fitlog_app', values.password) as app:
            app.execute('CREATE TABLE public.bootstrap_sample(id integer PRIMARY KEY)')
            app.execute('INSERT INTO public.bootstrap_sample VALUES (1)')
            assert app.execute('SELECT id FROM public.bootstrap_sample').fetchone() == (1,)
            app.execute('ALTER TABLE public.bootstrap_sample ADD COLUMN description text')
            app.execute('DROP TABLE public.bootstrap_sample')
            for query in ('CREATE DATABASE forbidden', 'CREATE ROLE forbidden',
                          'SET ROLE fitlog_admin', 'CREATE SCHEMA forbidden',
                          'SELECT operation FROM _fitlog_bootstrap.initialization',
                          'SELECT operation FROM _fitlog_bootstrap.operation_claim',
                          'CREATE TEMP TABLE forbidden(id integer)'):
                rejected(partial(app.execute, query))
            admin.execute('CREATE TABLE public.admin_only(id integer)')
            rejected(lambda: app.execute('SELECT id FROM public.admin_only'))
            rejected(lambda: app.execute('INSERT INTO public.admin_only VALUES (1)'))
            admin.execute('DROP TABLE public.admin_only')
        # Independent checks of membership direction and unauthorized ACL drift.
        assert admin.execute("SELECT count(*) FROM pg_auth_members WHERE member="
                             "(SELECT oid FROM pg_roles WHERE rolname='fitlog_app')").fetchone() == (0,)
        assert admin.execute("SELECT bool_or(admin_option) FROM pg_auth_members WHERE roleid="
                             "(SELECT oid FROM pg_roles WHERE rolname='fitlog_app') AND member="
                             "(SELECT oid FROM pg_roles WHERE rolname='fitlog_admin')").fetchone() == (True,)
        admin.execute('GRANT SELECT(operation) ON _fitlog_bootstrap.initialization TO fitlog_app')
        rejected(lambda: database.verify(REQUEST))
        admin.execute('REVOKE SELECT(operation) ON _fitlog_bootstrap.initialization FROM fitlog_app')
        admin.execute('CREATE FUNCTION _fitlog_bootstrap.unexpected() RETURNS integer '
                      'LANGUAGE SQL AS $$SELECT 1$$')
        rejected(lambda: database.verify(REQUEST))
        admin.execute('DROP FUNCTION _fitlog_bootstrap.unexpected()')
        admin.execute("CREATE TYPE _fitlog_bootstrap.unexpected AS ENUM ('x')")
        rejected(lambda: database.verify(REQUEST))
        admin.execute('DROP TYPE _fitlog_bootstrap.unexpected')
        admin.execute('CREATE INDEX unexpected ON _fitlog_bootstrap.initialization(account)')
        rejected(lambda: database.verify(REQUEST))
        admin.execute('DROP INDEX _fitlog_bootstrap.unexpected')
        with admin.transaction(force_rollback=True):
            admin.execute('ALTER TABLE _fitlog_bootstrap.initialization '
                          'ALTER COLUMN operation TYPE varchar')
            rejected(lambda: database.verify(REQUEST))
        admin.execute('GRANT CONNECT ON DATABASE fitlog TO fitlog_app WITH GRANT OPTION')
        rejected(lambda: database.verify(REQUEST))
        admin.execute('REVOKE GRANT OPTION FOR CONNECT ON DATABASE fitlog FROM fitlog_app')
        admin.execute('GRANT SELECT ON _fitlog_bootstrap.initialization TO fitlog_app')
        rejected(lambda: database.verify(REQUEST))
        admin.execute('REVOKE SELECT ON _fitlog_bootstrap.initialization FROM fitlog_app')
        admin.execute('GRANT TEMP ON DATABASE fitlog TO fitlog_app')
        rejected(lambda: database.verify(REQUEST))
        admin.execute('REVOKE TEMP ON DATABASE fitlog FROM fitlog_app')
        admin.execute("UPDATE _fitlog_bootstrap.initialization SET version='unknown'")
        rejected(lambda: database.before(REQUEST))
        admin.execute('UPDATE _fitlog_bootstrap.initialization SET version=%s', (TOKEN,))
        database.verify(REQUEST)
        # Apply the repository's real migrations as the app, never as postgres/admin.
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.settings', 'FITLOG_ENV': 'local',
               'DJANGO_SECRET_KEY': 'migration-public-fixture',
               'AUTH_RATE_LIMIT_HMAC_KEY': 'fitlog-local-only-public-hmac-key-never-use-in-production',
               'POSTGRES_HOST': 'db-valid', 'POSTGRES_DB': 'fitlog', 'POSTGRES_USER': 'fitlog_app',
               'POSTGRES_PASSWORD': values.password, 'PGSSLMODE': 'verify-full',
               'PGSSLROOTCERT': CA}
        migrated = subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], env=env,
                                  capture_output=True, text=True, timeout=90)
        diagnostic = migrated.stderr
        for private in (values.django, values.hmac, values.password):
            diagnostic = diagnostic.replace(private, '[redacted]')
        assert migrated.returncode == 0, diagnostic
        with connect('fitlog_app', values.password) as app:
            assert app.execute('SELECT count(*) >= 22 FROM public.django_migrations').fetchone() == (True,)
        assert database.before(REQUEST) is True
        # Closing a lock connection must not trigger automatic reconnection.
        with connect('fitlog_admin', PASSWORD) as closed:
            closed.close()
            rejected(lambda: Database(closed).initialize(REQUEST, values))
    print('Bootstrap: non-superuser role/ACL/marker, rollback/resume, refusal, app migrations: OK')


if __name__ == '__main__':
    main()

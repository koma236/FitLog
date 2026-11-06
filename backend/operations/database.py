"""PostgreSQL initial provisioning under a session lock, with atomic role/ACL/marker."""
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import psycopg
from psycopg import sql

from operations.contract import Request, SecretValues, require

CA = str(Path(__file__).resolve().parents[1] / "certs/rds-ap-northeast-1-bundle.pem")
LOCK = 482736190658
COLUMNS = ("operation", "account", "region", "environment", "database", "secret_arn", "version")


class ConnectionOptions(TypedDict):
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str
    sslrootcert: str
    connect_timeout: int
    passfile: str
    options: str


def connection_options(host: str, user: str, password: str, ca: str = CA) -> ConnectionOptions:
    return {"host": host, "port": 5432, "dbname": "fitlog", "user": user,
            "password": password, "sslmode": "verify-full", "sslrootcert": ca,
            "connect_timeout": 5, "passfile": "/dev/null",
            "options": "-c search_path=pg_catalog -c statement_timeout=10000 -c lock_timeout=5000"}


@dataclass
class Database:
    connection: psycopg.Connection[tuple[object, ...]]

    def scalar(self, query: str, params: tuple[object, ...] = ()) -> object:
        row = self.connection.execute(query, params).fetchone()
        require(row is not None)
        assert row is not None
        return row[0]

    def acquire(self) -> None:
        require(self.scalar("SELECT pg_try_advisory_lock(%s)", (LOCK,)) is True)
        require(self.scalar("SELECT current_database()") == "fitlog")
        require(self.scalar("SELECT session_user::text") == "fitlog_admin")
        require(self.scalar("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()") is True)

    def role_exists(self) -> bool:
        return self.scalar("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='fitlog_app')") is True

    def empty(self, allow_control: bool = False) -> None:
        require(self.scalar("SELECT count(*) FROM pg_namespace WHERE nspname NOT IN "
                            "('pg_catalog','information_schema','pg_toast','public') "
                            "AND (%s OR nspname<>'_fitlog_bootstrap') "
                            "AND nspname !~ '^pg_(toast_)?temp_[0-9]+$'", (not allow_control,)) == 0)
        require(self.scalar("SELECT pg_get_userbyid(nspowner)::text FROM pg_namespace "
                            "WHERE nspname='public'") == "pg_database_owner")
        require(self.scalar("SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql'") == 0)
        for catalog, namespace in (("pg_class", "relnamespace"), ("pg_proc", "pronamespace"),
                                   ("pg_type", "typnamespace"), ("pg_operator", "oprnamespace"),
                                   ("pg_collation", "collnamespace"),
                                   ("pg_conversion", "connamespace"),
                                   ("pg_opclass", "opcnamespace"), ("pg_opfamily", "opfnamespace"),
                                   ("pg_ts_config", "cfgnamespace"),
                                   ("pg_ts_dict", "dictnamespace"),
                                   ("pg_ts_parser", "prsnamespace"),
                                   ("pg_ts_template", "tmplnamespace"),
                                ("pg_statistic_ext", "stxnamespace")):
            query = sql.SQL("SELECT count(*) FROM {} WHERE {} = "
                            "(SELECT oid FROM pg_namespace WHERE nspname='public')").format(
                                sql.Identifier(catalog), sql.Identifier(namespace))
            require(self.connection.execute(query).fetchone() == (0,))
        for catalog in ("pg_largeobject_metadata", "pg_event_trigger", "pg_publication",
                        "pg_foreign_server", "pg_user_mappings"):
            require(self.connection.execute(sql.SQL("SELECT count(*) FROM {}").format(
                sql.Identifier(catalog))).fetchone() == (0,))
        # pg_subscription is shared across databases; restrict to this DB and metadata only.
        require(self.scalar("SELECT count(subdbid) FROM pg_subscription WHERE subdbid="
                            "(SELECT oid FROM pg_database WHERE datname=current_database())") == 0)

    def asserted_lock(self) -> None:
        require(not self.connection.closed and self.scalar(
            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' "
            "AND pid=pg_backend_pid() AND granted "
            "AND classid=(%s::bigint >> 32)::oid AND objid=(%s::bigint & 4294967295)::oid)",
            (LOCK, LOCK)) is True)

    def claimed(self) -> bool:
        return self.scalar("SELECT EXISTS(SELECT 1 FROM pg_namespace "
                           "WHERE nspname='_fitlog_bootstrap')") is True

    def before(self, request: Request) -> bool:
        self.asserted_lock()
        exists = self.role_exists()
        if self.claimed():
            self.verify_control(request, exists)
            if exists:
                self.verify(request)
            else:
                self.empty(allow_control=True)
        else:
            require(not exists)
            self.empty()
        require(self.scalar("SELECT pg_get_userbyid(datdba)::text FROM pg_database "
                            "WHERE datname='fitlog'") == "fitlog_admin")
        return exists

    def create_record(self, name: str, request: Request) -> None:
        require(name in ("operation_claim", "initialization"))
        claim = name == "operation_claim"
        prefix = ("singleton boolean PRIMARY KEY CHECK (singleton), operation text NOT NULL, "
                  if claim else "operation text PRIMARY KEY, ")
        self.connection.execute(sql.SQL("CREATE TABLE _fitlog_bootstrap.{} (" + prefix +
            "account text NOT NULL, region text NOT NULL, environment text NOT NULL, "
            "database text NOT NULL, secret_arn text NOT NULL, version text NOT NULL)").format(
                sql.Identifier(name)))
        self.connection.execute(sql.SQL("REVOKE ALL ON _fitlog_bootstrap.{} FROM PUBLIC").format(
            sql.Identifier(name)))
        fields = "singleton," if claim else ""
        value = "true," if claim else ""
        self.connection.execute(sql.SQL("INSERT INTO _fitlog_bootstrap.{} (" + fields +
            "operation,account,region,environment,database,secret_arn,version) VALUES (" + value +
            "%s,%s,%s,%s,%s,%s,%s)").format(sql.Identifier(name)), request.marker())

    def reserve(self, request: Request) -> None:
        self.asserted_lock()
        if self.claimed():
            self.verify_control(request, self.role_exists())
            return
        require(not self.role_exists())
        with self.connection.transaction():
            self.empty()
            self.connection.execute("CREATE SCHEMA _fitlog_bootstrap AUTHORIZATION fitlog_admin")
            self.connection.execute("REVOKE ALL ON SCHEMA _fitlog_bootstrap FROM PUBLIC")
            self.create_record("operation_claim", request)
            self.verify_control(request, False)
        # An unknown commit outcome propagates; never reconnect or write a secret here.
        self.check_reservation(request)

    def check_reservation(self, request: Request) -> None:
        self.asserted_lock()
        self.verify_control(request, self.role_exists())

    def initialize(self, request: Request, values: SecretValues) -> None:
        self.check_reservation(request)
        with self.connection.transaction():
            require(not self.role_exists())
            self.empty(allow_control=True)
            verifier = self.connection.pgconn.encrypt_password(
                values.password.encode(), b"fitlog_app", b"scram-sha-256").decode()
            self.connection.execute(sql.SQL(
                "CREATE ROLE fitlog_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
            ).format(sql.Literal(verifier)))
            self.connection.execute("REVOKE ALL ON DATABASE fitlog FROM PUBLIC")
            self.connection.execute("GRANT CONNECT ON DATABASE fitlog TO fitlog_app")
            self.connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            self.connection.execute("GRANT USAGE, CREATE ON SCHEMA public TO fitlog_app")
            self.create_record("initialization", request)
            self.verify(request)

    def verify_table(self, name: str, request: Request) -> None:
        require(name in ("operation_claim", "initialization"))
        table = "_fitlog_bootstrap." + name
        claim = name == "operation_claim"
        require(self.scalar("SELECT pg_get_userbyid(relowner)::text FROM pg_class "
                            "WHERE oid=%s::regclass", (table,)) == "fitlog_admin")
        require(self.scalar(
            "SELECT relkind='r' AND relpersistence='p' AND NOT relispartition "
            "AND NOT relrowsecurity AND NOT relforcerowsecurity FROM pg_class "
            "WHERE oid=%s::regclass", (table,)) is True)
        columns = self.connection.execute(
            "SELECT attname::text,atttypid::regtype::text,attnotnull,atthasdef,"
            "attidentity::text,attgenerated::text FROM pg_attribute WHERE attrelid=%s::regclass "
            "AND attnum>0 AND NOT attisdropped ORDER BY attnum", (table,)).fetchall()
        expected = [(column, "text", True, False, "", "") for column in COLUMNS]
        if claim:
            expected.insert(0, ("singleton", "boolean", True, False, "", ""))
        require(columns == expected)
        require(self.scalar(
            "SELECT count(*) FROM pg_attribute a WHERE a.attrelid=%s::regclass AND a.attnum>0 "
            "AND (a.attisdropped OR EXISTS(SELECT 1 FROM "
            "aclexplode(CASE WHEN cardinality(a.attacl)>0 THEN a.attacl END) p WHERE p.grantee<>"
            "(SELECT relowner FROM pg_class WHERE oid=a.attrelid)))", (table,)) == 0)
        require(self.scalar(
            "SELECT count(*) FROM pg_class c, LATERAL aclexplode(c.relacl) a "
            "WHERE c.oid=%s::regclass AND a.grantee<>c.relowner", (table,)) == 0)
        require(self.scalar(
            "SELECT count(*) FROM pg_index WHERE indrelid=%s::regclass AND indisprimary "
            "AND indisunique AND indisvalid AND indisready AND indexprs IS NULL "
            "AND indpred IS NULL AND indnatts=1 AND indnkeyatts=1 "
            "AND indkey='1'::int2vector", (table,)) == 1)
        constraints = self.connection.execute(
            "SELECT contype::text,conkey,condeferrable,condeferred,convalidated,"
            "CASE WHEN contype='c' THEN pg_get_constraintdef(oid) ELSE '' END "
            "FROM pg_constraint WHERE conrelid=%s::regclass ORDER BY contype", (table,)).fetchall()
        expected_constraints: list[tuple[object, ...]] = [("p", [1], False, False, True, "")]
        if claim:
            expected_constraints.insert(0, ("c", [1], False, False, True, "CHECK (singleton)"))
        require(constraints == expected_constraints)
        for catalog, column in (("pg_trigger", "tgrelid"), ("pg_rewrite", "ev_class"),
                                ("pg_policy", "polrelid")):
            require(self.connection.execute(sql.SQL(
                "SELECT count(*) FROM {} WHERE {}=%s::regclass"
            ).format(sql.Identifier(catalog), sql.Identifier(column)), (table,)).fetchone() == (0,))
        require(self.scalar("SELECT count(*) FROM pg_inherits WHERE inhrelid=%s::regclass "
                            "OR inhparent=%s::regclass", (table, table)) == 0)
        fields = sql.SQL("singleton,") if claim else sql.SQL("")
        rows = self.connection.execute(sql.SQL("SELECT {}operation,account,region,environment,"
            "database,secret_arn,version FROM _fitlog_bootstrap.{}").format(
                fields, sql.Identifier(name))).fetchall()
        require(rows == [((True,) + request.marker()) if claim else request.marker()])

    def verify_control(self, request: Request, completed: bool) -> None:
        require(self.scalar("SELECT pg_get_userbyid(nspowner)::text FROM pg_namespace "
                            "WHERE nspname='_fitlog_bootstrap'") == "fitlog_admin")
        tables = ["operation_claim", "initialization"] if completed else ["operation_claim"]
        require(self.scalar("SELECT count(*) FROM pg_class WHERE relnamespace="
                            "'_fitlog_bootstrap'::regnamespace") == len(tables) * 2)
        for table in tables:
            self.verify_table(table, request)
        for catalog, column in (("pg_proc", "pronamespace"), ("pg_operator", "oprnamespace"),
                                ("pg_collation", "collnamespace"),
                                ("pg_conversion", "connamespace"), ("pg_opclass", "opcnamespace"),
                                ("pg_opfamily", "opfnamespace"), ("pg_ts_config", "cfgnamespace"),
                                ("pg_ts_dict", "dictnamespace"), ("pg_ts_parser", "prsnamespace"),
                                ("pg_ts_template", "tmplnamespace"),
                                ("pg_statistic_ext", "stxnamespace"),
                                ("pg_default_acl", "defaclnamespace")):
            require(self.connection.execute(sql.SQL(
                "SELECT count(*) FROM {} WHERE {}='_fitlog_bootstrap'::regnamespace"
            ).format(sql.Identifier(catalog), sql.Identifier(column))).fetchone() == (0,))
        names = ["_fitlog_bootstrap." + table for table in tables]
        require(self.scalar(
            "SELECT count(*) FROM pg_type WHERE typnamespace='_fitlog_bootstrap'::regnamespace "
            "AND oid NOT IN (SELECT c.reltype FROM pg_class c WHERE c.oid=ANY(%s::regclass[]) "
            "UNION ALL SELECT t.typarray FROM pg_type t JOIN pg_class c ON c.reltype=t.oid "
            "WHERE c.oid=ANY(%s::regclass[]))", (names, names)) == 0)
        require(self.scalar(
            "SELECT count(*) FROM pg_namespace n, "
            "LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a "
            "WHERE n.nspname='_fitlog_bootstrap' AND a.grantee<>n.nspowner") == 0)

    def verify(self, request: Request) -> None:
        self.verify_control(request, True)
        require(self.scalar("SELECT pg_get_userbyid(nspowner)::text FROM pg_namespace "
                            "WHERE nspname='public'") == "pg_database_owner")
        require(self.scalar("SELECT pg_get_userbyid(datdba)::text FROM pg_database "
                            "WHERE datname='fitlog'") == "fitlog_admin")
        attributes = self.connection.execute(
            "SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,"
            "rolbypassrls,rolinherit FROM pg_roles WHERE rolname='fitlog_app'").fetchone()
        require(attributes == (True, False, False, False, False, False, False))
        require(self.scalar("SELECT count(*) FROM pg_auth_members WHERE member="
                            "(SELECT oid FROM pg_roles WHERE rolname='fitlog_app')") == 0)
        require(self.scalar("SELECT count(*) FROM pg_auth_members WHERE roleid="
                            "(SELECT oid FROM pg_roles WHERE rolname='fitlog_app') "
                            "AND member<>(SELECT oid FROM pg_roles WHERE rolname='fitlog_admin')") == 0)
        require(self.scalar("SELECT coalesce(bool_or(admin_option),false) FROM pg_auth_members "
                            "WHERE roleid=(SELECT oid FROM pg_roles WHERE rolname='fitlog_app') "
                            "AND member=(SELECT oid FROM pg_roles WHERE rolname='fitlog_admin')")
                is True)
        for privilege, expected in (("CONNECT", True), ("CREATE", False), ("TEMP", False)):
            require(self.scalar("SELECT has_database_privilege('fitlog_app','fitlog',%s)",
                                (privilege,)) is expected)
        for privilege in ("USAGE", "CREATE"):
            require(self.scalar("SELECT has_schema_privilege('fitlog_app','public',%s)",
                                (privilege,)) is True)
            require(self.scalar("SELECT has_schema_privilege('fitlog_app',"
                                "'_fitlog_bootstrap',%s)", (privilege,)) is False)
        # Effective privilege checks alone miss delegation and otherwise inaccessible grants.
        database_acl = self.connection.execute(
            "SELECT a.privilege_type::text,a.is_grantable FROM pg_database d, "
            "LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a "
            "WHERE d.datname='fitlog' AND a.grantee<>d.datdba ORDER BY 1,2").fetchall()
        require(database_acl == [("CONNECT", False)])
        require(self.scalar(
            "SELECT count(*) FROM pg_database d, "
            "LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a "
            "WHERE d.datname='fitlog' AND a.grantee<>d.datdba AND a.grantee<>"
            "(SELECT oid FROM pg_roles WHERE rolname='fitlog_app')") == 0)
        schema_acl = self.connection.execute(
            "SELECT a.privilege_type::text,a.is_grantable FROM pg_namespace n, "
            "LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a "
            "WHERE n.nspname='public' AND a.grantee<>n.nspowner ORDER BY 1,2").fetchall()
        require(schema_acl == [("CREATE", False), ("USAGE", False)])
        require(self.scalar(
            "SELECT count(*) FROM pg_namespace n, "
            "LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a "
            "WHERE n.nspname='public' AND a.grantee<>n.nspowner AND a.grantee<>"
            "(SELECT oid FROM pg_roles WHERE rolname='fitlog_app')") == 0)


def verify_login(host: str, values: SecretValues, ca: str = CA) -> None:
    with psycopg.connect(**connection_options(host, "fitlog_app", values.password, ca)) as conn:
        require(conn.execute("SELECT session_user::text,current_database()").fetchone()
                == ("fitlog_app", "fitlog"))
        require(conn.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()
                == (True,))
        require(conn.execute("SELECT has_schema_privilege('public','CREATE'), "
                             "has_schema_privilege('_fitlog_bootstrap','USAGE')").fetchone()
                == (True, False))

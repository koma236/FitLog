"""Real libpq verify-full checks on an isolated, temporary PostgreSQL network.

Run while holding the FitLog runtime lease, after building the production image.
No AWS access, host ports, shared DB, or persistent Docker volumes are used.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from tests.production_smoke import IMAGE, docker


def openssl(*args: str) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True, text=True, timeout=30)


def owned_resource_id(kind: str, name: str, run_token: str) -> str | None:
    """Resolve only this run's exact name and ownership label, including stopped resources."""
    listing = ("ps", "--all") if kind == "container" else ("network", "ls")
    name_field = "{{.Names}}" if kind == "container" else "{{.Name}}"
    rows = docker(*listing, "--filter", "name=" + name,
                  "--filter", "label=fitlog.tls-run=" + run_token,
                  "--format", "{{.ID}} " + name_field)
    matches = [fields[0] for row in rows.splitlines()
               if len(fields := row.split()) == 2 and fields[1] == name]
    assert len(matches) <= 1, "Ambiguous owned resource inventory"
    return matches[0] if matches else None


def cleanup_owned_resources(
    client: str, database: str, network: str, run_token: str,
    primary_error: BaseException | None,
) -> None:
    """Attempt every owned cleanup, preserving the original failure on cleanup errors."""
    failures: list[Exception] = []
    for name in (client, database):
        try:
            container = owned_resource_id("container", name, run_token)
            if container is None:
                continue
            if docker("inspect", "--format", "{{.State.Running}}", container).strip() == "true":
                docker("stop", "--time", "10", container)
            assert docker("inspect", "--format", "{{.State.Running}}", container).strip() == "false"
            docker("rm", container)
        except Exception as error:
            failures.append(error)
    try:
        network_id = owned_resource_id("network", network, run_token)
        if network_id is not None:
            assert json.loads(docker("network", "inspect", network_id))[0]["Containers"] == {}
            docker("network", "rm", network_id)
    except Exception as error:
        failures.append(error)
    if failures:
        errors: list[BaseException] = ([primary_error] if primary_error is not None else [])
        errors.extend(failures)
        raise BaseExceptionGroup("TLS smoke failed to clean up owned resources", errors)


def main() -> None:
    # Use the exact image already pinned by the project, not a floating tag.
    compose = Path(__file__).resolve().parents[2] / "compose.yaml"
    image_lines = [line.strip() for line in compose.read_text().splitlines()
                   if line.strip().startswith("image: postgres:")]
    assert len(image_lines) == 1
    postgres_image = image_lines[0].removeprefix("image: ")
    assert "@sha256:" in postgres_image
    run_token = uuid.uuid4().hex
    name = "fitlog-fl09b4-tls-" + str(os.getpid()) + "-" + run_token[:12]
    network = name + "-network"
    client = name + "-client"
    try:
        with tempfile.TemporaryDirectory(prefix="fitlog-tls-") as folder:
            fixtures = Path(folder)
            os.chmod(fixtures, 0o755)
            for prefix in ("ca", "unrelated"):
                openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                        "-keyout", str(fixtures / (prefix + ".key")),
                        "-out", str(fixtures / (prefix + ".pem")), "-subj", "/CN=FitLog TLS test " + prefix,
                        "-addext", "basicConstraints=critical,CA:TRUE")
            openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(fixtures / "server.key"),
                    "-out", str(fixtures / "server.csr"), "-subj", "/CN=db-valid")
            (fixtures / "server.ext").write_text("subjectAltName=DNS:db-valid\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n")
            openssl("x509", "-req", "-in", str(fixtures / "server.csr"),
                    "-CA", str(fixtures / "ca.pem"), "-CAkey", str(fixtures / "ca.key"),
                    "-CAcreateserial", "-days", "2", "-extfile", str(fixtures / "server.ext"),
                    "-out", str(fixtures / "server.pem"))
            # Copy only the server key/leaf into PostgreSQL; CA private keys stay on the host.
            server_files = fixtures / "server"
            client_files = fixtures / "client"
            server_files.mkdir(mode=0o755)
            client_files.mkdir(mode=0o755)
            for file in ("server.key", "server.pem"):
                (server_files / file).write_bytes((fixtures / file).read_bytes())
                os.chmod(server_files / file, 0o644)
            for file in ("ca.pem", "unrelated.pem"):
                (client_files / file).write_bytes((fixtures / file).read_bytes())
                os.chmod(client_files / file, 0o644)
            docker("network", "create", "--internal", "--label", "fitlog.tls-run=" + run_token, network)
            docker("create", "--name", name, "--network", network,
                   "--label", "fitlog.tls-run=" + run_token,
                   "--network-alias", "db-valid", "--network-alias", "db-wrong",
                   "--mount", f"type=bind,src={server_files},dst=/fixtures,readonly",
                   "--tmpfs", "/var/lib/postgresql/data:rw",
                   "--env", "POSTGRES_PASSWORD=tls-public-fixture",
                   "--env", "POSTGRES_DB=fitlog", postgres_image, "bash", "-c",
                   "install -o postgres -g postgres -m 600 /fixtures/server.key /tmp/server.key; "
                   "install -m 644 /fixtures/server.pem /tmp/server.pem; "
                   "exec docker-entrypoint.sh postgres -c ssl=on "
                   "-c ssl_cert_file=/tmp/server.pem -c ssl_key_file=/tmp/server.key")
            docker("start", name)
            deadline = time.monotonic() + 45
            while True:
                ready = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1",
                                        "-U", "postgres", "-d", "fitlog"],
                                       capture_output=True, text=True, timeout=10)
                if ready.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError("Isolated TLS PostgreSQL did not become ready")
                time.sleep(0.25)
            script = '''
import psycopg

def connect(host, ca):
    return psycopg.connect(host=host, dbname="fitlog", user="postgres",
        password="tls-public-fixture", sslmode="verify-full", sslrootcert=ca, connect_timeout=5)

with connect("db-valid", "/fixtures/ca.pem") as connection:
    assert connection.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()").fetchone() == (True,)
for host, ca, reason in [
    ("db-valid", "/fixtures/unrelated.pem", "certificate verify failed"),
    ("db-wrong", "/fixtures/ca.pem", "does not match host name"),
]:
    try:
        connect(host, ca)
    except psycopg.OperationalError as error:
        assert reason in str(error).lower(), "Negative case must fail due to certificate verification"
    else:
        raise AssertionError("verify-full accepted an untrusted certificate or wrong hostname")
print("PostgreSQL TLS: matching CA/SAN succeeds; wrong CA and SAN are rejected: OK")
'''
            docker("create", "--interactive", "--name", client, "--network", network,
                   "--label", "fitlog.tls-run=" + run_token,
                   "--mount", f"type=bind,src={client_files},dst=/fixtures,readonly",
                   IMAGE, "python", "-")
            print(docker("start", "--attach", "--interactive", client, source=script).strip())
    finally:
        cleanup_owned_resources(
            client, name, network, run_token, sys.exception(),
        )


if __name__ == "__main__":
    main()

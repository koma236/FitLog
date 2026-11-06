"""Host-side smoke: isolated Docker containers, no published ports or AWS access.

Run after building fitlog-fl09b4-production-44, while holding the FitLog runtime lease:
python3 backend/tests/production_smoke.py
"""
import json
import os
import subprocess
from pathlib import Path

IMAGE = "fitlog-fl09b4-production-44"
ENV = {
    "DJANGO_SECRET_KEY": "S" * 64,
    "AUTH_RATE_LIMIT_HMAC_KEY": "H" * 64,
    "FITLOG_PUBLIC_HOST": "d111111abcdef8.cloudfront.net",
    "PRIVATE_MEDIA_BUCKET": "fitlog-test-private",
    "PRIVATE_MEDIA_EXPECTED_OWNER": "123456789012",
    "AWS_REGION": "ap-northeast-1",
    "POSTGRES_HOST": "demo.example.rds.amazonaws.com",
    "POSTGRES_DB": "fitlog",
    "POSTGRES_USER": "fitlog",
    "POSTGRES_PASSWORD": "smoke-only-password",
    "POSTGRES_SSLROOTCERT": "/app/certs/rds-ap-northeast-1-bundle.pem",
    "AWS_EC2_METADATA_DISABLED": "true",
    "FITLOG_LOG_FORMAT": "json",
    "FITLOG_APP_VERSION": "0123456789abcdef0123456789abcdef01234567",
}


def docker(*args: str, source: str | None = None) -> str:
    result = subprocess.run(["docker", *args], input=source, text=True, capture_output=True, timeout=50)
    if result.returncode:
        raise RuntimeError(f"Docker smoke operation failed: {args[0]}\n{result.stderr}")
    return result.stdout


def main() -> None:
    options = [item for key, value in ENV.items() for item in ("--env", key + "=" + value)]
    for probe in (False, True):
        name = "fitlog-fl09a-smoke-" + str(os.getpid()) + ("-log" if probe else "-app")
        extra = (["--volume", str(Path(__file__).resolve()) + ":/tmp/production_smoke.py:ro"]
                 if probe else [])
        command = (["gunicorn", "--pythonpath", "/app", "--chdir", "/tmp", "--config", "/app/config/gunicorn.py",
                    "production_smoke:application"] if probe else [])
        docker("run", "--detach", "--name", name, "--network", "none", *options,
               *extra, IMAGE, *command)
        try:
            assert docker("exec", name, "id", "-u").strip() != "0"
            script = '''
import http.client, time
def request(method, path, host="10.0.1.8"):
    c=http.client.HTTPConnection("127.0.0.1",8000,timeout=2)
    c.request(method,path,headers={"Host":host})
    r=c.getresponse(); status=r.status; r.read(); c.close(); return status
for attempt in range(40):
    try:
        first=request("GET", "/api/health/live")
        break
    except (OSError, http.client.HTTPException):
        time.sleep(.2)
else:
    raise AssertionError("Gunicorn did not become available")
'''
            if probe:
                script += '''
assert first == 200
assert request("GET","/api/media/content/PRIVATE-URL-TOKEN") == 500
import socket
with socket.create_connection(("127.0.0.1",8000),timeout=2) as s:
    s.sendall(b"GET /PRIVATE-BAD-REQUEST HTTP/1.1\\r\\nBad Header: PRIVATE-HEADER\\r\\n\\r\\n")
    assert b"400" in s.recv(4096)
'''
            else:
                script += '''
assert first == 200
assert request("HEAD","/api/health/live") == 200
assert request("GET","/api/health/ready") == 400
assert request("GET","/api/health/livex") == 400
assert request("POST","/api/health/live") == 400
assert request("GET","/api/auth/csrf","d111111abcdef8.cloudfront.net") == 200
'''
            docker("exec", "-i", name, "python", "-", source=script)
            if not probe:
                docker("exec", name, "python", "manage.py", "check")
                help_text = docker("exec", name, "python", "manage.py", "cleanup_images", "--help")
                assert "cleanup_images" in help_text
            docker("stop", "--time", "35", name)
            assert docker("inspect", "--format", "{{.State.ExitCode}}", name).strip() == "0"
            logs = docker("logs", name)  # stderr is inspected separately below as well.
            full = subprocess.run(["docker", "logs", name], capture_output=True, text=True, timeout=10)
            assert full.returncode == 0
            logs += full.stderr
            assert all(value not in logs for value in ("PRIVATE", "Traceback", "smoke-only-password", "S" * 64, "H" * 64))
            rows = [json.loads(line) for line in logs.splitlines()]
            assert rows and all(row["app_version"] == ENV["FITLOG_APP_VERSION"] for row in rows)
            assert any(row["event"] == "server_info" for row in rows)
            if probe:
                assert any(row["event"] == "server_error" and row["level"] == "ERROR" for row in rows)
                assert any(row["event"] == "server_warning" for row in rows)
        finally:
            state = docker("inspect", "--format", "{{.State.Running}}", name).strip()
            if state == "true":
                docker("stop", "--time", "35", name)
            docker("rm", name)
    print("production smoke: non-root, settings/check/help, live/Host, worker error, malformed request, safe logs, SIGTERM: OK")


def application(environ: dict[str, str], start_response: object) -> list[bytes]:
    # Mounted test-only WSGI app exercises Gunicorn's own exception handling.
    if environ["PATH_INFO"] != "/api/health/live":
        raise ValueError("PRIVATE-WORKER-EXCEPTION")
    from collections.abc import Callable
    from typing import cast
    cast(Callable[..., object], start_response)("200 OK", [("Content-Type", "text/plain")])
    return [b"ok"]


if __name__ == "__main__":
    main()

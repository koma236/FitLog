"""Local-only browser runtime. Shares the adopted lock/process primitives."""
import importlib.util
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

spec = importlib.util.spec_from_file_location("fitlog_registered_checks", Path(__file__).resolve().parents[1] / "scripts/run-checks.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


class RuntimeSession:
    def __init__(self, lock, driver):
        self.lock, self.driver = lock, driver
        self.report = {"lock_released": False}

    def run(self):
        passed = False
        try:
            self.lock.acquire()
            self.driver.prepare()
            self.driver.exercise()
            passed = True
        except (Exception, KeyboardInterrupt):
            self.report["error"] = "OPERATION_FAILED"
        finally:
            if self.lock.acquired:
                # A repeated interrupt must not skip the remaining owned stops.
                handlers = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
                try:
                    passed = self.finish(passed)
                finally:
                    for sig, handler in handlers.items():
                        signal.signal(sig, handler)
        return passed and self.report["lock_released"]

    def finish(self, passed):
        """Stop first, verify ownership, then release; uncertain cleanup retains lock."""
        if self.lock.acquired:
            if self.lock.owned():
                try:
                    if self.driver.stop_owned():
                        self.lock.release()
                        self.report["lock_released"] = True
                    else:
                        passed = False
                except (Exception, KeyboardInterrupt):
                    passed = False
                    self.report["error"] = "STOP_UNCONFIRMED"
            else:
                passed = False
                self.report["error"] = "OWNER_CHANGED"
        return passed


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COMMON = Path("/Users/saki/project/FitLog/.git")


def snapshot():
    """Hash source files, including untracked task files, without saving contents."""
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()
    files = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    digest = hashlib.sha256()
    for name in sorted(set(files) - {""}):
        path = ROOT / name
        if path.is_file():
            digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return {"commit": git("rev-parse", "HEAD"), "source_sha256": digest.hexdigest(),
            "dirty_paths": git("status", "--short").splitlines()}


def port_open(port):
    with socket.socket() as connection:
        connection.settimeout(.3)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def validate_browser_result(output, run_id):
    """CLI success alone is insufficient when tests were absent or not reached."""
    try:
        story = json.loads((output / "journey.json").read_text())
        runner = json.loads((output / "runner.json").read_text())
        rows = story["steps"]
        expected = {f"E{number:02}" for number in range(1, 11)}
        if (story["run_id"] != run_id or len(rows) != 10
                or {row["id"] for row in rows} != expected
                or any(row["status"] != "pass" or not row.get("started") or not row.get("finished") for row in rows)):
            raise ValueError()
        cleanup = story["cleanup"]
        if (len(cleanup) != 2 or {row["action"] for row in cleanup} != {"A-owned-ui-cleanup", "B-owned-ui-cleanup"}
                or any(row["status"] != "pass" for row in cleanup)):
            raise ValueError()
        resources = story["resources"]
        users = resources["users"]
        if (not isinstance(users, list) or len(users) != 2 or len(set(users)) != 2
                or any(str(uuid.UUID(value)) != value for value in users)
                or resources["posts"] != [] or resources["comments"] != []):
            raise ValueError()
        if (runner["status"] != "passed" or runner["worker_error"] is not False or not runner["tests"]
                or any(row["status"] != "passed" for row in runner["tests"])):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise RuntimeError("BROWSER_RESULT_INVALID") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("REDIRECT_BLOCKED")


class LocalDriver:
    def __init__(self, lock, output, capture=False):
        self.lock, self.output, self.capture = lock, output, capture
        self.started = []
        self.initial_ids = set()
        self.inventory_known = False
        self.safe = True
        self.cleaning = False
        self.persistence_failed = False
        self.report = {"operations": [], "migrations": {}, "environment": "local", "started_at": shared.now()}

    def save(self):
        self.output.mkdir(parents=True, exist_ok=True)
        temp = self.output / "runtime.json.tmp"
        temp.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temp.replace(self.output / "runtime.json")

    def persist(self):
        try:
            self.save()
        except OSError:
            self.persistence_failed = True
            self.report["persistence"] = "failed"
            if not self.cleaning:
                raise

    def command(self, name, argv, timeout=90, env=None):
        if not self.lock.owned():
            raise RuntimeError("OWNER_CHANGED")
        entry = {"id": name, "started_at": shared.now(), "exit_code": None}
        self.report["operations"].append(entry)
        self.persist()
        child = None
        previous_safe = self.safe
        self.safe = False
        try:
            child = subprocess.Popen(argv, cwd=ROOT, env={**os.environ, **(env or {})},
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            stdout, _ = child.communicate(timeout=timeout)
            if shared.group_exists(child.pid):
                shared.stop_group(child)
                raise ChildProcessError("DESCENDANT_REMAINED")
            self.safe = previous_safe
            entry["exit_code"] = child.returncode
            if child.returncode:
                raise RuntimeError("COMMAND_FAILED")
            return stdout.decode(errors="replace")
        except BaseException:
            if child is not None:
                shared.stop_group(child)
            self.safe = previous_safe
            raise
        finally:
            entry["ended_at"] = shared.now()
            self.persist()

    def containers(self):
        raw = self.command("inventory", shared.COMPOSE + ["ps", "--all", "--format", "json"]).strip()
        records = json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines()]
        if not isinstance(records, list) or any(not row.get("ID") or not row.get("Service") or not row.get("State") for row in records):
            raise RuntimeError("INVENTORY_INVALID")
        return records

    def migrations(self, phase):
        run = shared.COMPOSE + ["run", "--rm", "--no-deps", "backend"] + shared.MANAGE
        plan = self.command("migration-plan-" + phase, run + ["showmigrations", "--plan"])
        raw = self.command("migration-graph-" + phase, run + ["shell", "-c", shared.MIGRATION_QUERY])
        rows = [json.loads(line[len("FITLOG_MIGRATIONS:"):]) for line in raw.splitlines() if line.startswith("FITLOG_MIGRATIONS:")]
        if len(rows) != 1 or rows[0].get("unknown") != [] or rows[0].get("consistent") is not True:
            raise RuntimeError("MIGRATION_MISMATCH")
        self.report["migrations"][phase] = {"plan": plan.splitlines(), **rows[0]}
        self.save()

    def prepare(self):
        records = self.containers()
        self.inventory_known = True
        self.initial_ids = {row["ID"] for row in records}
        self.report["initial"] = [{key: row.get(key) for key in ["ID", "Service", "State", "Image"]} for row in records]
        if any(row["Service"] != "postgres" and row["State"] not in {"exited", "dead", "created"} for row in records) or any(port_open(port) for port in [15173, 18080]):
            raise RuntimeError("RUNTIME_BUSY")
        db = [row for row in records if row["Service"] == "postgres"]
        if len(db) > 1 or db and db[0]["State"] not in {"running", "exited", "created"}:
            raise RuntimeError("DB_STATE_UNKNOWN")
        self.command("build", shared.COMPOSE + ["build", "backend", "frontend"], 600)
        if not db or db[0]["State"] != "running":
            self.started.append("postgres")
            self.command("start-db", shared.COMPOSE + ["up", "-d", "--wait", "postgres"])
        self.migrations("before")
        self.command("migrate", shared.COMPOSE + ["run", "--rm", "--no-deps", "backend"] + shared.MANAGE + ["migrate", "--noinput"])
        self.migrations("after")
        self.started.extend(["backend", "frontend"])
        self.command("start-app", shared.COMPOSE + ["up", "-d", "--no-deps", "backend", "frontend"])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        deadline = time.monotonic() + 90
        for path in ["http://127.0.0.1:18080/api/health/live", "http://127.0.0.1:18080/api/health/ready", "http://127.0.0.1:15173/"]:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("READINESS_TIMEOUT")
                try:
                    with opener.open(path, timeout=3) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.HTTPError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("READINESS_TIMEOUT") from None
                time.sleep(.3)
        self.report["images"] = self.command("image-identities", shared.COMPOSE + ["images", "--format", "json"])

    def exercise(self):
        journal = ROOT / "e2e/.artifacts/attempts.json"
        attempts = json.loads(journal.read_text()) if journal.exists() else []
        # Original three + three + four individual approvals; retain every attempt.
        if len(attempts) >= 10:
            raise RuntimeError("SESSION_RUN_LIMIT")
        attempts.append(self.lock.owner["run_id"])
        journal.write_text(json.dumps(attempts) + "\n")
        self.command("browser", ["node", "e2e/node_modules/@playwright/test/cli.js", "test", "--config=e2e/playwright.config.ts"],
                     1200 if self.capture else 900,
                     {"FITLOG_E2E_RUN_ID": self.lock.owner["run_id"], "FITLOG_E2E_CAPTURE": "1" if self.capture else "0"})
        validate_browser_result(self.output, self.lock.owner["run_id"])
        self.report["browser_result_confirmed"] = True
        if self.capture:
            if not (self.output / "capture-safe.json").is_file():
                raise RuntimeError("CAPTURE_NOT_CONFIRMED")
            videos = list((self.output / "videos-quarantine").glob("*.webm"))
            if len(videos) != 2:
                raise RuntimeError("CAPTURE_COUNT_MISMATCH")
            for index, video in enumerate(videos):
                self.command("video-decode-" + str(index), ["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], 60)
            self.report["capture"] = {"environment": "local", "decode_verified": True, "videos": len(videos), "human_visual_playback": "not_run"}

    def stop_owned(self):
        self.cleaning = True
        safe = self.safe
        # Attempt every owned stop even if recording or a previous stop failed.
        if self.started:
            try:
                self.command("stop-owned", shared.COMPOSE + ["stop", *reversed(self.started)])
            except (Exception, KeyboardInterrupt):
                safe = False
        try:
            if self.inventory_known:
                records = self.containers()
                if any(row["ID"] not in self.initial_ids and row["State"] not in {"exited", "dead", "created"} for row in records):
                    safe = False
                if any(row["Service"] in self.started and row["State"] not in {"exited", "dead", "created"} for row in records):
                    safe = False
            if any(service in self.started for service in ["backend", "frontend"]) and any(port_open(port) for port in [15173, 18080]):
                safe = False
        except (Exception, KeyboardInterrupt):
            safe = False
        self.report["cleanup"] = {"owned_services": self.started, "stop_confirmed": safe}
        return safe and self.safe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    if any(os.environ.get(key) for key in ["DEBUG", "PWDEBUG", "NODE_DEBUG"]):
        print("VERBOSE_BLOCKED")
        return 1
    common, branch = shared.git_context(ROOT)
    # git_context already rejects trunk; later task branches can reuse this suite.
    if common.resolve() != EXPECTED_COMMON.resolve():
        print("WORKTREE_MISMATCH")
        return 1
    run_id = uuid.uuid4().hex[:12]
    output = ROOT / "e2e/.artifacts" / run_id
    lock = shared.RuntimeLock(common, ROOT, branch, run_id)
    driver = LocalDriver(lock, output, args.capture)
    driver.report["source_before"] = snapshot()
    driver.report["toolchain"] = {
        "node": subprocess.check_output(["node", "--version"]).decode().strip(),
        "os": platform.platform(),
        "packages": json.loads((ROOT / "e2e/package.json").read_text())["devDependencies"],
        "lock_sha256": hashlib.sha256((ROOT / "e2e/package-lock.json").read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256((ROOT / "e2e/fixtures/pixels.png").read_bytes()).hexdigest(),
    }
    session = RuntimeSession(lock, driver)
    handlers = {}
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    for sig in (signal.SIGTERM, signal.SIGINT):
        handlers[sig] = signal.signal(sig, interrupted)
    try:
        passed = session.run()
        driver.report.update(lifecycle=session.report, ended_at=shared.now(), source_after=snapshot())
        if driver.report["source_before"] != driver.report["source_after"]:
            passed = False
            driver.report["source_changed"] = True
        try:
            driver.save()
        except OSError:
            driver.persistence_failed = True
        if driver.persistence_failed:
            passed = False
        print(json.dumps({"run_id": run_id, "passed": passed, "lock_released": session.report["lock_released"]}))
        return 0 if passed else 1
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(main())

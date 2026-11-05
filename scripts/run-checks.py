#!/usr/bin/env python3
"""FitLog's fixed local checks. No Git/gh commands or quality flag writes.

Caller must first verify the adopted common Git directory (see run-checks.md).
Only --help is accepted; registry and output paths are not CLI parameters.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import tomllib
import uuid

COMPOSE = ["docker", "compose", "--project-name", "fitlog-dev", "-f", "compose.yaml"]
EXPECTED = ["compose-build", "backend-lint", "backend-types", "django-check",
            "backend-migrate", "migration-drift", "backend-tests", "frontend-lint",
            "frontend-types", "frontend-tests", "frontend-build"]
MANAGE = ["uv", "run", "--frozen", "--no-sync", "python", "manage.py"]
MIGRATION_QUERY = """
import json
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
loader = MigrationLoader(connection)
applied = set(MigrationRecorder(connection).applied_migrations())
# Replaced migrations remain legitimate applied nodes for squashed histories.
known = set(loader.disk_migrations)
for migration in loader.disk_migrations.values():
    known.update(migration.replaces or [])
loader.check_consistent_history(connection)
print('FITLOG_MIGRATIONS:' + json.dumps({
    'applied': sorted(applied), 'graph': sorted(loader.graph.nodes),
    'unknown': sorted(applied - known), 'consistent': True}))
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def git_context(root):
    dotgit = root / ".git"
    if dotgit.is_file():
        text = dotgit.read_text().strip()
        if not text.startswith("gitdir: "):
            raise ValueError("Invalid .git pointer")
        admin = (root / text[8:]).resolve()
    elif dotgit.is_dir():
        admin = dotgit.resolve()
    else:
        raise ValueError("Missing Git metadata")
    common = admin
    if (admin / "commondir").is_file():
        common = (admin / (admin / "commondir").read_text().strip()).resolve()
    head = (admin / "HEAD").read_text().strip()
    if not head.startswith("ref: refs/heads/"):
        raise ValueError("A named task branch is required")
    branch = head[len("ref: refs/heads/"):]
    if branch in {"main", "master"}:
        raise ValueError("Do not run checks on trunk")
    return common, branch


def validate_registry(registry, root):
    checks = registry.get("checks")
    if not isinstance(checks, list) or len(checks) != 11 or not all(isinstance(c, dict) for c in checks) or [c.get("id") for c in checks] != EXPECTED:
        raise ValueError("Registry must contain the fixed 11 check IDs in order")
    for check in checks:
        argv, cwd = check.get("argv"), check.get("cwd")
        env, timeout = check.get("env"), check.get("timeout_seconds")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and "\0" not in a for a in argv):
            raise ValueError("argv must be a nonempty string array")
        if argv[:len(COMPOSE)] != COMPOSE or argv[len(COMPOSE):len(COMPOSE)+1] not in [["build"], ["run"]]:
            raise ValueError("Only fixed Compose build/run registry commands are supported")
        if not isinstance(cwd, str) or not (root / cwd).resolve().is_relative_to(root.resolve()) or not (root / cwd).is_dir():
            raise ValueError("cwd must exist inside this worktree")
        if not isinstance(env, dict) or not all(isinstance(k, str) and k and "=" not in k and "\0" not in k and isinstance(v, str) and "\0" not in v for k, v in env.items()):
            raise ValueError("env must map valid names to strings")
        if type(timeout) is not int or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
    return checks


class RuntimeLock:
    def __init__(self, common, root, branch, run_id):
        self.path = common / "fitlog-runtime.lock"
        self.owner = {"task": branch, "branch": branch, "worktree": str(root),
                      "host": socket.gethostname(), "pid": os.getpid(),
                      "started_at": now(), "run_id": run_id,
                      "resources": ["fitlog-dev Compose/DB/images"]}
        self.acquired = False
        self.identity = None

    def acquire(self):
        self.path.mkdir()
        self.identity = (self.path.stat().st_dev, self.path.stat().st_ino)
        try:
            with (self.path / "owner.json").open("x") as file:
                json.dump(self.owner, file, indent=2)
            self.acquired = True
        except BaseException:
            # Only our own partial owner file and empty directory may be removed.
            owner_path = self.path / "owner.json"
            if owner_path.is_file():
                try:
                    content = json.loads(owner_path.read_text())
                except (ValueError, OSError):
                    content = None
                if content == self.owner:
                    owner_path.unlink()
            if not any(self.path.iterdir()):
                self.path.rmdir()
            raise

    def owned(self):
        if not self.acquired or self.path.is_symlink():
            return False
        try:
            identity = (self.path.stat().st_dev, self.path.stat().st_ino)
            return identity == self.identity and not (self.path / "owner.json").is_symlink() and json.loads((self.path / "owner.json").read_text()) == self.owner
        except (OSError, ValueError):
            return False

    def release(self):
        if not self.owned() or set(p.name for p in self.path.iterdir()) != {"owner.json"}:
            raise RuntimeError("Lock ownership/content changed; leave untouched")
        (self.path / "owner.json").unlink()
        self.path.rmdir()
        self.acquired = False


class UnsafeProcessGroup(RuntimeError):
    """Host descendants could not be confirmed stopped; retain the runtime lock."""


class CapturedOutput:
    def __init__(self, code, text, error):
        self.code, self.text, self.error = code, text, error


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError as error:
        raise UnsafeProcessGroup(f"Cannot confirm process group {pgid}: {error}") from error


def _wait_for_group_exit(child):
    """The leader exiting does not prove that its descendants have exited."""
    for sig, grace in [(signal.SIGTERM, 10), (signal.SIGKILL, 2)]:
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            pass
        except OSError:
            # Permission errors can be transient while the group is exiting.
            # Only confirmed disappearance below permits release.
            pass
        deadline = time.monotonic() + grace
        while True:
            child.poll()  # Reap the leader, including when only descendants remain.
            try:
                if not group_exists(child.pid):
                    child.wait()
                    return
            except UnsafeProcessGroup:
                pass  # Retry within the deadline; never interpret EPERM as gone.
            if time.monotonic() >= deadline:
                break
            time.sleep(.05)
    raise UnsafeProcessGroup(f"Process group {child.pid} remains after KILL")


def stop_group(child):
    """Defer repeated interrupts until the termination attempt is complete."""
    handlers, deferred = {}, []
    def defer(signum, frame):
        deferred.append(signum)
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, defer)
        _wait_for_group_exit(child)
    except BaseException as error:
        raise UnsafeProcessGroup(f"Group {child.pid} termination unconfirmed: {error}") from error
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    return deferred


def execute_process(argv, cwd, env, timeout, log, cleanup=False):
    """Cleanup commands may capture small outputs in memory when disk logging fails."""
    output, log_error = None, None
    try:
        output = log.open("w")
    except OSError as error:
        if not cleanup:
            error.processes_stopped = True  # No child has been started yet.
            raise
        log_error = error
    try:
        child = subprocess.Popen(argv, cwd=cwd, env={**os.environ, **env},
                                 stdout=output if output else subprocess.PIPE, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        try:
            if output:
                code = child.wait(timeout=timeout)
                text = None
            else:
                captured, _ = child.communicate(timeout=timeout)
                code, text = child.returncode, captured.decode(errors="replace")
        except BaseException as error:
            deferred = stop_group(child)
            error.processes_stopped = True
            error.deferred_signals = deferred
            raise
        if group_exists(child.pid):
            stop_group(child)
            error = ChildProcessError("Descendants remained after command leader exited")
            error.processes_stopped = True
            raise error
        return CapturedOutput(code, text, log_error) if log_error else code
    finally:
        if output:
            output.close()


class AbortRun(RuntimeError):
    pass


class ChecksRun:
    def __init__(self, root, execute=execute_process):
        self.root = root.resolve()
        self.execute = execute
        common, branch = git_context(self.root)
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
        self.lock = RuntimeLock(common, self.root, branch, self.run_id)
        self.output = self.root / ".quality-check-runs" / self.run_id
        self.output.mkdir(parents=True)
        self.report = {"run_id": self.run_id, "started_at": now(), "worktree": str(self.root),
                       "branch": branch, "common_git_dir": str(common), "checks": [],
                       "operations": [], "errors": [], "cleanup": {"lock_released": False}}
        self.started_db = False
        self.db_ready = False
        self.initial_ids = set()
        self.inventory_known = False
        self.failed = False
        self.host_processes_safe = True
        self.captured_outputs = {}

    def save(self):
        temp = self.output / "results.json.tmp"
        temp.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temp.replace(self.output / "results.json")
        lines = ["# Local checks", "", f"Run: {self.run_id}", "", "| id | status | exit |", "|---|---|---|"]
        lines += [f'| {c["id"]} | {c["status"]} | {c["exit_code"]} |' for c in self.report["checks"]]
        lines += ["", "Cleanup: " + json.dumps(self.report["cleanup"]), "", "Errors: " + json.dumps(self.report["errors"], ensure_ascii=False)]
        (self.output / "summary.md").write_text("\n".join(lines) + "\n")

    def error(self, error):
        self.failed = True
        self.report["errors"].append(f"{type(error).__name__}: {error}")

    def persist(self, cleanup=False):
        try:
            self.save()
        except OSError as error:
            self.error(error)
            print(f"Cannot save results: {error}", file=sys.stderr, flush=True)
            if not cleanup:
                raise AbortRun("Result save failed") from error

    def command(self, name, argv, timeout=120, env=None, cwd=None, entry=None, cleanup=False):
        if not self.lock.owned():
            raise AbortRun("Runtime lock ownership lost")
        if entry is None:
            entry = {"id": name}
            self.report["operations"].append(entry)
        log = self.output / (name + ".log")
        entry.update(argv=argv, cwd=str(cwd or self.root), env=env or {},
                     started_at=now(), ended_at=None, exit_code=None, status="running", log_path=str(log))
        try:
            self.persist(cleanup)
            print(f"START {name}", flush=True)
            previous_safe = self.host_processes_safe
            self.host_processes_safe = False
            try:
                result = self.execute(argv, cwd or self.root, env or {}, timeout, log, cleanup=cleanup)
            except BaseException as error:
                if getattr(error, "processes_stopped", False):
                    self.host_processes_safe = previous_safe
                if getattr(error, "deferred_signals", None):
                    entry["deferred_signals"] = error.deferred_signals
                raise
            else:
                self.host_processes_safe = previous_safe
            if isinstance(result, CapturedOutput):
                code = result.code
                self.captured_outputs[name] = result.text
                entry["log_error"] = str(result.error)
                entry["captured_output"] = result.text
                self.error(result.error)
            else:
                code = result
            entry.update(exit_code=code, status="passed" if code == 0 else "failed")
            if code:
                self.failed = True
            if code < 0:
                raise ChildProcessError(f"Command terminated by signal {-code}")
            return code
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt, UnsafeProcessGroup) as error:
            if isinstance(error, UnsafeProcessGroup):
                self.host_processes_safe = False
            entry.update(status="aborted", error=f"{type(error).__name__}: {error}")
            raise AbortRun(entry["error"]) from error
        finally:
            entry["ended_at"] = now()
            self.persist(cleanup)

    def require(self, name, argv, timeout=120, cleanup=False):
        if self.command(name, argv, timeout, cleanup=cleanup):
            raise AbortRun(f"{name} failed")
        if name in self.captured_outputs:
            return self.captured_outputs[name]
        return (self.output / (name + ".log")).read_text()

    def containers(self, name, cleanup=False):
        raw = self.require(name, COMPOSE + ["ps", "--all", "--format", "json"], 60, cleanup).strip()
        records = json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines()]
        if not isinstance(records, list) or any(not isinstance(r, dict) or not r.get("State") or not r.get("Service") for r in records):
            raise AbortRun("Unknown Compose inventory format")
        return records

    def migrations(self, name, build=False, cleanup=False):
        run = COMPOSE + ["run", "--rm"] + (["--build"] if build else []) + ["--no-deps", "backend"]
        self.require(name + "-plan", run + MANAGE + ["showmigrations", "--plan"], 900 if build else 120, cleanup)
        text = self.require(name + "-graph", run + MANAGE + ["shell", "-c", MIGRATION_QUERY], 120, cleanup)
        marker = "FITLOG_MIGRATIONS:"
        rows = [line[len(marker):] for line in text.splitlines() if line.startswith(marker)]
        if len(rows) != 1:
            raise AbortRun("Migration graph record missing/ambiguous")
        state = json.loads(rows[0])
        self.report.setdefault("migrations", {})[name] = state
        if state.get("consistent") is not True or state.get("unknown") != []:
            raise AbortRun("Unknown applied migrations or inconsistent history; do not migrate/reset")

    def cleanup(self):
        safe = self.host_processes_safe
        try:
            if not self.lock.acquired:
                return
            if not self.lock.owned():
                raise AbortRun("Lock owner changed; no further runtime operations")
            if self.inventory_known:
                try:
                    records = self.containers("containers-after", cleanup=True)
                    residual = [r for r in records if r["Service"] != "postgres" and r.get("ID") not in self.initial_ids and r["State"] not in {"exited", "dead"}]
                    if residual:
                        raise AbortRun("New containers remain; retain lock and inspect operation logs")
                except (Exception, KeyboardInterrupt) as error:
                    safe = False
                    self.error(error)
            try:
                if self.db_ready and safe:
                    self.migrations("migrations-final", cleanup=True)
            except (Exception, KeyboardInterrupt) as error:
                self.error(error)
            finally:
                try:
                    if self.started_db:
                        self.require("db-stop", COMPOSE + ["stop", "postgres"], cleanup=True)
                        records = self.containers("db-after-stop", cleanup=True)
                        if any(r["Service"] == "postgres" and r["State"] not in {"exited", "dead", "created"} for r in records):
                            raise AbortRun("DB stop not confirmed")
                except (Exception, KeyboardInterrupt) as error:
                    safe = False
                    self.error(error)
                finally:
                    try:
                        records = self.containers("containers-final", cleanup=True)
                        if any(r["Service"] != "postgres" and r.get("ID") not in self.initial_ids and r["State"] not in {"exited", "dead"} for r in records):
                            raise AbortRun("Containers remain after final migration record; retain lock")
                    except (Exception, KeyboardInterrupt) as error:
                        safe = False
                        self.error(error)
        except (Exception, KeyboardInterrupt) as error:
            safe = False
            self.error(error)
        finally:
            try:
                if self.lock.acquired and safe and self.host_processes_safe:
                    self.lock.release()
                    self.report["cleanup"]["lock_released"] = True
            except (Exception, KeyboardInterrupt) as error:
                self.error(error)
            self.report["cleanup"].update(db_started_by_run=self.started_db,
                                          lock_exists_after=self.lock.path.exists())

    def run(self):
        print(f"Results: {self.output}", flush=True)
        handlers = {}
        def interrupted(signum, frame):
            raise KeyboardInterrupt(f"signal {signum}")
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                handlers[sig] = signal.signal(sig, interrupted)
            raw = (self.root / ".ai-dev/project.toml").read_bytes()
            checks = validate_registry(tomllib.loads(raw.decode()), self.root)
            self.report.update(registry_sha256=hashlib.sha256(raw).hexdigest(),
                               script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            self.report["checks"] = [dict(c, status="not_run", reason="preparation not completed", started_at=None, ended_at=None, exit_code=None, log_path=None) for c in checks]
            self.persist()
            self.lock.acquire()
            records = self.containers("containers-before")
            self.inventory_known = True
            self.initial_ids = {r.get("ID") for r in records}
            if any("-run-" in r.get("Name", "") and r["State"] not in {"exited", "dead"} for r in records):
                raise AbortRun("Pre-existing one-off container; runtime is still in use")
            db = [r for r in records if r["Service"] == "postgres"]
            if len(db) > 1 or (db and db[0]["State"] not in {"running", "exited", "created"}):
                raise AbortRun("Unknown/multiple DB state; leave untouched")
            self.report["db_initial"] = db
            if not db or db[0]["State"] != "running":
                self.started_db = True
                self.require("db-start", COMPOSE + ["up", "-d", "--wait", "postgres"], 180)
            self.db_ready = True
            self.migrations("migrations-before", build=True)
            for index, (check, entry) in enumerate(zip(checks, self.report["checks"])):
                try:
                    if check["id"] == "backend-migrate":
                        self.migrations("migrations-pre-migrate")
                    code = self.command(check["id"], check["argv"], check["timeout_seconds"], check["env"], self.root / check["cwd"], entry)
                    entry.pop("reason", None)
                    if check["id"] == "backend-migrate":
                        self.migrations("migrations-post-migrate")
                    if code and check["id"] == "compose-build":
                        raise AbortRun("compose-build failed")
                except (Exception, KeyboardInterrupt) as error:
                    for remaining in self.report["checks"][index:]:
                        if remaining["status"] == "not_run":
                            remaining["reason"] = f"aborted: {error}"
                    raise
        except (Exception, KeyboardInterrupt) as error:
            self.error(error)
            for entry in self.report["checks"]:
                if entry["status"] == "not_run" and entry["reason"] == "preparation not completed":
                    entry["reason"] = f"preparation failed: {error}"
        finally:
            # A repeated interrupt must not skip the remaining cleanup attempts.
            for sig in handlers:
                signal.signal(sig, signal.SIG_IGN)
            try:
                self.cleanup()
                self.report["ended_at"] = now()
                self.persist(cleanup=True)
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
        passed = len(self.report["checks"]) == 11 and all(c["status"] == "passed" for c in self.report["checks"])
        return 0 if passed and not self.failed and self.report["cleanup"]["lock_released"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        return ChecksRun(Path(__file__).resolve().parents[1]).run()
    except (OSError, ValueError) as error:
        print(f"Cannot initialize checks: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

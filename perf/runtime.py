"""Docker ownership boundary. Only resources created in this run are removable."""
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def owned_cleanup(call, run_id, resources):
    for kind, name in reversed(resources):
        if kind not in {"container", "volume", "network"} or not re.fullmatch(
                "perf_" + re.escape(run_id) + r"_[a-z]+", name):
            raise ValueError("foreign resource name")
        data = json.loads(call(["docker", kind, "inspect", name]))
        labels = data[0].get("Config", {}).get("Labels", {}) if kind == "container" else data[0].get("Labels", {})
        if (not labels or labels.get("fitlog.perf.run") != run_id
                or labels.get("fitlog.perf.worktree") != str(ROOT)):
            raise ValueError("foreign resource owner")
        if kind == "container":
            call(["docker", "container", "stop", "--time", "10", name])
        call(["docker", kind, "rm", name])


def existing_resources(call, run_id, resources, states):
    """Reconcile intents. An absent uncertain create is not proof it completed."""
    present = []
    for kind, name in resources:
        if kind not in {"container", "volume", "network"} or not re.fullmatch(
                "perf_" + re.escape(run_id) + r"_[a-z]+", name):
            raise ValueError("foreign resource intent")
        argv = ["docker", kind, "ls"] + (["--all"] if kind == "container" else [])
        names = call([*argv, "--format", "{{.Names}}" if kind == "container" else "{{.Name}}"])
        if name in names.splitlines():
            present.append((kind, name))
        elif states.get(name) != "created":
            raise ValueError("creation outcome still unknown; retain lock and intent")
    return present


ROOT = Path(__file__).resolve().parents[1]
COMMON = Path("/Users/saki/project/FitLog/.git")


def command(argv, *, timeout=300):
    process = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=2)
        raise
    if process.returncode:
        # Fixed local commands only; do not relay product response/log contents.
        raise RuntimeError(f"command failed: {argv[:3]} exit={process.returncode}")
    return stdout


def snapshot():
    tracked = command(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"]).split("\0")
    digest = hashlib.sha256()
    for name in sorted(set(filter(None, tracked))):
        path = ROOT / name
        if path.is_file() and not path.is_symlink():
            digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return {"commit": command(["git", "rev-parse", "HEAD"]).strip(),
            "source_sha256": digest.hexdigest()}


@contextlib.contextmanager
def runtime_lock(task):
    actual = Path(command(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]).strip()).resolve()
    if actual != COMMON:
        raise ValueError("unexpected shared git directory")
    lock = actual / "fitlog-runtime.lock"
    owner = {"task": task, "worktree": str(ROOT), "branch": command(["git", "branch", "--show-current"]).strip(),
             "host": socket.gethostname(), "pid": os.getpid(), "started_at": datetime.now(UTC).isoformat(),
             "resources": ["fixed port 18080", "performance containers", "dev images"]}
    lock.mkdir()  # EEXIST is contention, never stale-lock recovery.
    identity = (lock.stat().st_dev, lock.stat().st_ino)
    owner_path = lock / "owner.json"
    try:
        with owner_path.open("x") as stream:
            json.dump(owner, stream)
    except BaseException:
        # Only remove an empty directory just created by this process.
        if not owner_path.exists():
            lock.rmdir()
        raise
    def owned():
        try:
            return (not lock.is_symlink() and not owner_path.is_symlink()
                    and (lock.stat().st_dev, lock.stat().st_ino) == identity
                    and json.loads(owner_path.read_text()) == owner)
        except (ValueError, OSError):
            return False
    safe = {"release": True, "owned": owned}
    try:
        yield safe
    finally:
        if safe["release"] and owned() and {p.name for p in lock.iterdir()} == {"owner.json"}:
            owner_path.unlink()
            lock.rmdir()


def ensure_port_free():
    with socket.socket() as probe:
        # Reuse a closed test server's TIME_WAIT sockets, never an active listener.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", 18080))


class Runtime:
    def __init__(self, folder, owned=lambda: True):
        self.run_id = uuid.uuid4().hex
        self.prefix = "perf_" + self.run_id
        self.resources = []
        self.resource_states = {}
        self.owned = owned
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.stats = []
        self.sampling_stop = threading.Event()
        self.ledger = {"run_id": self.run_id, "worktree": str(ROOT),
                       "owner_pid": os.getpid(),
                       "branch": command(["git", "branch", "--show-current"]).strip(),
                       "resources": self.resources, "resource_states": self.resource_states}
        self.save()

    def save(self):
        temporary = self.folder / "ownership.json.tmp"
        with temporary.open("w") as stream:
            json.dump(self.ledger, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.folder / "ownership.json")

    def call(self, argv, *, timeout=300):
        if not self.owned():
            raise RuntimeError("runtime lock ownership lost")
        remaining = 1740 - (time.monotonic() - self.started)  # reserve 60s for cleanup
        if remaining <= 0:
            raise TimeoutError("performance run exceeded 30 minutes")
        return command(argv, timeout=min(timeout, remaining))

    def create(self, kind, suffix, argv):
        name = self.prefix + "_" + suffix
        # Creation never reuses resources, even if a previous run used the same label.
        listing = ["docker", kind, "ls"] + (["--all"] if kind == "container" else [])
        names = self.call([*listing, "--format", "{{.Name}}" if kind != "container" else "{{.Names}}"])
        if name in names.splitlines():
            raise ValueError("resource already exists")
        labels = ["--label", "fitlog.perf.run=" + self.run_id,
                  "--label", "fitlog.perf.worktree=" + str(ROOT)]
        self.resources.append((kind, name))
        self.resource_states[name] = "creating"
        self.save()
        try:
            self.call(["docker", kind, "create", *labels, *argv, name] if kind != "container" else
                      ["docker", "container", "create", "--name", name, *labels, *argv])
        except BaseException:
            self.resource_states[name] = "unknown"
            self.save()
            raise
        self.resource_states[name] = "created"
        self.save()
        return name

    def prepare(self, scenario):
        ensure_port_free()
        info = json.loads(self.call(["docker", "info", "--format", "{{json .}}"] ))
        if info["MemTotal"] < 4 * 1024 ** 3 or shutil.disk_usage(ROOT).free < 2 * 1024 ** 3:
            raise ValueError("insufficient local resources")
        self.call(["docker", "compose", "--project-name", "fitlog-dev", "-f", "compose.yaml", "build", "backend"], timeout=900)
        compose = json.loads(self.call(["docker", "compose", "-f", "compose.yaml", "config", "--format", "json"]))
        pg_image = compose["services"]["postgres"]["image"]
        self.call(["docker", "image", "inspect", pg_image])
        network = self.create("network", "net", [])
        db_volume = self.create("volume", "data", [])
        media = self.create("volume", "media", [])
        db_name = self.create("container", "db", ["--network", network,
            "--mount", f"type=volume,src={db_volume},dst=/var/lib/postgresql/data",
            "-e", "POSTGRES_DB=" + self.prefix, "-e", "POSTGRES_USER=fitlog",
            "-e", "POSTGRES_PASSWORD=fitlog-local-only-not-a-secret", pg_image])
        self.call(["docker", "container", "start", db_name])
        ready = False
        for _ in range(60):
            try:
                self.call(["docker", "exec", db_name, "pg_isready", "-U", "fitlog", "-d", self.prefix], timeout=5)
                ready = True
                break
            except RuntimeError:
                time.sleep(.5)
        if not ready:
            raise RuntimeError("isolated PostgreSQL not ready")
        env = {**compose["services"]["backend"]["environment"],
               "POSTGRES_DB": self.prefix, "POSTGRES_HOST": db_name, "PERF_RUN_ID": self.run_id,
               "PYTHONPATH": "/probe:/app", "DJANGO_SETTINGS_MODULE": "perf.local_settings"}
        arguments = ["--network", network, "--memory", "1g", "-p", "127.0.0.1:18080:8000",
                     "--mount", f"type=bind,src={ROOT / 'perf'},dst=/probe/perf,readonly",
                     "--mount", f"type=volume,src={media},dst=/app/media_assets/private"]
        for key, value in env.items():
            arguments += ["-e", f"{key}={value}"]
        self.backend = self.create("container", "app", [*arguments, "fitlog-dev-backend",
             "python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"])
        self.call(["docker", "container", "start", self.backend])
        self.call(["docker", "exec", self.backend, "python", "manage.py", "migrate", "--noinput"])
        counts = json.loads(self.call(["docker", "exec", self.backend, "python", "-m", "perf.seed", "seed", scenario]))
        from perf.client import Session
        for _ in range(60):
            try:
                if Session().request("GET", "/api/health/ready")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError("API readiness failed")
        self.sampler = threading.Thread(target=self.sample, daemon=True)
        self.sampler.start()
        versions = json.loads(self.call(["docker", "exec", self.backend, "python", "-c",
            "import json,sys,django,psycopg,PIL; print(json.dumps({'python':sys.version.split()[0],"
            "'django':django.get_version(),'psycopg':psycopg.__version__,'pillow':PIL.__version__}))"]))
        return {"database_counts": counts, "docker_memory": info["MemTotal"],
                "docker_cpus": info["NCPU"], "host": platform.platform(),
                "machine": platform.machine(), "host_python": platform.python_version(),
                "backend_image": json.loads(self.call(["docker", "image", "inspect", "fitlog-dev-backend"]))[0]["Id"],
                "postgres_image": pg_image, "versions": versions,
                "server": "Django runserver --noreload; DEBUG=false; 1GiB", "snapshot": snapshot()}

    def sample(self):
        while not self.sampling_stop.is_set():
            try:
                values = command(["docker", "stats", "--no-stream", "--format", "{{json .}}", self.backend,
                                  self.prefix + "_db"], timeout=10)
                self.stats.append({"at": datetime.now(UTC).isoformat(),
                                   "containers": [json.loads(x) for x in values.splitlines()]})
            except Exception as error:
                self.stats.append({"at": datetime.now(UTC).isoformat(), "not_run": type(error).__name__})
            self.sampling_stop.wait(5)

    def audit(self, scenario, mode):
        return json.loads(self.call(["docker", "exec", self.backend, "python", "-m", "perf.seed",
                                      "audit-load" if mode == "load" else "audit", scenario]))


def unit_tests():
    with runtime_lock("Issue55-perf-unit-tests"):
        ensure_port_free()
        return subprocess.call([sys.executable, "-B", "-m", "unittest", "discover", "-s", "perf", "-t", ".", "-p", "test_*.py"], cwd=ROOT)


def main():
    import argparse

    from perf.runner import cleanup_signals, run_load

    parser = argparse.ArgumentParser(description="Bounded local-only performance system test")
    parser.add_argument("mode", choices=["unit-tests", "smoke", "load", "image", "auth-burst", "cleanup"])
    parser.add_argument("--record", help="own result-folder UUID for explicit cleanup")
    parser.add_argument("--scenario", choices=["normal", "boundary"], default="normal")
    args = parser.parse_args()
    if args.mode == "cleanup":
        from perf.cleanup import cleanup_record
        return cleanup_record(args.record)
    if args.record is not None:
        parser.error("--record is only valid with cleanup")
    if args.mode == "unit-tests":
        return unit_tests()
    with runtime_lock("Issue55-" + args.mode) as safe:
        runtime = Runtime(ROOT / "docs/superpowers/plans/perf-results" / uuid.uuid4().hex, safe["owned"])
        result = {"schema_version": 1, "run_id": runtime.run_id, "scenario": args.scenario,
                  "mode": args.mode, "started_at": datetime.now(UTC).isoformat(), "status": "fail",
                  "started_at_jst": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
                  "aws": "not_run", "cleanup": "not_run"}
        workers_stopped = True  # No workers exist during preparation.
        try:
            result["environment"] = runtime.prepare(args.scenario)
            if time.monotonic() - runtime.started > 1740 - (370 if args.mode == "load" else 160):
                raise TimeoutError("not enough work budget for a complete measurement")
            workers_stopped = False  # Caller needs positive evidence after entering a job manager.
            if args.mode in {"smoke", "load"}:
                measured = run_load(args.scenario, args.mode)
            else:
                from perf.special import run_special
                measured = run_special(args.mode)
            result.update(measured)
            workers_stopped = measured["workers_stopped"]
            if not workers_stopped:
                safe["release"] = False
                raise RuntimeError("workers still alive")
            result["after_counts"] = runtime.audit(args.scenario, args.mode)
            result["snapshot_after"] = snapshot()
            result["status"] = measured["summary"]["status"]
            if result["environment"]["snapshot"] != result["snapshot_after"]:
                result["status"] = "fail"
                result["snapshot_changed"] = True
        except BaseException as error:
            result["error_type"] = type(error).__name__
            result["status"] = "fail"
            print(f"run failed: {type(error).__name__}", flush=True)
        finally:
            permit_cleanup = safe["release"] and workers_stopped
            safe["release"] = False  # Only a fully confirmed teardown can enable release again.
            deferred = []
            try:
                with cleanup_signals() as deferred:
                    runtime.sampling_stop.set()
                    if hasattr(runtime, "sampler"):
                        runtime.sampler.join(timeout=12)
                        if runtime.sampler.is_alive():
                            permit_cleanup = False
                    if not permit_cleanup or not safe["owned"]():
                        raise RuntimeError("worker, sampler or lock ownership unconfirmed")
                    cleanup_deadline = min(runtime.started + 1800, time.monotonic() + 60)
                    def cleanup_call(argv):
                        if not safe["owned"]():
                            raise RuntimeError("runtime lock ownership lost")
                        remaining = cleanup_deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("cleanup deadline")
                        return command(argv, timeout=remaining)
                    present = existing_resources(cleanup_call, runtime.run_id, runtime.resources, runtime.resource_states)
                    owned_cleanup(cleanup_call, runtime.run_id, present)
                    if any(kind == "container" and name.endswith("_app") for kind, name in runtime.resources):
                        ensure_port_free()
                    result["cleanup"] = "pass"
                    safe["release"] = True
            except BaseException as error:
                result["cleanup"] = type(error).__name__
                safe["release"] = False
                result["status"] = "fail"
            if deferred:
                result["deferred_signals"] = deferred
                result["status"] = "fail"
            result["resource_samples"] = runtime.stats
            result["finished_at"] = datetime.now(UTC).isoformat()
            result["duration_seconds"] = time.monotonic() - runtime.started
            (runtime.folder / "results.json").write_text(json.dumps(result, indent=2))
            with (runtime.folder / "requests.jsonl").open("w") as stream:
                for row in result.get("rows", []):
                    stream.write(json.dumps(row) + "\n")
            print(json.dumps({"result": str(runtime.folder / "results.json"), "status": result["status"],
                              "cleanup": result["cleanup"]}), flush=True)
        return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())

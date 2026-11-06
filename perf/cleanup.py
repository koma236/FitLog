"""Explicit recovery for a finished own run. Never reclaims an existing lock."""
import json
import os
import re

from perf.runtime import ROOT, command, owned_cleanup, runtime_lock


def validate_record(record_id):
    if not isinstance(record_id, str) or not re.fullmatch(r"[a-f0-9]{32}", record_id):
        raise ValueError("record folder UUID required")
    folder = ROOT / "docs/superpowers/plans/perf-results" / record_id
    path = folder / "ownership.json"
    if folder.is_symlink() or path.is_symlink():
        raise ValueError("symlink record refused")
    record = json.loads(path.read_text())
    if (record.get("worktree") != str(ROOT) or record.get("branch") != command(
            ["git", "branch", "--show-current"]).strip()
            or not re.fullmatch(r"[a-f0-9]{32}", record.get("run_id", ""))
            or type(record.get("owner_pid")) is not int or record["owner_pid"] <= 1):
        raise ValueError("not an own run record")
    prefix = "perf_" + record["run_id"]
    allowed = {("network", prefix + "_net"), ("volume", prefix + "_data"),
               ("volume", prefix + "_media"), ("container", prefix + "_db"), ("container", prefix + "_app")}
    resources = [tuple(x) for x in record.get("resources", [])]
    if len(resources) != len(set(resources)) or not set(resources) <= allowed:
        raise ValueError("unexpected resource in record")
    try:
        os.kill(record["owner_pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError("record owner still alive")
    return folder, record


def cleanup_record(record_id):
    with runtime_lock("Issue55-explicit-cleanup") as safe:
        folder, record = validate_record(record_id)
        resources = []
        for kind, name in record["resources"]:
            args = ["docker", kind, "ls"] + (["--all"] if kind == "container" else [])
            names = command([*args, "--format", "{{.Names}}" if kind == "container" else "{{.Name}}"])
            if name in names.splitlines():
                resources.append((kind, name))
        try:
            def call(argv):
                if not safe["owned"]():
                    raise ValueError("runtime lock owner changed")
                return command(argv, timeout=15)
            owned_cleanup(call, record["run_id"], resources)
        except BaseException:
            safe["release"] = False
            raise
        (folder / "explicit-cleanup.json").write_text(json.dumps({"status": "pass", "checked": record["resources"]}))
        return 0

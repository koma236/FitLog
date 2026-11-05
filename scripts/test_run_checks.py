"""Oracles: approved Issue #38 design §1; no real Docker/Git mutations."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).with_name("run-checks.py")


class ChecksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT.exists():
            raise AssertionError("approved checks script is not implemented")
        spec = importlib.util.spec_from_file_location("run_checks", SCRIPT)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()
        (self.root / ".git/HEAD").write_text("ref: refs/heads/chore/operations-38\n")
        (self.root / ".ai-dev").mkdir()
        self.registry = Path(__file__).parents[1] / ".ai-dev/project.toml"
        (self.root / ".ai-dev/project.toml").write_bytes(self.registry.read_bytes())
        self.calls = []
        self.db = []
        self.fail_id = None
        self.abnormal = None
        self.owner_change = False
        self.residual = False

    def fake(self, argv, cwd, env, timeout, log, cleanup=False):
        self.calls.append(list(argv))
        text = "ok\n"
        code = 0
        name = log.stem
        if "ps" in argv:
            text = json.dumps(self.db)
            if self.residual and name == "containers-after":
                text = json.dumps([{"ID": "left", "Name": "fitlog-dev-backend-run-left", "Service": "backend", "State": "running"}])
        if "up" in argv:
            self.db = [{"ID": "db", "Service": "postgres", "State": "running", "Health": "healthy"}]
        if "stop" in argv:
            self.db = [r for r in self.db if r["Service"] != "postgres"] + [{"ID": "db", "Service": "postgres", "State": "exited"}]
        if "shell" in argv:
            text = 'FITLOG_MIGRATIONS:' + json.dumps({"unknown": [], "consistent": True}) + '\n'
        if name == self.fail_id:
            code = 7
            if self.abnormal:
                log.write_text(text)
                # This boundary fake has no live child, matching a confirmed stop.
                self.abnormal.processes_stopped = True
                raise self.abnormal
        if self.owner_change and name == "compose-build":
            (self.root / ".git/fitlog-runtime.lock/owner.json").write_text('{"other":true}')
        log.write_text(text)
        return code

    def run_fixture(self):
        runner = self.mod.ChecksRun(self.root, execute=self.fake)
        code = runner.run()
        return code, runner.report, runner

    def test_existing_lock_never_calls_docker(self):
        (self.root / ".git/fitlog-runtime.lock").mkdir()
        code, report, _ = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(report["checks"]), 11)

    def test_db_started_and_stopped_and_all_checks_recorded(self):
        code, report, runner = self.run_fixture()
        self.assertEqual(code, 0)
        self.assertTrue(any("up" in a for a in self.calls))
        self.assertTrue(any("stop" in a for a in self.calls))
        self.assertFalse(runner.lock.path.exists())
        self.assertEqual(len(report["checks"]), 11)
        for check in report["checks"]:
            self.assertEqual(check["exit_code"], 0)
            self.assertIsNotNone(check["started_at"])
            self.assertIsNotNone(check["ended_at"])
            self.assertTrue(Path(check["log_path"]).is_file())

    def test_running_db_is_never_stopped(self):
        self.db = [{"ID": "db", "Service": "postgres", "State": "running", "Health": "healthy"}]
        self.assertEqual(self.run_fixture()[0], 0)
        self.assertFalse(any("stop" in a or "up" in a for a in self.calls))

    def test_stopped_db_is_stopped_again_after_run(self):
        self.db = [{"ID": "db", "Service": "postgres", "State": "exited"}]
        self.assertEqual(self.run_fixture()[0], 0)
        self.assertTrue(any("stop" in a for a in self.calls))

    def test_unknown_or_multiple_db_refused(self):
        for db in [[{"State": "paused", "Service": "postgres"}], [{"State": "running", "Service": "postgres"}] * 2]:
            with self.subTest(db=db):
                self.db = db
                code, report, _ = self.run_fixture()
                self.assertNotEqual(code, 0)
                self.assertTrue(all(c["status"] == "not_run" for c in report["checks"]))
                self.assertFalse(any("stop" in a or "up" in a for a in self.calls))

    def test_partial_start_failure_still_stops_db(self):
        self.fail_id = "db-start"
        code, report, _ = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertTrue(any("stop" in a for a in self.calls))
        self.assertTrue(report["cleanup"]["lock_released"])

    def test_nonzero_continues_but_build_failure_aborts(self):
        for check_id, count in [("backend-lint", 11), ("compose-build", 1)]:
            with self.subTest(check_id=check_id):
                self.fail_id = check_id
                code, report, _ = self.run_fixture()
                self.assertNotEqual(code, 0)
                self.assertEqual(sum(c["status"] != "not_run" for c in report["checks"]), count)

    def test_timeout_signal_and_spawn_failure_abort(self):
        for error in [subprocess.TimeoutExpired("fake", 1), KeyboardInterrupt("SIGTERM"), FileNotFoundError("fake")]:
            with self.subTest(error=error):
                self.fail_id = "backend-lint"
                self.abnormal = error
                code, report, _ = self.run_fixture()
                self.assertNotEqual(code, 0)
                self.assertTrue(all(c["status"] == "not_run" for c in report["checks"][2:]))
                self.assertTrue(report["cleanup"]["lock_released"])

    def test_stop_failure_keeps_lock(self):
        self.fail_id = "db-stop"
        code, report, runner = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertTrue(runner.lock.path.exists())
        self.assertFalse(report["cleanup"]["lock_released"])

    def test_owner_change_never_deletes_or_stops(self):
        self.owner_change = True
        code, _, runner = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads((runner.lock.path / "owner.json").read_text()), {"other": True})
        self.assertFalse(any("stop" in a for a in self.calls))

    def test_residual_container_keeps_lock(self):
        self.residual = True
        code, _, runner = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertTrue(runner.lock.path.exists())

    def test_migration_record_failure_runs_cleanup(self):
        self.fail_id = "migrations-before-plan"
        code, report, _ = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertTrue(any("stop" in a for a in self.calls))
        self.assertTrue(report["cleanup"]["lock_released"])

    def test_unknown_migration_refuses_checks(self):
        original = self.fake
        def unknown(argv, cwd, env, timeout, log, cleanup=False):
            code = original(argv, cwd, env, timeout, log)
            if "shell" in argv:
                log.write_text('FITLOG_MIGRATIONS:{"unknown":[["other","0001"]],"consistent":true}\n')
            return code
        runner = self.mod.ChecksRun(self.root, execute=unknown)
        self.assertNotEqual(runner.run(), 0)
        self.assertTrue(all(c["status"] == "not_run" for c in runner.report["checks"]))

    def test_save_failure_after_start_still_cleans_up(self):
        runner = self.mod.ChecksRun(self.root, execute=self.fake)
        original = runner.save
        def broken():
            if any("up" in a for a in self.calls):
                raise OSError("disk full")
            original()
        runner.save = broken
        self.assertNotEqual(runner.run(), 0)
        self.assertTrue(any("stop" in a for a in self.calls))
        self.assertFalse(runner.lock.path.exists())

    def test_linked_worktree_common_dir(self):
        (self.root / ".git/HEAD").unlink()
        (self.root / ".git").rmdir()
        common = self.root / "common"
        admin = common / "worktrees/task"
        admin.mkdir(parents=True)
        (admin / "commondir").write_text("../..\n")
        (admin / "HEAD").write_text("ref: refs/heads/chore/task-38\n")
        (self.root / ".git").write_text(f"gitdir: {admin}\n")
        self.assertEqual(self.mod.git_context(self.root), (common.resolve(), "chore/task-38"))

    def test_inventory_failure_still_attempts_own_db_stop_and_retains_lock(self):
        self.fail_id = "containers-after"
        code, _, runner = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertTrue(any("stop" in a for a in self.calls))
        self.assertTrue(runner.lock.path.exists())

    def test_final_migration_timeout_residual_is_not_released(self):
        original = self.fake
        def leftover(argv, cwd, env, timeout, log, cleanup=False):
            code = original(argv, cwd, env, timeout, log)
            if log.stem == "migrations-final-plan":
                self.db.append({"ID": "late", "Service": "backend", "State": "running"})
                raise subprocess.TimeoutExpired("fake", 1)
            return code
        runner = self.mod.ChecksRun(self.root, execute=leftover)
        self.assertNotEqual(runner.run(), 0)
        self.assertTrue(runner.lock.path.exists())

    def test_term_resistant_descendant_is_terminated_after_leader_exits(self):
        child = "import signal,time,os; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(30)"
        parent = f"import subprocess,sys,time,os; print(os.getpid(),flush=True); subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
        log = self.root / "descendant.log"
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.mod.execute_process([sys.executable, "-c", parent], self.root, {}, .3, log)
            descendant = int(log.read_text().splitlines()[1])
            with self.assertRaises(ProcessLookupError):
                os.kill(descendant, 0)
        finally:
            if log.exists() and log.read_text().strip():
                leader = int(log.read_text().splitlines()[0])
                try:
                    os.killpg(leader, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_unconfirmed_host_group_retains_lock(self):
        original = self.fake
        def unsafe(argv, cwd, env, timeout, log, cleanup=False):
            if log.stem == "backend-lint":
                raise self.mod.UnsafeProcessGroup("group still exists")
            return original(argv, cwd, env, timeout, log, cleanup)
        runner = self.mod.ChecksRun(self.root, execute=unsafe)
        self.assertNotEqual(runner.run(), 0)
        self.assertTrue(runner.lock.path.exists())

    def test_group_permission_error_is_unsafe(self):
        with patch.object(os, "killpg", side_effect=PermissionError("fixture")):
            with self.assertRaises(self.mod.UnsafeProcessGroup):
                self.mod.group_exists(12345)

    def test_transient_group_confirmation_waits_for_disappearance(self):
        child = Mock(pid=12345)
        with patch.object(os, "killpg"), patch.object(self.mod, "group_exists", side_effect=[self.mod.UnsafeProcessGroup("exiting"), False]):
            self.mod.stop_group(child)
        child.wait.assert_called_once()

    def test_interrupt_during_group_stop_is_deferred_until_group_disappears(self):
        import threading
        for sig, with_descendant in [(signal.SIGINT, False), (signal.SIGTERM, True)]:
            with self.subTest(sig=sig, descendant=with_descendant):
                timer = None
                group_log = None
                original_stop = self.mod.stop_group
                def interrupt_while_stopping(child):
                    nonlocal timer
                    timer = threading.Timer(.05, lambda: os.kill(os.getpid(), sig))
                    timer.start()
                    return original_stop(child)
                def execute(argv, cwd, env, timeout, log, cleanup=False):
                    nonlocal group_log
                    if log.stem != "backend-lint":
                        return self.fake(argv, cwd, env, timeout, log, cleanup)
                    group_log = log
                    program = "import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(30)"
                    if with_descendant:
                        program = f"import os,subprocess,sys,time; print(os.getpid(),flush=True); subprocess.Popen([sys.executable,'-c',{program!r}]); time.sleep(30)"
                    return self.mod.execute_process([sys.executable, "-c", program], cwd, env, .3, log, cleanup)
                runner = self.mod.ChecksRun(self.root, execute=execute)
                try:
                    with patch.object(self.mod, "stop_group", interrupt_while_stopping):
                        self.assertNotEqual(runner.run(), 0)
                    pids = [int(p) for p in group_log.read_text().splitlines()]
                    for pid in pids:
                        with self.assertRaises(ProcessLookupError):
                            os.kill(pid, 0)
                    self.assertTrue(runner.host_processes_safe)
                    self.assertFalse(runner.lock.path.exists())
                finally:
                    if timer:
                        timer.cancel()
                        timer.join()
                    if group_log and group_log.exists() and group_log.read_text().strip():
                        leader = int(group_log.read_text().splitlines()[0])
                        try:
                            os.killpg(leader, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            os.waitpid(leader, 0)
                        except ChildProcessError:
                            pass
                    # Each subcase owns its fixture lock, never the shared lock.
                    if runner.lock.owned():
                        runner.lock.release()

    def test_uncertified_interrupt_retains_lock(self):
        def unconfirmed(argv, cwd, env, timeout, log, cleanup=False):
            if log.stem == "backend-lint":
                raise KeyboardInterrupt("termination was not confirmed")
            return self.fake(argv, cwd, env, timeout, log, cleanup)
        runner = self.mod.ChecksRun(self.root, execute=unconfirmed)
        self.assertNotEqual(runner.run(), 0)
        self.assertFalse(runner.host_processes_safe)
        self.assertTrue(runner.lock.path.exists())

    def test_log_creation_failure_does_not_block_actual_cleanup_process(self):
        original_open = Path.open
        state = {"running": False, "stop_spawned": False}
        def disk_full(path, *args, **kwargs):
            if state["running"] and path.suffix == ".log":
                raise OSError("ENOSPC fixture")
            return original_open(path, *args, **kwargs)
        def harmless(argv, cwd, env, timeout, log, cleanup=False):
            output = "ok"
            if "ps" in argv:
                output = json.dumps([{"ID":"db","Service":"postgres","State":"running" if state["running"] else "exited"}])
            if "shell" in argv:
                output = 'FITLOG_MIGRATIONS:{"unknown":[],"consistent":true}'
            result = self.mod.execute_process([sys.executable, "-c", f"print({output!r})"], cwd, env, timeout, log, cleanup=cleanup)
            if "up" in argv:
                state["running"] = True
            if "stop" in argv:
                state.update(running=False, stop_spawned=True)
            return result
        runner = self.mod.ChecksRun(self.root, execute=harmless)
        with patch.object(Path, "open", disk_full):
            self.assertNotEqual(runner.run(), 0)
        self.assertTrue(state["stop_spawned"])
        self.assertFalse(state["running"])
        self.assertTrue(any("ENOSPC" in e for e in runner.report["errors"]))

    def test_real_sigint_and_sigterm_wait_for_child(self):
        import threading
        for sig in [signal.SIGINT, signal.SIGTERM]:
            with self.subTest(sig=sig):
                log = self.root / "signal-child.log"
                def interrupt(signum, frame):
                    raise KeyboardInterrupt(str(signum))
                old = signal.signal(sig, interrupt)
                timer = threading.Timer(0.2, lambda: os.kill(os.getpid(), sig))
                timer.start()
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        self.mod.execute_process([sys.executable, "-c", "import os,time; print(os.getpid(),flush=True); time.sleep(30)"], self.root, {}, 10, log)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(int(log.read_text().strip()), 0)
                finally:
                    timer.cancel()
                    timer.join()
                    signal.signal(sig, old)

    def test_registry_rejects_invalid_values(self):
        import copy
        import tomllib
        valid = tomllib.loads(self.registry.read_text())
        cases = []
        for key, value in [("argv", []), ("argv", ["docker", 1]), ("cwd", ".."), ("timeout_seconds", 0), ("timeout_seconds", True), ("env", {"bad": 3})]:
            bad = copy.deepcopy(valid)
            bad["checks"][0][key] = value
            cases.append(bad)
        bad = copy.deepcopy(valid)
        bad["checks"].reverse()
        cases.extend([bad, {"checks": []}, {"checks": valid["checks"] + [None]}])
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    self.mod.validate_registry(case, self.root)

    def test_process_timeout_waits_for_child(self):
        log = self.root / "child.log"
        with self.assertRaises(subprocess.TimeoutExpired):
            self.mod.execute_process([sys.executable, "-c", "import os,time; print(os.getpid(),flush=True); time.sleep(30)"], self.root, {}, 0.15, log)
        pid = int(log.read_text().strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_cli_rejects_extra_arguments(self):
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--command", "anything"], capture_output=True)
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()

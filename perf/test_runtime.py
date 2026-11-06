import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from perf.runtime import ROOT, owned_cleanup, runtime_lock


class OwnershipTests(unittest.TestCase):
    def test_existing_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            common = Path(folder).resolve()
            with patch("perf.runtime.COMMON", common), patch("perf.runtime.command", side_effect=[str(common), "test/55"]):
                with runtime_lock("first"):
                    before = (common / "fitlog-runtime.lock/owner.json").read_text()
                    with patch("perf.runtime.command", side_effect=[str(common), "test/55"]):
                        with self.assertRaises(FileExistsError):
                            with runtime_lock("second"):
                                self.fail("must not acquire another owner's lock")
                    self.assertEqual((common / "fitlog-runtime.lock/owner.json").read_text(), before)
            self.assertFalse((common / "fitlog-runtime.lock").exists())

    def test_changed_owner_is_never_released(self):
        with tempfile.TemporaryDirectory() as folder:
            common = Path(folder).resolve()
            with patch("perf.runtime.COMMON", common), patch("perf.runtime.command", side_effect=[str(common), "test/55"]):
                with runtime_lock("first") as safe:
                    (common / "fitlog-runtime.lock/owner.json").write_text(json.dumps({"pid": "other"}))
                    self.assertFalse(safe["owned"]())
            self.assertTrue((common / "fitlog-runtime.lock/owner.json").exists())

    def test_only_recorded_matching_resources_are_removed(self):
        call = Mock(side_effect=[json.dumps([{"Labels": {"fitlog.perf.run": "abc", "fitlog.perf.worktree": str(ROOT)}}]), ""])
        owned_cleanup(call, "abc", [("volume", "perf_abc_media")])
        self.assertEqual(call.call_args_list[1].args[0],
                         ["docker", "volume", "rm", "perf_abc_media"])

    def test_foreign_name_or_label_never_removed(self):
        for name, label in (("fitlog-dev-postgres", "abc"), ("perf_abc_media", "other")):
            call = Mock(return_value='[{"Labels":{"fitlog.perf.run":"' + label + '"}}]')
            with self.assertRaises(ValueError):
                owned_cleanup(call, "abc", [("volume", name)])
            self.assertFalse(any("rm" in x.args[0] for x in call.call_args_list))

    def test_different_worktree_label_never_removed(self):
        call = Mock(return_value=json.dumps([{"Labels": {"fitlog.perf.run": "abc", "fitlog.perf.worktree": "other"}}]))
        with self.assertRaises(ValueError):
            owned_cleanup(call, "abc", [("volume", "perf_abc_media")])
        self.assertFalse(any("rm" in x.args[0] for x in call.call_args_list))

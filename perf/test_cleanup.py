import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from perf.cleanup import validate_record


class CleanupTests(unittest.TestCase):
    def test_forged_or_live_run_rejected_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "docs/superpowers/plans/perf-results" / ("a" * 32)
            folder.mkdir(parents=True)
            record = {"run_id": "b" * 32, "worktree": str(root), "branch": "test/55",
                      "owner_pid": 123, "resources": [["volume", "perf_" + "b" * 32 + "_media"]]}
            path = folder / "ownership.json"
            path.write_text(json.dumps(record))
            with patch("perf.cleanup.ROOT", root), patch("perf.cleanup.command", return_value="test/55"), patch("perf.cleanup.os.kill"):
                with self.assertRaises(ValueError):
                    validate_record("a" * 32)
            record["worktree"] = "other"
            path.write_text(json.dumps(record))
            with patch("perf.cleanup.ROOT", root), patch("perf.cleanup.command", return_value="test/55"):
                with self.assertRaises(ValueError):
                    validate_record("a" * 32)

    def test_only_finished_own_run_and_exact_resource_names_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "docs/superpowers/plans/perf-results" / ("a" * 32)
            folder.mkdir(parents=True)
            record = {"run_id": "b" * 32, "worktree": str(root), "branch": "test/55", "owner_pid": 123,
                      "resources": [["volume", "perf_" + "b" * 32 + "_media"]]}
            path = folder / "ownership.json"
            path.write_text(json.dumps(record))
            with patch("perf.cleanup.ROOT", root), patch("perf.cleanup.command", return_value="test/55"), patch("perf.cleanup.os.kill", side_effect=ProcessLookupError):
                self.assertEqual(validate_record("a" * 32)[1], record)
                record["resources"] = [["volume", "fitlog-dev-postgres-data"]]
                path.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    validate_record("a" * 32)

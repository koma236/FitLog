import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("prebilling", Path(__file__).with_name("readiness.py"))
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def test_existing_draft_cli_does_not_open_network(self):
        probe = '''import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from operations.deployment_cli import main
with patch("socket.socket", side_effect=AssertionError("network forbidden")):
    result = main(["--manifest", sys.argv[2], "--draft"])
raise SystemExit(result)
'''
        result = subprocess.run([sys.executable, "-B", "-c", probe, str(readiness.ROOT / "backend"),
                                 str(Path(__file__).with_name("draft.json"))],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fixed_offline_argv_and_unresolved_approval(self):
        with patch.object(readiness.subprocess, "run") as run:
            run.return_value.returncode = 0
            result = readiness.inspect_draft(Path(__file__).with_name("draft.json"))
        self.assertEqual(result["aws"], "not_run")
        self.assertEqual(result["approval"], "未承認")
        self.assertEqual(result["readiness"], "未決")
        argv = run.call_args.args[0]
        self.assertEqual(argv[-1], "--draft")
        self.assertNotIn("--aws-approved", argv)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_actual_offline_cli_accepts_null_rejects_unknown_and_region(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "draft.json"
            for data, expected in (({"schema_version": 1, "region": "ap-northeast-1", "account": None}, "pass"),
                                   ({"schema_version": 1, "region": "us-east-1"}, "fail"),
                                   ({"schema_version": 1, "credentials": "forbidden"}, "fail")):
                path.write_text(json.dumps(data))
                self.assertEqual(readiness.inspect_draft(path)["draft_validation"], expected)

    def test_two_builds_and_residual_are_independent_addends(self):
        # Manual arithmetic: 2*(4 hours * $2/hour + $3 one-off) + $5 residual = $27.
        self.assertEqual(readiness.two_builds(Decimal(4), Decimal(2), Decimal(3), Decimal(5)), Decimal(27))
        for hours in (Decimal(0), Decimal(-1), Decimal("NaN")):
            with self.assertRaises(ValueError):
                readiness.two_builds(hours, Decimal(2), Decimal(3), Decimal(5))

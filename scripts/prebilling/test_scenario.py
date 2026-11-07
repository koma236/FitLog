"""Independent arithmetic and invalid-input oracles for offline planning."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("prebilling", Path(__file__).with_name("readiness.py"))
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


def fixture():
    return {
        "schema_version": 1,
        "builds": [
            {"environment": "fitlog-demo-first", "hours": "4", "one_off_usd": "0.02",
             "variable_usd": "0.03", "start_at": "2026-11-08T00:00:00+00:00",
             "close_start_at": "2026-11-08T02:00:00+00:00",
             "public_end_at": "2026-11-08T03:00:00+00:00",
             "destroy_by": "2026-11-08T04:00:00+00:00"},
            {"environment": "fitlog-demo-second", "hours": "4", "one_off_usd": "0.02",
             "variable_usd": "0.03", "start_at": "2026-11-08T13:00:00+09:00",
             "close_start_at": "2026-11-08T15:00:00+09:00",
             "public_end_at": "2026-11-08T16:00:00+09:00",
             "destroy_by": "2026-11-08T17:00:00+09:00"}],
        "hourly_usd": "0.10", "residual_usd": "0.90", "contingency_usd": "0.10",
        "budget_usd": "1.90"}


class ScenarioTests(unittest.TestCase):
    def inspect(self, data, raw=False):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario.json"
            path.write_text(data if raw else json.dumps(data))
            return readiness.inspect_scenario(path)

    def test_manual_arithmetic_and_no_approval(self):
        # 2 * (4 * .10 + .02 + .03) + .90 + .10 = 1.90.
        result = self.inspect(fixture())
        self.assertEqual(result["estimate_usd"], "1.90")
        self.assertEqual(result["scenario_validation"], "pass")
        self.assertEqual(result["within_budget"], True)

    def test_asymmetric_builds_and_upward_display_rounding(self):
        data = fixture()
        data["builds"][1]["hours"] = "5"
        data["builds"][1]["variable_usd"] = "0.030001"
        data["budget_usd"] = "2.01"
        result = self.inspect(data)
        self.assertEqual(result["estimate_usd"], "2.01")
        self.assertEqual(result["estimate_exact_usd"], "2.000001")

    def test_tiny_budget_excess_is_not_rounded_away(self):
        data = fixture()
        data["builds"][1]["variable_usd"] = "0.030001"
        result = self.inspect(data)
        self.assertEqual(result["scenario_validation"], "pass")
        self.assertFalse(result["within_budget"])
        self.assertEqual(result["estimate_exact_usd"], "1.900001")

    def test_invalid_numeric_classes(self):
        for value in (True, 1, None, "NaN", "Infinity", "-1", "+1", "1e2", " .1",
                      ".1", "1.", "1.0000001", "1000000000", "", "1 " ):
            with self.subTest(value=value):
                data = fixture()
                data["hourly_usd"] = value
                with self.assertRaises(ValueError):
                    self.inspect(data)
        for field in ("hours", "one_off_usd", "variable_usd"):
            data = fixture()
            data["builds"][0][field] = "-1"
            with self.assertRaises(ValueError):
                self.inspect(data)

    def test_maximum_precision_does_not_round_during_arithmetic(self):
        data = fixture()
        data["hourly_usd"] = "999999999.999999"
        for build in data["builds"]:
            build["hours"] = "999999999.999999"
        result = self.inspect(data)
        self.assertEqual(result["estimate_exact_usd"], "1999999999999996001.100000000002")
        self.assertFalse(result["within_budget"])

    def test_schema_and_environment_fail_closed(self):
        changes = [lambda d: d.update(unknown=True), lambda d: d.update(schema_version=True),
                   lambda d: d.pop("budget_usd"), lambda d: d.update(builds=d["builds"][:1]),
                   lambda d: d["builds"][0].update(unknown=True),
                   lambda d: d["builds"][0].update(environment="other-env"),
                   lambda d: d["builds"][0].update(environment="fitlog-demo-" + "a" * 20),
                   lambda d: d["builds"][1].update(environment=d["builds"][0]["environment"]),
                   lambda d: d.update(budget_usd="0"),
                   lambda d: d["builds"][0].update(hours="0")]
        for change in changes:
            data = copy.deepcopy(fixture())
            change(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.inspect(data)

    def test_deadlines_and_duration_use_actual_timezone(self):
        changes = [lambda d: d["builds"][0].update(start_at="2026-11-08T00:00:00"),
                   lambda d: d["builds"][0].update(start_at="invalid"),
                   lambda d: d["builds"][0].update(close_start_at=d["builds"][0]["start_at"]),
                   lambda d: d["builds"][0].update(public_end_at=d["builds"][0]["close_start_at"]),
                   lambda d: d["builds"][0].update(destroy_by=d["builds"][0]["public_end_at"]),
                   lambda d: d["builds"][1].update(start_at="2026-11-08T12:59:59+09:00"),
                   lambda d: d["builds"][0].update(hours="3.999999")]
        for change in changes:
            data = fixture()
            change(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.inspect(data)

    def test_malformed_timezone_is_rejected_before_datetime_normalizes_it(self):
        time_keys = ("start_at", "close_start_at", "public_end_at", "destroy_by")
        for offset in ("+00:60", "+09:60", "+00:99", "-00:99", "+24:00", "+00:00:60"):
            data = fixture()
            for build in data["builds"]:
                for key in time_keys:
                    build[key] = build[key][:-6] + offset
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.inspect(data)
        # Z remains a valid explicit UTC offset representation.
        data = fixture()
        for key in time_keys:
            data["builds"][0][key] = data["builds"][0][key][:-6] + "Z"
        self.assertEqual(self.inspect(data)["scenario_validation"], "pass")

    def test_duplicate_keys_invalid_json_and_missing_file(self):
        for raw in ('{"schema_version":1,"schema_version":1}',
                    json.dumps(fixture()).replace('"hours": "4"', '"hours": "4", "hours": "4"'),
                    '[1,2]', '{"schema_version":NaN}', '{broken'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.inspect(raw, raw=True)
        with self.assertRaises(ValueError):
            readiness.inspect_scenario(Path("/nonexistent-fitlog-scenario.json"))

    def test_input_errors_are_sanitized_but_programming_errors_propagate(self):
        with patch.object(Path, "read_text", side_effect=OSError("SECRET_SENTINEL")):
            with self.assertRaisesRegex(ValueError, "^invalid_scenario$"):
                readiness.inspect_scenario(Path("unused"))
        with patch.object(readiness, "_scenario", side_effect=RuntimeError("unexpected")):
            with self.assertRaises(RuntimeError):
                self.inspect(fixture())

    def test_invalid_draft_still_fails_with_valid_scenario(self):
        with tempfile.TemporaryDirectory() as folder:
            scenario, draft = Path(folder) / "scenario.json", Path(folder) / "draft.json"
            scenario.write_text(json.dumps(fixture()))
            draft.write_text('{"region":"us-east-1"}')
            result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("readiness.py")),
                                     "--scenario", str(scenario), "--draft", str(draft)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["draft_validation"], "fail")

    def test_cli_failures_preserve_draft_status_and_do_not_echo_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario.json"
            for data, expected in ((fixture(), 0), ({"password": "SECRET_SENTINEL"}, 1)):
                path.write_text(json.dumps(data))
                result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("readiness.py")),
                                         "--scenario", str(path)], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertNotIn("SECRET_SENTINEL", result.stdout + result.stderr)
                parsed = json.loads(result.stdout)
                self.assertEqual(parsed["aws"], "not_run")
                self.assertEqual(parsed["approval"], "未承認")
                self.assertEqual(parsed["readiness"], "未決")
            data = fixture()
            data["budget_usd"] = "1.89"
            path.write_text(json.dumps(data))
            result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("readiness.py")),
                                     "--scenario", str(path)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()

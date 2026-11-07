"""Offline draft checks only. No AWS SDK, credentials or execution opt-in."""
import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from decimal import (
    ROUND_CEILING,
    Decimal,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    localcontext,
)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _require(condition):
    if not condition:
        raise ValueError("invalid_scenario")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _amount(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,6})?", value) is not None)
    return Decimal(value)


def _time(value):
    _require(isinstance(value, str))
    # fromisoformat normalizes malformed offsets (for example +00:99).
    # Validate the supplied offset before converting any deadline to UTC.
    _require(re.search(r"(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$", value) is not None)
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None)
    return parsed.astimezone(UTC)


def _scenario(data):
    _require(isinstance(data, dict) and set(data) == {
        "schema_version", "builds", "hourly_usd", "residual_usd", "contingency_usd", "budget_usd"})
    _require(type(data["schema_version"]) is int and data["schema_version"] == 1)
    _require(isinstance(data["builds"], list) and len(data["builds"]) == 2)
    hourly, residual, contingency, budget = (
        _amount(data[key]) for key in ("hourly_usd", "residual_usd", "contingency_usd", "budget_usd"))
    _require(budget > 0)
    environments = set()
    previous_destroy = None
    estimate = residual + contingency
    for build in data["builds"]:
        _require(isinstance(build, dict) and set(build) == {
            "environment", "hours", "one_off_usd", "variable_usd", "start_at", "close_start_at",
            "public_end_at", "destroy_by"})
        environment = build["environment"]
        _require(isinstance(environment, str) and len(environment) <= 24
                 and re.fullmatch(r"fitlog-demo-[a-z0-9]+(?:-[a-z0-9]+)*", environment) is not None
                 and environment not in environments)
        environments.add(environment)
        hours, one_off, variable = (
            _amount(build[key]) for key in ("hours", "one_off_usd", "variable_usd"))
        _require(hours > 0)
        start, close, public_end, destroy = (
            _time(build[key]) for key in ("start_at", "close_start_at", "public_end_at", "destroy_by"))
        _require(start < close < public_end < destroy
                 and (previous_destroy is None or previous_destroy <= start))
        duration = destroy - start
        microseconds = (duration.days * 86400 + duration.seconds) * 1000000 + duration.microseconds
        _require(hours * 3600000000 >= microseconds)
        previous_destroy = destroy
        estimate += hours * hourly + one_off + variable
    # Compare exact values before the intentionally upward display rounding.
    within_budget = estimate <= budget
    exact = format(estimate.normalize(), "f")
    with localcontext() as display:
        display.traps[Inexact] = False
        display.traps[Rounded] = False
        shown = format(estimate.quantize(Decimal("0.01"), rounding=ROUND_CEILING), "f")
    return {"scenario_validation": "pass", "within_budget": within_budget,
            "estimate_exact_usd": exact, "estimate_usd": shown, "currency": "USD"}


def inspect_scenario(path):
    """Validate only local assumptions; never authorize an AWS operation."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        with localcontext() as context:
            context.prec = 50
            for signal in (Inexact, Rounded, InvalidOperation, Overflow):
                context.traps[signal] = True
            return _scenario(data)
    except (OSError, ValueError, TypeError, ArithmeticError, RecursionError):
        # Do not expose paths, supplied values, or parser/Decimal diagnostics.
        raise ValueError("invalid_scenario") from None


def inspect_draft(path):
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/deployment/deploy.py"),
                                "--manifest", str(path.resolve()), "--draft"],
                               cwd=ROOT, capture_output=True, text=True, timeout=15)
    # CLI output is intentionally not relayed: drafts are non-secret by policy,
    # but a wrongly supplied manifest must not get its contents copied to logs.
    return {"draft_validation": "pass" if completed.returncode == 0 else "fail",
            "aws": "not_run", "approval": "未承認", "readiness": "未決",
            "unresolved": ["account", "operator role", "AZ/minor/CA", "budget", "deadline",
                           "resource identity", "protected state", "later billing review owner"]}


def two_builds(hours, hourly, one_off, residual):
    if any(not x.is_finite() or x < 0 for x in (hours, hourly, one_off, residual)) or hours == 0:
        raise ValueError("invalid estimate quantities")
    return 2 * (hours * hourly + one_off) + residual


def sensitivity():
    # Tokyo official Price List (2026-11-07), 730-hour month for estimates only.
    task = Decimal("0.05056") * Decimal("0.25") + Decimal("0.00553")
    hourly = task + Decimal("0.025") + Decimal("0.138") * 20 / 730 + Decimal("0.0243") + Decimal("0.008") + Decimal("0.005") * 3
    one_off = (task + Decimal("0.005")) * Decimal("0.5")
    storage_hourly = (Decimal(".2") * Decimal(".025") + Decimal(".5") * Decimal(".10")
                      + Decimal(".1") * Decimal(".033") + 2 * Decimal(".40")) / 730
    variable_per_build = (Decimal(".114") + Decimal(".1") * Decimal(".060")
                          + 10000 * Decimal(".0000012") + 1000 * Decimal(".0000047")
                          + 10000 * Decimal(".00000037") + Decimal(".1") * Decimal(".76")
                          + 100 * Decimal(".000005"))
    # Two final 20GB snapshots, 7 days; two builds' S3/ECR/logs retained 7 days.
    retained_hourly = (40 * Decimal(".095") + Decimal(".4") * Decimal(".025")
                       + Decimal(1) * Decimal(".10") + Decimal(".2") * Decimal(".033")) / 730
    residual = retained_hourly * 168
    intermediate = retained_hourly / 2 * 4  # first build held 4h before rebuilding.
    return {"currency": "USD", "kind": "assumed_quantity_estimate_not_budget",
            "hourly_per_build": str(hourly), "one_off_per_build": str(one_off),
            "core_two_builds": {str(h): str(two_builds(Decimal(h), hourly, one_off, Decimal(0)))
                                for h in (1, 4, 8, 24)},
            "assumed_two_builds_with_retention": {
                str(h): str(two_builds(Decimal(h), hourly + storage_hourly,
                                      one_off + variable_per_build, residual + intermediate))
                for h in (1, 4, 8, 24)},
            "retention_7_days": str(residual), "intermediate_4_hours": str(intermediate),
            "excluded_unresolved": ["actual GB/request/LCU and retention duration", "tax and FX",
                                    "CPU credits and inter-AZ transfer", "additional verification fixtures"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=Path(__file__).with_name("draft.json"))
    parser.add_argument("--scenario", type=Path, help="Local two-build assumptions; grants no AWS permission")
    args = parser.parse_args()
    result = inspect_draft(args.draft)
    scenario = None
    if args.scenario is not None:
        try:
            scenario = inspect_scenario(args.scenario)
        except ValueError:
            scenario = {"scenario_validation": "fail", "within_budget": False}
    output = {**result, "cost_sensitivity": sensitivity()}
    if scenario is not None:
        output["scenario"] = scenario
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["draft_validation"] == "pass" and (
        scenario is None or scenario["within_budget"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

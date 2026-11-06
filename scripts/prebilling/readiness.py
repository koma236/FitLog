"""Offline draft checks only. No AWS SDK, credentials or execution opt-in."""
import argparse
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
    args = parser.parse_args()
    result = inspect_draft(args.draft)
    print(json.dumps({**result, "cost_sensitivity": sensitivity()}, ensure_ascii=False, indent=2))
    return 0 if result["draft_validation"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

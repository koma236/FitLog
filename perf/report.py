"""Nearest-rank statistics with explicit failure and missing-slot accounting."""
import math
from collections import defaultdict


def percentiles(values):
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("missing or invalid latency")
    ordered = sorted(values)
    return {f"p{q}_ms": ordered[math.ceil(q / 100 * len(ordered)) - 1]
            for q in (50, 95, 99)}


def summarize(rows, planned, *, required=None, minimum=50, latency_gate=True):
    groups = defaultdict(list)
    for row in rows:
        groups[row["route"] + " " + row["method"]].append(row)
    metrics = {}
    valid = bool(rows) and planned > 0 and len(rows) == planned
    if required is not None and set(groups) != set(required):
        valid = False
    for key, items in sorted(groups.items()):
        failed = sum(bool(x["error"]) or x["status"] != 200 for x in items)
        server_errors = sum(500 <= x["status"] <= 599 for x in items)
        stats = percentiles([x["elapsed_ms"] for x in items])
        passed = (not failed and len(items) >= minimum
                  and (not latency_gate or stats["p95_ms"] < 1000))
        metrics[key] = {"count": len(items), **stats, "failures": failed,
                        "error_rate": failed / len(items), "5xx_rate": server_errors / len(items),
                        "status": "pass" if passed else "fail"}
        valid = valid and passed
    return {"status": "pass" if valid else "fail", "planned": planned,
            "completed": len(rows), "missed_slots": max(0, planned - len(rows)),
            "routes": metrics,
            "overall": percentiles([x["elapsed_ms"] for x in rows]) if rows else None}

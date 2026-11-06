import unittest

from perf import report


class ReportTests(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(report.percentiles(list(range(1, 101))),
                         {"p50_ms": 50, "p95_ms": 95, "p99_ms": 99})

    def test_empty_and_nonfinite_are_rejected(self):
        for values in ([], [float("nan")], [-1], [float("inf")]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                report.percentiles(values)

    def test_threshold_and_missing_cannot_pass(self):
        rows = [{"route": "detail", "method": "GET", "elapsed_ms": 999,
                 "status": 200, "error": None} for _ in range(100)]
        self.assertEqual(report.summarize(rows, 100)["status"], "pass")
        self.assertEqual(report.summarize(rows, 101)["status"], "fail")
        for row in rows:
            row["elapsed_ms"] = 1000
        self.assertEqual(report.summarize(rows, 100)["status"], "fail")

    def test_errors_and_small_samples_cannot_pass(self):
        for status, error in ((401, "http"), (403, "http"), (429, "http"),
                              (500, "http"), (0, "timeout"), (200, "content")):
            rows = [{"route": "detail", "method": "GET", "elapsed_ms": 1,
                     "status": status, "error": error} for _ in range(100)]
            self.assertEqual(report.summarize(rows, 100)["status"], "fail")
        self.assertEqual(report.summarize(rows[:1], 1)["status"], "fail")
        self.assertEqual(report.summarize([], 0)["status"], "fail")

    def test_required_routes_not_hidden_by_fast_aggregate(self):
        rows = [{"route": "detail", "method": "GET", "elapsed_ms": 1,
                 "status": 200, "error": None} for _ in range(100)]
        self.assertEqual(report.summarize(rows, 100, required={"search GET"})["status"], "fail")

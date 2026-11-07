"""AWS smoke volume is not the existing five-actor capacity test."""
import unittest
from perf.aws_report import report


class AwsReportTests(unittest.TestCase):
    def rows(self):
        return [{'route': route, 'method': 'GET', 'status': 200, 'error': None, 'elapsed_ms': n}
                for route in ('all', 'following', 'detail') for n in range(1, 61)]

    def test_nearest_rank_and_exact_required_samples(self):
        result = report(self.rows())
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['routes']['all GET']['p95_ms'], 57)
        self.assertEqual(report(self.rows()[:-1])['status'], 'fail')

    def test_1000ms_failure_and_missing_are_not_success(self):
        rows = self.rows()
        for row in rows: row['elapsed_ms'] = 1000
        self.assertEqual(report(rows)['status'], 'fail')
        rows = self.rows(); rows[0]['status'] = 500
        self.assertEqual(report(rows)['status'], 'fail')
        self.assertEqual(report([])['status'], 'fail')

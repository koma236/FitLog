import unittest

from perf.seed import guard


class SeedGuardTests(unittest.TestCase):
    def test_shared_or_wrong_database_rejected(self):
        for name, host in (("fitlog", "postgres"), ("perf_abc", "postgres"),
                           ("fitlog", "perf_abc_db")):
            with self.assertRaises(ValueError):
                guard("abc", {"NAME": name, "HOST": host})
        guard("abc", {"NAME": "perf_abc", "HOST": "perf_abc_db"})

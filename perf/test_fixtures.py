import json
import unittest
from unittest.mock import Mock

from perf import fixtures as f


class FixtureTests(unittest.TestCase):
    def test_reported_latency_ends_at_body_receipt(self):
        from perf.runner import Actor
        actor = Actor(0, "normal")
        actor.session = Mock()
        actor.session.request.return_value = (200, json.dumps(f.post_dto(0, 0, "normal")).encode(), 123)
        self.assertEqual(actor.operation(4)["elapsed_ms"], 123)

    def test_counts_and_boundary(self):
        self.assertEqual(f.dimensions("normal"), (3, 3))
        self.assertEqual(f.dimensions("boundary"), (10, 20))
        with self.assertRaises(ValueError):
            f.dimensions("million")
        self.assertEqual(len(set(f.post_id(i) for i in range(1000))), 1000)
        self.assertEqual(f.post_id(0).version, 4)

    def test_independent_order_and_scope(self):
        self.assertEqual(f.indices(0, "all")[:3], [999, 998, 997])
        self.assertEqual(f.indices(0, "following")[:4], [997, 996, 995, 992])
        self.assertEqual(len(f.indices(0, "following")), 600)
        self.assertEqual(len(f.indices(0, "user")), 200)

    def test_content_rejects_empty_wrong_viewer_and_missing_set(self):
        row = f.post_dto(0, 0, "normal")
        f.check_post(row, 0, 0, "normal")
        row["viewer_id"] = str(f.user_id(1))
        with self.assertRaises(ValueError):
            f.check_post(row, 0, 0, "normal")
        row["viewer_id"] = str(f.user_id(0))
        row["exercises"][0]["sets"].pop()
        with self.assertRaises(ValueError):
            f.check_post(row, 0, 0, "normal")

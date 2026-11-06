"""Target bootstrap may create ECR only; never bless a full/empty/destructive plan."""
import unittest

from check_plan import check


class PlanTests(unittest.TestCase):
    def test_exactly_one_ecr_create(self):
        create = {'address': 'aws_ecr_repository.backend', 'change': {'actions': ['create']}}
        self.assertTrue(check({'resource_changes': [create]}))
        for changes in ([], [create, create],
                        [{'address': create['address'], 'change': {'actions': ['delete', 'create']}}],
                        [{'address': 'aws_db_instance.runtime', 'change': {'actions': ['create']}}]):
            with self.subTest(changes=changes):
                self.assertFalse(check({'resource_changes': changes}))

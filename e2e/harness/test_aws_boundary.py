"""C04 oracles fixed before implementation; synthetic, offline-only."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
import aws_contract as contract
import test_aws_contract as legacy
from boundary_fixtures import complete, mutate_inventory, mutate_observation


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        legacy.ContractTests.setUp(self)
        complete(self.root, self.data)

    def test_complete_actual_facts_allow_final_acceptance_readiness(self):
        self.assertTrue(contract.final_ready(self.data))
        contract.validate(self.data, self.now)
        result = contract.boundary_status(self.data)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(set(result['probes']), set(contract.FINAL_PROBES))
        self.assertEqual(result['probes']['task']['classification'], 'sg-restricted')

    def test_wrong_identity_and_unknown_or_secret_fields_fail(self):
        for change in (
            lambda row: row['identity'].update(account='999999999999'),
            lambda row: row['identity'].update(run_id='00000000-0000-4000-8000-000000000099'),
            lambda row: row.update(headers={'Authorization': 'PRIVATE-CANARY'}),
            lambda row: row.update(observed_at='2026-11-07T09:00:00Z'),
        ):
            with self.subTest(change=change):
                data = copy.deepcopy(self.data)
                mutate_observation(self.root, data, 'task', change)
                self.assertEqual(contract.boundary_status(data)['status'], 'fail')
                with self.assertRaises(contract.Invalid): contract.validate(data, self.now)
                complete(self.root, self.data)

    def test_unknown_targets_sg_bypass_object_and_oac_confusions_fail(self):
        for change in (
            lambda inv: inv['targets']['task'].update(public_ip='198.51.100.99'),
            lambda inv: inv['targets']['alb']['ingress'].append({'protocol': '-1', 'from_port': 0, 'to_port': 65535, 'source_type': 'cidr', 'source': '0.0.0.0/0'}),
            lambda inv: inv['targets']['task']['security_groups'].append('sg-33333333'),
            lambda inv: inv['targets']['task'].update(arn=inv['targets']['task']['arn'].replace('123456789012', '999999999999')),
            lambda inv: inv['targets']['static'].update(key='missing.txt'),
            lambda inv: inv['targets']['other']['oac'].update(signing_behavior='never'),
            lambda inv: inv['targets']['other'].update(origin_path='/different'),
            lambda inv: inv['targets']['other'].update(path_pattern='/private/*'),
            lambda inv: inv['targets']['other'].update(id=inv['targets']['distribution']['id']),
            lambda inv: inv['targets']['function'].update(sha256='0' * 64),
        ):
            with self.subTest(change=change):
                data = copy.deepcopy(self.data)
                mutate_inventory(self.root, data, change)
                self.assertEqual(contract.boundary_status(data)['status'], 'fail')
                complete(self.root, self.data)

    def test_inventory_must_match_independent_original(self):
        mutate_inventory(self.root, self.data, lambda inv: inv['targets']['task'].update(eni='eni-22222222'), sync_original=False)
        self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')

    def test_http_alb_denial_is_distinct_from_sg_restriction(self):
        import hashlib
        mutate_observation(self.root, self.data, 'alb-normal', lambda row: row['attempts'][0].update(
            result={'transport': 'http', 'status': 403, 'response_class': 'alb-denied', 'body_bytes': 9,
                    'body_sha256': hashlib.sha256(b'Forbidden').hexdigest()}))
        self.assertEqual(contract.boundary_status(self.data)['probes']['alb-normal'], {'status': 'pass', 'classification': 'http-denied'})

    def test_receipt_schema_duplicate_probe_and_false_identity_are_refused(self):
        from boundary_fixtures import write
        ref = self.data['evidence'][0]
        receipt = contract.load(ref['path']); receipt['schema_version'] = 99
        ref.update(write(self.root, 'receipt-alb-normal', receipt))
        self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')
        complete(self.root, self.data)
        self.data['evidence'].append(copy.deepcopy(self.data['evidence'][0]))
        self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')

    def test_http_errors_and_broken_positive_contrasts_never_pass(self):
        for probe, index, change in (
            ('s3-static', 0, {'status': 404}), ('s3-media', 0, {'status': 200}),
            ('other-distribution', 0, {'status': 403}), ('viewer-headers', 0, {'status': 403}),
            ('viewer-headers', 1, {'body_sha256': '0' * 64}),
            ('task', 0, {'transport': 'error'}), ('alb-host', 0, {'transport': 'error'}),
        ):
            with self.subTest(probe=probe, change=change):
                data = copy.deepcopy(self.data)
                mutate_observation(self.root, data, probe, lambda obs: obs['attempts'][index]['result'].update(change))
                self.assertEqual(contract.boundary_status(data)['status'], 'fail')
                complete(self.root, self.data)

    def test_missing_is_not_run_but_does_not_hide_a_failure(self):
        self.data['evidence'].pop()
        self.assertEqual(contract.boundary_status(self.data)['status'], 'not_run')
        mutate_observation(self.root, self.data, 's3-static', lambda obs: obs['attempts'][0]['result'].update(status=200))
        self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')

    def test_missing_dependency_cannot_hide_available_invalid_observation_or_original(self):
        for missing in ('original-function.json', 'original-task.json', 'inventory.json'):
            with self.subTest(missing=missing):
                complete(self.root, self.data)
                mutate_observation(self.root, self.data, 's3-static', lambda row: row['attempts'][0]['result'].update(status=200))
                (self.root / missing).unlink()
                self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')
                with self.assertRaises(contract.Invalid): contract.validate(self.data, self.now)
        complete(self.root, self.data)
        (self.root / 'original-function.json').unlink()
        (self.root / 'original-static.json').write_text('{}')
        self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')

    def test_missing_unrelated_original_preserves_available_probe_results(self):
        (self.root / 'original-function.json').unlink()
        result = contract.boundary_status(self.data)
        self.assertEqual(result['status'], 'not_run')
        self.assertEqual(result['probes']['s3-static']['status'], 'pass')
        self.assertEqual(result['probes']['viewer-headers']['status'], 'not_run')

    def test_tampered_missing_and_unsafe_originals(self):
        path = self.root / 'original-task.json'
        path.write_text('{}')
        self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')
        complete(self.root, self.data)
        path.unlink()
        self.assertEqual(contract.boundary_status(self.data)['status'], 'not_run')
        complete(self.root, self.data)
        path.chmod(0o644)
        self.assertEqual(contract.boundary_status(self.data)['status'], 'fail')

    def test_b_ip_parameters_must_match_and_probes_cannot_be_omitted(self):
        handoff = contract.load(self.data['handoff']['path'])
        from boundary_fixtures import write
        handoff['probes']['ip'] = 'not_run'
        self.data['handoff'] = write(self.root, 'handoff', handoff)
        self.assertFalse(contract.final_ready(self.data))


if __name__ == '__main__': unittest.main()

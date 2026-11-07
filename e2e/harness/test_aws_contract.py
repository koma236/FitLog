"""Offline authorization and evidence must precede every client creation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

spec = importlib.util.spec_from_file_location('aws_contract', Path(__file__).parents[1] / 'aws_contract.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.now = datetime(2026, 11, 7, 8, tzinfo=timezone.utc)
        self.data = contract.fixture()
        self.data['evidence'] = []
        refs = []
        for step in contract.B_START:
            receipt = {'schema_version': 2, 'step': step, 'status': 'pass',
                       'run_id': self.data['run_id'], 'source_revision': self.data['source'],
                       'image_digest': self.data['image_digest'], 'frontend_sha256': self.data['frontend_sha256'],
                       'deployment_identity': 'e' * 64,
                       'origin': self.data['origin'] if step in ('backend', 'public-health') else None}
            path = self.root / ('b-' + step + '.json')
            contract.exclusive_json(path, receipt)
            refs.append({'step': step, 'path': str(path), 'sha256': contract.canonical_hash(receipt)})
        handoff = {**{k: v for k, v in contract.identity(self.data).items() if k != 'source'},
                   'source_revision': self.data['source'], 'schema_version': 1, 'status': 'ready_for_c',
                   'evidence': refs, 'probes': {'permissions': 'not_run', 'ip': 'not_run'},
                   'window': {'starts_at': self.data['starts_at'], 'ends_at': self.data['expires_at'], 'approval_reference': self.data['approval']['reference']}}
        p = self.root / 'handoff.json'
        contract.exclusive_json(p, handoff)
        self.data['handoff'] = {'path': str(p), 'sha256': contract.sha256(p)}
        for probe in contract.EXTERNAL_PROBES:
            value = {**contract.identity(self.data), 'probe_id': probe, 'status': 'pass'}
            p = self.root / (probe + '.json')
            contract.exclusive_json(p, value)
            self.data['evidence'].append({'probe_id': probe, 'path': str(p), 'sha256': contract.sha256(p)})

    def test_ready_evidence_permits_start_but_not_final_acceptance(self):
        result = contract.validate(self.data, self.now)
        self.assertEqual(result['origin'], 'https://dexample.cloudfront.net')
        self.assertFalse(contract.final_ready(result))

    def test_expired_future_dirty_unknown_and_origin_confusions_refused(self):
        cases = [('expires_at', '2026-11-07T08:00:00Z'), ('starts_at', '2026-11-07T08:01:00Z'),
                 ('unknown', True), ('source', 'not-a-commit'),
                 ('origin', 'https://dexample.cloudfront.net:443'),
                 ('origin', 'https://dexample.cloudfront.net/'),
                 ('origin', 'https://u:p@dexample.cloudfront.net'),
                 ('origin', 'https://other.cloudfront.net')]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                data = copy.deepcopy(self.data); data[key] = value
                with self.assertRaises(contract.Invalid):
                    contract.validate(data, self.now)

    def test_wrong_run_hash_symlink_mode_and_missing_evidence_refused(self):
        p = Path(self.data['evidence'][0]['path'])
        original = p.read_bytes()
        row = json.loads(original); row['run_id'] = '00000000-0000-4000-8000-000000000099'
        p.write_text(json.dumps(row)); self.data['evidence'][0]['sha256'] = contract.sha256(p)
        with self.assertRaises(contract.Invalid): contract.validate(self.data, self.now)
        p.write_bytes(original); self.data['evidence'][0]['sha256'] = contract.sha256(p)
        p.chmod(0o644)
        with self.assertRaises(contract.Invalid): contract.validate(self.data, self.now)
        p.chmod(0o600)
        link = self.root / 'link'; link.symlink_to(p)
        self.data['evidence'][0]['path'] = str(link)
        with self.assertRaises(contract.Invalid): contract.validate(self.data, self.now)
        self.data['handoff']['sha256'] = '0' * 64
        with self.assertRaises(contract.Invalid): contract.validate(self.data, self.now)

    def test_original_b_receipt_cannot_be_replaced_by_a_success_summary(self):
        h = contract.load(self.data['handoff']['path'])
        Path(h['evidence'][0]['path']).write_text('{"status":"pass"}')
        with self.assertRaises(contract.Invalid): contract.validate(self.data, self.now)

    def test_b_window_accepts_its_existing_utc_isoformat_with_fractional_seconds(self):
        p = Path(self.data['handoff']['path'])
        handoff = contract.load(p)
        handoff['window']['starts_at'] = '2026-11-07T07:58:59.500000+00:00'
        handoff['window']['ends_at'] = '2026-11-07T08:40:00.500000+00:00'
        p.write_text(json.dumps(handoff)); self.data['handoff']['sha256'] = contract.sha256(p)
        contract.validate(self.data, self.now)

    def test_campaign_attempt_is_durable_and_never_refunded(self):
        campaign = self.root / 'campaign'
        campaign.mkdir(mode=0o700)
        contract.init_campaign(campaign, 'aws-one', 'aws-two')
        contract.claim(campaign, self.data)
        with self.assertRaises(contract.Invalid): contract.claim(campaign, self.data)
        other = copy.deepcopy(self.data)
        other['environment'] = 'aws-two'; other['test_run'] = 'bbbbbbbbbbbb'
        contract.claim(campaign, other)
        other['test_run'] = 'cccccccccccc'
        with self.assertRaises(contract.Invalid): contract.claim(campaign, other)
        self.assertEqual(len(list(campaign.glob('attempt-*.json'))), 2)

    def test_missing_campaign_and_same_environment_refused(self):
        with self.assertRaises(contract.Invalid): contract.claim(self.root, self.data)
        with self.assertRaises(contract.Invalid): contract.init_campaign(self.root, 'aws-one', 'aws-one')


if __name__ == '__main__': unittest.main()

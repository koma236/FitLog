"""Artifact binding oracle: approved AWS B design §3; never contacts AWS."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_contract import fixture

from operations.deployment_contract import DeploymentError, Manifest


def artifact_fixture(data=None):
    data = data or fixture()
    return {'schema_version': 1, 'run_id': data['run_id'],
            'source_revision': data['source_revision'], 'source_tree': 'e' * 40,
            'backend': {
                'repository': f"{data['account']}.dkr.ecr.ap-northeast-1.amazonaws.com/{data['environment']}/backend",
                'tag': data['source_revision'] + '-' + data['run_id'],
                'local_image_id': 'sha256:' + 'f' * 64,
                'registry_digest': data['image_digest'], 'platform': 'linux/amd64',
                'revision_label': data['source_revision']},
            'frontend_sha256': data['frontend_sha256'],
            'started_at': '2026-11-07T00:00:00+00:00',
            'finished_at': '2026-11-07T00:01:00+00:00',
            'commands': [{'kind': 'frontend', 'exit_code': 0}, {'kind': 'backend', 'exit_code': 0}]}


def private_json(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path


class ArtifactTests(unittest.TestCase):
    def test_binds_registry_digest_separately_from_local_image_id(self):
        from operations.deployment_artifacts import validate_artifacts
        data = fixture()
        record = artifact_fixture(data)
        self.assertEqual(validate_artifacts(record, Manifest.parse(data)), record)
        changes = [({'revision_label': 'd' * 40}), {'platform': 'linux/arm64'},
                   {'tag': 'latest'}, {'registry_digest': record['backend']['local_image_id']},
                   {'repository': '123456789012.dkr.ecr.us-east-1.amazonaws.com/x'}]
        for change in changes:
            invalid = copy.deepcopy(record)
            invalid['backend'].update(change)
            with self.subTest(change=change), self.assertRaises(DeploymentError):
                validate_artifacts(invalid, Manifest.parse(data))

    def test_unknown_fields_failed_builds_and_cross_run_rejected(self):
        from operations.deployment_artifacts import validate_artifacts
        record, manifest = artifact_fixture(), Manifest.parse(fixture())
        for key, value in [('password', 'PRIVATE'), ('source_tree', 'latest'),
                           ('run_id', '33333333-3333-4333-8333-333333333333'),
                           ('frontend_sha256', 'a' * 64), ('finished_at', '2020-01-01T00:00:00Z'),
                           ('commands', [{'kind': 'frontend', 'exit_code': 1}])]:
            invalid = copy.deepcopy(record)
            invalid[key] = value
            with self.subTest(key=key), self.assertRaises(DeploymentError):
                validate_artifacts(invalid, manifest)

    def test_private_input_rejects_symlink_and_permissions(self):
        from operations.deployment_artifacts import read_private
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source = private_json(root / 'record.json', artifact_fixture())
            self.assertEqual(read_private(source)['schema_version'], 1)
            link = root / 'link.json'
            link.symlink_to(source)
            with self.assertRaises(DeploymentError):
                read_private(link)
            source.chmod(0o644)
            with self.assertRaises(DeploymentError):
                read_private(source)

    def test_clean_source_tree_checked_before_accepting_build_record(self):
        from operations.deployment_artifacts import check_source
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
            git('init', '-q')
            (root / 'fixture').write_text('public source')
            (root / 'code.py').write_text("filter_name = 'filter=lfs'\n")
            git('add', 'fixture', 'code.py')
            git('-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
                '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
            revision, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
            self.assertEqual(check_source(root, revision), tree)
            (root / 'untracked').write_text('must not be built')
            with self.assertRaises(DeploymentError):
                check_source(root, revision)

    def test_publication_is_atomic_and_never_overwrites(self):
        from operations.deployment_artifacts import publish_private, read_private
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'record.json'
            publish_private(path, {'status': 'pass'})
            with self.assertRaises(FileExistsError):
                publish_private(path, {'status': 'fail'})
            self.assertEqual(read_private(path), {'status': 'pass'})

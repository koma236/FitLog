"""Static deployment is an explicit hashed file list, never recursive deletion."""
import tempfile
import unittest
from pathlib import Path

from test_contract import fixture

from operations.deployment_assets import bundle, upload
from operations.deployment_contract import DeploymentError, Manifest


class Api:
    def __init__(self):
        self.calls = []
    def call(self, service, operation, **kwargs):
        self.calls.append((service, operation, kwargs))
        return {}


class AssetTests(unittest.TestCase):
    def test_existing_bundle_with_nested_and_flat_assets_remains_valid(self):
        from operations.deployment_assets import validate_inventory
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'assets' / 'a').mkdir(parents=True)
            (root / 'assets' / 'a.js').write_text('flat asset')
            (root / 'assets' / 'a' / 'b.js').write_text('nested asset')
            (root / 'index.html').write_text('fixture')
            assets = bundle(root)
            validate_inventory(assets, assets['sha256'])

    def test_inventory_hash_cannot_certify_an_altered_file_list(self):
        from operations.deployment_assets import validate_inventory
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'index.html').write_text('public fixture')
            assets = bundle(root)
            validate_inventory(assets, assets['sha256'])
            original = assets['sha256']
            assets['files'][0]['size'] += 1
            with self.assertRaises(DeploymentError):
                validate_inventory(assets, original)

    def test_upload_rejects_changed_files_before_any_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'index.html').write_text('public-fixture')
            assets = bundle(root)
            data = fixture()
            data['frontend_sha256'] = assets['sha256']
            (root / 'index.html').write_text('different')
            api = Api()
            with self.assertRaises(DeploymentError):
                upload(api, Manifest.parse(data), root, assets)
            self.assertEqual(api.calls, [])

    def test_bundle_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'index.html').symlink_to('/etc/passwd')
            with self.assertRaises(DeploymentError):
                bundle(root)

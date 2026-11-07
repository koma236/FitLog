import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

spec = importlib.util.spec_from_file_location('browser_ownership', Path(__file__).parents[1] / 'browser_ownership.py')
owned = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owned)


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.row = {'schema_version': 1, 'run_id': 'aaaaaaaaaaaa', 'node_pid': 100,
                    'phase': 'launched', 'pid': 12345, 'pgid': 12345, 'birth': 'known-start'}

    def save(self):
        owned.exclusive_json(self.root / 'browser-worker-0.json', self.row)

    def test_detached_browser_is_stopped_separately_from_the_node_group(self):
        self.save(); active = {12345}; killed = []
        def kill(group, _signal): killed.append(group); active.remove(group)
        self.assertTrue(owned.stop_browsers(self.root, 'aaaaaaaaaaaa', required=True,
                        exists=lambda group: group in active, identity=lambda _pid: ('known-start', 12345), kill=kill))
        self.assertEqual(killed, [12345])

    def test_unknown_or_reused_browser_never_counts_as_stopped(self):
        self.save(); killed = []
        self.assertFalse(owned.stop_browsers(self.root, 'aaaaaaaaaaaa', required=True,
                         exists=lambda _group: True, identity=lambda _pid: ('different-start', 12345), kill=lambda *args: killed.append(args)))
        self.assertEqual(killed, [])

    def test_missing_or_partial_intent_retains_stop_uncertainty(self):
        self.assertFalse(owned.stop_browsers(self.root, 'aaaaaaaaaaaa', required=True))
        self.row.update(phase='launching', pid=None, pgid=None, birth=None); self.save()
        self.assertFalse(owned.stop_browsers(self.root, 'aaaaaaaaaaaa', required=True))

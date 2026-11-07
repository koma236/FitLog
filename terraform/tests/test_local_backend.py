"""Exercise the shipped backend declaration with Terraform's built-in provider only."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class LocalBackendTests(unittest.TestCase):
    def test_saved_plans_keep_two_environments_separate(self):
        declaration = Path(__file__).resolve().parents[1] / "backend.tf"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            module = root / "module"
            module.mkdir(mode=0o700)
            (module / "backend.tf").write_bytes(declaration.read_bytes())
            # No AWS resources/provider: init and saved-plan apply are entirely local.
            (module / "main.tf").write_text('''variable "environment" { type = string }
resource "terraform_data" "marker" { input = var.environment }
output "marker" { value = terraform_data.marker.output }
''')
            records = []
            for name in ("first", "second"):
                protected = root / name
                protected.mkdir(mode=0o700)
                state, plan = protected / "terraform.tfstate", protected / "saved.plan"
                env = {"PATH": os.environ["PATH"], "HOME": str(root),
                       "TF_DATA_DIR": str(protected / "data"), "CHECKPOINT_DISABLE": "1",
                       "TF_CLI_CONFIG_FILE": "/dev/null", "TF_IN_AUTOMATION": "1",
                       "AWS_EC2_METADATA_DISABLED": "true",
                       "AWS_SHARED_CREDENTIALS_FILE": "/dev/null", "AWS_CONFIG_FILE": "/dev/null"}

                def run(*args, env=env):
                    return subprocess.run(["terraform", f"-chdir={module}", *args], env=env,
                                          capture_output=True, text=True, timeout=30, check=True)

                run("init", "-input=false", f"-backend-config=path={state}")
                run("plan", "-input=false", f"-var=environment={name}", f"-out={plan}")
                self.assertFalse(state.exists(), "plan must not provision its marker")
                run("apply", "-input=false", str(plan))
                record = json.loads(state.read_text())
                self.assertEqual(record["outputs"]["marker"]["value"], name)
                self.assertFalse((module / "terraform.tfstate").exists())
                records.append((state, record))
            self.assertNotEqual(records[0][1]["lineage"], records[1][1]["lineage"])
            self.assertEqual(json.loads(records[0][0].read_text()), records[0][1],
                             "second environment must not alter the first state")


if __name__ == "__main__":
    unittest.main()

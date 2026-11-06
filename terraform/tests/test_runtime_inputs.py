"""Required/null input failures must occur before any AWS provider operation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class RuntimeInputTests(unittest.TestCase):
    def test_missing_and_null_runtime_inputs_are_rejected(self):
        module = Path(__file__).resolve().parents[1]
        fixtures = {
            "expected_account_id": '"123456789012"',
            "environment_name": '"fitlog-demo-test"',
            "availability_zones": '["ap-northeast-1a", "ap-northeast-1c"]',
            "origin_verify_secret": '"' + "a" * 64 + '"',
            "backend_image_digest": '"sha256:' + "a" * 64 + '"',
            "backend_source_revision": '"' + "b" * 40 + '"',
            "postgres_engine_version": '"17.6"',
            "db_final_snapshot_identifier": '"fitlog-demo-test-final-fixture"',
            "enable_backend_service": "false",
            "enable_proxy_trust": "false",
        }
        required = ("backend_image_digest", "backend_source_revision", "postgres_engine_version",
                    "db_final_snapshot_identifier")
        for key in required:
            for missing in (False, True):
                with self.subTest(key=key, missing=missing):
                    values = dict(fixtures)
                    if missing:
                        del values[key]
                    else:
                        values[key] = "null"
                    with tempfile.TemporaryDirectory(prefix=".runtime-input-", dir=module) as folder:
                        testfile = Path(folder) / "input.tftest.hcl"
                        testfile.write_text('mock_provider "aws" {\n override_during = plan\n source = "./tests/mocks"\n}\nvariables {\n' +
                                            "\n".join(f"{k} = {v}" for k, v in values.items()) +
                                            '\n}\nrun "invalid_input" { command = plan }\n')
                        result = subprocess.run(
                            ["terraform", f"-chdir={module}", "test", "-no-color",
                             f"-test-directory={Path(folder).name}"],
                            env={"PATH": os.environ["PATH"], "CHECKPOINT_DISABLE": "1",
                                 "TF_CLI_CONFIG_FILE": "/dev/null", "TF_IN_AUTOMATION": "1",
                                 "AWS_EC2_METADATA_DISABLED": "true",
                                 "AWS_SHARED_CREDENTIALS_FILE": "/dev/null", "AWS_CONFIG_FILE": "/dev/null"},
                            capture_output=True, text=True, timeout=45,
                        )
                        output = result.stdout + result.stderr
                        self.assertNotEqual(result.returncode, 0, output)
                        self.assertIn(key, output)
                        self.assertIn("No value for required variable" if missing else
                                      "required variable may not be set to null", output)


if __name__ == "__main__":
    unittest.main()

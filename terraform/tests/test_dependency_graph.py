"""Check real Terraform scheduling dependencies without credentials or AWS calls."""
import os
from pathlib import Path
import re
import subprocess
import unittest


class EdgeDependencyTests(unittest.TestCase):
    def test_public_alb_waits_for_internet_routing(self):
        # AWS requires an attached IGW for internet-facing ALB creation:
        # https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-application-load-balancer.html
        # Public route association also ensures the chosen subnets are ready.
        module = Path(__file__).resolve().parents[1]
        graph = subprocess.run(
            ["terraform", f"-chdir={module}", "graph"],
            env={"PATH": os.environ["PATH"], "CHECKPOINT_DISABLE": "1",
                 "TF_CLI_CONFIG_FILE": "/dev/null", "TF_IN_AUTOMATION": "1",
                 "AWS_EC2_METADATA_DISABLED": "true",
                 "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
                 "AWS_CONFIG_FILE": "/dev/null"},
            check=True, capture_output=True, text=True, timeout=30,
        ).stdout
        edges = {}
        for source, dependency in re.findall(r'^\s*"([^"]+)" -> "([^"]+)";', graph, re.MULTILINE):
            edges.setdefault(source, set()).add(dependency)

        pending = ["aws_lb.api"]
        reachable = set()
        while pending:
            node = pending.pop()
            if node not in reachable:
                reachable.add(node)
                pending.extend(edges.get(node, set()))
        self.assertIn("aws_route_table_association.public", reachable,
                      "ALB creation must wait for both public subnet route associations")
        self.assertIn("aws_internet_gateway.public", reachable,
                      "ALB creation must wait for IGW attachment")

    def test_service_waits_for_ingress_permissions_and_routing(self):
        module = Path(__file__).resolve().parents[1]
        graph = subprocess.run(
            ["terraform", f"-chdir={module}", "graph"],
            env={"PATH": os.environ["PATH"], "CHECKPOINT_DISABLE": "1",
                 "TF_CLI_CONFIG_FILE": "/dev/null", "TF_IN_AUTOMATION": "1",
                 "AWS_EC2_METADATA_DISABLED": "true",
                 "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
                 "AWS_CONFIG_FILE": "/dev/null"},
            check=True, capture_output=True, text=True, timeout=30,
        ).stdout
        edges = {}
        for source, dependency in re.findall(r'^\s*"([^"]+)" -> "([^"]+)";', graph, re.MULTILINE):
            edges.setdefault(source, set()).add(dependency)
        pending, reachable = ["aws_ecs_service.backend"], set()
        while pending:
            node = pending.pop()
            if node not in reachable:
                reachable.add(node)
                pending.extend(edges.get(node, set()))
        for dependency in (
            "aws_lb_listener.api", "aws_lb_listener_rule.cloudfront",
            "aws_route_table_association.public", "aws_internet_gateway.public",
            "aws_vpc_security_group_rules_exclusive.boundary",
            "aws_iam_role_policy.execution", "aws_iam_role_policy.media",
            "aws_iam_role_policy.application_secret",
        ):
            self.assertIn(dependency, reachable)
        self.assertNotRegex(graph, r'(?:resource|data)?\.?aws_secretsmanager_secret_version\.')
        policies = set(re.findall(r'"(aws_iam_role_policy\.[a-z_]+)"', graph))
        self.assertEqual(policies, {"aws_iam_role_policy.media", "aws_iam_role_policy.execution",
                                    "aws_iam_role_policy.application_secret",
                                    "aws_iam_role_policy.bootstrap",
                                    "aws_iam_role_policy.bootstrap_execution"})


if __name__ == "__main__":
    unittest.main()

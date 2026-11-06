"""Fault-injection checks for owned TLS fixture cleanup; no Docker daemon needed."""
import subprocess
import unittest
from unittest.mock import patch

from tests import production_tls_smoke as tls


class DockerBoundary:
    def __init__(self, stop_failure: bool = False) -> None:
        self.running = {"client", "database"}
        self.containers = {"client", "database"}
        self.network_exists = True
        self.stop_failure = stop_failure
        self.owned = {"client", "database"}
        self.network_owned = True

    def command(self, *args: str) -> str:
        operation, name = args[0], args[-1]
        if operation == "ps" or args[:2] == ("network", "ls"):
            assert "label=fitlog.tls-run=run-token" in args
            query = next(arg.removeprefix("name=") for arg in args if arg.startswith("name="))
            if operation == "ps":
                return f"{query} {query}" if query in self.containers & self.owned else ""
            return "network network" if self.network_exists and self.network_owned else ""
        if operation == "stop":
            if name == "client" and self.stop_failure:
                raise RuntimeError("injected client stop failure")
            self.running.remove(name)
        elif operation == "inspect":
            return "true" if name in self.running else "false"
        elif operation == "rm":
            if name in self.running:
                raise RuntimeError("refuse to remove a running container")
            self.containers.remove(name)
        elif args[:2] == ("network", "inspect"):
            return '[{"Containers":' + ('{"client":{}}' if self.containers else '{}') + '}]'
        elif args[:2] == ("network", "rm"):
            if self.containers:
                raise RuntimeError("refuse to remove a used network")
            self.network_exists = False
        else:
            raise AssertionError(f"Unexpected Docker operation: {args}")
        return ""


class TLSCleanupTests(unittest.TestCase):
    def test_timeout_still_removes_owned_client_database_and_network(self) -> None:
        boundary = DockerBoundary()
        timeout = subprocess.TimeoutExpired("docker start", 50)
        with patch.object(tls, "docker", boundary.command):
            tls.cleanup_owned_resources("client", "database", "network", "run-token", timeout)
        self.assertEqual(boundary.containers, set())
        self.assertEqual(boundary.running, set())
        self.assertFalse(boundary.network_exists)

    def test_client_cleanup_failure_still_removes_database_and_preserves_primary_error(self) -> None:
        boundary = DockerBoundary(stop_failure=True)
        timeout = subprocess.TimeoutExpired("docker start", 50)
        with patch.object(tls, "docker", boundary.command), self.assertRaises(ExceptionGroup) as caught:
            tls.cleanup_owned_resources("client", "database", "network", "run-token", timeout)
        self.assertEqual(boundary.containers, {"client"})
        self.assertNotIn("database", boundary.running)
        self.assertTrue(boundary.network_exists)
        self.assertIs(caught.exception.exceptions[0], timeout)
        self.assertTrue(any("client stop failure" in str(e) for e in caught.exception.exceptions))


    def test_created_but_not_started_client_is_reclaimed_after_ambiguous_create(self) -> None:
        boundary = DockerBoundary()
        boundary.running.remove("client")
        with patch.object(tls, "docker", boundary.command):
            tls.cleanup_owned_resources("client", "database", "network", "run-token", None)
        self.assertEqual(boundary.containers, set())
        self.assertFalse(boundary.network_exists)

    def test_absent_resources_are_normal_when_create_failed_before_daemon_commit(self) -> None:
        boundary = DockerBoundary()
        boundary.containers.clear()
        boundary.running.clear()
        boundary.network_exists = False
        with patch.object(tls, "docker", boundary.command):
            tls.cleanup_owned_resources("client", "database", "network", "run-token", None)
        self.assertEqual(boundary.containers, set())

    def test_unowned_resources_are_preserved(self) -> None:
        boundary = DockerBoundary()
        boundary.owned.clear()
        boundary.network_owned = False
        with patch.object(tls, "docker", boundary.command):
            tls.cleanup_owned_resources("client", "database", "network", "run-token", None)
        self.assertEqual(boundary.containers, {"client", "database"})
        self.assertTrue(boundary.network_exists)


if __name__ == "__main__":
    unittest.main()

"""Inject lost Docker responses after real daemon commits, then verify no owned leaks.

Run with the FitLog runtime lease and the production image already built.
"""
import subprocess
from unittest.mock import patch

from tests import production_tls_smoke as tls
from tests.production_smoke import docker


def run_case(point: str) -> None:
    real_docker = docker
    run_token: str | None = None
    injected = False

    def interrupted(*args: str, source: str | None = None) -> str:
        nonlocal run_token, injected
        for arg in args:
            if arg.startswith("fitlog.tls-run="):
                run_token = arg.split("=", 1)[1]
        hit = (
            (point == "start" and args[:3] == ("start", "--attach", "--interactive")) or
            (point == "create-client" and args[0] == "create" and "--interactive" in args) or
            (point == "create-database" and args[0] == "create" and "--interactive" not in args) or
            (point == "create-network" and args[:2] == ("network", "create"))
        )
        if hit:
            if point == "start":
                real_docker("start", args[-1])
                assert real_docker("inspect", "--format", "{{.State.Running}}", args[-1]).strip() == "true"
            else:
                real_docker(*args, source=source)
            injected = True
            raise subprocess.TimeoutExpired("docker " + point, 50)
        return real_docker(*args, source=source)

    try:
        with patch.object(tls, "docker", interrupted):
            tls.main()
    except subprocess.TimeoutExpired:
        assert injected
    else:
        raise AssertionError("Expected transport timeout at " + point)
    assert run_token is not None
    label = "label=fitlog.tls-run=" + run_token
    assert real_docker("ps", "--all", "--filter", label, "--format", "{{.Names}}").strip() == ""
    assert real_docker("network", "ls", "--filter", label, "--format", "{{.Name}}").strip() == ""
    print("Injected timeout after " + point + ": all owned resources reclaimed; original timeout preserved: OK")


def main() -> None:
    for point in ("start", "create-client", "create-database", "create-network"):
        run_case(point)


if __name__ == "__main__":
    main()

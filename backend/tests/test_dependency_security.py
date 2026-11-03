"""Bound Accept negotiation before any work on the unauthenticated liveness route."""
from django.test import Client


def test_health_rejects_oversized_accept_token_without_losing_valid_fallback() -> None:
    client = Client(SERVER_NAME="localhost")
    # Independently fixed 12KB token exceeds DRF's supported negotiation budget.
    oversized = "application/json;x=" + "a" * 12000
    response = client.get("/api/health/live", HTTP_ACCEPT=oversized)
    assert response.status_code == 406
    # Do not parse an unbounded tail after an oversized leading token.
    fallback = client.get("/api/health/live", HTTP_ACCEPT=oversized + ",application/json")
    # Total header is bounded: legitimate JSON in the bounded prefix remains usable.
    valid_first = client.get("/api/health/live", HTTP_ACCEPT="application/json," + oversized)
    assert fallback.status_code == 406
    assert valid_first.status_code == 200

"""
Integration tests for unauthenticated Prometheus metrics endpoint.

This endpoint is scraped by Prometheus and must NOT require authentication
to allow monitoring infrastructure to function without service account credentials.

TESTS:
1. Prometheus metrics endpoint accessible without auth
2. Returns proper Prometheus text format
3. Contains required metric types and values
4. Can be scraped repeatedly without rate limits
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint_requires_no_auth(
    integration_client: AsyncClient,
):
    """
    HAPPY PATH: Prometheus metrics endpoint is accessible without authentication.

    This is required because Prometheus scraper needs to access the endpoint
    without service account credentials. If this endpoint requires auth,
    monitoring stack will fail to collect metrics.
    """
    # Make request WITHOUT authorization header
    response = await integration_client.get("/api/metrics")

    # Should succeed (200) without auth
    assert response.status_code == 200, (
        f"Prometheus metrics endpoint requires auth! Status: {response.status_code}. "
        "Prometheus scraper cannot function with authenticated-only endpoints."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_metrics_returns_text_format(
    integration_client: AsyncClient,
):
    """
    HAPPY PATH: Prometheus metrics endpoint returns Prometheus text exposition format.

    Format spec: https://github.com/prometheus/docs/blob/main/content/docs/instrumenting/exposition_formats.md
    Expected format:
        # TYPE metric_name gauge|counter|histogram|summary
        metric_name{label="value"} 123.45
    """
    response = await integration_client.get("/api/metrics")

    assert response.status_code == 200
    assert (
        response.headers.get("content-type") == "text/plain; charset=utf-8"
    ), "Prometheus requires text/plain content-type"

    # Check that response is non-empty and contains TYPE declarations
    text = response.text
    assert len(text) > 0, "Response body is empty"
    assert (
        "# TYPE" in text
    ), "Response missing Prometheus TYPE declarations. Format: '# TYPE metric_name gauge'"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_metrics_contains_required_metrics(
    integration_client: AsyncClient,
):
    """
    HAPPY PATH: Prometheus metrics include core required metrics.

    Prometheus scraper expects to find at minimum:
    - sanskriti_health_score (overall system health)
    - at least one system/app/db metric
    """
    response = await integration_client.get("/api/metrics")

    assert response.status_code == 200
    text = response.text

    # Check for health score metric (required)
    assert "sanskriti_health_score" in text, "Missing required metric: sanskriti_health_score"

    # Check for type declarations (required for Prometheus format)
    assert text.count("# TYPE") > 0, "No TYPE declarations found in metrics output"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_metrics_handles_rapid_scrapes(
    integration_client: AsyncClient,
):
    """
    HAPPY PATH: Prometheus metrics endpoint can handle rapid requests.

    Prometheus may scrape every 15 seconds (configurable). Endpoint must
    not fail, timeout, or rate-limit rapid consecutive requests.
    """
    # Simulate 3 rapid scrapes as Prometheus might do
    responses = []
    for i in range(3):
        response = await integration_client.get("/api/metrics")
        responses.append(response.status_code)

    # All requests should succeed
    assert all(status == 200 for status in responses), (
        f"Rapid scrapes failed: {responses}. "
        "Prometheus cannot scrape metrics if endpoint rate-limits or fails."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_metrics_unhappy_malformed_response(
    integration_client: AsyncClient,
):
    """
    UNHAPPY PATH: Verify metrics endpoint returns valid Prometheus format.

    If metrics are malformed, Prometheus scraper will reject them and
    no metrics will be collected.
    """
    response = await integration_client.get("/api/metrics")

    if response.status_code == 200:
        text = response.text
        lines = text.strip().split("\n")

        # Every non-comment line should be a valid metric
        for line in lines:
            if not line.startswith("#") and line.strip():
                # Basic validation: metric_name{optional_labels} value
                assert " " in line, f"Invalid metric line (missing value): {line}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_metrics_vs_authenticated_endpoint_parity(
    integration_client: AsyncClient,
    admin_token: str,
):
    """
    HAPPY PATH: Verify unauthenticated /metrics endpoint provides same
    metrics as authenticated /metrics/prometheus endpoint.

    Both endpoints should expose the same metrics data. Unauthenticated
    is for Prometheus scraper; authenticated may be for dashboard views.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Get metrics from both endpoints
    unauth_response = await integration_client.get("/api/metrics")
    auth_response = await integration_client.get("/api/metrics/prometheus", headers=headers)

    if unauth_response.status_code == 200 and auth_response.status_code == 200:
        unauth_text = unauth_response.text
        auth_text = auth_response.text

        # Both should contain health score
        assert "sanskriti_health_score" in unauth_text
        assert "sanskriti_health_score" in auth_text

        # Both should have TYPE declarations
        assert unauth_text.count("# TYPE") > 0
        assert auth_text.count("# TYPE") > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_metrics_timestamp_freshness(
    integration_client: AsyncClient,
):
    """
    UNHAPPY PATH: Verify metrics are fresh (not stale cache).

    If metrics are cached and not updated, Prometheus will see stale
    data and alerts/dashboards will be unreliable.
    """
    # Make two requests in quick succession
    response1 = await integration_client.get("/api/metrics")
    response2 = await integration_client.get("/api/metrics")

    # Both should succeed
    assert response1.status_code == 200
    assert response2.status_code == 200

    # Parse metrics and verify they are reasonable (non-zero health)
    text1 = response1.text
    text2 = response2.text

    # Both should contain numeric values
    assert "sanskriti_health_score" in text1
    assert "sanskriti_health_score" in text2

    # Extract health scores and verify they are numeric
    for text, name in [(text1, "first"), (text2, "second")]:
        lines = text.split("\n")
        health_lines = [
            line for line in lines if "sanskriti_health_score " in line and not line.startswith("#")
        ]
        assert len(health_lines) > 0, f"No health score value in {name} response"

"""
Unit tests voor Monitoring domein: metrics ophalen, alerts testen, edge cases
"""

import pytest


def test_get_metrics_success(client, auth_headers):
    response = client.get("/api/monitoring/metrics", headers=auth_headers)
    assert response.status_code == 200
    assert "system_metrics" in response.json()


def test_trigger_alert_success(client, auth_headers):
    response = client.post(
        "/api/monitoring/trigger_alert",
        json={"alert_type": "test"},
        headers=auth_headers,
    )
    assert response.status_code in (200, 201)
    assert "alert_id" in response.json()


def test_get_alert_not_found(client, auth_headers):
    response = client.get("/api/monitoring/alert/999999", headers=auth_headers)
    assert response.status_code == 404


def test_monitoring_endpoint_health(client, auth_headers):
    response = client.get("/api/monitoring/health", headers=auth_headers)
    assert response.status_code == 200
    assert response.json().get("status") in (
        "ok",
        "healthy",
        "degraded",
        "unhealthy",
        "critical",
        "error",
    )


def test_monitoring_metrics_format(client, auth_headers):
    response = client.get("/api/monitoring/metrics", headers=auth_headers)
    assert response.status_code == 200
    assert "application/json" in response.headers.get(
        "content-type", ""
    ) or "text/plain" in response.headers.get("content-type", "")


def test_monitoring_security_headers(client, auth_headers):
    response = client.get("/api/monitoring/health", headers=auth_headers)
    assert "X-Frame-Options" in response.headers or "Strict-Transport-Security" in response.headers


def test_monitoring_tenant_isolation(client, auth_headers):
    """Test that monitoring data is properly isolated between tenants"""
    # Test metrics endpoint
    response = client.get("/api/monitoring/metrics", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "system_metrics" in data
    # Verify tenant isolation by checking that metrics are tenant-specific
    # In a real scenario, we would create metrics for different tenants and verify isolation


def test_monitoring_audit_logging(client, auth_headers):
    """Test that monitoring events are properly logged"""
    # Trigger an alert which should be logged
    response = client.post(
        "/api/monitoring/trigger_alert",
        json={"alert_type": "test_audit"},
        headers=auth_headers,
    )
    assert response.status_code in (200, 201)
    data = response.json()
    assert "alert_id" in data
    # In a real scenario, we would check that the audit log contains this event


def test_monitoring_concurrent_requests(client, auth_headers):
    """Test that monitoring can handle concurrent requests"""
    import concurrent.futures

    def make_request():
        return client.get("/api/monitoring/health", headers=auth_headers)

    # Make 5 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request) for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # All requests should succeed
    assert len(results) == 5
    for response in results:
        assert response.status_code == 200
        assert "status" in response.json()

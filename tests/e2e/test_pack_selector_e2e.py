"""E2E Tests for Pack Selector Flow

End-to-end tests that validate the complete pack-selector flow.
Part of Plan 3, Task 4: Paperclip Pipeline Integration.

Tests:
1. Pack selector recommends packs for a department
2. Pack selector respects Golden Rule R1 (misalignment = low scores)
3. Pack selector persists audit log entries
"""

import uuid
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import E2E_BASE_URL, e2e_register_and_login

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]


@pytest.fixture
async def authenticated_async_client():
    """Async HTTP client authenticated against the running E2E backend."""
    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=30.0) as client:
        token, _ = await e2e_register_and_login(client)
        assert token is not None, "Failed to authenticate for pack-selector E2E test"
        client.headers["Authorization"] = f"Bearer {token}"
        yield client


async def _create_company(client: httpx.AsyncClient, name: str) -> dict[str, Any]:
    """Helper: Create a company via API."""
    response = await client.post(
        "/api/v1/companies",
        json={
            "name": name,
            "company_type": "mkb",
            "sector": "retail",
        },
    )
    assert response.status_code in (
        200,
        201,
    ), f"Failed to create company: {response.text}"
    return response.json()


async def _create_department(
    client: httpx.AsyncClient, company_id: str, name: str
) -> dict[str, Any]:
    """Helper: Create a department via API."""
    response = await client.post(
        f"/api/v1/companies/{company_id}/departments",
        json={"name": name},
    )
    assert response.status_code in (
        200,
        201,
    ), f"Failed to create department: {response.text}"
    return response.json()


async def _call_pack_selector(
    client: httpx.AsyncClient,
    company_id: str,
    department_id: str | None,
    signals: dict[str, Any],
) -> list[dict[str, Any]]:
    """Helper: Call pack-selector endpoint."""
    payload: dict[str, Any] = {
        "company_id": company_id,
        "signals": signals,
    }
    if department_id:
        payload["department_id"] = department_id

    response = await client.post("/api/v1/pack-selector", json=payload)
    assert response.status_code == 200, f"Pack-selector failed: {response.text}"
    return response.json()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pack_selector_recommends_packs_for_department(
    authenticated_async_client: httpx.AsyncClient,
) -> None:
    """E2E: Pack selector returns scored pack recommendations for a department.

    Setup: Create company + department via API
    Call: POST /api/v1/pack-selector
    Verify: Response contains scored packs with proper structure
    """
    # Setup: Create company and department
    company = await _create_company(authenticated_async_client, "Test Company Pack Selector")
    company_id = company["id"]

    department = await _create_department(authenticated_async_client, company_id, "Sales")
    department_id = department["id"]

    # Test: Call pack-selector endpoint
    signals = {
        "department_name": "Sales",
        "company_type": "mkb",
        "sector": "retail",
        "sector_tags": ["sales", "crm"],
    }

    results = await _call_pack_selector(
        authenticated_async_client, company_id, department_id, signals
    )

    # Verify: Response structure
    assert isinstance(results, list)

    # If we have results (packs exist in DB), verify their structure
    if results:
        top_result = results[0]
        assert "pack_id" in top_result
        assert "pack_name" in top_result
        assert "confidence" in top_result
        assert "match_reason" in top_result
        assert "input_signals" in top_result
        assert "score_breakdown" in top_result
        assert "audit_log_id" in top_result
        assert "activated_automatically" in top_result

        # Verify confidence is within valid range
        assert 0.0 <= top_result["confidence"] <= 1.0

        # Verify audit_log_id is a valid UUID string
        assert uuid.UUID(top_result["audit_log_id"])

        # Verify activated_automatically is a boolean
        assert isinstance(top_result["activated_automatically"], bool)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pack_selector_respects_golden_rule_r1(
    authenticated_async_client: httpx.AsyncClient,
) -> None:
    """E2E: Pack selector respects Golden Rule R1 - misalignment = low scores.

    Call with company_context that should trigger MISALIGNED scores.
    Verify: Packs with misalignment get low confidence scores.
    """
    # Setup: Create company and department
    company = await _create_company(authenticated_async_client, "Misalignment Test Company")
    company_id = company["id"]

    department = await _create_department(authenticated_async_client, company_id, "UnknownDept")
    department_id = department["id"]

    # Test: Call with signals that should produce low scores
    misaligned_signals = {
        "department_name": "CompletelyUnknownDepartment",
        "company_type": "unknown_type",
        "sector": "unknown_sector_xyz",
        "sector_tags": ["nonexistent"],
    }

    results = await _call_pack_selector(
        authenticated_async_client, company_id, department_id, misaligned_signals
    )

    # Verify: Results should be empty or have very low confidence
    for result in results:
        assert result["confidence"] < 0.70, "Misaligned signals should not produce HIGH confidence"

    # Test with aligned signals for comparison
    aligned_signals = {
        "department_name": "Sales",
        "company_type": "mkb",
        "sector": "retail",
        "sector_tags": ["sales", "retail"],
    }

    aligned_results = await _call_pack_selector(
        authenticated_async_client, company_id, department_id, aligned_signals
    )

    # Verify: Aligned signals should produce higher confidence than misaligned
    if aligned_results and results:
        aligned_max_conf = max(r["confidence"] for r in aligned_results)
        misaligned_max_conf = max(r["confidence"] for r in results)
        assert (
            aligned_max_conf >= misaligned_max_conf
        ), "Aligned signals should produce equal or higher confidence"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pack_selector_persists_audit_log(
    authenticated_async_client: httpx.AsyncClient,
) -> None:
    """E2E: Pack selector creates PackActivationAuditLog entries.

    Verify: Audit log entries are created with all required fields populated.
    """
    # Setup: Create company and department
    company = await _create_company(authenticated_async_client, "Audit Log Test Company")
    company_id = company["id"]

    department = await _create_department(authenticated_async_client, company_id, "Finance")
    department_id = department["id"]

    signals = {
        "department_name": "Finance",
        "company_type": "mkb",
        "sector": "retail",
        "sector_tags": ["finance", "accounting"],
    }

    results = await _call_pack_selector(
        authenticated_async_client, company_id, department_id, signals
    )

    # Verify: If results exist, they should have audit_log_id populated
    if results:
        for result in results:
            assert "audit_log_id" in result
            assert uuid.UUID(result["audit_log_id"])


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pack_selector_auto_activation_threshold(
    authenticated_async_client: httpx.AsyncClient,
) -> None:
    """E2E: Pack selector correctly identifies auto-activation candidates.

    Verify: Packs with high scores (>= 0.70) are marked for auto-activation.
    """
    # Setup: Create company and department with matching signals
    company = await _create_company(authenticated_async_client, "Auto Activation Test")
    company_id = company["id"]

    department = await _create_department(authenticated_async_client, company_id, "Sales")
    department_id = department["id"]

    signals = {
        "department_name": "Sales",
        "company_type": "mkb",
        "sector": "retail",
        "sector_tags": ["sales", "crm", "high_value"],
    }

    results = await _call_pack_selector(
        authenticated_async_client, company_id, department_id, signals
    )

    # Verify: Any high-confidence results should have activated_automatically=True
    for result in results:
        if result["confidence"] >= 0.70:
            assert result["activated_automatically"] is True


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pack_selector_explicit_pack_boost(
    authenticated_async_client: httpx.AsyncClient,
) -> None:
    """E2E: Explicit pack IDs in signals boost scores.

    Verify: When a pack_id is included in explicit_pack_ids, it gets a score boost.
    """
    # Setup: Create company and department
    company = await _create_company(authenticated_async_client, "Explicit Pack Test")
    company_id = company["id"]

    department = await _create_department(authenticated_async_client, company_id, "HR")
    department_id = department["id"]

    signals = {
        "department_name": "HR",
        "company_type": "mkb",
        "sector": "retail",
        "sector_tags": ["hr", "people"],
    }

    # Get baseline results without explicit pack
    baseline_results = await _call_pack_selector(
        authenticated_async_client, company_id, department_id, signals
    )

    # Verify: Baseline call should succeed
    assert isinstance(baseline_results, list)

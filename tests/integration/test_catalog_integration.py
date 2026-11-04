"""
Integration Tests for Enterprise Catalog Endpoint

Tests GET /api/v1/agents/catalog against the REAL running backend.
No mocks, no placeholders — validates the full stack:
  login → JWT → auth middleware → catalog loader → YAML config → response

Prerequisites:
  - Backend running on localhost (port from BACKEND_PORT env var or 8111)
  - PostgreSQL with admin user seeded
  - config/agents/*.yaml and config/domain_packs.yaml present

Usage:
  pytest tests/integration/test_catalog_integration.py -v
"""

import os

import httpx
import pytest

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8111")
ADMIN_EMAIL = "admin@sanskritisetu.org"
ADMIN_PASSWORD = "Admin123!"

# Expected counts from real YAML config
EXPECTED_AGENT_COUNT = 135
EXPECTED_PACK_COUNT = 80
EXPECTED_DEPARTMENT_COUNT = 25
EXPECTED_VERSION = "2.0.0"


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def backend_available():
    """Skip all tests if backend is not reachable."""
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            pytest.skip(f"Backend not healthy: status {r.status_code}")
    except httpx.ConnectError:
        pytest.skip(f"Backend not reachable at {BASE_URL}")
    except httpx.TimeoutException:
        pytest.skip(f"Backend timed out at {BASE_URL}")


@pytest.fixture(scope="module")
def admin_token(backend_available):
    """Authenticate as admin and return JWT access token."""
    r = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={
            "username": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "grant_type": "password",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} - test user may not exist in database")
    token = r.json().get("access_token")
    if not token:
        pytest.skip("No access_token in login response")
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Authorization headers with Bearer token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def catalog_response(auth_headers):
    """Fetch catalog once per module (expensive call, reuse across tests)."""
    r = httpx.get(
        f"{BASE_URL}/api/v1/agents/catalog",
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 200, f"Catalog request failed: {r.status_code} {r.text}"
    return r.json()


# ============================================================================
# AUTH & ACCESS TESTS
# ============================================================================


class TestCatalogAuth:
    """Verify authentication and authorization for the catalog endpoint."""

    def test_catalog_requires_auth(self, backend_available):
        """Unauthenticated request returns 401 or 403."""
        r = httpx.get(f"{BASE_URL}/api/v1/agents/catalog", timeout=10)
        assert r.status_code in (401, 403)

    def test_catalog_rejects_invalid_token(self, backend_available):
        """Invalid JWT returns 401."""
        r = httpx.get(
            f"{BASE_URL}/api/v1/agents/catalog",
            headers={"Authorization": "Bearer invalid.token.here"},
            timeout=10,
        )
        assert r.status_code in (401, 403)


# ============================================================================
# CATALOG STRUCTURE TESTS
# ============================================================================


class TestCatalogStructure:
    """Validate the overall structure and completeness of the catalog."""

    def test_catalog_returns_200(self, auth_headers, backend_available):
        """Catalog endpoint returns HTTP 200."""
        r = httpx.get(
            f"{BASE_URL}/api/v1/agents/catalog",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 200

    def test_response_has_required_keys(self, catalog_response):
        """Response contains agents, packs, and metadata."""
        assert "agents" in catalog_response
        assert "packs" in catalog_response
        assert "metadata" in catalog_response

    def test_agent_count(self, catalog_response):
        """Catalog contains exactly 135 agents from YAML config."""
        assert len(catalog_response["agents"]) == EXPECTED_AGENT_COUNT

    def test_pack_count(self, catalog_response):
        """Catalog contains exactly 80 domain packs."""
        assert len(catalog_response["packs"]) == EXPECTED_PACK_COUNT


# ============================================================================
# METADATA TESTS
# ============================================================================


class TestCatalogMetadata:
    """Validate catalog metadata accuracy."""

    def test_metadata_version(self, catalog_response):
        """Metadata version is 2.0.0."""
        assert catalog_response["metadata"]["version"] == EXPECTED_VERSION

    def test_metadata_agent_count_matches(self, catalog_response):
        """Metadata totalAgents matches actual agent list length."""
        meta = catalog_response["metadata"]
        assert meta["totalAgents"] == len(catalog_response["agents"])

    def test_metadata_pack_count_matches(self, catalog_response):
        """Metadata totalPacks matches actual pack list length."""
        meta = catalog_response["metadata"]
        assert meta["totalPacks"] == len(catalog_response["packs"])

    def test_metadata_has_timestamp(self, catalog_response):
        """Metadata contains an ISO-format last_updated timestamp."""
        ts = catalog_response["metadata"]["last_updated"]
        assert ts, "last_updated is empty"
        assert "T" in ts, f"Not ISO format: {ts}"


# ============================================================================
# AGENT DATA QUALITY TESTS
# ============================================================================


class TestAgentData:
    """Validate agent data integrity from real YAML config."""

    def test_agent_has_required_fields(self, catalog_response):
        """Every agent has all required fields."""
        required = {
            "id",
            "name",
            "description",
            "department",
            "capabilities",
            "version",
            "status",
            "inputs",
            "outputs",
            "metadata",
        }
        for agent in catalog_response["agents"]:
            missing = required - set(agent.keys())
            assert not missing, f"Agent {agent.get('id', '?')} missing: {missing}"

    def test_all_agents_have_id(self, catalog_response):
        """Every agent has a non-empty id."""
        for agent in catalog_response["agents"]:
            assert agent["id"], f"Agent has empty id: {agent.get('name')}"

    def test_agent_ids_are_unique(self, catalog_response):
        """All agent IDs are unique."""
        ids = [a["id"] for a in catalog_response["agents"]]
        assert len(ids) == len(set(ids)), "Duplicate agent IDs found"

    def test_all_agents_active(self, catalog_response):
        """All 135 loaded agents are active (no deprecated in current config)."""
        statuses = {a["status"] for a in catalog_response["agents"]}
        assert statuses == {"active"}, f"Unexpected statuses: {statuses}"

    def test_department_coverage(self, catalog_response):
        """Agents span exactly 25 departments."""
        departments = {a["department"] for a in catalog_response["agents"]}
        assert (
            len(departments) == EXPECTED_DEPARTMENT_COUNT
        ), f"Expected {EXPECTED_DEPARTMENT_COUNT} departments, got {len(departments)}: {departments}"

    def test_known_departments_present(self, catalog_response):
        """Key departments from enterprise categories exist."""
        departments = {a["department"] for a in catalog_response["agents"]}
        expected_subset = {
            "finance_treasury",
            "hr_culture",
            "it_security",
            "legal_compliance",
            "sales_marketing",
            "operations_supply_chain",
            "communications_pr",
        }
        missing = expected_subset - departments
        assert not missing, f"Missing departments: {missing}"

    def test_agent_metadata_has_technology(self, catalog_response):
        """Every agent's metadata includes a technology field."""
        for agent in catalog_response["agents"]:
            meta = agent.get("metadata", {})
            assert "technology" in meta, f"Agent {agent['id']} missing technology in metadata"

    def test_capabilities_are_lists(self, catalog_response):
        """Capabilities, inputs, and outputs are lists."""
        for agent in catalog_response["agents"]:
            assert isinstance(
                agent["capabilities"], list
            ), f"Agent {agent['id']}: capabilities is not a list"
            assert isinstance(agent["inputs"], list), f"Agent {agent['id']}: inputs is not a list"
            assert isinstance(agent["outputs"], list), f"Agent {agent['id']}: outputs is not a list"


# ============================================================================
# PACK DATA QUALITY TESTS
# ============================================================================


class TestPackData:
    """Validate domain pack data integrity from real YAML config."""

    def test_pack_has_required_fields(self, catalog_response):
        """Every pack has all required fields."""
        required = {"id", "name", "description", "category", "agents", "metadata"}
        for pack in catalog_response["packs"]:
            missing = required - set(pack.keys())
            assert not missing, f"Pack {pack.get('id', '?')} missing: {missing}"

    def test_pack_ids_are_unique(self, catalog_response):
        """All pack IDs are unique."""
        ids = [p["id"] for p in catalog_response["packs"]]
        assert len(ids) == len(set(ids)), "Duplicate pack IDs found"

    def test_pack_categories_diverse(self, catalog_response):
        """Packs span multiple categories (finance, hr, it, etc.)."""
        categories = {p["category"] for p in catalog_response["packs"]}
        expected_subset = {"finance", "hr", "it", "legal", "ops", "sales"}
        missing = expected_subset - categories
        assert not missing, f"Missing pack categories: {missing}"

    def test_pack_has_agents_list(self, catalog_response):
        """Every pack references at least one agent."""
        for pack in catalog_response["packs"]:
            assert isinstance(pack["agents"], list), f"Pack {pack['id']}: agents is not a list"
            assert len(pack["agents"]) > 0, f"Pack {pack['id']} has no agents"

    def test_pack_metadata_has_sla(self, catalog_response):
        """Every pack metadata includes step_count, modes, and total_sla_seconds."""
        for pack in catalog_response["packs"]:
            meta = pack.get("metadata", {})
            assert "step_count" in meta, f"Pack {pack['id']} missing step_count"
            assert "modes" in meta, f"Pack {pack['id']} missing modes"
            assert "total_sla_seconds" in meta, f"Pack {pack['id']} missing total_sla_seconds"
            assert meta["step_count"] > 0, f"Pack {pack['id']} has 0 steps"
            assert meta["total_sla_seconds"] > 0, f"Pack {pack['id']} has 0 SLA"

    def test_pack_modes_valid(self, catalog_response):
        """Pack modes contain only valid values (sequential, parallel)."""
        valid_modes = {"sequential", "parallel"}
        for pack in catalog_response["packs"]:
            modes = set(pack.get("metadata", {}).get("modes", []))
            invalid = modes - valid_modes
            assert not invalid, f"Pack {pack['id']} has invalid modes: {invalid}"


# ============================================================================
# SPECIFIC AGENT VALIDATION
# ============================================================================


class TestSpecificAgents:
    """Spot-check known agents from the YAML config."""

    def test_crisis_manager_exists(self, catalog_response):
        """CrisisManagerAgent from communications_pr is in the catalog."""
        agents_by_id = {a["id"]: a for a in catalog_response["agents"]}
        assert "ext.communications_pr.crisismanager.001" in agents_by_id
        agent = agents_by_id["ext.communications_pr.crisismanager.001"]
        assert agent["name"] == "CrisisManagerAgent"
        assert agent["department"] == "communications_pr"
        assert agent["status"] == "active"

    def test_monthly_close_pack_exists(self, catalog_response):
        """Monthly Financial Close pack is in the catalog."""
        packs_by_id = {p["id"]: p for p in catalog_response["packs"]}
        assert "finance.monthly_close" in packs_by_id
        pack = packs_by_id["finance.monthly_close"]
        assert pack["name"] == "Monthly Financial Close"
        assert pack["category"] == "finance"
        assert len(pack["agents"]) > 0

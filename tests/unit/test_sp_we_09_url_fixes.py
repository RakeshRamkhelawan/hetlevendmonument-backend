"""SP-WE-09: URL fixes for canvas, analytics, pack feedback, explainability."""

import pytest


@pytest.mark.unit
class TestURLFixes:
    def test_pack_feedback_in_production_router_registry(self) -> None:
        """Pack feedback router registered via company Laag 2 registry (ADR-033)."""
        # Na SP-API-001 Dag 5 staat pack_feedback in registries/company.py,
        # niet meer direct in router_registry.py.
        with open("src/core/api/registries/company.py", encoding="utf-8") as f:
            content = f.read()
        assert "pack_feedback" in content

    def test_agent_analytics_ooda_endpoint_exists(self) -> None:
        """Agent analytics /ooda stub endpoint exists in source."""
        with open("src/core/api/v1/analytics/agents.py", encoding="utf-8") as f:
            content = f.read()
        assert "ooda" in content
        assert "501" in content

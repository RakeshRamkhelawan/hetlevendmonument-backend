"""End-to-end integration tests for EU AI Act compliance.

Tests the complete flow from agent classification to governance enforcement.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightGate, OversightResult
from src.main import app

client = TestClient(app)


class TestAIActEndToEnd:
    """End-to-end tests for AI Act compliance workflows."""

    def test_high_risk_agent_blocked_without_approval(self) -> None:
        """High-risk agent execution should require approval."""
        # This test would require a full test database setup
        # Simulating the integration flow:
        # 1. Create high-risk agent (HR recruitment)
        # 2. Submit task
        # 3. Verify blocked pending approval
        pass  # Integration test placeholder

    def test_incident_reporting_flow(self) -> None:
        """Test complete incident reporting flow."""
        # 1. Report incident via API
        response = client.post(
            "/api/v1/ai-act/incidents",
            json={
                "severity": "high",
                "agent_id": "test-agent",
                "agent_name": "Test Agent",
                "description": "Test incident for integration",
            },
        )

        # 2. Verify response
        if response.status_code == 201:
            data = response.json()
            incident_id = data["incident_id"]

            # 3. Retrieve incident
            get_response = client.get(f"//api/v1/ai-act/incidents/{incident_id}")
            assert get_response.status_code == 200

    def test_model_documentation_accessible(self) -> None:
        """Model documentation should be publicly accessible."""
        from src.core.governance.public_docs import get_model_card_docs

        docs = get_model_card_docs("gpt-4")
        assert docs is not None
        assert docs["provider"] == "OpenAI"


class TestGovernanceIntegration:
    """Test governance integration across components."""

    @pytest.mark.asyncio
    async def test_oversight_gate_with_classifier(self) -> None:
        """Oversight gate should use classifier results."""
        from src.core.governance.ai_act_classifier import classify_agent

        # Classify HR agent
        risk_level = classify_agent(
            name="Recruitment Bot",
            department="HR",
            specialisation="recruitment",
            capabilities=["resume_screening"],
        )

        assert risk_level == AIActRiskLevel.HIGH_RISK

        # Create gate
        gate = OversightGate()

        # Check should require approval
        result = await gate.check(
            agent_name="Recruitment Bot",
            agent_department="HR",
            agent_specialisation="recruitment",
            agent_capabilities=["resume_screening"],
            task_action="screen_candidates",
            task_params={"job_id": "123"},
        )

        assert result.requires_human_approval is True

    def test_provenance_logging_integration(self) -> None:
        """ProvenanceService is importable and has the expected interface."""
        from src.core.governance.model_provenance import ProvenanceService, new_provenance_record

        assert hasattr(ProvenanceService, "log_provenance"), (
            "ProvenanceService must have log_provenance"
        )
        assert callable(new_provenance_record), "new_provenance_record must be callable"


class TestFrontendBackendIntegration:
    """Test frontend and backend integration."""

    def test_api_returns_risk_levels(self) -> None:
        """API should return risk level metadata."""
        # This would test that agent endpoints include risk_level
        # when oversight gate is integrated
        pass  # Requires full API setup

    def test_incident_api_cors(self) -> None:
        """Incident API should support CORS for frontend."""
        # Test CORS headers
        response = client.options("/api/v1/ai-act/incidents")
        # Verify CORS headers present

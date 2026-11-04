"""TDD tests -- EU-AI-004 QualityGate._check_risk_classification (SP-DLP-002 Dag 4).

The architecture test test_eu_ai_004_quality_gate_has_risk_classification_check
is already GREEN -- these unit tests verify the method contract.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock


def test_quality_management_has_check_risk_classification() -> None:
    """quality_management.py moet _check_risk_classification() definieren -- EU-AI-004."""
    src = Path("src/core/governance/quality_management.py").read_text(encoding="utf-8")
    assert "_check_risk_classification" in src, (
        "QualityGate mist _check_risk_classification() -- EU-AI-004"
    )


@pytest.mark.asyncio
async def test_quality_gate_risk_classification_returns_bool() -> None:
    """_check_risk_classification() moet een bool retourneren (niet None)."""
    from src.core.governance.quality_management import QualityGate

    mock_db = AsyncMock()
    gate = QualityGate(db=mock_db)
    result = await gate._check_risk_classification(tenant_id=1, agent_name="test-agent")
    assert isinstance(result, bool), (
        "_check_risk_classification() moet bool retourneren -- EU-AI-004"
    )

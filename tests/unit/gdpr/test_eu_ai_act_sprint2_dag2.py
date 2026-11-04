"""TDD tests -- EU AI Act Sprint 2 Dag 2 (EU-AI-001/004/005/007).

RED before fixes, GREEN after.
"""

import inspect


# ──────────────────────────────────────────────────────────────────────────────
# EU-AI-001: GovernanceContract koppeling aan RiskRegister (Art. 9)
# ──────────────────────────────────────────────────────────────────────────────


def test_risk_register_importable() -> None:
    """RiskRegister klasse moet importeerbaar zijn (EU-AI-001 / Art. 9)."""
    try:
        from src.core.governance.risk_register import RiskRegister  # noqa: F401
    except ImportError:
        raise AssertionError(
            "RiskRegister niet importeerbaar -- EU AI Act Art. 9: "
            "geen risicoregister beschikbaar voor governance-contract"
        )


def test_risk_register_validate_contract() -> None:
    """RiskRegister.validate_contract() moet een GovernanceContract valideren (EU-AI-001)."""
    from src.core.governance.governance_contract import GovernanceContract
    from src.core.governance.risk_register import RiskRegister

    rr = RiskRegister()
    contract = GovernanceContract(agent_id="test-agent", tenant_id=1)
    result = rr.validate_contract(contract)
    assert isinstance(result, bool), "validate_contract() moet bool retourneren"


def test_governance_contract_has_risk_register_link() -> None:
    """GovernanceContract moet koppeling naar RiskRegister exposeren (EU-AI-001)."""
    from src.core.governance.governance_contract import GovernanceContract

    src = inspect.getsource(GovernanceContract)
    assert "RiskRegister" in src or "risk_register" in src, (
        "GovernanceContract broncode bevat geen verwijzing naar RiskRegister -- "
        "EU AI Act Art. 9: risk assessment niet gekoppeld aan contract"
    )


# ──────────────────────────────────────────────────────────────────────────────
# EU-AI-004: HITL-goedkeuring opslaan in GovernanceContract.evidence (Art. 14)
# ──────────────────────────────────────────────────────────────────────────────


def test_governance_contract_has_record_hitl_approval() -> None:
    """GovernanceContract.record_hitl_approval() must exist (EU-AI-004 / Art. 14)."""
    from src.core.governance.governance_contract import GovernanceContract

    assert hasattr(GovernanceContract, "record_hitl_approval"), (
        "GovernanceContract.record_hitl_approval() ontbreekt -- "
        "EU AI Act Art. 14: HITL-goedkeuring niet aantoonbaar opgeslagen"
    )


def test_record_hitl_approval_stores_in_evidence() -> None:
    """record_hitl_approval() moet approved_actions opslaan in evidence (EU-AI-004)."""
    from src.core.governance.governance_contract import GovernanceContract

    contract = GovernanceContract(agent_id="test-agent", tenant_id=1)
    contract.record_hitl_approval(approved_by="reviewer@test.com", action="execute")
    assert "hitl_approval" in contract.evidence, (
        "record_hitl_approval() slaat niet op in evidence['hitl_approval'] -- "
        "EU AI Act Art. 14: geen traceerbaarheid van HITL-goedkeuring"
    )


def test_record_hitl_approval_enables_human_in_loop_action() -> None:
    """Na HITL-goedkeuring moet is_action_permitted() True retourneren voor HUMAN_IN_LOOP (EU-AI-004)."""
    from src.core.governance.governance_contract import AutonomyLevel, GovernanceContract

    contract = GovernanceContract(
        agent_id="test-agent",
        tenant_id=1,
        autonomy_level=AutonomyLevel.HUMAN_IN_LOOP,
    )
    contract.record_hitl_approval(approved_by="reviewer@test.com", action="execute")
    assert contract.is_action_permitted("execute") is True, (
        "is_action_permitted() retourneert False na HITL-goedkeuring -- "
        "EU AI Act Art. 14: goedgekeurde actie wordt onterecht geblokkeerd"
    )


# ──────────────────────────────────────────────────────────────────────────────
# EU-AI-005: AI-disclosure bij start van interactie (Art. 52)
# ──────────────────────────────────────────────────────────────────────────────


def test_get_ai_disclosure_text_importable() -> None:
    """get_ai_disclosure_text() moet importeerbaar zijn uit attribution (EU-AI-005 / Art. 52)."""
    try:
        from src.core.governance.attribution import get_ai_disclosure_text  # noqa: F401
    except ImportError:
        raise AssertionError(
            "get_ai_disclosure_text() niet importeerbaar -- "
            "EU AI Act Art. 52: geen standaard AI-disclosure tekst beschikbaar"
        )


def test_get_ai_disclosure_text_returns_nonempty_string() -> None:
    """get_ai_disclosure_text() moet een niet-lege string retourneren (EU-AI-005)."""
    from src.core.governance.attribution import get_ai_disclosure_text

    text = get_ai_disclosure_text()
    assert isinstance(text, str) and len(text) > 20, (
        "get_ai_disclosure_text() retourneert lege of te korte string -- "
        "EU AI Act Art. 52: disclosure tekst onvoldoende informatief"
    )


def test_get_ai_disclosure_text_contains_ai_keyword() -> None:
    """AI-disclosure tekst moet 'AI' of 'artificial intelligence' bevatten (EU-AI-005 / Art. 52)."""
    from src.core.governance.attribution import get_ai_disclosure_text

    text = get_ai_disclosure_text().lower()
    assert "ai" in text or "artificial intelligence" in text, (
        "disclosure tekst bevat geen 'AI' of 'artificial intelligence' -- "
        "EU AI Act Art. 52: gebruiker wordt niet geidentificeerd dat ze met AI interageren"
    )


# ──────────────────────────────────────────────────────────────────────────────
# EU-AI-007: Explainability endpoint (GET /decisions/{id}/explanation)
# ──────────────────────────────────────────────────────────────────────────────


def test_explanation_endpoint_router_importable() -> None:
    """Explainability router moet importeerbaar zijn (EU-AI-007)."""
    try:
        from src.core.api.v1.gdpr_compliance import explanation_router  # noqa: F401
    except ImportError:
        try:
            from src.core.governance.explainability_router import router  # noqa: F401
        except ImportError:
            raise AssertionError(
                "Explainability router niet importeerbaar -- "
                "EU AI Act Art. 13/86: /decisions/{id}/explanation endpoint niet beschikbaar"
            )


def test_explanation_router_has_decisions_route() -> None:
    """Explanation router moet een route met 'decisions' bevatten (EU-AI-007)."""
    try:
        from src.core.api.v1.gdpr_compliance import explanation_router as mod

        src = inspect.getsource(mod)
    except ImportError:
        from src.core.governance import explainability_router as mod

        src = inspect.getsource(mod)

    assert "decisions" in src, (
        "Explainability router bevat geen 'decisions' route -- "
        "EU AI Act Art. 13/86: /decisions/{id}/explanation endpoint niet geimplementeerd"
    )

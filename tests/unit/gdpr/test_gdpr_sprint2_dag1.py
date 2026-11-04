"""TDD tests -- GDPR Sprint 2 Dag 1 (AUDIT-GDPR-001/003/007/008).

RED before fixes, GREEN after.
"""

import inspect


# ──────────────────────────────────────────────────────────────────────────────
# GDPR-008: Hard delete cascade compleet (UserConsent, AIDecision, etc.)
# ──────────────────────────────────────────────────────────────────────────────


def _delete_src() -> str:
    from src.core.governance.dsar_service import DSARService

    return inspect.getsource(DSARService.delete_user_data)


def test_hard_delete_includes_user_consent() -> None:
    """Hard delete moet UserConsent verwijderen (AUDIT-GDPR-008 / Art. 17)."""
    src = _delete_src()
    assert "UserConsent" in src, (
        "delete_user_data() hard-delete branch bevat geen UserConsent delete -- "
        "GDPR Art. 17 Right to Erasure onvolledig: UserConsent blijft achter"
    )


def test_hard_delete_includes_ai_decision() -> None:
    """Hard delete moet AIDecision verwijderen (AUDIT-GDPR-008 / Art. 17)."""
    src = _delete_src()
    assert "AIDecision" in src, (
        "delete_user_data() hard-delete branch bevat geen AIDecision delete -- "
        "GDPR Art. 17 Right to Erasure onvolledig: AIDecision blijft achter"
    )


def test_hard_delete_includes_user_profiling_opt_out() -> None:
    """Hard delete moet UserProfilingOptOut verwijderen (AUDIT-GDPR-008 / Art. 17)."""
    src = _delete_src()
    assert "UserProfilingOptOut" in src, (
        "delete_user_data() hard-delete branch bevat geen UserProfilingOptOut delete -- "
        "GDPR Art. 17 Right to Erasure onvolledig: profiling opt-out records blijven achter"
    )


def test_hard_delete_includes_point_transaction() -> None:
    """Hard delete moet PointTransaction verwijderen (AUDIT-GDPR-008 / Art. 17)."""
    src = _delete_src()
    assert "PointTransaction" in src, (
        "delete_user_data() hard-delete branch bevat geen PointTransaction delete -- "
        "GDPR Art. 17 Right to Erasure onvolledig: gamification data blijft achter"
    )


# ──────────────────────────────────────────────────────────────────────────────
# GDPR-007: Portability filter op user_id (Art. 20)
# ──────────────────────────────────────────────────────────────────────────────


def _portability_src() -> str:
    from src.core.api.v1.gdpr_compliance import portability_router

    return inspect.getsource(portability_router)


def test_portability_agents_filtered_by_user() -> None:
    """Agent export moet gefilterd zijn op created_by == current_user.id (AUDIT-GDPR-007)."""
    src = _portability_src()
    assert "created_by" in src, (
        "portability_router.py filtert agents NIET op created_by / user_id -- "
        "GDPR Art. 20: gebruiker ontvangt data van alle collega's in de tenant"
    )


def test_portability_workflows_filtered_by_user() -> None:
    """Workflow export moet gefilterd zijn op created_by == current_user.id (AUDIT-GDPR-007)."""
    src = _portability_src()
    # Verify the TODO comments are gone -- replaced by actual filter
    assert "# TODO(Rakesh): filter on Workflow" not in src, (
        "portability_router.py: Workflow TODO nog aanwezig -- filter op created_by nog niet geimplementeerd"
    )


def test_portability_agents_todo_resolved() -> None:
    """Agent export TODO moet opgelost zijn (AUDIT-GDPR-007)."""
    src = _portability_src()
    assert "# TODO(Rakesh): filter on Agent" not in src, (
        "portability_router.py: Agent TODO nog aanwezig -- filter op created_by nog niet geimplementeerd"
    )


# ──────────────────────────────────────────────────────────────────────────────
# GDPR-003: Art. 13 privacy notice endpoint aanwezig
# ──────────────────────────────────────────────────────────────────────────────


def test_privacy_notice_endpoint_exists() -> None:
    """GET /privacy/notice endpoint moet bestaan (AUDIT-GDPR-003 / Art. 13)."""
    src = _portability_src()
    assert "/privacy/notice" in src or "privacy_notice" in src, (
        "portability_router.py bevat geen GET /privacy/notice endpoint -- "
        "GDPR Art. 13: privacyinformatie niet beschikbaar voor betrokkenen"
    )


def test_privacy_notice_contains_required_fields() -> None:
    """Privacy notice moet Art. 13-verplichte velden bevatten (AUDIT-GDPR-003)."""
    src = _portability_src()
    required = ["controller", "dpo", "legal_basis", "retention", "data_subject_rights"]
    missing = [f for f in required if f not in src]
    assert not missing, f"privacy notice endpoint mist Art. 13-verplichte velden: {missing}"


# ──────────────────────────────────────────────────────────────────────────────
# GDPR-001: RequiresLawfulBasis FastAPI dependency importeerbaar
# ──────────────────────────────────────────────────────────────────────────────


def test_lawful_basis_dependency_importable() -> None:
    """lawful_basis_dependency FastAPI factory moet importeerbaar zijn (AUDIT-GDPR-001)."""
    try:
        from src.core.governance.lawful_basis_registry import lawful_basis_dependency  # noqa: F401
    except ImportError:
        raise AssertionError(
            "lawful_basis_dependency niet importeerbaar uit lawful_basis_registry -- "
            "GDPR Art. 6: geen afdwingbare FastAPI dependency voor rechtsgrondencontrole"
        )


def test_lawful_basis_dependency_returns_callable() -> None:
    """lawful_basis_dependency(endpoint) moet een FastAPI Depends-compatibele callable retourneren (AUDIT-GDPR-001)."""
    from src.core.governance.lawful_basis_registry import lawful_basis_dependency

    dep = lawful_basis_dependency("/api/test")
    assert callable(dep), (
        "lawful_basis_dependency() retourneert geen callable -- "
        "kan niet als FastAPI Depends() gebruikt worden"
    )

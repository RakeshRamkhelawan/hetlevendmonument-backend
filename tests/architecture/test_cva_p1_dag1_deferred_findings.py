"""Architecture tests for SP-CVA-P1 Dag 1 deferred FA-findings.

These tests are intentionally RED (failing) until the backlog items are fixed.
Each test documents a specific FA-finding that was deferred from the independent review.
CI must keep failing until each item is resolved.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_risk_register_adapter_fail_safe_on_missing_tenant() -> None:
    """TODO(SP-CVA-P1-BACKLOG): _RiskRegisterAdapter must fail-safe when tenant_id is None.

    FA-002 (code-reviewer): _RiskRegisterAdapter.actor_track_record() applies the tenant_id
    filter only conditionally (if tenant_id is not None). When the ContextVar is unset,
    queries return cross-tenant rows -- violating ADR-004/ADR-005 tenant isolation.

    Fix: add `if tenant_id is None: return []` BEFORE the execute() call.
    Test becomes GREEN when factory.py has an early-return guard for None tenant_id.
    """
    source = (_REPO_ROOT / "src/core/copilot/council/factory.py").read_text(encoding="utf-8")
    # Verify the fix: the adapter must have an early-return guard for None tenant_id
    # before touching the DB. Currently it does not -- this assertion fails until fixed.
    has_guard = (
        "if tenant_id is None:\n                return []" in source
        or "if tenant_id is None: return []" in source
    )
    assert has_guard, (
        "_RiskRegisterAdapter.actor_track_record() lacks an early-return guard for None tenant_id. "
        "Without this, queries proceed without tenant filter when ContextVar is unset -- "
        "ADR-004/ADR-005 tenant isolation violation. "
        "Fix: add `if tenant_id is None: return []` before the `execute()` call in factory.py. "
        "SP-CVA-P1-BACKLOG: FA-002 (code-reviewer) deferred from dag 1 review."
    )


def test_chat_router_system_prompt_import_via_facade() -> None:
    """TODO(SP-CVA-P1-BACKLOG): chat_router.py must not import directly from agents (ADR-033).

    FA-004 (code-reviewer): chat_router.py has a top-level import:
      from src.core.agents.ultimate_cva.system_prompt import get_system_prompt
    This is a forbidden direct domain-import from a router file (ADR-033 Contract 1).
    The import-linter only covers files named router.py -- chat_router.py slips through.

    Fix: move get_system_prompt into dependencies.py (the ADR-033 facade), then import
    from src.core.api.v1.cva.dependencies in chat_router.py.
    Test becomes GREEN when chat_router.py no longer imports from src.core.agents directly.
    """
    source = (_REPO_ROOT / "src/core/api/v1/cva/chat_router.py").read_text(encoding="utf-8")
    has_direct_agent_import = "from src.core.agents.ultimate_cva.system_prompt" in source
    assert not has_direct_agent_import, (
        "chat_router.py contains a direct import from src.core.agents.ultimate_cva.system_prompt. "
        "ADR-033 forbids direct domain-imports in router files. "
        "Fix: move get_system_prompt into dependencies.py and import from the facade. "
        "SP-CVA-P1-BACKLOG: FA-004 (code-reviewer) deferred from dag 1 review."
    )


def test_prompt_injection_error_does_not_leak_tenant_id_in_details() -> None:
    """TODO(SP-CVA-P1-BACKLOG): PromptInjectionError must not include tenant_id in details.

    FA-004 (security-reviewer): src/core/ai/prompt_guard.py creates PromptInjectionError with
      details={"tenant_id": tenant_id}
    If any AI route forgets the local except-PromptInjectionError catch, the global
    sanskriti_error_handler serialises the exception (incl. details) into the HTTP response,
    leaking tenant_id to the client.

    Fix: remove details={"tenant_id": tenant_id} from the PromptInjectionError constructor
    in prompt_guard.py. The tenant_id is already logged at WARNING level above the raise.
    Test becomes GREEN when prompt_guard.py no longer passes tenant_id in exception details.
    """
    source = (_REPO_ROOT / "src/core/ai/prompt_guard.py").read_text(encoding="utf-8")
    has_tenant_in_details = 'details={"tenant_id"' in source or "details={'tenant_id'" in source
    assert not has_tenant_in_details, (
        "prompt_guard.py passes details={'tenant_id': tenant_id} to PromptInjectionError. "
        "If the local HTTP-entry catch is ever missing, the global exception handler "
        "serialises tenant_id into the 400 response -- OWASP A05 information disclosure. "
        "Fix: remove the details= kwarg; tenant_id is already in the WARNING log. "
        "SP-CVA-P1-BACKLOG: FA-004 (security-reviewer) deferred from dag 1 review."
    )


def test_proactive_endpoint_documents_no_prompt_guard_scan() -> None:
    """TODO(SP-CVA-P1-BACKLOG): proactive respond endpoint should scan or document why not.

    FA-002 (security-reviewer): turn_endpoint.py /proactive/{signal_id}/respond accepts
    a ProactiveResponseRequest with a free `params` dict. It has no PromptGuard scan.
    If params is ever forwarded to an LLM call, there is no HTTP-level guard.

    Fix: either add a PromptGuard scan on the relevant free-text field in ProactiveResponseRequest,
    or add an explicit comment explaining why scanning is not needed (e.g. params is enum-bounded).
    Test becomes GREEN when a scan or explicit no-scan comment is present.
    """
    source = (_REPO_ROOT / "src/core/copilot/api/turn_endpoint.py").read_text(encoding="utf-8")
    proactive_section_start = source.find("respond_to_proactive_signal")
    assert proactive_section_start != -1, "respond_to_proactive_signal handler not found"
    proactive_section = source[proactive_section_start : proactive_section_start + 800]
    has_scan = "_prompt_guard" in proactive_section
    has_no_scan_comment = (
        "no-prompt-guard" in proactive_section or "no prompt guard" in proactive_section.lower()
    )
    assert has_scan or has_no_scan_comment, (
        "turn_endpoint.py respond_to_proactive_signal has no PromptGuard scan and no "
        "explanatory comment. If params is forwarded to an LLM, injection is unguarded. "
        "Fix: add _prompt_guard.sanitize() on free-text params, or add a comment: "
        "# no-prompt-guard: params is enum-bounded, never raw LLM input. "
        "SP-CVA-P1-BACKLOG: FA-002 (security-reviewer) deferred from dag 1 review."
    )

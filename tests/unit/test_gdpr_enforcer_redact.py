"""TDD tests for GDPREnforcer.redact_pii() + detokenize() -- SP-DLP-001 Dag 2."""

import asyncio

from src.core.governance.gdpr_enforcer import GDPREnforcer, _pii_token_map


def test_redact_pii_replaces_email_with_placeholder():
    enforcer = GDPREnforcer()
    masked, token_map = enforcer.redact_pii("Stuur naar jan@example.com graag")
    assert "jan@example.com" not in masked
    assert len(token_map) == 1
    original = list(token_map.values())[0]
    assert original == "jan@example.com"


def test_redact_pii_no_pii_returns_text_and_empty_map():
    enforcer = GDPREnforcer()
    text = "Dit bericht bevat geen persoonlijke gegevens."
    masked, token_map = enforcer.redact_pii(text)
    assert masked == text
    assert token_map == {}


def test_redact_pii_placeholder_is_present_in_masked_text():
    enforcer = GDPREnforcer()
    masked, token_map = enforcer.redact_pii("jan@example.com")
    placeholder = list(token_map.keys())[0]
    assert placeholder in masked


def test_detokenize_restores_original_email():
    enforcer = GDPREnforcer()
    masked, token_map = enforcer.redact_pii("Stuur naar jan@example.com")
    restored = enforcer.detokenize(masked, token_map)
    assert restored == "Stuur naar jan@example.com"


def test_detokenize_empty_map_returns_text_unchanged():
    enforcer = GDPREnforcer()
    text = "Geen tokens in deze tekst."
    assert enforcer.detokenize(text, {}) == text


def test_redact_pii_replaces_all_occurrences_of_same_pii_type():
    enforcer = GDPREnforcer()
    masked, token_map = enforcer.redact_pii("jan@example.com en piet@example.com")
    assert "jan@example.com" not in masked, "eerste email lekt naar provider"
    assert "piet@example.com" not in masked, "tweede email lekt naar provider"
    assert len(token_map) == 2, f"verwacht 2 tokens, kreeg {len(token_map)}"


def test_redact_pii_sets_contextvar():
    """R5: redact_pii() moet de token_map opslaan in de ContextVar."""
    enforcer = GDPREnforcer()
    _pii_token_map.set(None)
    masked, token_map = enforcer.redact_pii("jan@example.com")
    stored = _pii_token_map.get()
    assert stored == token_map, f"ContextVar niet gezet door redact_pii(): {stored!r}"


def test_redact_pii_contextvar_is_isolated():
    """Tasks binnen hetzelfde gather hebben eigen context -- token_maps mogen niet mengen."""

    async def task_a() -> dict[str, str]:
        _pii_token_map.set({"[TOKEN_PII_0]": "a@a.nl"})
        await asyncio.sleep(0)
        result = _pii_token_map.get()
        return result if result is not None else {}

    async def task_b() -> dict[str, str]:
        _pii_token_map.set({"[TOKEN_PII_0]": "b@b.nl"})
        await asyncio.sleep(0)
        result = _pii_token_map.get()
        return result if result is not None else {}

    async def run() -> tuple[dict[str, str], dict[str, str]]:
        results = await asyncio.gather(task_a(), task_b())
        return results[0], results[1]

    a_result, b_result = asyncio.run(run())
    assert a_result != b_result

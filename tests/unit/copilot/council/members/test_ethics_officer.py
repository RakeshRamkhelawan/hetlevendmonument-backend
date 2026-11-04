from datetime import datetime, timezone
from uuid import uuid4

import json

import pytest

from src.core.copilot.council.members.ethics_officer import EthicsOfficer
from src.core.copilot.council.types import (
    DataClassification,
    DeliberationContext,
    Proposal,
    ProposalTrigger,
    VerdictType,
)


class MockCache:
    def __init__(self):
        self.store = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: dict, ttl: int):
        self.store[key] = value


@pytest.fixture
def proposal():
    return Proposal(
        tenant_id=1,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="test_action",
        action_params={},
        reasoning="This is a test reasoning.",
        data_classification=DataClassification.PUBLIC,
        confidence=0.9,
        model_id="test",
        model_version="1.0",
        context_snapshot={},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def context():
    return DeliberationContext(
        tenant_settings={},
        user_preferences={"language": "nl"},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=uuid4(),
    )


@pytest.fixture
def officer():
    return EthicsOfficer()


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_when_no_bias_terms(officer, proposal, context):
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "NO_BIAS_DETECTED"
    assert verdict.evidence["language_used"] == "nl"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_on_single_medium_term(officer, proposal, context):
    # 'meestal' is 1 medium term
    object.__setattr__(proposal, "reasoning", "meestal is dit goed.")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_on_two_medium_terms(officer, proposal, context):
    # 2 medium terms: 'meestal' and 'altijd'
    object.__setattr__(proposal, "reasoning", "meestal is dit altijd goed.")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_modify_on_single_high_bias_term(officer, proposal, context):
    object.__setattr__(proposal, "reasoning", "alle mannen doen dit.")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert verdict.reason_code == "HIGH_BIAS_LANGUAGE_DETECTED"
    assert "alle mannen" in verdict.evidence["high_matches"]
    # De AANGEPASTE TEKST staat sinds ADR-036 OP-95 niet meer in de evidence, alleen het feit dat
    # er is aangepast en hoeveel. Die tekst was de VOLLEDIGE `proposal.reasoning` en ging via
    # `compute_officer_verdicts_hash()` de onuitwisbare ADR-019-keten in. Gemeten dat niets hem
    # gebruikte: `copilot/service.py:494-497` leest uitsluitend `officer_mods["action_params"]`.
    assert verdict.evidence["modifications"]["reasoning_modified"] is True
    assert verdict.evidence["modifications"]["replacements"] == 1


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_modify_on_multiple_high_bias_terms(officer, proposal, context):
    object.__setattr__(proposal, "reasoning", "alle mannen en alle vrouwen doen dit.")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert "alle mannen" in verdict.evidence["high_matches"]
    assert "alle vrouwen" in verdict.evidence["high_matches"]


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_modify_on_three_medium_bias_terms(officer, proposal, context):
    object.__setattr__(proposal, "reasoning", "meestal is het altijd en nooit goed.")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert verdict.reason_code == "EXCESSIVE_GENERALIZATION"
    assert len(verdict.evidence["medium_matches"]) >= 3


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_language_dutch_uses_dutch_lexicon(officer, proposal, context):
    context.user_preferences["language"] = "nl"
    object.__setattr__(proposal, "reasoning", "alle mannen")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.evidence["language_used"] == "nl"
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_language_english_uses_english_lexicon(officer, proposal, context):
    context.user_preferences["language"] = "en"
    object.__setattr__(proposal, "reasoning", "all men")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.evidence["language_used"] == "en"
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_unknown_language_falls_back_to_dutch(officer, proposal, context):
    context.user_preferences["language"] = "fr"
    object.__setattr__(proposal, "reasoning", "alle mannen")
    verdict = await officer.deliberate(proposal, context)
    assert verdict.evidence["language_used"] == "nl"
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_miss_invokes_lexicon_logic(proposal, context):
    cache = MockCache()
    officer = EthicsOfficer(cache=cache)
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE
    assert not verdict.used_cache


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_hit_returns_cached_verdict(proposal, context):
    cache = MockCache()
    officer = EthicsOfficer(cache=cache)
    # First call sets cache
    await officer.deliberate(proposal, context)
    # Modify proposal to normally cause modify, but cache will return approve
    object.__setattr__(proposal, "reasoning", "alle mannen")
    verdict = await officer.deliberate(proposal, context)
    # Note: the cache key uses a hash of reasoning, so changing the reasoning changes the cache key.
    # We must explicitly set the cache for the new key.
    cache_key = officer._cache_key(proposal, "nl")
    await cache.set(
        cache_key,
        {
            "verdict": VerdictType.APPROVE_WITH_MODIFICATION.value,
            "reason_code": "CACHED_MOD",
            "reason_text": "text",
            "evidence": {},
        },
        300,
    )
    verdict2 = await officer.deliberate(proposal, context)
    assert verdict2.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert verdict2.used_cache is True
    assert verdict2.reason_code == "CACHED_MOD"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_modification_is_recorded_without_the_text(officer, proposal, context):
    """Sinds ADR-036 OP-95 legt de evidence het FEIT vast, niet de tekst.

    Deze test heette `test_modification_includes_neutralized_text` en eiste dat de geneutraliseerde
    tekst in de evidence stond. Die tekst is de volledige `proposal.reasoning` met alleen de
    bias-termen vervangen -- tot 10.000 tekens modeltekst -- en gaat mee in `decision_hash`, en dus
    de onuitwisbare keten in.

    Gemeten dat er geen consument was: `copilot/service.py:494-497` leest uitsluitend
    `officer_mods["action_params"]`. De tekst werd dus permanent vastgelegd zonder dat iets hem
    opvroeg. De eigenschap die deze test hoort te bewaken -- het raadslid detecteert bias en grijpt
    in -- staat hieronder, en die is niet verzwakt.
    """
    object.__setattr__(proposal, "reasoning", "alle mannen weten dit.")
    verdict = await officer.deliberate(proposal, context)

    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert verdict.evidence["modifications"]["reasoning_modified"] is True
    assert "alle mannen" in verdict.evidence["high_matches"]
    assert "weten dit" not in json.dumps(verdict.evidence, default=str), (
        "De onderbouwing bevat nog steeds tekst uit het `reasoning` van het model."
    )


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_includes_lexicon_version(officer, proposal, context):
    verdict = await officer.deliberate(proposal, context)
    assert "lexicon_version" in verdict.evidence
    assert verdict.evidence["lexicon_version"] == "1.0.0"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_ethics_officer_never_emits_veto(officer, context):
    import random

    words = ["alle mannen", "meestal", "nooit", "test", "waarom", "alle vrouwen", "die mensen"]
    for i in range(100):
        # Pick 1-5 random words
        reasoning = " ".join(random.sample(words, random.randint(1, 5)))
        p = Proposal(
            tenant_id=1,
            user_id=1,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="test",
            action_params={},
            reasoning=reasoning,
            data_classification=DataClassification.PUBLIC,
            confidence=0.9,
            model_id="test",
            model_version="1.0",
            context_snapshot={},
            timestamp=datetime.now(timezone.utc),
        )
        verdict = await officer.deliberate(p, context)
        assert verdict.verdict not in (
            VerdictType.VETO,
            VerdictType.REQUIRE_DEFERRAL,
            VerdictType.REQUIRE_HITL,
        )


@pytest.mark.unit
@pytest.mark.als
def test_can_veto_class_attribute_is_false():
    assert EthicsOfficer.can_veto is False


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_exception_returns_fallback_approve(officer, proposal, context):
    # Force an exception by passing an invalid type that fails in .lower()
    object.__setattr__(proposal, "reasoning", 123)
    verdict = await officer.deliberate(proposal, context)
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "OFFICER_ERROR"

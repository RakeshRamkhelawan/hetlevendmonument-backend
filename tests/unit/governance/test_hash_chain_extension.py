import pytest
import hashlib
import json
from src.core.governance.hash_chain import compute_chain_hash, compute_officer_verdicts_hash
from src.core.copilot.council.types import OfficerVerdict
from src.core.copilot.council.members.base import VerdictType

@pytest.mark.unit
def test_compute_chain_hash_without_ai_context_matches_legacy_signature():
    """Verify that omitting ai_context produces the exact same hash as the legacy implementation."""
    # The legacy format was basically sha256(canonical JSON of the basic dict).
    # Wait, the prompt says the previous implementation was:
    # data: dict = { "decision_id": ..., "timestamp": ..., "tenant_id": ..., "user_id": ...,
    # "action_type": ..., "action_params_canonical_sha256": _sha256(...), "previous_hash": ... }
    # So we just verify it matches what we expect from that JSON.
    decision_id = "test_decision_1"
    timestamp = "2026-05-23T12:00:00Z"
    tenant_id = 1
    user_id = 42
    action_type = "test_action"
    action_params_canonical = '{"key":"value"}'
    previous_hash = "abcdef123456"

    legacy_data = {
        "decision_id": decision_id,
        "timestamp": timestamp,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "action_type": action_type,
        "action_params_canonical_sha256": hashlib.sha256(action_params_canonical.encode("utf-8")).hexdigest(),
        "previous_hash": previous_hash,
    }
    legacy_canonical = json.dumps(legacy_data, sort_keys=True, separators=(",", ":"))
    expected_legacy_hash = hashlib.sha256(legacy_canonical.encode("utf-8")).hexdigest()

    actual_hash = compute_chain_hash(
        decision_id=decision_id,
        timestamp=timestamp,
        tenant_id=tenant_id,
        user_id=user_id,
        action_type=action_type,
        action_params_canonical=action_params_canonical,
        previous_hash=previous_hash,
    )

    assert actual_hash == expected_legacy_hash

@pytest.mark.unit
def test_compute_chain_hash_with_none_ai_context_equals_default():
    """ai_context=None produces the same result as omitting it."""
    hash1 = compute_chain_hash(
        decision_id="test_decision_1",
        timestamp="2026-05-23T12:00:00Z",
        tenant_id=1,
        user_id=42,
        action_type="test_action",
        action_params_canonical='{"key":"value"}',
        previous_hash="abcdef123456",
    )
    hash2 = compute_chain_hash(
        decision_id="test_decision_1",
        timestamp="2026-05-23T12:00:00Z",
        tenant_id=1,
        user_id=42,
        action_type="test_action",
        action_params_canonical='{"key":"value"}',
        previous_hash="abcdef123456",
        ai_context=None,
    )
    assert hash1 == hash2

@pytest.mark.unit
def test_compute_chain_hash_with_ai_context_produces_different_hash():
    """Adding ai_context produces a different hash than without."""
    hash1 = compute_chain_hash(
        decision_id="test_decision_1",
        timestamp="2026-05-23T12:00:00Z",
        tenant_id=1,
        user_id=42,
        action_type="test_action",
        action_params_canonical='{"key":"value"}',
        previous_hash="abcdef123456",
    )
    hash2 = compute_chain_hash(
        decision_id="test_decision_1",
        timestamp="2026-05-23T12:00:00Z",
        tenant_id=1,
        user_id=42,
        action_type="test_action",
        action_params_canonical='{"key":"value"}',
        previous_hash="abcdef123456",
        ai_context={
            "proposal_id": "prop1",
            "model_id": "test_model",
            "model_version": "v1",
            "reasoning_hash": "hash",
            "data_classification": "public",
            "officer_verdicts_hash": "verdicts",
        },
    )
    assert hash1 != hash2

@pytest.mark.unit
def test_ai_context_field_order_does_not_affect_hash():
    """Different order of ai_context keys should yield the same hash."""
    kwargs = dict(
        decision_id="test_decision_1",
        timestamp="2026-05-23T12:00:00Z",
        tenant_id=1,
        user_id=42,
        action_type="test_action",
        action_params_canonical='{"key":"value"}',
        previous_hash="abcdef123456",
    )
    hash1 = compute_chain_hash(
        **kwargs,
        ai_context={
            "proposal_id": "prop1",
            "model_id": "test_model",
        },
    )
    hash2 = compute_chain_hash(
        **kwargs,
        ai_context={
            "model_id": "test_model",
            "proposal_id": "prop1",
        },
    )
    assert hash1 == hash2

@pytest.mark.unit
def test_ai_context_extra_keys_are_ignored():
    """Extra keys should not affect the hash due to strict whitelisting."""
    kwargs = dict(
        decision_id="test_decision_1",
        timestamp="2026-05-23T12:00:00Z",
        tenant_id=1,
        user_id=42,
        action_type="test_action",
        action_params_canonical='{"key":"value"}',
        previous_hash="abcdef123456",
    )
    hash1 = compute_chain_hash(
        **kwargs,
        ai_context={
            "proposal_id": "prop1",
            "model_id": "test_model",
        },
    )
    hash2 = compute_chain_hash(
        **kwargs,
        ai_context={
            "proposal_id": "prop1",
            "model_id": "test_model",
            "unauthorized_key": "injected_value",
        },
    )
    assert hash1 == hash2

@pytest.mark.unit
def test_officer_verdicts_hash_deterministic_across_verdict_order():
    """Sorting by officer_name makes the hash deterministic."""
    v1 = OfficerVerdict(
        officer_name="EthicsOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        confidence=0.9,
        reason_code="OK",
        reason_text="ok",
        evidence={},
        deliberation_ms=10,
    )
    v2 = OfficerVerdict(
        officer_name="SecurityOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.VETO,
        confidence=0.99,
        reason_code="DENY",
        reason_text="no",
        evidence={},
        deliberation_ms=10,
    )

    hash1 = compute_officer_verdicts_hash([v1, v2])
    hash2 = compute_officer_verdicts_hash([v2, v1])
    assert hash1 == hash2

@pytest.mark.unit
def test_officer_verdicts_hash_changes_on_confidence_change():
    """A small change in confidence leads to a different hash."""
    v1 = OfficerVerdict(
        officer_name="EthicsOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        confidence=0.95,
        reason_code="OK",
        reason_text="ok",
        evidence={},
        deliberation_ms=10,
    )
    v2 = OfficerVerdict(
        officer_name="EthicsOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        confidence=0.96,
        reason_code="OK",
        reason_text="ok",
        evidence={},
        deliberation_ms=10,
    )
    hash1 = compute_officer_verdicts_hash([v1])
    hash2 = compute_officer_verdicts_hash([v2])
    assert hash1 != hash2

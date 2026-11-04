"""Unit tests for Signal data type."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.types import Signal


@pytest.mark.unit
class TestSignalValidation:
    def _valid_signal(self, **kwargs: object) -> Signal:
        defaults = {
            "tenant_id": 1,
            "affected_user_id": 1,
            "monitor_name": "mock",
            "title": "Title",
            "body": "Body",
            "severity": Severity.LOW,
            "data_classification": DataClassification.INTERNAL,
            "suggested_actions": [],
            "detection_reasoning": "reason",
            "confidence": 0.5,
            "context": {},
        }
        defaults.update(kwargs)  # type: ignore[arg-type]
        return Signal(**defaults)  # type: ignore[arg-type]

    def test_signal_creation_success(self) -> None:
        signal = self._valid_signal()
        assert signal.tenant_id == 1
        assert signal.title == "Title"
        assert isinstance(signal.signal_id, UUID)
        assert signal.created_at.tzinfo is not None

    def test_signal_validation_rejects_negative_confidence(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            self._valid_signal(confidence=-0.1)

    def test_signal_validation_rejects_over_one_confidence(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            self._valid_signal(confidence=1.1)

    def test_signal_validation_rejects_empty_title(self) -> None:
        with pytest.raises(ValueError, match="title and body"):
            self._valid_signal(title="")

    def test_signal_validation_rejects_empty_body(self) -> None:
        with pytest.raises(ValueError, match="title and body"):
            self._valid_signal(body="")

    def test_signal_validation_rejects_zero_tenant_id(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            self._valid_signal(tenant_id=0)

    def test_signal_validation_rejects_negative_tenant_id(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            self._valid_signal(tenant_id=-1)

    def test_signal_validation_rejects_zero_user_id(self) -> None:
        with pytest.raises(ValueError, match="affected_user_id"):
            self._valid_signal(affected_user_id=0)

    def test_signal_validation_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            self._valid_signal(created_at=datetime(2024, 1, 1))


@pytest.mark.unit
class TestSignalSerialization:
    def test_signal_to_dict_roundtrip(self) -> None:
        original = Signal(
            tenant_id=42,
            affected_user_id=7,
            monitor_name="health",
            title="Agent failing",
            body="Agent X has 60% error rate",
            severity=Severity.HIGH,
            data_classification=DataClassification.CONFIDENTIAL,
            suggested_actions=[{"label": "View", "action": "navigate"}],
            detection_reasoning="error_rate > 0.5",
            confidence=0.95,
            context={"agent_id": "x"},
        )
        d = original.to_dict()
        restored = Signal.from_dict(d)

        assert restored.tenant_id == original.tenant_id
        assert restored.affected_user_id == original.affected_user_id
        assert restored.monitor_name == original.monitor_name
        assert restored.title == original.title
        assert restored.body == original.body
        assert restored.severity == original.severity
        assert restored.data_classification == original.data_classification
        assert restored.suggested_actions == original.suggested_actions
        assert restored.detection_reasoning == original.detection_reasoning
        assert restored.confidence == original.confidence
        assert restored.context == original.context
        assert restored.signal_id == original.signal_id
        assert restored.created_at == original.created_at


@pytest.mark.unit
class TestSignalProperties:
    def test_signal_critical_sets_bypass_flag(self) -> None:
        signal = Signal(
            tenant_id=1,
            affected_user_id=1,
            monitor_name="m",
            title="t",
            body="b",
            severity=Severity.CRITICAL,
            data_classification=DataClassification.INTERNAL,
            suggested_actions=[],
            detection_reasoning="r",
            confidence=0.5,
            context={},
        )
        assert signal.bypasses_budget is True

    def test_signal_non_critical_does_not_bypass_budget(self) -> None:
        signal = Signal(
            tenant_id=1,
            affected_user_id=1,
            monitor_name="m",
            title="t",
            body="b",
            severity=Severity.HIGH,
            data_classification=DataClassification.INTERNAL,
            suggested_actions=[],
            detection_reasoning="r",
            confidence=0.5,
            context={},
        )
        assert signal.bypasses_budget is False

    def test_dedup_key_format(self) -> None:
        signal = Signal(
            tenant_id=2,
            affected_user_id=1,
            monitor_name="health",
            title="t",
            body="b",
            severity=Severity.LOW,
            data_classification=DataClassification.INTERNAL,
            suggested_actions=[],
            detection_reasoning="r",
            confidence=0.5,
            context={},
        )
        assert signal.dedup_key("agent-x") == "monitor_dedup:health:2:agent-x"

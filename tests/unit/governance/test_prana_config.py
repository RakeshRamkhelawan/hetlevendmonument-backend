"""Fase 2 -- prana enforcement feature flag.

Default OFF for a safe rollout: has_budget->True / no charge until budgets are provisioned
and the flag is explicitly flipped in production (same env-var style as
CVA_GOVERNANCE_FAIL_SECURE).
"""

import pytest

from src.core.governance.prana_config import prana_enforcement_enabled, prana_grace_floor


@pytest.mark.unit
def test_default_is_off(monkeypatch):
    monkeypatch.delenv("PRANA_ENFORCEMENT_ENABLED", raising=False)
    assert prana_enforcement_enabled() is False


@pytest.mark.unit
@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "YES"])
def test_enabled_when_truthy(monkeypatch, value):
    monkeypatch.setenv("PRANA_ENFORCEMENT_ENABLED", value)
    assert prana_enforcement_enabled() is True


@pytest.mark.unit
@pytest.mark.parametrize("value", ["false", "0", "no", "", "off"])
def test_disabled_when_falsy(monkeypatch, value):
    monkeypatch.setenv("PRANA_ENFORCEMENT_ENABLED", value)
    assert prana_enforcement_enabled() is False


@pytest.mark.unit
def test_grace_floor_default_zero(monkeypatch):
    monkeypatch.delenv("PRANA_GRACE_FLOOR", raising=False)
    assert prana_grace_floor() == 0


@pytest.mark.unit
def test_grace_floor_reads_positive_value(monkeypatch):
    monkeypatch.setenv("PRANA_GRACE_FLOOR", "25")
    assert prana_grace_floor() == 25


@pytest.mark.unit
@pytest.mark.parametrize("value", ["-5", "abc", ""])
def test_grace_floor_clamps_invalid_to_zero(monkeypatch, value):
    monkeypatch.setenv("PRANA_GRACE_FLOOR", value)
    assert prana_grace_floor() == 0

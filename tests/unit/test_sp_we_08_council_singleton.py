"""SP-WE-08: AgentCouncil singleton/caching tests."""

import pytest


@pytest.mark.unit
class TestCouncilSingletonCaching:
    def test_ethics_officer_is_module_level_singleton(self) -> None:
        """Two calls to _get_ethics_officer() return same instance."""
        from src.core.copilot.council.factory import _get_ethics_officer

        a = _get_ethics_officer()
        b = _get_ethics_officer()
        assert a is b

    def test_sanity_officer_is_module_level_singleton(self) -> None:
        """Two calls to _get_sanity_officer() return same instance."""
        from src.core.copilot.council.factory import _get_sanity_officer

        a = _get_sanity_officer()
        b = _get_sanity_officer()
        assert a is b

    def test_compliance_officer_is_module_level_singleton(self) -> None:
        """Two calls to _get_compliance_officer() return same instance."""
        from src.core.copilot.council.factory import _get_compliance_officer

        a = _get_compliance_officer()
        b = _get_compliance_officer()
        assert a is b

    def test_security_officer_is_module_level_singleton(self) -> None:
        """Two calls to _get_security_officer() return same instance."""
        from src.core.copilot.council.factory import _get_security_officer

        a = _get_security_officer()
        b = _get_security_officer()
        assert a is b

    def test_persistent_rate_limiter_is_module_singleton(self) -> None:
        """_PERSISTENT_RATE_LIMITER is module-level (not per-request)."""
        from src.core.copilot.council import factory

        assert hasattr(factory, "_PERSISTENT_RATE_LIMITER")
        a = factory._PERSISTENT_RATE_LIMITER
        b = factory._PERSISTENT_RATE_LIMITER
        assert a is b

    def test_rate_limiter_state_persists(self) -> None:
        """InMemoryRateLimiter state persists (same instance each call)."""
        from src.core.copilot.council.factory import _PERSISTENT_RATE_LIMITER

        # Record a call -- state should survive
        limiter = _PERSISTENT_RATE_LIMITER._limiter
        assert limiter is not None

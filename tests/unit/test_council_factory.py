"""Unit tests for council factory module.

Regression tests for CG-001: bare object() sentinel removal from
ComplianceOfficer._guardian injection in _get_compliance_officer().
"""

import pytest


class TestComplianceOfficerGuardian:
    """Regression tests for CG-001: bare object() sentinel removal."""

    def test_compliance_officer_guardian_is_not_bare_object(self):
        """Guardian must not be a bare object() instance."""
        from src.core.copilot.council.factory import _get_compliance_officer

        _get_compliance_officer.cache_clear()

        officer = _get_compliance_officer()

        assert type(officer._guardian).__name__ != "object", (
            "ComplianceOfficer._guardian is still a bare object(). "
            "Expected _NullComplianceGuardian sentinel. (CG-001)"
        )

    def test_compliance_officer_guardian_class_is_named_null_sentinel(self):
        """Guardian class name must clearly communicate null-object intent."""
        from src.core.copilot.council.factory import _get_compliance_officer

        _get_compliance_officer.cache_clear()

        officer = _get_compliance_officer()
        class_name = type(officer._guardian).__name__

        assert "Null" in class_name or "Sentinel" in class_name, (
            f"Guardian class '{class_name}' does not communicate null-object intent. "
            "Expected a name containing 'Null' or 'Sentinel'."
        )

    def test_compliance_officer_guardian_satisfies_protocol(self):
        """Guardian must satisfy ComplianceGuardian Protocol (empty, but explicit)."""
        from src.core.copilot.council.factory import _get_compliance_officer

        _get_compliance_officer.cache_clear()

        officer = _get_compliance_officer()

        # Protocol has zero required methods -- any instance satisfies it.
        # This test confirms the sentinel is a proper instance, not None.
        assert hasattr(officer._guardian, "__class__")
        assert officer._guardian is not None

    def test_compliance_officer_singleton_returns_same_instance(self):
        """lru_cache(maxsize=1) must return the same officer instance."""
        from src.core.copilot.council.factory import _get_compliance_officer

        _get_compliance_officer.cache_clear()

        officer_a = _get_compliance_officer()
        officer_b = _get_compliance_officer()

        assert officer_a is officer_b, (
            "ComplianceOfficer singleton violated: two different instances returned."
        )

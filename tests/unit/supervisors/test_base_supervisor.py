"""Tests for BaseSupervisor abstract class."""

from abc import ABC

import pytest

from src.core.als.supervisors.base_supervisor import BaseSupervisor


class TestBaseSupervisorInterface:
    """Test that BaseSupervisor is properly abstract."""

    def test_base_supervisor_is_abstract(self):
        """BaseSupervisor should be an abstract class."""
        assert issubclass(BaseSupervisor, ABC)

    def test_cannot_instantiate_base(self):
        """Should not be able to instantiate BaseSupervisor directly."""
        with pytest.raises(TypeError):
            BaseSupervisor()

    def test_required_attributes_defined(self):
        """BaseSupervisor should define required class attributes."""
        assert hasattr(BaseSupervisor, "supervisor_id")
        assert hasattr(BaseSupervisor, "domain")
        assert hasattr(BaseSupervisor, "managed_agents")

    def test_required_methods_abstract(self):
        """BaseSupervisor should have abstract methods."""
        assert hasattr(BaseSupervisor, "decompose_task")
        assert hasattr(BaseSupervisor, "delegate")
        assert hasattr(BaseSupervisor, "handle_timeout")

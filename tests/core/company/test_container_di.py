"""Tests for container DI registration."""

import pytest

from src.core.container import Container
from src.core.procedures.domain_pack_registry import DomainPackRegistry


def test_container_can_create_pack_activation_scorer():
    c = Container()
    scorer = c.pack_activation_scorer()
    assert scorer is not None


def test_container_can_create_goal_alignment_validator():
    c = Container()
    validator = c.goal_alignment_validator()
    assert validator is not None


def test_container_can_create_department_service():
    c = Container()
    # Should not raise
    service = c.department_service()
    assert service is not None


def test_container_provides_non_none_pack_registry():
    """Container provides actual registry, not None placeholder."""
    c = Container()
    registry = c.domain_pack_registry()
    assert registry is not None
    assert isinstance(registry, DomainPackRegistry)

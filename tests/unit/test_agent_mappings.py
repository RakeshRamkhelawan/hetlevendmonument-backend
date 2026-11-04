"""Tests for department to agent type mappings.

This module tests the agent mapping functionality that determines
which agent types are relevant for specific departments.
"""

import pytest

from src.core.company.agent_mappings import get_agents_for_department


def test_get_agents_for_engineering() -> None:
    """Test that Engineering department returns expected agents."""
    agents = get_agents_for_department("Engineering")

    assert len(agents) >= 3
    assert "Code Reviewer" in agents
    assert "Tech Lead" in agents


def test_get_agents_for_keuken() -> None:
    """Test that Keuken department returns expected hospitality agents."""
    agents = get_agents_for_department("Keuken")

    assert len(agents) >= 2
    assert "Sous Chef" in agents


def test_get_agents_for_unknown_department() -> None:
    """Test that unknown departments return Generalist fallback."""
    agents = get_agents_for_department("UnknownDepartment")

    assert agents == ["Generalist"]


def test_get_agents_for_management() -> None:
    """Test that Management department returns expected agents."""
    agents = get_agents_for_department("Management")

    assert len(agents) >= 1
    assert "Executive Assistant" in agents


def test_get_agents_case_insensitive() -> None:
    """Test that department lookup is case-insensitive."""
    agents_lower = get_agents_for_department("engineering")
    agents_upper = get_agents_for_department("ENGINEERING")
    agents_mixed = get_agents_for_department("Engineering")

    assert agents_lower == agents_upper == agents_mixed


def test_get_agents_for_product() -> None:
    """Test Product department mapping."""
    agents = get_agents_for_department("Product")

    assert len(agents) >= 2
    assert "Product Manager" in agents


def test_get_agents_for_sales() -> None:
    """Test Sales department mapping."""
    agents = get_agents_for_department("Sales")

    assert len(agents) >= 2
    assert "Sales Development Rep" in agents


def test_get_agents_for_winkel() -> None:
    """Test Winkel (Retail) department mapping."""
    agents = get_agents_for_department("Winkel")

    assert len(agents) >= 2
    assert "Store Associate" in agents


def test_get_agents_for_hr() -> None:
    """Test HR department mapping."""
    agents = get_agents_for_department("HR")

    assert len(agents) >= 1
    assert "Recruiter" in agents


def test_get_agents_for_finance() -> None:
    """Test Finance department mapping."""
    agents = get_agents_for_department("Finance")

    assert len(agents) >= 1
    assert "Accountant" in agents

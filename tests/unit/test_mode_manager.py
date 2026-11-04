"""
Unit tests for ModeManager module.

Tests cover:
- Mode switching with history tracking
- Mode determination from parsed commands
- TriggerType-based mode selection
- Context initialization

Usage:
    pytest tests/unit/test_mode_manager.py -v
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.core.agents.ultimate_cva.mode_manager import ModeManager
from src.core.agents.ultimate_cva.models import CVAMode, IntentType, ParsedCommand

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mode_manager():
    """Provide a fresh ModeManager instance."""
    return ModeManager()


@pytest.fixture
def mode_manager_with_fetcher():
    """ModeManager with mock dashboard fetcher."""
    fetcher = AsyncMock(return_value={"status": "healthy"})
    return ModeManager(dashboard_fetcher=fetcher)


@pytest.fixture
def parsed_command_ceo():
    """ParsedCommand with CEO_DIRECTIVE intent."""
    return ParsedCommand(
        intent=IntentType.CEO_DIRECTIVE,
        original_text="optimize all agents",
        confidence=0.95,
        parameters={},
    )


@pytest.fixture
def parsed_command_low_confidence():
    """ParsedCommand with low confidence."""
    return ParsedCommand(
        intent=IntentType.SYSTEM_STATUS,
        original_text="show status",
        confidence=0.5,
        parameters={},
    )


@pytest.fixture
def parsed_command_task():
    """ParsedCommand with TASK_MANAGEMENT intent."""
    return ParsedCommand(
        intent=IntentType.TASK_MANAGEMENT,
        original_text="create new task",
        confidence=0.9,
        parameters={},
    )


# =============================================================================
# TEST MODE SWITCHING
# =============================================================================


@pytest.mark.asyncio
async def test_switch_mode_changes_current_mode(mode_manager):
    """Test that switch_mode updates current mode."""
    # Arrange
    new_mode = CVAMode.PROACTIVE

    # Act
    result = await mode_manager.switch_mode(new_mode, "test switch")

    # Assert
    assert result is True
    assert mode_manager.current_mode == CVAMode.PROACTIVE


@pytest.mark.asyncio
async def test_switch_mode_returns_false_if_same_mode(mode_manager):
    """Test that switching to same mode returns False."""
    # Arrange - CEO_MODE is default
    same_mode = CVAMode.CEO_MODE

    # Act
    result = await mode_manager.switch_mode(same_mode, "same mode")

    # Assert
    assert result is False


@pytest.mark.asyncio
async def test_switch_mode_records_history(mode_manager):
    """Test that mode switches are recorded in history."""
    # Arrange & Act
    await mode_manager.switch_mode(CVAMode.REACTIVE, "first switch")
    await mode_manager.switch_mode(CVAMode.AUTONOMOUS, "second switch")

    # Assert
    assert len(mode_manager.mode_history) == 2
    assert mode_manager.mode_history[0]["to"] == "reactive"
    assert mode_manager.mode_history[1]["to"] == "autonomous"


@pytest.mark.asyncio
async def test_switch_mode_history_contains_timestamps(mode_manager):
    """Test that history entries have timestamps."""
    # Arrange & Act
    await mode_manager.switch_mode(CVAMode.PROACTIVE, "test")

    # Assert
    entry = mode_manager.mode_history[0]
    assert "timestamp" in entry
    assert "from" in entry
    assert "to" in entry
    assert "reason" in entry


# =============================================================================
# TEST MODE DETERMINATION
# =============================================================================


def test_determine_mode_ceo_directive(mode_manager, parsed_command_ceo):
    """Test that CEO_DIRECTIVE intent maps to CEO_MODE."""
    # Act
    result = mode_manager.determine_optimal_mode(parsed_command_ceo)

    # Assert
    assert result == CVAMode.CEO_MODE


def test_determine_mode_low_confidence_uses_reactive(mode_manager, parsed_command_low_confidence):
    """Test that low confidence commands use REACTIVE mode."""
    # Act
    result = mode_manager.determine_optimal_mode(parsed_command_low_confidence)

    # Assert
    assert result == CVAMode.REACTIVE


def test_determine_mode_task_management_uses_proactive(mode_manager, parsed_command_task):
    """Test that TASK_MANAGEMENT intent uses PROACTIVE mode."""
    # Act
    result = mode_manager.determine_optimal_mode(parsed_command_task)

    # Assert
    assert result == CVAMode.PROACTIVE


# =============================================================================
# TEST TRIGGER TYPE MAPPING
# =============================================================================


def test_mode_from_trigger_type_emergency(mode_manager, parsed_command_task):
    """Test EMERGENCY trigger maps to CEO_MODE."""
    # Arrange
    with patch("src.core.agents.ultimate_cva.mode_manager.logger"):
        try:
            from src.core.agents.cva_autonomous_trigger import TriggerType

            # Act
            result = mode_manager.determine_optimal_mode(parsed_command_task, TriggerType.EMERGENCY)
            # Assert
            assert result == CVAMode.CEO_MODE
        except ImportError:
            pytest.skip("TriggerType not available")


def test_mode_from_trigger_type_scheduled(mode_manager, parsed_command_task):
    """Test SCHEDULED trigger maps to PROACTIVE mode."""
    try:
        from src.core.agents.cva_autonomous_trigger import TriggerType

        result = mode_manager.determine_optimal_mode(parsed_command_task, TriggerType.SCHEDULED)
        assert result == CVAMode.PROACTIVE
    except ImportError:
        pytest.skip("TriggerType not available")


# =============================================================================
# TEST CEO MODE CONTEXT INITIALIZATION
# =============================================================================


@pytest.mark.asyncio
async def test_ceo_mode_context_initialization(mode_manager_with_fetcher):
    """Test that CEO mode initializes strategic context."""
    # Arrange
    manager = mode_manager_with_fetcher

    # Act
    await manager.switch_mode(CVAMode.REACTIVE, "setup")  # Change from default
    await manager.switch_mode(CVAMode.CEO_MODE, "test ceo init")

    # Assert
    assert "ceo_mode" in manager.mode_context
    assert "initialized_at" in manager.mode_context["ceo_mode"]


@pytest.mark.asyncio
async def test_autonomous_mode_context_initialization(mode_manager):
    """Test that autonomous mode initializes context."""
    # Act
    await mode_manager.switch_mode(CVAMode.AUTONOMOUS, "test autonomous")

    # Assert
    assert "autonomous_mode" in mode_manager.mode_context
    assert mode_manager.mode_context["autonomous_mode"]["learning_enabled"] is True


# =============================================================================
# TEST HISTORY MANAGEMENT
# =============================================================================


def test_get_recent_history_empty(mode_manager):
    """Test getting history when empty."""
    # Act
    history = mode_manager.get_recent_history()

    # Assert
    assert history == []


@pytest.mark.asyncio
async def test_get_recent_history_limited(mode_manager):
    """Test that get_recent_history respects limit."""
    # Arrange
    for i in range(10):
        await mode_manager.switch_mode(CVAMode.REACTIVE, f"switch {i}")
        await mode_manager.switch_mode(CVAMode.PROACTIVE, f"switch {i}")

    # Act
    history = mode_manager.get_recent_history(limit=5)

    # Assert
    assert len(history) == 5


@pytest.mark.asyncio
async def test_history_trimmed_at_max(mode_manager):
    """Test that history is trimmed when exceeding max."""
    # Arrange
    manager = ModeManager(max_history=5)

    # Act - Create more than max history entries
    for i in range(10):
        await manager.switch_mode(CVAMode.REACTIVE, f"switch {i}")
        await manager.switch_mode(CVAMode.PROACTIVE, f"switch {i}")

    # Assert
    assert len(manager.mode_history) <= 5

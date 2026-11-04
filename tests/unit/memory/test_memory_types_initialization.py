"""Unit tests for MemoryEntry types initialization."""

from datetime import datetime, timezone
import pytest

from src.core.memory.types import EpisodicMemory, TacticalMemory


def test_tactical_memory_initialization() -> None:
    mem = TacticalMemory(
        id="tac-1",
        timestamp=datetime.now(timezone.utc),
        agent_type="orchestrator",
        content="optimized pattern",
    )
    assert mem.agent_assignments == []


def test_episodic_memory_initialization() -> None:
    mem = EpisodicMemory(
        id="epi-1",
        timestamp=datetime.now(timezone.utc),
        agent_type="subagent",
        content="step executed",
    )
    assert mem.error_patterns == []
    assert mem.execution_steps == []

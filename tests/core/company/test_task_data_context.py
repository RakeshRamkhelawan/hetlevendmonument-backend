"""Tests for TaskData.company_context field (Golden Rule R1)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.company.context import AgentExecutionContext, GoalChain
from src.core.shared.interfaces import TaskData


def make_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(),
    )


def test_task_data_accepts_company_context():
    """TaskData can be created with company_context field."""
    ctx = make_context()
    task = TaskData(
        title="Test task",
        description="desc",
        company_context=ctx,
    )
    assert task.company_context is ctx


def test_task_data_company_context_defaults_to_none():
    """Existing code that creates TaskData without context still works."""
    task = TaskData(title="Legacy task", description="desc")
    assert task.company_context is None


def test_task_data_company_context_is_typed():
    """company_context must be AgentExecutionContext or None."""
    with pytest.raises(Exception):
        TaskData(title="t", description="d", company_context={"bad": "dict"})


def test_task_data_company_context_refuses_a_valid_looking_dict():
    """Ook een dict die WEL alle velden heeft wordt geweigerd, geen coercion.

    Vastgelegd 2026-09-10 bij het weghalen van de `Any`-annotatie op dit veld. Met het
    echte type op het veld bouwt pydantic van een COMPLETE dict zelf een
    AgentExecutionContext; dat zou een gedragswijziging zijn tegenover de oude
    `Any | None`-annotatie, die elke dict weigerde. Gemeten op 2026-09-10, drie
    varianten: alleen het type -> dict aangenomen; type plus `Field(strict=True)` ->
    dict nog steeds aangenomen; type plus een validator in mode="before" -> dict
    geweigerd. Alleen de laatste houdt het gedrag gelijk.

    De test hierboven (`{"bad": "dict"}`) vangt dit NIET: die dict mist verplichte
    velden en faalt in alle drie de varianten.
    """
    ctx = make_context()
    # ValidationError met match, niet het brede Exception van de test hierboven: anders
    # houdt elke latere TypeError of ImportError deze test groen zonder dat de VALIDATOR
    # nog iets weigert (Gate-2-bevinding 2026-09-10).
    with pytest.raises(ValidationError, match="must be AgentExecutionContext or None"):
        TaskData(
            title="t",
            description="d",
            company_context=ctx.model_dump(),
        )


def test_task_data_keeps_the_exact_context_object():
    """De legitieme kant: geen kopie, geen revalidatie -- hetzelfde object komt terug."""
    ctx = make_context()
    task = TaskData(title="t", description="d", company_context=ctx)
    assert task.company_context is ctx


def test_existing_context_property_still_works():
    """The existing .context property alias to metadata is not broken."""
    task = TaskData(title="t", description="d", metadata={"key": "val"})
    assert task.context == {"key": "val"}

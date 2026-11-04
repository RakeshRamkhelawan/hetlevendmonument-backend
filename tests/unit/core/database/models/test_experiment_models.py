"""Unit tests for src.core.database.models.experiment."""

from datetime import datetime, timezone
from uuid import uuid4

from src.core.database.models.experiment import (
    Experiment,
    ExperimentVariant,
    ExperimentAssignment,
    ExperimentEvent,
    __all__ as experiment_all,
)


def test_experiment_models_exports():
    """Validates all intended models are exported."""
    assert "Experiment" in experiment_all
    assert "ExperimentVariant" in experiment_all
    assert "ExperimentAssignment" in experiment_all
    assert "ExperimentEvent" in experiment_all


def test_experiment_attributes():
    """Tests Experiment attributes, defaults, and representation."""
    exp_id = uuid4()
    creator_id = uuid4()
    now = datetime.now(timezone.utc)

    exp = Experiment(
        id=exp_id,
        name="Onboarding Flow Optimization",
        description="Testing 3-step vs 5-step onboarding",
        start_date=now,
        status="running",
        traffic_split=0.5,
        tenant_id=101,
        created_by=creator_id,
    )

    assert exp.id == exp_id
    assert exp.name == "Onboarding Flow Optimization"
    assert exp.status == "running"
    assert exp.traffic_split == 0.5
    assert exp.tenant_id == 101
    assert exp.created_by == creator_id

    repr_str = repr(exp)
    assert "Experiment" in repr_str
    assert str(exp_id) in repr_str
    assert "Onboarding Flow Optimization" in repr_str


def test_experiment_variant_attributes():
    """Tests ExperimentVariant fields and representation."""
    var_id = uuid4()
    exp_id = uuid4()

    variant = ExperimentVariant(
        id=var_id,
        experiment_id=exp_id,
        name="treatment",
        config={"button_color": "blue", "steps": 3},
    )

    assert variant.id == var_id
    assert variant.experiment_id == exp_id
    assert variant.name == "treatment"
    assert variant.config == {"button_color": "blue", "steps": 3}

    repr_str = repr(variant)
    assert "ExperimentVariant" in repr_str
    assert "treatment" in repr_str


def test_experiment_assignment_attributes():
    """Tests ExperimentAssignment fields and representation."""
    assign_id = uuid4()
    exp_id = uuid4()
    company_id = uuid4()

    assignment = ExperimentAssignment(
        id=assign_id,
        experiment_id=exp_id,
        company_id=company_id,
        variant="control",
    )

    assert assignment.id == assign_id
    assert assignment.experiment_id == exp_id
    assert assignment.company_id == company_id
    assert assignment.variant == "control"

    repr_str = repr(assignment)
    assert "ExperimentAssignment" in repr_str
    assert str(company_id) in repr_str
    assert "control" in repr_str


def test_experiment_event_attributes():
    """Tests ExperimentEvent fields and representation."""
    event_id = uuid4()
    exp_id = uuid4()
    company_id = uuid4()

    event = ExperimentEvent(
        id=event_id,
        experiment_id=exp_id,
        company_id=company_id,
        event_type="conversion",
        variant="treatment",
        event_metadata={"value": 99.95, "currency": "EUR"},
    )

    assert event.id == event_id
    assert event.experiment_id == exp_id
    assert event.company_id == company_id
    assert event.event_type == "conversion"
    assert event.variant == "treatment"
    assert event.event_metadata == {"value": 99.95, "currency": "EUR"}

    repr_str = repr(event)
    assert "ExperimentEvent" in repr_str
    assert "conversion" in repr_str
    assert "treatment" in repr_str

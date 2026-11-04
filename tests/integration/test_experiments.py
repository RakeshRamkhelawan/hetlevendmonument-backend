"""Integration tests for Experiment Service (A/B Testing)

Tests experiment lifecycle, variant assignment, event tracking, and metrics.
Part of Paperclip Pipeline Integration - Plan 4, Task 8.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.database.models.experiment import (
    Experiment,
    ExperimentAssignment,
    ExperimentEvent,
    ExperimentVariant,
)
from src.core.services.experiment_service import ExperimentService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


class TestExperimentAssignment:
    """Test experiment variant assignment consistency."""

    async def test_experiment_assignment_is_consistent(self, postgres_session):
        """Test that same company always gets same variant."""
        # Arrange: Create experiment
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Consistency",
            description="Test experiment for assignment consistency",
            variants=[
                {"name": "control", "config": {"color": "blue"}},
                {"name": "treatment", "config": {"color": "green"}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )

        # Start the experiment
        await service.start_experiment(experiment.id)

        company_id = uuid4()

        # Act: Assign variant to company_id multiple times
        variants = []
        for _ in range(5):
            variant = await service.assign_variant_with_split(experiment.id, company_id)
            variants.append(variant)

        # Assert: Same variant returned every time
        assert all(v == variants[0] for v in variants), (
            f"Variants should be consistent but got: {variants}"
        )

    async def test_experiment_assignment_stores_in_database(self, postgres_session):
        """Test that assignments are persisted in database."""
        # Arrange: Create experiment
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Persistence",
            description="Test assignment persistence",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        company_id = uuid4()

        # Act: Assign variant
        variant = await service.assign_variant_with_split(experiment.id, company_id)

        # Assert: Check assignment in database
        result = await postgres_session.execute(
            select(ExperimentAssignment).where(
                (ExperimentAssignment.experiment_id == experiment.id)
                & (ExperimentAssignment.company_id == company_id)
            )
        )
        assignment = result.scalar_one()

        assert assignment is not None
        assert assignment.variant == variant

    async def test_different_companies_get_variants(self, postgres_session):
        """Test that different companies can get different variants."""
        # Arrange: Create experiment with 50/50 split
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Distribution",
            description="Test variant distribution",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Act: Assign variants to many companies
        control_count = 0
        treatment_count = 0
        num_companies = 20

        for _ in range(num_companies):
            company_id = uuid4()
            variant = await service.assign_variant_with_split(experiment.id, company_id)
            if variant == "control":
                control_count += 1
            else:
                treatment_count += 1

        # Assert: Both variants should be assigned (roughly 50/50)
        assert control_count > 0, "Should have some control assignments"
        assert treatment_count > 0, "Should have some treatment assignments"
        # Allow for some variance, but should be roughly balanced
        total = control_count + treatment_count
        ratio = control_count / total
        assert 0.2 <= ratio <= 0.8, f"Ratio {ratio} is outside expected range"

    async def test_experiment_traffic_split_respected(self, postgres_session):
        """Test that traffic split configuration is respected."""
        # Arrange: Create experiment with 80/20 split
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Traffic Split",
            description="Test traffic split configuration",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.8,  # 80% to treatment
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Act: Assign variants to many companies
        treatment_count = 0
        num_companies = 50

        for _ in range(num_companies):
            company_id = uuid4()
            variant = await service.assign_variant_with_split(experiment.id, company_id)
            if variant == "treatment":
                treatment_count += 1

        # Assert: Treatment should have significantly more assignments
        ratio = treatment_count / num_companies
        assert ratio >= 0.6, f"Treatment ratio {ratio} is below expected range"

    async def test_nonexistent_experiment_defaults_to_control(self, postgres_session):
        """Test that non-existent experiment defaults to control."""
        # Arrange: Use non-existent experiment ID
        service = ExperimentService(postgres_session)
        non_existent_id = uuid4()
        company_id = uuid4()

        # Act: Assign variant
        variant = await service.assign_variant_with_split(non_existent_id, company_id)

        # Assert: Should default to control
        assert variant == "control"


class TestExperimentEventTracking:
    """Test experiment event tracking."""

    async def test_experiment_event_tracking(self, postgres_session):
        """Test that events are tracked correctly."""
        # Arrange: Create experiment and assign variant
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Event Tracking",
            description="Test event tracking functionality",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        company_id = uuid4()
        variant = await service.assign_variant_with_split(experiment.id, company_id)

        # Act: Track exposed and converted events
        await service.track_event(
            experiment_id=experiment.id,
            company_id=company_id,
            event_type="exposed",
            variant=variant,
            metadata={"page": "home"},
        )

        await service.track_event(
            experiment_id=experiment.id,
            company_id=company_id,
            event_type="converted",
            variant=variant,
            metadata={"conversion_type": "signup"},
        )

        # Assert: Check events in database
        result = await postgres_session.execute(
            select(ExperimentEvent).where(ExperimentEvent.experiment_id == experiment.id)
        )
        events = result.scalars().all()

        assert len(events) == 2
        event_types = [e.event_type for e in events]
        assert "exposed" in event_types
        assert "converted" in event_types

    async def test_event_tracking_with_metadata(self, postgres_session):
        """Test that event metadata is stored correctly."""
        # Arrange: Create experiment
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Metadata",
            description="Test event metadata",
            variants=[
                {"name": "control", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        company_id = uuid4()
        metadata = {
            "page": "checkout",
            "referrer": "google",
            "device": "mobile",
        }

        # Act: Track event with metadata
        event = await service.track_event(
            experiment_id=experiment.id,
            company_id=company_id,
            event_type="exposed",
            variant="control",
            metadata=metadata,
        )

        # Assert: Check metadata persisted
        assert event.event_metadata == metadata

        # Verify in database
        result = await postgres_session.execute(
            select(ExperimentEvent).where(ExperimentEvent.id == event.id)
        )
        stored_event = result.scalar_one()
        assert stored_event.event_metadata == metadata

    async def test_multiple_events_same_company(self, postgres_session):
        """Test tracking multiple events for same company."""
        # Arrange: Create experiment
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Multiple Events",
            description="Test multiple events per company",
            variants=[
                {"name": "control", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        company_id = uuid4()

        # Act: Track multiple exposed events
        for i in range(3):
            await service.track_event(
                experiment_id=experiment.id,
                company_id=company_id,
                event_type="exposed",
                variant="control",
                metadata={"visit": i + 1},
            )

        # Assert: Check all events stored
        result = await postgres_session.execute(
            select(ExperimentEvent).where(
                (ExperimentEvent.experiment_id == experiment.id)
                & (ExperimentEvent.company_id == company_id)
            )
        )
        events = result.scalars().all()

        assert len(events) == 3


class TestExperimentMetrics:
    """Test experiment metrics calculation."""

    async def test_experiment_metrics_calculation(self, postgres_session):
        """Test metrics calculation."""
        # Arrange: Create experiment with events
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Metrics",
            description="Test metrics calculation",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Create events for control: 100 exposed, 10 converted (10%)
        for i in range(100):
            company_id = uuid4()
            await service.track_event(
                experiment_id=experiment.id,
                company_id=company_id,
                event_type="exposed",
                variant="control",
            )
            if i < 10:  # 10 conversions
                await service.track_event(
                    experiment_id=experiment.id,
                    company_id=company_id,
                    event_type="converted",
                    variant="control",
                )

        # Create events for treatment: 100 exposed, 20 converted (20%)
        for i in range(100):
            company_id = uuid4()
            await service.track_event(
                experiment_id=experiment.id,
                company_id=company_id,
                event_type="exposed",
                variant="treatment",
            )
            if i < 20:  # 20 conversions
                await service.track_event(
                    experiment_id=experiment.id,
                    company_id=company_id,
                    event_type="converted",
                    variant="treatment",
                )

        # Act: Calculate metrics
        metrics = await service.calculate_metrics(experiment.id)

        # Assert: Check conversion rates
        assert metrics["experiment_id"] == str(experiment.id)
        assert metrics["metrics"]["control"]["exposures"] == 100
        assert metrics["metrics"]["control"]["conversions"] == 10
        assert metrics["metrics"]["control"]["conversion_rate"] == 0.1
        assert metrics["metrics"]["treatment"]["exposures"] == 100
        assert metrics["metrics"]["treatment"]["conversions"] == 20
        assert metrics["metrics"]["treatment"]["conversion_rate"] == 0.2
        assert metrics["total_exposures"] == 200
        assert metrics["total_conversions"] == 30

    async def test_experiment_metrics_empty(self, postgres_session):
        """Test metrics calculation with no events."""
        # Arrange: Create experiment with no events
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Empty Metrics",
            description="Test metrics with no events",
            variants=[
                {"name": "control", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Act: Calculate metrics
        metrics = await service.calculate_metrics(experiment.id)

        # Assert: Should return empty metrics
        assert metrics["experiment_id"] == str(experiment.id)
        assert metrics["metrics"] == {}
        assert metrics["total_exposures"] == 0
        assert metrics["total_conversions"] == 0

    async def test_experiment_metrics_single_variant(self, postgres_session):
        """Test metrics calculation for single variant."""
        # Arrange: Create experiment with events for only one variant
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Single Variant Metrics",
            description="Test metrics with single variant",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Create events for only control
        for i in range(50):
            company_id = uuid4()
            await service.track_event(
                experiment_id=experiment.id,
                company_id=company_id,
                event_type="exposed",
                variant="control",
            )
            if i < 5:
                await service.track_event(
                    experiment_id=experiment.id,
                    company_id=company_id,
                    event_type="converted",
                    variant="control",
                )

        # Act: Calculate metrics
        metrics = await service.calculate_metrics(experiment.id)

        # Assert: Only control should have metrics
        assert "control" in metrics["metrics"]
        assert "treatment" not in metrics["metrics"]
        assert metrics["metrics"]["control"]["conversion_rate"] == 0.1


class TestExperimentLifecycle:
    """Test experiment lifecycle operations."""

    async def test_create_experiment(self, postgres_session):
        """Test experiment creation."""
        # Arrange
        service = ExperimentService(postgres_session)
        created_by = uuid4()

        # Act
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Create",
            description="Test experiment creation",
            variants=[
                {"name": "control", "config": {"color": "blue"}},
                {"name": "treatment", "config": {"color": "green"}},
            ],
            traffic_split=0.5,
            created_by=created_by,
        )

        # Assert
        assert experiment.name == "Test Create"
        assert experiment.description == "Test experiment creation"
        assert experiment.status == "draft"
        assert experiment.traffic_split == 0.5
        assert experiment.created_by == created_by

        # Check variants created
        result = await postgres_session.execute(
            select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
        )
        variants = result.scalars().all()
        assert len(variants) == 2
        variant_names = [v.name for v in variants]
        assert "control" in variant_names
        assert "treatment" in variant_names

    async def test_start_experiment(self, postgres_session):
        """Test starting an experiment."""
        # Arrange: Create draft experiment
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Start",
            description="Test experiment start",
            variants=[
                {"name": "control", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        assert experiment.status == "draft"

        # Act: Start experiment
        started = await service.start_experiment(experiment.id)

        # Assert
        assert started is not None
        assert started.status == "running"
        assert started.start_date is not None

    async def test_stop_experiment(self, postgres_session):
        """Test stopping an experiment."""
        # Arrange: Create and start experiment
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Stop",
            description="Test experiment stop",
            variants=[
                {"name": "control", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Act: Stop experiment
        stopped = await service.stop_experiment(experiment.id, reason="test_complete")

        # Assert
        assert stopped is not None
        assert stopped.status == "completed"
        assert stopped.end_date is not None

    async def test_get_active_experiments(self, postgres_session):
        """Test getting active experiments."""
        # Arrange: Create multiple experiments
        service = ExperimentService(postgres_session)

        # Create and start experiment 1
        exp1 = await service.create_experiment(
            tenant_id=1,
            name="Test Active 1",
            description="Test active experiments",
            variants=[{"name": "control", "config": {}}],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(exp1.id)

        # Create experiment 2 (stay in draft)
        await service.create_experiment(
            tenant_id=1,
            name="Test Draft",
            description="Test draft experiment",
            variants=[{"name": "control", "config": {}}],
            traffic_split=0.5,
            created_by=uuid4(),
        )

        # Act
        active = await service.get_active_experiments()

        # Assert: Should only get running experiments
        assert len(active) >= 1
        assert all(e.status == "running" for e in active)
        assert any(e.name == "Test Active 1" for e in active)

    async def test_get_experiment_by_name(self, postgres_session):
        """Test getting experiment by name."""
        # Arrange
        service = ExperimentService(postgres_session)
        await service.create_experiment(
            tenant_id=1,
            name="Unique Test Name",
            description="Test get by name",
            variants=[{"name": "control", "config": {}}],
            traffic_split=0.5,
            created_by=uuid4(),
        )

        # Act
        found = await service.get_experiment_by_name("Unique Test Name")
        not_found = await service.get_experiment_by_name("Non Existent")

        # Assert
        assert found is not None
        assert found.name == "Unique Test Name"
        assert not_found is None


class TestStatisticalSignificance:
    """Test statistical significance calculations."""

    async def test_check_statistical_significance(self, postgres_session):
        """Test chi-square test for statistical significance."""
        # Arrange: Create experiment with significant difference
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Significance",
            description="Test statistical significance",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Create significant difference: control 10%, treatment 25%
        for i in range(100):
            company_id = uuid4()
            await service.track_event(
                experiment_id=experiment.id,
                company_id=company_id,
                event_type="exposed",
                variant="control",
            )
            if i < 10:
                await service.track_event(
                    experiment_id=experiment.id,
                    company_id=company_id,
                    event_type="converted",
                    variant="control",
                )

        for i in range(100):
            company_id = uuid4()
            await service.track_event(
                experiment_id=experiment.id,
                company_id=company_id,
                event_type="exposed",
                variant="treatment",
            )
            if i < 25:
                await service.track_event(
                    experiment_id=experiment.id,
                    company_id=company_id,
                    event_type="converted",
                    variant="treatment",
                )

        # Act: Check statistical significance
        result = await service.check_statistical_significance(experiment.id)

        # Assert
        assert "chi2_stat" in result
        assert "p_value" in result
        assert "is_significant" in result
        assert "recommendation" in result
        assert result["control_conversion_rate"] == 0.1
        assert result["treatment_conversion_rate"] == 0.25

    async def test_statistical_significance_missing_data(self, postgres_session):
        """Test significance check with missing variant data."""
        # Arrange: Create experiment with no events
        service = ExperimentService(postgres_session)
        experiment = await service.create_experiment(
            tenant_id=1,
            name="Test Significance Empty",
            description="Test significance with no data",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
            traffic_split=0.5,
            created_by=uuid4(),
        )
        await service.start_experiment(experiment.id)

        # Act
        result = await service.check_statistical_significance(experiment.id)

        # Assert: Should return error for missing data
        assert "error" in result
        assert result["is_significant"] is False

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.production_integration import ABTestConfiguration, DeploymentPhase

# Will fail until implemented
from src.domains.agentic.services.experimentation_service import ExperimentationService


class TestExperimentationService:
    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self):
        # We might need to mock internal dependencies if they are heavy
        return ExperimentationService()

    @pytest.mark.asyncio
    async def test_create_prompt_experiment(self, service, mock_db_session):
        """Should create a new experiment configuration and persist it."""

        # Determine expected input config
        config = {
            "name": "Polite vs Concise",
            "description": "Testing tone impact on satisfaction",
            "prompt_template_id": 1,
            "variants": [
                {"name": "Control", "traffic": 0.5, "is_control": True},
                {"name": "Treatment A", "traffic": 0.5},
            ],
        }

        # Mock dependecy calls
        with patch.object(
            service.ab_framework, "create_ab_test", return_value="exp_123"
        ) as mock_core_create:
            experiment_id = await service.create_experiment(db=mock_db_session, **config)

            assert experiment_id == "exp_123"
            mock_core_create.assert_called_once()

            # Verify it delegates to core AB framework
            call_args = mock_core_create.call_args[0][0]
            assert isinstance(call_args, ABTestConfiguration)
            assert call_args.test_name == "Polite vs Concise"

    @pytest.mark.asyncio
    async def test_assign_variant_consistency(self, service):
        """Same user should always get same variant for same experiment."""

        # Setup active experiment in service or mock
        experiment_id = "exp_tone_check"
        user_id = "user_123"

        # Mock core router assignment (since it's internal to framework assign_variant)
        # Note: service.get_assigned_variant calls ab_framework.assign_variant
        with patch.object(service.ab_framework, "assign_variant", return_value="variant_A"):
            variant1 = await service.get_assigned_variant(experiment_id, user_id)
            variant2 = await service.get_assigned_variant(experiment_id, user_id)

            assert variant1 == variant2
            assert variant1 == "variant_A"

    @pytest.mark.asyncio
    async def test_record_feedback_integration(self, service, mock_db_session):
        """Feedback should record metrics in AB framework."""

        experiment_id = "exp_123"
        variant_id = "var_A"
        user_id = "user_99"
        score = 5  # High satisfaction

        with patch.object(service.ab_framework, "record_metric") as mock_record:
            await service.record_experiment_feedback(
                db=mock_db_session,
                experiment_id=experiment_id,
                variant_id=variant_id,
                user_id=user_id,
                score=score,
            )

            # Should record satisfaction metric
            mock_record.assert_called()
            args = mock_record.call_args
            assert args[0][0] == experiment_id
            assert args[0][3] == "user_satisfaction"  # metric name
            assert args[0][4] == 5.0  # value

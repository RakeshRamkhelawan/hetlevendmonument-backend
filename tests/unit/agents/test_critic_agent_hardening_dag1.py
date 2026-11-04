"""SP-AGT-010 Dag 1 -- CriticAgent hardening: YAML hot-reload, provider diversiteit, N config.

TDD: alle tests moeten ROOD zijn voor implementatie begint.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# (A) YAML capability_schemas programmatisch inlezen (BE-AGT-018-minor-1)
# ---------------------------------------------------------------------------


class TestOutputSchemaValidatorYAMLReload:
    """OutputSchemaValidator laadt schemas programmatisch -- geen module-level singleton."""

    def test_validator_for_capability_loads_from_yaml(self) -> None:
        """create_for_capability() leest schema uit critic_agent.yaml voor de opgegeven capability."""
        from src.core.agents.critic_agent import OutputSchemaValidator

        validator = OutputSchemaValidator.create_for_capability("accuracy_assessment")

        # accuracy_assessment vereist required_type=dict en required_fields=[score, reasoning]
        result = validator.validate({"score": 0.8, "reasoning": "ok"})
        assert result.passed is True

    def test_validator_for_capability_rejects_missing_field(self) -> None:
        """create_for_capability() laadt required_fields correct -- ontbrekend veld geeft failed."""
        from src.core.agents.critic_agent import OutputSchemaValidator

        validator = OutputSchemaValidator.create_for_capability("accuracy_assessment")

        result = validator.validate({"score": 0.8})  # "reasoning" ontbreekt
        assert result.passed is False
        assert any("reasoning" in issue for issue in result.issues)

    def test_validator_for_unknown_capability_returns_default(self) -> None:
        """create_for_capability() met onbekende capability retourneert een lege validator."""
        from src.core.agents.critic_agent import OutputSchemaValidator

        validator = OutputSchemaValidator.create_for_capability("nonexistent_capability")
        # Lege validator: alles passeert (geen constraints)
        result = validator.validate("some output")
        assert result.passed is True

    def test_validator_for_capability_reads_yaml_each_call(self) -> None:
        """create_for_capability() leest YAML opnieuw bij elke aanroep -- geen module-level cache."""
        import yaml
        from src.core.agents.critic_agent import OutputSchemaValidator

        with patch("yaml.safe_load", wraps=yaml.safe_load) as mock_yaml:
            OutputSchemaValidator.create_for_capability("accuracy_assessment")
            OutputSchemaValidator.create_for_capability("safety_scanning")

        # Elke aanroep leest het YAML-bestand
        assert mock_yaml.call_count >= 2


# ---------------------------------------------------------------------------
# (B) Judge panel provider-diversiteit (BE-AGT-019-open-1)
# ---------------------------------------------------------------------------


class TestJudgePanelProviderDiversity:
    """Elke judge in het panel gebruikt het model van de TENANT (brief 2026-10-20, ADR-041 B14).

    Voorheen: een andere leverancier per rechter (deepseek, gemini, openai) voor diversiteit. Dat stuurde de
    uitvoer van een klant naar leveranciers die hij niet koos; de diversiteit is bewust opgegeven.
    """

    @pytest.mark.asyncio
    async def test_judge_panel_uses_the_tenant_model_for_every_judge(self) -> None:
        from src.core.agents.critic_agent import CriticAgent

        CriticAgent._instances.clear()
        agent = CriticAgent(tenant_id=1)

        mock = MagicMock()
        mock.generate_response = AsyncMock(
            return_value={
                "success": True,
                "content": '{"score": 0.8, "issues": [], "suggestions": []}',
            }
        )
        with patch.object(agent, "_get_llm_client", return_value=mock):
            uitslag = await agent._run_judge_panel("test prompt", n_judges=3, timeout_per_judge=5.0)

        assert (mock.generate_response.await_count, [s for _, s in uitslag]) == (3, [0.8, 0.8, 0.8])


# ---------------------------------------------------------------------------
# (C) N configureerbaar via critic_agent.yaml (BE-AGT-019-open-2)
# ---------------------------------------------------------------------------


class TestJudgePanelSizeFromConfig:
    """judge_panel_size in critic_agent.yaml bepaalt het aantal judges."""

    @pytest.mark.asyncio
    async def test_judge_panel_size_read_from_config(self) -> None:
        """CriticAgent leest judge_panel_size uit YAML -- niet de hardcoded N=3."""
        from src.core.agents.critic_agent import CriticAgent
        from src.core.shared.interfaces import ExecutionResult

        CriticAgent._instances.clear()
        agent = CriticAgent(tenant_id=1)

        mock_result = MagicMock(spec=ExecutionResult)
        mock_result.output = "test output"

        run_panel_calls: list[tuple[str, int, float]] = []

        async def mock_run_judge_panel(
            prompt: str, n_judges: int, timeout_per_judge: float
        ) -> list[tuple[int, float | None]]:
            run_panel_calls.append((prompt, n_judges, timeout_per_judge))
            return [(i, 0.7) for i in range(n_judges)]

        # YAML heeft judge_panel_size: 2 (gesimuleerd)
        with patch.object(agent, "_run_judge_panel", side_effect=mock_run_judge_panel):
            with patch.object(agent, "_get_judge_panel_size", return_value=2):
                await agent._judge_panel_critique("TestAgent", mock_result)

        assert len(run_panel_calls) == 1
        _, n_judges_used, _ = run_panel_calls[0]
        assert n_judges_used == 2, f"Verwacht 2 judges uit config, maar kreeg {n_judges_used}"

    def test_critic_agent_has_get_judge_panel_size_method(self) -> None:
        """CriticAgent heeft een _get_judge_panel_size() methode die YAML uitleest."""
        from src.core.agents.critic_agent import CriticAgent

        CriticAgent._instances.clear()
        agent = CriticAgent(tenant_id=1)

        assert hasattr(agent, "_get_judge_panel_size"), (
            "CriticAgent mist _get_judge_panel_size() methode"
        )
        size = agent._get_judge_panel_size()
        assert isinstance(size, int)
        assert 1 <= size <= 5, f"judge_panel_size moet tussen 1 en 5 liggen, maar was {size}"

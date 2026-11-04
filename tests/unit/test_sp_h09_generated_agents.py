"""
SP-H09: Generated agents placeholders aanpakken (B-016).

79 generated agents hebben lege CAPABILITIES = [] en get_capabilities() -> [].
AgentRouter selecteert op capabilities; lege catalog = nooit of willekeurig geselecteerd.

Fix: ENABLE_GENERATED_AGENTS=false (default).
Bij false: SubagentLoader slaat alle generated/ bestanden over.
Bij true: agents beschikbaar voor dev/test.

Tests:
1. _is_generated_agents_enabled() default = false
2. Flag true/numeric schakelt in
3. _should_skip_file() slaat generated/ over bij false
4. _should_skip_file() laadt generated/ bij true
5. Niet-generated files worden altijd geladen
6. Bestaand skip-gedrag (_ prefix, __init__.py) blijft intact
7. Behavioral: operator ziet geen generated agents by default
8. .env.example documenteert de flag
"""

import os
import pathlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _echte_subagent_loader():
    """test_subagent_endpoints.py zet bij het verzamelen een MagicMock in sys.modules.

    Zonder deze opruiming hangt de uitslag hier af van de testvolgorde: draait deze file
    na het verzamelen van die file, dan geeft `_is_generated_agents_enabled()` een
    MagicMock terug en faalt `is False`. Gemeten in de pre-push-selectie van 2026-11-01.
    `patch.dict` zet sys.modules na de test terug zoals het was (ADR-036 OP-45).
    """
    naam = "src.core.agents.subagent_loader"
    with patch.dict(sys.modules):
        if isinstance(sys.modules.get(naam), MagicMock):
            sys.modules.pop(naam, None)
        yield


class TestGeneratedAgentsFlagResolution:
    """Unit tests voor _is_generated_agents_enabled() resolver."""

    def test_default_is_false_when_flag_unset(self):
        """ENABLE_GENERATED_AGENTS default = false (lege catalogs niet in productie)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_GENERATED_AGENTS", None)
            from src.core.agents.subagent_loader import _is_generated_agents_enabled

            assert _is_generated_agents_enabled() is False

    def test_flag_true_string_enables(self):
        """ENABLE_GENERATED_AGENTS=true schakelt agents in."""
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "true"}, clear=False):
            from src.core.agents.subagent_loader import _is_generated_agents_enabled

            assert _is_generated_agents_enabled() is True

    def test_flag_numeric_one_enables(self):
        """ENABLE_GENERATED_AGENTS=1 schakelt agents in (truthy parsering)."""
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "1"}, clear=False):
            from src.core.agents.subagent_loader import _is_generated_agents_enabled

            assert _is_generated_agents_enabled() is True

    def test_flag_yes_enables(self):
        """ENABLE_GENERATED_AGENTS=yes schakelt agents in."""
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "yes"}, clear=False):
            from src.core.agents.subagent_loader import _is_generated_agents_enabled

            assert _is_generated_agents_enabled() is True

    def test_flag_false_string_disables(self):
        """ENABLE_GENERATED_AGENTS=false schakelt agents uit."""
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "false"}, clear=False):
            from src.core.agents.subagent_loader import _is_generated_agents_enabled

            assert _is_generated_agents_enabled() is False

    def test_flag_on_enables(self):
        """ENABLE_GENERATED_AGENTS=on schakelt agents in."""
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "on"}, clear=False):
            from src.core.agents.subagent_loader import _is_generated_agents_enabled

            assert _is_generated_agents_enabled() is True

    def test_flag_zero_disables(self):
        """ENABLE_GENERATED_AGENTS=0 schakelt agents uit."""
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "0"}, clear=False):
            from src.core.agents.subagent_loader import _is_generated_agents_enabled

            assert _is_generated_agents_enabled() is False


class TestShouldSkipFileWithGeneratedFlag:
    """Unit tests voor SubagentLoader._should_skip_file() met de feature flag."""

    def test_generated_file_skipped_when_flag_false(self):
        """Generated agent file wordt overgeslagen als ENABLE_GENERATED_AGENTS=false."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_GENERATED_AGENTS", None)
            from src.core.agents.subagent_loader import SubagentLoader

            loader = SubagentLoader()
            path = Path("src/core/agents/generated/backend_architect_agent.py")
            assert loader._should_skip_file(path) is True, (
                "Generated agent moet overgeslagen worden als flag niet gezet is (B-016)"
            )

    def test_generated_file_included_when_flag_true(self):
        """Generated agent file wordt geladen als ENABLE_GENERATED_AGENTS=true."""
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "true"}, clear=False):
            from src.core.agents.subagent_loader import SubagentLoader

            loader = SubagentLoader()
            path = Path("src/core/agents/generated/backend_architect_agent.py")
            assert loader._should_skip_file(path) is False, (
                "Generated agent mag NIET overgeslagen worden als ENABLE_GENERATED_AGENTS=true"
            )

    def test_non_generated_file_always_included_when_flag_false(self):
        """Normale (niet-generated) agent files worden altijd geladen, ook als flag false."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_GENERATED_AGENTS", None)
            from src.core.agents.subagent_loader import SubagentLoader

            loader = SubagentLoader()
            path = Path("src/core/agents/router_agent.py")
            assert loader._should_skip_file(path) is False, (
                "Niet-generated agents mogen nooit overgeslagen worden door feature flag"
            )

    def test_underscore_prefix_file_always_skipped(self):
        """Files die beginnen met _ worden altijd overgeslagen (bestaand gedrag onveranderd)."""
        from src.core.agents.subagent_loader import SubagentLoader

        loader = SubagentLoader()
        path = Path("src/core/agents/_internal.py")
        assert loader._should_skip_file(path) is True

    def test_init_file_always_skipped(self):
        """__init__.py wordt altijd overgeslagen (bestaand gedrag onveranderd)."""
        from src.core.agents.subagent_loader import SubagentLoader

        loader = SubagentLoader()
        path = Path("src/core/agents/__init__.py")
        assert loader._should_skip_file(path) is True

    def test_normal_agent_file_not_skipped(self):
        """Normaal agent-bestand buiten generated/ wordt niet overgeslagen."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_GENERATED_AGENTS", None)
            from src.core.agents.subagent_loader import SubagentLoader

            loader = SubagentLoader()
            path = Path("src/core/agents/base_agent.py")
            assert loader._should_skip_file(path) is False


class TestGeneratedAgentsBehavioral:
    """Behavioral tests vanuit operator-perspectief (B-016)."""

    def test_generated_agents_not_discovered_by_default(self):
        """
        Scenario: operator deployt zonder ENABLE_GENERATED_AGENTS.
        Verwacht: SubagentLoader slaat alle generated/ bestanden over.
        Reden: 77 agents met lege capabilities misleiden AgentRouter (B-016).
        """
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_GENERATED_AGENTS", None)
            from src.core.agents.subagent_loader import SubagentLoader

            loader = SubagentLoader()

            generated_paths = [
                Path("src/core/agents/generated/backend_architect_agent.py"),
                Path("src/core/agents/generated/sales_automator_agent.py"),
                Path("src/core/agents/generated/seo_content_writer_agent.py"),
                Path("src/core/agents/generated/kubernetes_architect_agent.py"),
                Path("src/core/agents/generated/typescript_pro_agent.py"),
            ]

            for path in generated_paths:
                assert loader._should_skip_file(path) is True, (
                    f"Generated agent {path.name} mag niet geladen worden (B-016)"
                )

    def test_generated_agents_available_when_flag_true(self):
        """
        Scenario: developer zet ENABLE_GENERATED_AGENTS=true lokaal.
        Verwacht: generated/ agents worden NIET overgeslagen.
        """
        with patch.dict(os.environ, {"ENABLE_GENERATED_AGENTS": "true"}, clear=False):
            from src.core.agents.subagent_loader import SubagentLoader

            loader = SubagentLoader()

            generated_paths = [
                Path("src/core/agents/generated/backend_architect_agent.py"),
                Path("src/core/agents/generated/sales_automator_agent.py"),
            ]

            for path in generated_paths:
                assert loader._should_skip_file(path) is False, (
                    f"Generated agent {path.name} zou beschikbaar moeten zijn als flag=true"
                )

    def test_various_generated_path_variants_all_skipped(self):
        """Verschillende pad-varianten van generated/ worden allemaal overgeslagen."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_GENERATED_AGENTS", None)
            from src.core.agents.subagent_loader import SubagentLoader

            loader = SubagentLoader()

            variants = [
                Path("generated/some_agent.py"),
                Path("core/agents/generated/some_agent.py"),
                Path("src/core/agents/generated/some_agent.py"),
            ]
            for path in variants:
                assert loader._should_skip_file(path) is True, (
                    f"Pad {path} bevat 'generated' en mag niet geladen worden bij flag=false"
                )


class TestAgentDefinitionDatetimeFix:
    """Test dat AgentDefinition.created_at timezone-aware is (CLAUDE.md vereiste)."""

    def test_agent_definition_created_at_is_timezone_aware(self):
        """
        AgentDefinition.created_at moet timezone-aware zijn (datetime.now(timezone.utc)).
        CLAUDE.md: nooit datetime.now() of datetime.utcnow() zonder timezone.utc.
        Pre-existing bug gesloten als onderdeel van SP-H09.
        """
        from src.core.agents.subagent_loader import AgentDefinition
        from src.core.types import AgentType

        defn = AgentDefinition(
            name="test_agent",
            module_path="src.core.agents.test_agent",
            class_name="TestAgent",
            agent_type=AgentType.GENERIC,
            description="Test agent for datetime verification",
            capabilities=[],
            dependencies=[],
            resource_requirements={
                "memory_mb": 100,
                "cpu_cores": 1,
                "disk_mb": 50,
                "network": False,
            },
            performance_profile={
                "avg_execution_time": 1.0,
                "throughput_per_minute": 60.0,
                "reliability_score": 0.9,
                "scalability_factor": 1.0,
            },
        )

        assert defn.created_at.tzinfo is not None, (
            "AgentDefinition.created_at is timezone-naive -- datetime.now(timezone.utc) fix niet actief"
        )


class TestEnvExampleDocumentation:
    """Documentatie-contract: .env.example bevat de flag."""

    def test_env_example_contains_enable_generated_agents(self):
        """.env.example documenteert ENABLE_GENERATED_AGENTS."""
        env_example_path = pathlib.Path(__file__).parents[2] / ".env.example"
        try:
            content = env_example_path.read_text(encoding="utf-8")
            assert "ENABLE_GENERATED_AGENTS" in content, (
                "ENABLE_GENERATED_AGENTS niet gedocumenteerd in .env.example"
            )
        except FileNotFoundError:
            pytest.fail(
                ".env.example niet gevonden -- ENABLE_GENERATED_AGENTS documentatie ontbreekt (B-016)"
            )

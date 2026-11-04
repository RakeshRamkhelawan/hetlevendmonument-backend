"""Tests for agent definition migration and validation scripts."""

import textwrap
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Helpers - build in-memory .md content without touching the filesystem
# ---------------------------------------------------------------------------

MINIMAL_CURRENT_MD = textwrap.dedent(
    """\
    ---
    name: test-agent
    description: A test agent. Use PROACTIVELY for testing.
    model: sonnet
    ollama_model: llama3.1:8b
    ---

    ## Purpose
    Testing.
"""
)

ALREADY_MIGRATED_MD = textwrap.dedent(
    """\
    ---
    name: test-agent
    description: A test agent. Use PROACTIVELY for testing.
    model: sonnet
    ollama_model: llama3.1:8b
    stack_layer: specialist
    role: ""
    task_scope: ""
    ---

    ## Purpose
    Testing.
"""
)

COMPLETE_MD = textwrap.dedent(
    """\
    ---
    name: python-pro
    description: >
      Master Python 3.12+ with modern features, async programming, and FastAPI.
      Use PROACTIVELY for Python development, code reviews, or refactoring.
    model: sonnet
    ollama_model: llama3.1:8b
    role: Genereert production-ready Python 3.12+ code en voert code reviews uit.
    task_scope: >
      Genereert Python-code met type hints en async patterns.
      Optimaliseert bestaande code op performance en leesbaarheid.
      Schrijft pytest-suites met >90% coverage.
      Gebruik PROACTIVELY bij Python development of refactoring.
    stack_layer: specialist
    trigger_conditions:
      type: intelligent
      description: Activeer bij Python-gerelateerde taken.
    tools:
      - llm_client
    collaborates_with:
      calls:
        - critic_agent
      called_by:
        - MasterOrchestratorAgent
        - AgentRouterAgent
    escalation_path:
      on_failure: MasterOrchestratorAgent
      on_low_confidence: MasterOrchestratorAgent
      on_out_of_scope: AgentRouterAgent
    output_format: >
      Markdown met codeblokken (Python), gevolgd door uitleg en suggesties.
    constraints:
      - Handelt geen infrastructuur-deployment taken af - escaleer naar deployment-engineer
      - Schrijft geen database-migraties - escaleer naar database-admin
      - Geeft geen architectuurbeslissingen - escaleer naar architect-review
    memory_type: none
    confidence_threshold: 0.7
    version: "1.0.0"
    tags:
      - python
      - backend
      - specialist
    ---

    ## Purpose
    Python expert.
"""
)


# ---------------------------------------------------------------------------
# Tests for migrate_agent_definitions.py
# ---------------------------------------------------------------------------


class TestMigrateAgentDefinitions:
    def test_adds_skeleton_to_minimal_md(self, tmp_path):
        """Migration adds new field skeleton to a minimal (4-field) .md file."""
        from scripts.migrate_agent_definitions import migrate_md_file

        md_file = tmp_path / "test-agent.md"
        md_file.write_text(MINIMAL_CURRENT_MD, encoding="utf-8")

        result = migrate_md_file(md_file, dry_run=False)

        assert "MIGRATED" in result
        content = md_file.read_text(encoding="utf-8")
        fm_text = content.split("---", 2)[1]
        fm = yaml.safe_load(fm_text)
        assert "stack_layer" in fm
        assert "role" in fm
        assert "task_scope" in fm
        assert "trigger_conditions" in fm
        assert "tools" in fm
        assert "collaborates_with" in fm
        assert "escalation_path" in fm
        assert "output_format" in fm
        assert "constraints" in fm
        assert "memory_type" in fm
        assert "confidence_threshold" in fm
        assert "version" in fm
        assert "tags" in fm

    def test_dry_run_does_not_modify_file(self, tmp_path):
        """Dry-run mode leaves the file unchanged."""
        from scripts.migrate_agent_definitions import migrate_md_file

        md_file = tmp_path / "test-agent.md"
        md_file.write_text(MINIMAL_CURRENT_MD, encoding="utf-8")
        original = md_file.read_text(encoding="utf-8")

        migrate_md_file(md_file, dry_run=True)

        assert md_file.read_text(encoding="utf-8") == original

    def test_skips_already_migrated_file(self, tmp_path):
        """Files that already contain stack_layer are skipped."""
        from scripts.migrate_agent_definitions import migrate_md_file

        md_file = tmp_path / "test-agent.md"
        md_file.write_text(ALREADY_MIGRATED_MD, encoding="utf-8")

        result = migrate_md_file(md_file, dry_run=False)

        assert "SKIP" in result

    def test_skips_file_without_frontmatter(self, tmp_path):
        """Files without YAML frontmatter are skipped."""
        from scripts.migrate_agent_definitions import migrate_md_file

        md_file = tmp_path / "no-frontmatter.md"
        md_file.write_text("# No frontmatter here\nJust markdown.\n", encoding="utf-8")

        result = migrate_md_file(md_file, dry_run=False)

        assert "SKIP" in result

    def test_preserves_existing_values(self, tmp_path):
        """Migration does not overwrite existing frontmatter values."""
        from scripts.migrate_agent_definitions import migrate_md_file

        md_file = tmp_path / "test-agent.md"
        md_file.write_text(MINIMAL_CURRENT_MD, encoding="utf-8")

        migrate_md_file(md_file, dry_run=False)

        content = md_file.read_text(encoding="utf-8")
        fm = yaml.safe_load(content.split("---", 2)[1])
        assert fm["name"] == "test-agent"
        assert fm["model"] == "sonnet"
        assert "Use PROACTIVELY" in fm["description"]


# ---------------------------------------------------------------------------
# Tests for validate_agent_definitions.py
# ---------------------------------------------------------------------------


class TestValidateAgentDefinitions:
    def test_complete_agent_is_valid(self, tmp_path):
        """A fully specified agent passes validation with no errors."""
        from scripts.validate_agent_definitions import MDFrontmatterValidator

        md_file = tmp_path / "python-pro.md"
        md_file.write_text(COMPLETE_MD, encoding="utf-8")
        validator = MDFrontmatterValidator()

        result = validator.validate_file(md_file)

        assert result.is_valid
        assert result.errors == []
        assert result.completion_pct == 100.0

    def test_minimal_agent_is_invalid(self, tmp_path):
        """A 4-field agent fails validation and lists missing fields."""
        from scripts.validate_agent_definitions import MDFrontmatterValidator

        md_file = tmp_path / "test-agent.md"
        md_file.write_text(MINIMAL_CURRENT_MD, encoding="utf-8")
        validator = MDFrontmatterValidator()

        result = validator.validate_file(md_file)

        assert not result.is_valid
        missing = {e for e in result.errors if "Missing" in e}
        assert len(missing) >= 9  # at least 9 of the 12 new fields missing

    def test_placeholder_produces_warning_not_error(self, tmp_path):
        """Placeholder values produce warnings, not hard errors."""
        from scripts.validate_agent_definitions import MDFrontmatterValidator

        placeholder_md = MINIMAL_CURRENT_MD.replace(
            "ollama_model: llama3.1:8b",
            'ollama_model: llama3.1:8b\nrole: ""\ntask_scope: See capabilities section',
        )
        md_file = tmp_path / "test-agent.md"
        md_file.write_text(placeholder_md, encoding="utf-8")
        validator = MDFrontmatterValidator()

        result = validator.validate_file(md_file)

        # role="" and task_scope=placeholder are warnings, not errors
        warn_fields = {w for w in result.warnings if "Placeholder" in w or "leeg" in w.lower()}
        assert len(warn_fields) >= 1

    def test_role_over_120_chars_is_warning(self, tmp_path):
        """A role string longer than 120 characters generates a warning."""
        from scripts.validate_agent_definitions import MDFrontmatterValidator

        long_role_md = COMPLETE_MD.replace(
            "role: Genereert production-ready Python 3.12+ code en voert code reviews uit.",
            "role: " + "A" * 130,
        )
        md_file = tmp_path / "python-pro.md"
        md_file.write_text(long_role_md, encoding="utf-8")
        validator = MDFrontmatterValidator()

        result = validator.validate_file(md_file)

        assert any("role" in w and "lang" in w.lower() for w in result.warnings)

    def test_fewer_than_3_constraints_is_warning(self, tmp_path):
        """Having fewer than 3 constraints generates a warning."""
        from scripts.validate_agent_definitions import MDFrontmatterValidator

        two_constraints_md = COMPLETE_MD.replace(
            "constraints:\n"
            "  - Handelt geen infrastructuur-deployment taken af - escaleer naar deployment-engineer\n"
            "  - Schrijft geen database-migraties - escaleer naar database-admin\n"
            "  - Geeft geen architectuurbeslissingen - escaleer naar architect-review",
            "constraints:\n"
            "  - Handelt geen infrastructuur-deployment taken af - escaleer naar deployment-engineer",
        )
        md_file = tmp_path / "python-pro.md"
        md_file.write_text(two_constraints_md, encoding="utf-8")
        validator = MDFrontmatterValidator()

        result = validator.validate_file(md_file)

        assert any("constraints" in w for w in result.warnings)

    def test_directory_validation_returns_summary(self, tmp_path):
        """validate_directory returns total, valid, invalid counts."""
        from scripts.validate_agent_definitions import MDFrontmatterValidator

        (tmp_path / "complete.md").write_text(COMPLETE_MD, encoding="utf-8")
        (tmp_path / "minimal.md").write_text(MINIMAL_CURRENT_MD, encoding="utf-8")
        validator = MDFrontmatterValidator()

        summary = validator.validate_directory(tmp_path)

        assert summary["total"] == 2
        assert summary["valid"] == 1
        assert summary["invalid"] == 1


# ---------------------------------------------------------------------------
# Tests for bulk_fill_common_fields.py
# ---------------------------------------------------------------------------


class TestBulkFillCommonFields:
    def test_fills_stack_layer_specialist(self, tmp_path):
        """Bulk fill sets stack_layer to 'specialist' for .md agents."""
        from scripts.bulk_fill_common_fields import bulk_fill_md_file

        md_file = tmp_path / "test-agent.md"
        # Use a skeleton-migrated file (has keys but empty values)
        skeleton_md = MINIMAL_CURRENT_MD.replace(
            "ollama_model: llama3.1:8b",
            'ollama_model: llama3.1:8b\nstack_layer: ""\nmemory_type: ""\nconfidence_threshold: null\nversion: ""',
        )
        md_file.write_text(skeleton_md, encoding="utf-8")

        bulk_fill_md_file(md_file)

        fm = yaml.safe_load(md_file.read_text(encoding="utf-8").split("---", 2)[1])
        assert fm["stack_layer"] == "specialist"
        assert fm["memory_type"] == "none"
        assert fm["confidence_threshold"] == 0.7
        assert fm["version"] == "1.0.0"

    def test_does_not_overwrite_filled_values(self, tmp_path):
        """Bulk fill does not overwrite values that are already set."""
        from scripts.bulk_fill_common_fields import bulk_fill_md_file

        md_file = tmp_path / "python-pro.md"
        md_file.write_text(COMPLETE_MD, encoding="utf-8")

        bulk_fill_md_file(md_file)

        fm = yaml.safe_load(md_file.read_text(encoding="utf-8").split("---", 2)[1])
        assert fm["stack_layer"] == "specialist"  # unchanged
        assert "python" in fm["tags"]  # custom tags preserved


# ---------------------------------------------------------------------------
# Tests for AgentDefinitionV1 Pydantic model
# ---------------------------------------------------------------------------


class TestAgentDefinitionV1Model:
    def test_agent_definition_v1_instantiates(self):
        """AgentDefinitionV1 can be created with all fields."""
        from src.core.agents.config.models import AgentDefinitionV1

        defn = AgentDefinitionV1(
            role="Generates production-ready Python code and performs code reviews.",
            stack_layer="specialist",
            task_scope="Writes Python code. Reviews existing code. Writes pytest suites.",
            trigger_conditions={"type": "intelligent", "description": "Python tasks"},
            tools=["llm_client"],
            collaborates_with={"calls": [], "called_by": ["MasterOrchestratorAgent"]},
            escalation_path={
                "on_failure": "MasterOrchestratorAgent",
                "on_out_of_scope": "AgentRouterAgent",
            },
            output_format="Markdown with code blocks.",
            constraints=[
                "No infrastructure tasks.",
                "No DB migrations.",
                "No architecture decisions.",
            ],
            memory_type="none",
            confidence_threshold=0.7,
            version="1.0.0",
            tags=["python", "specialist"],
        )
        assert defn.stack_layer == "specialist"
        assert defn.memory_type == "none"
        assert defn.confidence_threshold == 0.7
        assert defn.tags == ["python", "specialist"]

    def test_agent_definition_v1_all_fields_optional(self):
        """AgentDefinitionV1 can be created with no fields (all Optional)."""
        from src.core.agents.config.models import AgentDefinitionV1

        defn = AgentDefinitionV1()
        assert defn.role is None
        assert defn.stack_layer is None
        assert defn.tools is None

    def test_agent_config_not_modified(self):
        """AgentConfig does not have a 'definition' field (not touched in this task)."""
        from src.core.agents.config.models import AgentConfig

        fields = getattr(AgentConfig, "model_fields", None) or getattr(
            AgentConfig, "__fields__", {}
        )
        assert "definition" not in fields, (
            "AgentConfig should not have a definition field - "
            "AgentConfig has extra='forbid' and incompatible required fields."
        )


# ---------------------------------------------------------------------------
# Tests for AgentFactory AgentDefinition dataclass
# ---------------------------------------------------------------------------


class TestAgentFactoryDefinitionV1:
    def test_parse_agent_markdown_returns_definition_v1(self, tmp_path):
        """AgentFactory.parse_agent_markdown() populates definition_v1 from frontmatter."""
        from src.core.agents.agent_factory import AgentFactory

        migrated_md = """\
---
name: python-pro
description: Master Python 3.12+. Use PROACTIVELY for Python development.
model: sonnet
ollama_model: llama3.1:8b
role: Generates production-ready Python 3.12+ code and performs code reviews.
task_scope: Writes Python code. Reviews existing code. Writes pytest suites.
stack_layer: specialist
trigger_conditions:
  type: intelligent
  description: Activate for Python tasks.
tools:
  - llm_client
collaborates_with:
  calls: []
  called_by:
    - MasterOrchestratorAgent
escalation_path:
  on_failure: MasterOrchestratorAgent
  on_out_of_scope: AgentRouterAgent
output_format: Markdown with Python code blocks.
constraints:
  - No infrastructure tasks.
  - No DB migrations.
  - No architecture decisions.
memory_type: none
confidence_threshold: 0.7
version: "1.0.0"
tags:
  - python
  - specialist
---

## Purpose
Python expert.

## Capabilities
- Writes Python code
"""
        md_file = tmp_path / "python-pro.md"
        md_file.write_text(migrated_md, encoding="utf-8")

        factory = AgentFactory(agenten_directory=str(tmp_path))
        result = factory.parse_agent_markdown(md_file)

        assert result is not None
        assert result.definition_v1 is not None
        assert result.definition_v1.stack_layer == "specialist"
        assert result.definition_v1.memory_type == "none"
        assert result.definition_v1.version == "1.0.0"

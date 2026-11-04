"""Tests for the generated skill manifests and WorkerAgent wrappers."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.als.agents import skills
from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent

SKILLS_DIR = Path(__file__).parents[5] / "src" / "core" / "als" / "agents" / "skills"
MANIFESTS_DIR = SKILLS_DIR / "manifests"


@pytest.mark.parametrize("manifest_path", sorted(MANIFESTS_DIR.glob("*.yml")))
def test_manifest_is_valid_yaml(manifest_path: Path) -> None:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "skill_id" in data
    assert "department" in data
    assert data["skill_id"] == manifest_path.stem


@pytest.mark.parametrize("manifest_path", sorted(MANIFESTS_DIR.glob("*.yml")))
def test_manifest_loads_via_model(manifest_path: Path) -> None:
    manifest = SkillManifest.load(manifest_path)
    config = manifest.to_config()
    assert config["agent_id"] == manifest_path.stem
    assert config["allowed_tools"]
    assert config["system_prompt"]
    # ADR-036 D4-001/OP-165: to_config() moet annex_iii_classification/human_in_the_loop
    # daadwerkelijk doorgeven -- tot deze fix ontbraken beide velden hier stilzwijgend, en
    # `_council_rejection()`'s floor (specialist_base.py) zag het manifestveld dus nooit.
    # Gevonden door de verplichte blinde review (2026-08-19): het veld was ongedekt, geen
    # enkele test brak toen het per ongeluk verwijderd werd.
    assert config["human_in_the_loop"] == manifest.human_in_the_loop
    assert config["annex_iii_classification"] == manifest.annex_iii_classification


@pytest.mark.parametrize("skill_class", skills.SKILL_CLASSES)
def test_skill_instantiates(skill_class: type[BaseSpecialistAgent]) -> None:
    agent = skill_class(tenant_id=1)
    assert isinstance(agent, BaseSpecialistAgent)
    assert agent.tenant_id == 1
    assert agent.config["agent_id"]
    assert agent.allowed_tools


@pytest.mark.parametrize("skill_class", skills.SKILL_CLASSES)
def test_skill_act_delegates_to_base(skill_class: type[BaseSpecialistAgent]) -> None:
    """Ensure generated skills do not contain hardcoded stub act() bodies."""
    import inspect

    source = inspect.getsource(skill_class.act)
    assert "simulated_tools" not in source
    assert "confidence_score=0.95" not in source
    assert ("return ExecutionResult(" not in source) or ("await super().act" in source)


def test_all_skills_exported() -> None:
    """Every generated manifest has a corresponding exported skill class."""
    skill_files = {p.stem for p in SKILLS_DIR.glob("*.py") if p.name != "__init__.py"}
    manifest_files = {p.stem for p in MANIFESTS_DIR.glob("*.yml")}
    assert manifest_files == skill_files
    assert len(skills.SKILL_CLASSES) == len(manifest_files)


def test_annex_iii_skills_marked_hitl() -> None:
    manifest = SkillManifest.load(MANIFESTS_DIR / "talentacquisition.yml")
    assert manifest.annex_iii_classification == "annex_iii"
    assert manifest.human_in_the_loop == "hitl"

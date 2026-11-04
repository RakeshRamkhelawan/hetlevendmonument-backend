"""
G1: Comprehensive YAML and Agent Config Validation

Tests the EnterpriseCatalogLoader which does full Pydantic validation
(not just YAML syntax).
"""

from pathlib import Path

import pytest

from src.core.als.agents.loader import EnterpriseCatalogLoader


@pytest.mark.integration
def test_g1_enterprise_catalog_loader_audit():
    """G1: Audit all configs via EnterpriseCatalogLoader."""
    # Load all agents and packs
    loader = EnterpriseCatalogLoader(config_root="config")
    loader.load_all()

    # Get stats
    agent_count = len(loader.agents)
    pack_count = len(loader.packs)

    # Report
    print("\n=== G1 Audit Results ===")
    print(f"Total agents loaded: {agent_count}")
    print(f"Total packs loaded: {pack_count}")
    print(f"Total components: {agent_count + pack_count}")

    # Tel wat er WERKT, niet hoeveel regels er in de map staan.
    #
    # Hier stond tot 2026-09-25 `agent_count >= 285` plus `agent_count + pack_count >= 300`.
    # Gemeten op dat moment: 289 vermeldingen, waarvan 135 een skillmodule met de gezochte
    # klasse hebben. De overige 154 vallen stil terug op BaseSpecialistAgent. Die drempel
    # verdedigde dus juist de holle catalogus -- hij zou rood worden zodra iemand de lege
    # vermeldingen OPRUIMT, en bleef groen als alle 289 hun implementatie zouden verliezen.
    # Dat is de "succes zonder werk"-vorm, in een test. Zie BE-AGT-068.
    implemented = loader.implemented_agent_keys()
    print(f"Agents met een echte implementatie: {len(implemented)}")

    assert len(implemented) >= 130, (
        f"Minder dan 130 agents hebben een echte skillklasse: {len(implemented)}. "
        f"Gemeten stand 2026-09-25: 135 van 289 vermeldingen. Een daling betekent dat een "
        f"skillmodule is verdwenen of hernoemd, niet dat er een configuratie is opgeruimd."
    )
    assert pack_count >= 80, f"Expected at least 80 packs, got {pack_count}"

    total = len(implemented) + pack_count
    assert total >= 210, (
        f"Minder dan 210 werkende componenten: {total} "
        f"({len(implemented)} agents met implementatie + {pack_count} packs). "
        f"Gemeten stand 2026-09-25: 215."
    )


@pytest.mark.integration
def test_g1_agent_config_requirements():
    """G1: Verify loaded agents meet minimum configuration requirements."""
    loader = EnterpriseCatalogLoader(config_root="config")
    loader.load_all()

    # Each agent must have required fields
    for agent_id, agent in loader.agents.items():
        assert agent.agent_id, f"Agent {agent_id} missing agent_id"
        assert agent.name, f"Agent {agent_id} missing name"
        assert agent.department, f"Agent {agent_id} missing department"
        assert agent.class_name, f"Agent {agent_id} missing class_name"


@pytest.mark.integration
def test_g1_domain_pack_requirements():
    """G1: Verify loaded packs meet minimum configuration requirements."""
    loader = EnterpriseCatalogLoader(config_root="config")
    loader.load_all()

    # Each pack must have required fields
    for pack_id, pack in loader.packs.items():
        assert pack.pack_id, f"Pack {pack_id} missing pack_id"
        assert pack.name, f"Pack {pack_id} missing name"
        assert pack.steps, f"Pack {pack_id} missing steps"
        assert len(pack.steps) > 0, f"Pack {pack_id} has no workflow steps"


@pytest.mark.integration
def test_g1_cross_reference_validation():
    """G1: Verify packs only reference valid agents."""
    loader = EnterpriseCatalogLoader(config_root="config")
    loader.load_all()

    available_agent_ids = set(loader.agents.keys())

    # Check all pack steps reference valid agents
    for pack_id, pack in loader.packs.items():
        for step in pack.steps:
            agent_key = step.agent_id.lower()
            assert agent_key in available_agent_ids, (
                f"Pack {pack_id} references unknown agent: {step.agent_id} "
                f"(available: {available_agent_ids})"
            )


@pytest.mark.integration
def test_g1_minimum_agent_count():
    """G1: minstens 130 agents met een echte implementatie (niet: 285 yaml-bestanden)."""
    loader = EnterpriseCatalogLoader(config_root="config")
    loader.load_all()

    # Zelfde correctie als hierboven: de eis gaat over agents die IETS DOEN, niet over
    # het aantal yaml-bestanden. Zie BE-AGT-068.
    implemented = loader.implemented_agent_keys()
    assert len(implemented) >= 130, (
        f"G1 REQUIREMENT: minstens 130 agents met een echte skillklasse. "
        f"Nu: {len(implemented)} van {len(loader.agents)} catalogusvermeldingen. "
        f"Gemeten stand 2026-09-25: 135."
    )


@pytest.mark.integration
def test_g1_markdown_agents_are_covered_by_loaded_catalog():
    """G1: Every markdown specialist agent should map to a loaded catalog key."""
    loader = EnterpriseCatalogLoader(config_root="config")
    loader.load_all()

    loaded_keys = set(loader.agents.keys())
    md_files = sorted(Path("src/core/agents").glob("*.md"))

    missing = []
    for md_file in md_files:
        # Normalize markdown stem and loaded key the same way to compare robustly.
        stem = (
            md_file.stem.lower()
            .replace("_agent", "")
            .replace("-agent", "")
            .replace("agent", "")
            .replace("_", "")
            .replace("-", "")
        )
        has_match = any(key.replace("_", "").replace("-", "") == stem for key in loaded_keys)
        if not has_match:
            missing.append(str(md_file).replace("\\", "/"))

    assert not missing, (
        "G1 REQUIREMENT: Every markdown agent definition must be represented in loaded catalog. "
        f"Missing matches: {missing}"
    )


@pytest.mark.integration
@pytest.mark.slow
def test_g1_detailed_audit_report():
    """G1: Generate detailed audit report of all loaded configs."""
    loader = EnterpriseCatalogLoader(config_root="config")
    loader.load_all()

    # Count by department
    departments = {}
    for agent in loader.agents.values():
        dept = agent.department
        departments[dept] = departments.get(dept, 0) + 1

    print("\n=== G1 Detailed Audit Report ===")
    print(f"Total agents: {len(loader.agents)}")
    print(f"Total packs: {len(loader.packs)}")
    print("\nAgents by department:")
    for dept, count in sorted(departments.items(), key=lambda x: -x[1]):
        print(f"  {dept}: {count}")

    # Check technology distribution
    technologies = {}
    for agent in loader.agents.values():
        tech = agent.technology
        technologies[tech] = technologies.get(tech, 0) + 1

    print("\nAgents by technology:")
    for tech, count in sorted(technologies.items(), key=lambda x: -x[1])[:5]:
        print(f"  {tech}: {count}")

    # Success
    assert len(loader.agents) > 0, "No agents loaded!"
    assert len(loader.packs) > 0, "No packs loaded!"

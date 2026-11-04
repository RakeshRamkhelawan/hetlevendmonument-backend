"""Declarative manifest for ALS worker skills.

A SkillManifest is the single source of truth for a worker agent's identity,
allowed tools, memory namespaces, governance level and runtime budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class SkillBudgetExceeded(Exception):
    """Een skill-invocatie heeft zijn eigen gedeclareerde budget overschreden.

    ADR-036 D10 stap 5 (BE-AGT-041). Bewust NIET `InsufficientPranaError`
    (governance/prana_guard.py): dat gaat over het tenant-brede prana-tegoed, dit over de
    limieten die deze ene skill in zijn manifest voor zichzelf declareert. Twee
    verschillende begrenzingen, en ze kunnen onafhankelijk afgaan.

    De melding benoemt altijd WELKE limiet is geraakt en met welke waarde, zodat een
    budgetafbreking te onderscheiden is van een echte storing.
    """



@dataclass
class SkillBudget:
    """Runtime budget for one skill invocation."""

    max_steps: int = 8
    max_llm_calls: int = 5
    timeout_seconds: int = 60
    prana_cost_limit: int = 100

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "SkillBudget":
        return cls(
            max_steps=data.get("max_steps", 8),
            max_llm_calls=data.get("max_llm_calls", 5),
            timeout_seconds=data.get("timeout_seconds", 60),
            prana_cost_limit=data.get("prana_cost_limit", 100),
        )


@dataclass
class SkillManifest:
    """Declarative configuration for an ALS worker skill."""

    skill_id: str
    class_name: str
    department: str
    annex_iii_classification: str
    human_in_the_loop: str
    technology: str
    role: str
    goal: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    memory: dict[str, list[str]] = field(default_factory=dict)
    input_schema: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )
    output_schema: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )
    budget: SkillBudget = field(default_factory=SkillBudget)
    # ADR-036 OP-02. Het versienummer van DEZE tekst. Standaard 1, zodat de 135
    # bestaande manifesten geldig blijven zonder ze allemaal aan te raken; een manifest
    # dat gefaseerd wil uitrollen zet het expliciet en hoogt het op in zijn canary-blok.
    manifest_version: int = 1
    # Het onbewerkte canary-blok. Bewust NIET hier gevalideerd: `SkillManifest` kent geen
    # tenant en kan de uitrol dus niet beslissen. Validatie en fail-safe zitten in
    # `skill_rollout.resolve_config_for_tenant()`, op de plek waar de tenant bekend is.
    canary: dict[str, object] | None = None
    # De agentkaart (agentkaart dag 1, besluit Rakesh 2026-10-24): klantregels, gegevens, koppelingen, start, onthoudt, waarom,
    # proefset, eigenaar en vakregels van deze agent, naast rol, doel en gereedschap hierboven. Optioneel: een manifest zonder
    # kaart blijft geldig; de bedrade agents MOETEN er een hebben (tests/architecture/
    # test_werkende_agent_heeft_volledige_agentkaart.py). Hier onbewerkt bewaard; de toets leest het YAML-blok zelf.
    agentkaart: dict[str, object] | None = None

    @classmethod
    def load(cls, path: Path) -> "SkillManifest":
        """Load a manifest from a YAML file."""
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Manifest {path} is not a valid YAML mapping")
        return cls(
            skill_id=data["skill_id"],
            class_name=data["class_name"],
            department=data["department"],
            annex_iii_classification=data.get("annex_iii_classification", "none"),
            human_in_the_loop=data.get("human_in_the_loop", "hotl"),
            technology=data.get("technology", "llm"),
            role=data["role"],
            goal=data["goal"],
            system_prompt=data["system_prompt"],
            allowed_tools=data.get("allowed_tools", []),
            memory=data.get("memory", {}),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            budget=SkillBudget.from_dict(data.get("budget", {})),
            manifest_version=data.get("manifest_version", 1),
            canary=data.get("canary"),
            agentkaart=data.get("agentkaart"),
        )

    def to_config(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return the manifest as the dict shape expected by BaseSpecialistAgent."""
        return {
            "agent_id": self.skill_id,
            "name": self.role,
            "description": self.goal,
            "technology": self.technology,
            "department": self.department,
            "system_prompt": self.system_prompt,
            "allowed_tools": self.allowed_tools,
            "memory": self.memory,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            # ADR-036 D4-001: beide velden bestaan al op deze dataclass en worden al uit het
            # manifest geparsed, maar ontbraken hier -- `_council_rejection()`'s D4-002-floor
            # (specialist_base.py) leest `human_in_the_loop` uit `self.config` en zag hem tot nu
            # toe nooit, ongeacht wat het manifest declareerde.
            "annex_iii_classification": self.annex_iii_classification,
            "human_in_the_loop": self.human_in_the_loop,
            "budget": {
                "max_steps": self.budget.max_steps,
                "max_llm_calls": self.budget.max_llm_calls,
                "timeout_seconds": self.budget.timeout_seconds,
                "prana_cost_limit": self.budget.prana_cost_limit,
            },
            # ADR-036 OP-02: het versienummer reist mee de agent in, zodat een
            # waargenomen antwoord te herleiden is tot de tekst die het voortbracht.
            # `canary` gaat onbewerkt mee omdat pas `BaseSpecialistAgent.__init__` de
            # tenant kent en de uitrol kan beslissen.
            "manifest_version": self.manifest_version,
            "canary": self.canary,
            "agentkaart": self.agentkaart,
        }

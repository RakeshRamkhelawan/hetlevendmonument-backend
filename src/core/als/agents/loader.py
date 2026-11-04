import logging
import os
import re
from typing import TYPE_CHECKING, Any, Optional, cast

import yaml
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    # Alleen voor de annotatie: een echte import hier zou een cyclus geven
    # (specialist_base importeert uiteindelijk weer deze loader).
    from src.core.als.agents.specialist_base import BaseSpecialistAgent

logger = logging.getLogger(__name__)

# --- Models ---


class AgentConfig(BaseModel):
    agent_id: str
    name: str
    department: str
    technology: str
    module_path: str | None = None
    class_name: str
    description: str | None = None
    required_integrations: list[str] = Field(default_factory=list)
    is_active: bool = True
    priority: str = "MEDIUM"
    allowed_tools: list[str] = Field(default_factory=list)
    ooda_profile: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class WorkflowStep(BaseModel):
    agent_id: str
    mode: str = "sequential"
    sla_seconds: float = 30.0
    params: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class DomainPack(BaseModel):
    pack_id: str
    name: str
    steps: list[WorkflowStep]
    #: Nederlandse naam en korte omschrijving voor het scherm (`config/domain_packs.yaml` is de bron); `pack_id`
    #: en de Engelse `name` blijven wat ze waren.
    display_name: str | None = None
    description: str | None = None


# --- Loader ---


class EnterpriseCatalogLoader:
    """
    The central authority for discovering and validating Agents and Domain Packs.
    Ensures the system is aware of all components during build and runtime.
    """

    _instance: Optional["EnterpriseCatalogLoader"] = None
    _initialized: bool = False
    config_root: str = "config"
    agents: dict[str, "AgentConfig"] = {}
    packs: dict[str, "DomainPack"] = {}

    def __new__(cls, *args: Any, **kwargs: Any) -> "EnterpriseCatalogLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_root: str = "config") -> None:
        if self._initialized:
            # Keep singleton behavior, but allow callers/tests to switch roots safely.
            if self.config_root != config_root:
                self.config_root = config_root
                self.agents = {}
                self.packs = {}
            return
        self.config_root = config_root
        self.agents = {}
        self.packs = {}
        self._initialized = True

    def load_all(self) -> "EnterpriseCatalogLoader":
        """Discovers all agents and packs."""
        # Always rebuild catalog to avoid stale singleton state across calls.
        self.agents = {}
        self.packs = {}
        self._load_agents()
        self._load_packs()
        self._validate_cross_references()
        return self

    @staticmethod
    def _normalize_agent_key(class_name: str) -> str:
        """De catalogussleutel: de klassenaam zonder het achtervoegsel `Agent`.

        Hier stond tot 2026-09-26 `class_name.lower().replace("agent", "")`. Dat is een
        LOSSY afleiding: `str.replace` vervangt ELK voorkomen, niet het achtervoegsel.
        `DunningAgentAgent` werd daardoor `dunning`, waarna de loader
        `skills/dunning.py` VOND en daarin `DunningSkillSkill` zocht -- een bestaande,
        werkende skill die nooit laadde, met alleen een debug-regel als spoor
        (BE-AGT-068). `PaymentAgentRouterAgent` zou `paymentrouter` geven, en twee
        klassenamen kunnen zo op dezelfde sleutel uitkomen zonder dat iets dat merkt.

        Gemeten op 2026-09-26 over alle 139 configuraties: NUL sleutels veranderen door
        deze reparatie. De twee die het wel deden (`AgentHealthMonitorAgent`,
        `AgentRouterAgent`) waren catalogusvermeldingen zonder implementatie en zijn bij
        de opruiming van BE-AGT-068 verdwenen.

        `scripts/audit_agent_yaml.py::_normalize_key` houdt bewust een kopie van deze
        regel, zodat dat script buiten de applicatiecontext kan draaien. Dat de twee
        gelijk blijven wordt afgedwongen door
        `tests/architecture/test_de_twee_sleutelafleidingen_zijn_het_eens.py`.
        """
        romp = class_name[: -len("Agent")] if class_name.endswith("Agent") else class_name
        # Een klassenaam die exact "Agent" is zou een LEGE sleutel geven, en dan importeert
        # get_agent_instance `...skills.` -- dat faalt op een manier die niemand leest.
        # Zo'n naam bestaat vandaag niet; de terugval is er zodat hij niet stil kan ontstaan.
        return romp.lower() or class_name.lower()

    @staticmethod
    def _skill_class_name(class_name: str) -> str:
        """De klassenaam die get_agent_instance in de skillmodule zoekt.

        Staat hier als functie en niet als losse uitdrukking omdat een bewaker in
        tests/architecture deze afleiding moet kunnen AANROEPEN. Een kopie daar zou de
        wijziging overleven die hij hoort te betrappen.
        """
        return class_name.replace("Agent", "Skill")

    @classmethod
    def _normalize_agent_config(cls, raw_config: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        if "agent_id" in raw_config:
            return raw_config

        agent = raw_config.get("agent") or {}
        classification = raw_config.get("classification") or {}
        technical = raw_config.get("technical") or {}
        behaviour = raw_config.get("behaviour") or {}
        metadata = raw_config.get("metadata") or {}

        class_name = str(agent.get("name") or technical.get("class_name") or "").strip()
        if not class_name:
            raise ValueError("Missing agent.name/class_name in nested agent config")

        agent_key = cls._normalize_agent_key(class_name)
        return {
            "agent_id": agent_key,
            "name": class_name,
            "department": str(classification.get("department") or "Unknown"),
            "technology": str(technical.get("technology") or "unknown"),
            "module_path": technical.get("full_path"),
            "class_name": class_name,
            "description": metadata.get("description"),
            "required_integrations": list(raw_config.get("required_integrations") or []),
            "is_active": str(agent.get("status", "active")).lower() == "active",
            "priority": str(behaviour.get("priority") or "MEDIUM").upper(),
            "allowed_tools": list(raw_config.get("capabilities") or []),
            "ooda_profile": raw_config.get("ooda_profile"),
        }

    def validate_config(self, raw_config: dict[str, Any]) -> AgentConfig:  # TODO(TYPE): replace Any with concrete type
        return AgentConfig(**self._normalize_agent_config(raw_config))

    def _load_agents(self) -> None:
        agent_dir = os.path.join(self.config_root, "agents")
        if not os.path.exists(agent_dir):
            return

        for fn in os.listdir(agent_dir):
            if fn.endswith((".yaml", ".yml")):
                try:
                    with open(os.path.join(agent_dir, fn)) as f:
                        raw_config = yaml.safe_load(f) or {}
                        cfg = self.validate_config(raw_config)
                        # Create consistent key (lowercase class name without Agent suffix)
                        key = self._normalize_agent_key(cfg.class_name)
                        self.agents[key] = cfg
                except Exception as e:
                    logger.error(f"Failed to load agent {fn}: {e}")

    def _load_packs(self) -> None:
        pack_file = os.path.join(self.config_root, "domain_packs.yaml")
        if not os.path.exists(pack_file):
            return

        try:
            with open(pack_file) as f:
                data = yaml.safe_load(f)
                for p_data in data.get("packs", []):
                    pack = DomainPack(**p_data)
                    self.packs[pack.pack_id] = pack
        except Exception as e:
            logger.error(f"Failed to load domain packs: {e}")

    def _validate_cross_references(self) -> None:
        """CRITICAL: Ensures packs only refer to agents that actually exist."""
        missing: list[str] = []
        for pid, pack in self.packs.items():
            for step in pack.steps:
                key = step.agent_id.lower()
                if key not in self.agents:
                    exists = any(a.agent_id == step.agent_id for a in self.agents.values())
                    if not exists:
                        missing.append(f"Pack '{pid}' -> Agent '{step.agent_id}'")

        if missing:
            raise ValueError("Catalog Integrity Error: Missing references:\n" + "\n".join(missing))

        logger.info(
            f"Catalog validated: {len(self.agents)} agents and {len(self.packs)} packs are healthy."
        )

    def implemented_agent_keys(self) -> set[str]:
        """De catalogussleutels waarvoor een ECHTE skill bestaat.

        De catalogus bevat vermeldingen zonder implementatie; `get_agent_instance` valt
        daar terug op `BaseSpecialistAgent`. Een telling van `self.agents` zegt dus niets
        over hoeveel agents er werkelijk iets doen, en precies dat verschil is waar dit
        project op is stukgelopen (BE-AGT-068: 289 vermeldingen, 138 implementaties).

        Deze methode stelt dezelfde vraag als `get_agent_instance`, met dezelfde
        afleidingen, maar zonder te instantieren. Hij IMPORTEERT de skillmodules en is
        daarmee traag en niet bedoeld voor een verzoekpad -- gebruik hem voor metingen,
        bewakers en diagnostiek.
        """
        import importlib

        gevonden: set[str] = set()
        for agent_key, config in self.agents.items():
            try:
                module = importlib.import_module(f"src.core.als.agents.skills.{agent_key}")
            except ImportError:
                continue
            if getattr(module, self._skill_class_name(config.class_name), None) is not None:
                gevonden.add(agent_key)
        return gevonden

    def get_agent_instance(self, agent_key: str, tenant_id: int) -> "BaseSpecialistAgent":
        """
        Dynamically imports and instantiates the specific Skill class for an agent.
        Falls back to BaseSpecialistAgent if no specific skill file exists.

        Elke skill-klasse in src/core/als/agents/skills/ erft van BaseSpecialistAgent,
        net als het fallback-pad hieronder -- dat is de gemeenschappelijke ondergrens.
        Skill-specifieke methoden (zoals execute_with_manifest_prompt op de ADR-036
        D10-pilot) zitten daar niet in; een aanroeper die zo'n methode nodig heeft moet
        eerst vaststellen dat hij met die skill te maken heeft. Zie packs.py.
        """
        config = self.agents.get(agent_key)
        if not config:
            raise ValueError(f"Agent '{agent_key}' not found in catalog.")

        # Buiten de try: een fout hierin is geen "skill niet gevonden", en het except-blok
        # hieronder noemt beide namen in zijn melding -- ongebonden zouden ze daar een
        # NameError geven die de echte oorzaak verbergt.
        module_name = f"src.core.als.agents.skills.{agent_key}"
        class_name = self._skill_class_name(config.class_name)

        try:
            import importlib

            module = importlib.import_module(module_name)
            skill_class = getattr(module, class_name)

            # getattr op een dynamisch geimporteerde module levert Any. De cast legt de
            # invariant vast die het skills-pakket afdwingt: elke *Skill-klasse in
            # src/core/als/agents/skills/ erft van BaseSpecialistAgent, net als het
            # fallback-pad hieronder. String-vorm zodat er geen runtime-import nodig is.
            skill = skill_class(config=config.dict(), tenant_id=tenant_id)
            return cast("BaseSpecialistAgent", skill)

        except (ImportError, AttributeError) as e:
            # Twee gevallen die er hetzelfde uitzien en het NIET zijn.
            #
            # (a) De skillmodule bestaat helemaal niet. Dat is vandaag de normale stand
            #     voor de catalogusvermeldingen zonder implementatie; luid melden zou per
            #     cataloguslading honderden regels geven en echte fouten ondersneeuwen.
            #
            # (b) De module bestaat WEL maar levert de klasse niet op: een verkeerde
            #     class_name in de configuratie, een hernoemde klasse, of een kapotte
            #     import BINNEN de skill. Dat is altijd een defect, en het bleef tot
            #     2026-09-25 onzichtbaar -- `DunningAgentAgent` in de configuratie liet
            #     een volledig werkende skill nooit laden, met alleen een debug-regel als
            #     spoor. Zie BE-AGT-068.
            module_ontbreekt = isinstance(e, ModuleNotFoundError) and e.name == module_name
            if module_ontbreekt:
                logger.debug(
                    f"No skill module for {agent_key} ({module_name}); falling back to generic."
                )
            else:
                logger.warning(
                    "Skill module %s exists but did not yield class %s for agent %s; "
                    "falling back to generic. (%s: %s)",
                    module_name,
                    class_name,
                    agent_key,
                    type(e).__name__,
                    e,
                )

            from src.core.als.agents.specialist_base import BaseSpecialistAgent

            return BaseSpecialistAgent(config=config.dict(), tenant_id=tenant_id)

    def get_agent_registry_format(self) -> dict[str, tuple[str, str, str]]:
        """Returns the format expected by the legacy AGENT_REGISTRY."""

        def normalize_department_name(value: str) -> str:
            normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
            normalized = re.sub(r"_+", "_", normalized)
            replacements: dict[str, str] = {
                "it_security": "it_security",
                "it_infra_cyber_security": "it_security",
                "hr_culture": "hr_culture",
                "finance_treasury": "finance_treasury",
                "legal_compliance": "legal_compliance",
                "legal_risk_compliance": "legal_compliance",
                "strategy_business": "strategy_business",
                "product_innovation": "product_innovation",
                "operations_supply_chain": "operations_supply_chain",
                "sales_marketing": "sales_marketing",
                "customer_experience": "customer_experience",
                "data_ai_governance": "data_ai_governance",
            }
            return replacements.get(normalized, normalized)

        return {
            k: (normalize_department_name(v.department), v.class_name, v.technology)
            for k, v in self.agents.items()
        }


# Alias for backward compatibility
AgentCatalogLoader = EnterpriseCatalogLoader

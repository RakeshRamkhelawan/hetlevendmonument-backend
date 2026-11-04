"""Elk pad dat klantgegevens verwerkt, haalt zijn taalmodel via de ene deur (brief 2026-10-20, ADR-041 B14).

**Wat hij toetst (AST).** Buiten de LLM-pakketten zelf (`src/core/llm/`, `src/core/services/llm/` en de
gedeelde clientstapel) mag in `src/` niemand een taalmodel BOUWEN of KIEZEN langs de deur om:
`create_llm_client(...)`, `create_llm_client_from_config(...)`, `get_default_llm_config()`,
`get_cva_llm_config()`, `LLMService(...)`, `get_llm_service()`, `get_llm_provider(...)`,
`get_fallback_chain()`, `LLMProviderFactory.get_provider(...)`. Een pad met tenantgegevens gebruikt
`TenantTaalmodel(tenant_id)` of `LLMService.for_tenant(tenant_id)`.

**De uitzonderingen** staan in `BEKENDE_UITZONDERINGEN` met sleutel `bestand::functie`, een datum, een
categorie en een reden. Twee categorieen:

- `systeem`: het pad krijgt GEEN tenantgegevens (health, opstart, modellijst). Het platformstandaardmodel is
  dan juist goed; de reden zegt waarom er geen klantgegevens in zitten.
- `dood`: het pad heeft in `src/` geen aanroeper in een gemonteerde route of actor. De sleutel `aanroepers`
  noemt precies de bestanden die de module nog importeren; komt er een bij, dan faalt
  `test_een_dood_pad_heeft_geen_nieuwe_aanroeper` en moet het pad eerst naar de deur.

`test_de_uitzonderingslijst_is_niet_verouderd` faalt zodra een uitzondering niets meer vindt.

**Mutatiebewijs:** zie `docs/backend/review/review-BE-LLM-007.md`.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

#: Deze pakketten ZIJN de LLM-laag; daar mag je een model bouwen.
VRIJGESTELDE_PAKKETTEN = (
    "src/core/llm/",
    "src/core/services/llm/",
    "src/core/shared/llm_client.py",
    "src/scripts/",
)

#: Bestanden binnen een vrijgesteld pakket die TOCH gescand worden: een route hoort niet tot de LLM-laag zelf
#: (Gate 2 ronde 1, 2026-10-20: `llm/llm_endpoints.py` bouwt een module-level `LLMService()` en bood chat aan).
TOCH_GESCAND = {"src/core/llm/llm_endpoints.py"}

FABRIEKSNAMEN = {
    "create_llm_client",
    "create_llm_client_from_config",
    "get_default_llm_config",
    "get_cva_llm_config",
    "get_llm_service",
    "get_llm_provider",
    "get_fallback_chain",
}
KLASSEN = {"LLMService"}
FABRIEK_METHODEN = {("LLMProviderFactory", "get_provider")}

#: `bestand::functie` -> (datum, categorie, reden, module, aanroepers). `module` (punt-notatie) en `aanroepers`
#: alleen bij `dood`.
BEKENDE_UITZONDERINGEN: dict[str, tuple[str, str, str, str | None, frozenset[str]]] = {
    "src/core/agents/cva/llm_handler.py::LLMHandler.__init__": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die met `get_default_llm_config()` kiest (Ollama, of Google bij een sleutel): dit is de enige open restkans van deze lijst",
        "src.core.agents.cva.llm_handler",
        frozenset(
            {
                "src/core/agents/cva/agent.py",
                "src/core/agents/cva_agent.py",
                "src/core/agents/wrapper_agents.py",
            }
        ),
    ),
    "src/core/agents/cva/llm_handler.py::LLMHandler._get_llm_client_for_provider": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die met `get_default_llm_config()` kiest (Ollama, of Google bij een sleutel): dit is de enige open restkans van deze lijst",
        "src.core.agents.cva.llm_handler",
        frozenset(
            {
                "src/core/agents/cva/agent.py",
                "src/core/agents/cva_agent.py",
                "src/core/agents/wrapper_agents.py",
            }
        ),
    ),
    "src/core/agents/ethical/engine.py::EthicalReasoningSystem.initialize": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die alleen `anthropic` (ValueError) bouwt",
        "src.core.agents.ethical.engine",
        frozenset({"src/core/agents/ethical_reasoning_system.py"}),
    ),
    "src/core/agents/ethical_insight_generator.py::EthicalInsightGenerator.initialize": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die alleen `anthropic` (ValueError) bouwt",
        "src.core.agents.ethical_insight_generator",
        frozenset(),
    ),
    "src/core/agents/ethical_knowledge_graph.py::EthicalKnowledgeGraph.initialize": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die alleen `anthropic` (ValueError) bouwt",
        "src.core.agents.ethical_knowledge_graph",
        frozenset(),
    ),
    "src/core/agents/ethical_pattern_mining.py::EthicalPatternMiner.initialize": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die alleen `anthropic` (ValueError) bouwt",
        "src.core.agents.ethical_pattern_mining",
        frozenset(),
    ),
    "src/core/agents/ethics_classification_trainer.py::EthicsClassificationTrainer._initialize_llm": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die eerst `anthropic` (ValueError) probeert; de Google-tak daarna is onbereikbaar en `mock` weigert buiten tests",
        "src.core.agents.ethics_classification_trainer",
        frozenset(),
    ),
    "src/core/agents/ml_ethics_engine.py::MLEthicsEngine.initialize": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die alleen `anthropic` (ValueError) en `mock` (ValueError buiten tests) bouwt",
        "src.core.agents.ml_ethics_engine",
        frozenset({"src/core/agents/ml_ethics_agent.py"}),
    ),
    "src/core/agents/router_agent_service.py::RouterAgentService.execute_request": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.core.agents.router_agent_service",
        frozenset({"src/domains/workflows/services.py"}),
    ),
    "src/core/agents/vision_synthesis.py::VisionSynthesis._initialize_llm": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden (`_is_agent_class` kijkt ook naar methodenamen); NIET gemeten of dat in productie deze klasse vindt. Haar model komt uit de gedeelde fabriek, die eerst `anthropic` (ValueError) probeert; de Google-tak daarna is onbereikbaar en `mock` weigert buiten tests",
        "src.core.agents.vision_synthesis",
        frozenset(),
    ),
    "src/core/api/llm_endpoints.py::get_available_models": (
        "2026-10-20",
        "systeem",
        "modellijst en status van het PLATFORM; er gaan geen tenantgegevens doorheen",
        None,
        frozenset(),
    ),
    "src/core/api/llm_endpoints.py::get_llm_status": (
        "2026-10-20",
        "systeem",
        "modellijst en status van het PLATFORM; er gaan geen tenantgegevens doorheen",
        None,
        frozenset(),
    ),
    "src/core/api/setup/lifecycle.py::_test_llm_provider_health": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.core.api.setup.lifecycle",
        frozenset(),
    ),
    "src/core/api/v1/cva/dependencies.py::probe_llm_health": (
        "2026-10-20",
        "systeem",
        "gezondheidsmeting van de CVA-health: configuratie en bereikbaarheid, geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/api/v1/system/llm_health.py::llm_health_check": (
        "2026-10-20",
        "systeem",
        "beheerdersendpoints voor gezondheid, metrieken, wissel en test van het PLATFORMmodel; de wissel eist nu een platformbeheerder; geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/api/v1/system/llm_health.py::llm_metrics": (
        "2026-10-20",
        "systeem",
        "beheerdersendpoints voor gezondheid, metrieken, wissel en test van het PLATFORMmodel; de wissel eist nu een platformbeheerder; geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/api/v1/system/llm_health.py::llm_switch_provider": (
        "2026-10-20",
        "systeem",
        "beheerdersendpoints voor gezondheid, metrieken, wissel en test van het PLATFORMmodel; de wissel eist nu een platformbeheerder; geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/api/v1/system/llm_health.py::llm_test_prompt": (
        "2026-10-20",
        "systeem",
        "beheerdersendpoints voor gezondheid, metrieken, wissel en test van het PLATFORMmodel; de wissel eist nu een platformbeheerder; geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/api/v1/system/llm_status.py::llm_status": (
        "2026-10-20",
        "systeem",
        "status van het PLATFORMmodel; geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/app_lifespan.py::_init_llm_service": (
        "2026-10-20",
        "systeem",
        "opstart: gezondheid van het platformmodel en de keten voor de circuit-breakermonitor; geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/app_lifespan.py::_wire_proactive_extras": (
        "2026-10-20",
        "systeem",
        "opstart: gezondheid van het platformmodel en de keten voor de circuit-breakermonitor; geen tenantgegevens",
        None,
        frozenset(),
    ),
    "src/core/llm/llm_endpoints.py::<module>": (
        "2026-10-20",
        "dood",
        "de router is alleen gemonteerd door `register_routers` in `api/main.py`; de productie-ingang is `src.main:app` (scripts/entrypoint-prod.sh) en `create_test_app()` heeft geen `/api/v1/llm/chat` (gemeten 2026-10-20, zie `test_de_llm_chatroute_staat_niet_in_de_app`)",
        "src.core.llm.llm_endpoints",
        frozenset(
            {
                "src/core/api/main.py",
                "src/core/api/setup/lifecycle.py",
                "src/core/api/setup/router_registry.py",
            }
        ),
    ),
    "src/core/sandbox/doctor_agent.py::DoctorAgent._get_provider": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20); de SubagentLoader kan klassen op naam laden, NIET gemeten of dat deze klasse vindt (platform-zelfherstel, geen tenantgegevens)",
        "src.core.sandbox.doctor_agent",
        frozenset(),
    ),
    "src/core/services/ai_pack_customizer.py::AIPackCustomizer._get_llm": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.core.services.ai_pack_customizer",
        frozenset({"src/tests/integration/test_pack_intelligence.py"}),
    ),
    "src/core/services/multi_pack_assembler.py::MultiPackAssembler.suggest_multi_pack_combinations": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.core.services.multi_pack_assembler",
        frozenset({"src/tests/integration/test_pack_intelligence.py"}),
    ),
    "src/core/services/pack_template_converter.py::PackTemplateConverter.customize_template_with_llm": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.core.services.pack_template_converter",
        frozenset(
            {
                "src/core/services/ai_pack_customizer.py",
                "src/core/services/multi_pack_assembler.py",
                "src/tests/integration/test_pack_intelligence.py",
            }
        ),
    ),
    "src/core/shared/cva_llm_config.py::create_agent_llm_client": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.core.shared.cva_llm_config",
        frozenset(),
    ),
    "src/core/shared/cva_llm_config.py::create_cva_llm_client": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.core.shared.cva_llm_config",
        frozenset(),
    ),
    "src/domains/agentic/nodes/simulator_node.py::SimulatorNode.invoke": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.domains.agentic.nodes.simulator_node",
        frozenset({"src/domains/agentic/graph/experiment_builder.py"}),
    ),
    "src/domains/agentic/services/chat_service.py::AgentChatService.__init__": (
        "2026-10-20",
        "dood",
        "de enige gebruiker is src/api/v1/endpoints/agent.py (create_chat_service); die router staat niet in de app (gemeten 2026-10-20: module niet bereikbaar)",
        "src.domains.agentic.services.chat_service",
        frozenset({"src/api/v1/endpoints/agent.py", "src/core/app_factory.py"}),
    ),
    "src/domains/agentic/services/feature_router.py::FeatureContextDetector._classify_with_llm": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.domains.agentic.services.feature_router",
        frozenset(
            {
                "src/api/v1/endpoints/agent.py",
                "src/core/app_factory.py",
                "src/domains/agentic/services/chat_service.py",
            }
        ),
    ),
    "src/domains/agentic/services/prompt_mutator.py::PromptMutator.mutate_prompt": (
        "2026-10-20",
        "dood",
        "geen aanroeper in een gemonteerde route of actor: alle (transitieve) importeurs zijn zelf niet bereikbaar vanaf de app (importgraaf vanaf create_test_app, gemeten 2026-10-20)",
        "src.domains.agentic.services.prompt_mutator",
        frozenset(
            {
                "src/domains/agentic/graph/experiment_builder.py",
                "src/domains/agentic/nodes/generator_node.py",
            }
        ),
    ),
}


def _bestanden() -> list[Path]:
    uit: list[Path] = []
    for pad in sorted(SRC.rglob("*.py")):
        if "__pycache__" in pad.parts:
            continue
        relatief = pad.relative_to(REPO).as_posix()
        if relatief.startswith(VRIJGESTELDE_PAKKETTEN) and relatief not in TOCH_GESCAND:
            continue
        uit.append(pad)
    return uit


def _is_fabrieksaanroep(knoop: ast.Call) -> bool:
    functie = knoop.func
    if isinstance(functie, ast.Name):
        return functie.id in FABRIEKSNAMEN or functie.id in KLASSEN
    if isinstance(functie, ast.Attribute):
        if functie.attr in FABRIEKSNAMEN:
            return True
        if isinstance(functie.value, ast.Name):
            return (functie.value.id, functie.attr) in FABRIEK_METHODEN
    return False


def _vondsten(pad: Path) -> set[str]:
    """`bestand::functie` van elke aanroep die een model bouwt of kiest.

    Expliciete recursie met een stapel van omsluitende namen (zie ook de guard op DeepSeek): `ast.walk()`
    vanaf een functieknoop onderscheidt een geneste functie niet van zijn ouder.
    """
    relatief = pad.relative_to(REPO).as_posix()
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    gevonden: set[str] = set()

    def bezoek(knoop: ast.AST, stapel: list[str]) -> None:
        if isinstance(knoop, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            stapel = [*stapel, knoop.name]
        if isinstance(knoop, ast.Call) and _is_fabrieksaanroep(knoop):
            gevonden.add(f"{relatief}::{'.'.join(stapel) if stapel else '<module>'}")
        for kind in ast.iter_child_nodes(knoop):
            bezoek(kind, stapel)

    bezoek(boom, [])
    return gevonden


def _alle_vondsten() -> set[str]:
    uit: set[str] = set()
    for pad in _bestanden():
        uit |= _vondsten(pad)
    return uit


def _module_van(relatief: str) -> str:
    naam = relatief[:-3].replace("/", ".")
    return naam[: -len(".__init__")] if naam.endswith(".__init__") else naam


def _geimporteerd(pad: Path, boom: ast.AST) -> list[tuple[str, tuple[str, ...]]]:
    """`(module, namen)` per importstatement van dit bestand, met relatieve imports ALS absoluut."""
    relatief = pad.relative_to(REPO).as_posix()
    delen = _module_van(relatief).split(".")
    is_pakket = pad.name == "__init__.py"
    uit: list[tuple[str, tuple[str, ...]]] = []
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ImportFrom):
            if knoop.level:
                basis = delen if is_pakket else delen[:-1]
                basis = basis[: len(basis) - (knoop.level - 1)] if knoop.level > 1 else basis
                module = ".".join([*basis, *([knoop.module] if knoop.module else [])])
            else:
                module = knoop.module or ""
            uit.append((module, tuple(a.name for a in knoop.names)))
        elif isinstance(knoop, ast.Import):
            uit.extend((a.name, ()) for a in knoop.names)
    return uit


@functools.cache
def _importeurs() -> dict[str, frozenset[str]]:
    """module -> bestanden (geen `__init__.py`) die hem gebruiken, direct of via een heruitvoer in een pakket.

    Een `__init__.py` die uit een module heruitvoert telt zelf niet mee als gebruiker, maar wel een bestand dat
    een van die heruitgevoerde namen uit het PAKKET importeert (`from pakket import naam`), en `from pakket
    import submodule`. Gemeten per MODULE en niet per klassenaam: twee modules kunnen dezelfde klassenaam
    hebben (`LLMHandler` bestaat in `copilot` en in `agents/cva`).
    """
    bestanden = [
        (pad, ast.parse(pad.read_text(encoding="utf-8")))
        for pad in sorted(SRC.rglob("*.py"))
        if "__pycache__" not in pad.parts
    ]
    bekend = {_module_van(pad.relative_to(REPO).as_posix()) for pad, _ in bestanden}
    heruitvoer: dict[
        str, dict[str, set[str]]
    ] = {}  # pakket -> submodule -> namen die het heruitvoert
    for pad, boom in bestanden:
        if pad.name == "__init__.py":
            pakketnaam = _module_van(pad.relative_to(REPO).as_posix())
            for mod, namen in _geimporteerd(pad, boom):
                heruitvoer.setdefault(pakketnaam, {}).setdefault(mod, set()).update(namen)
    uit: dict[str, set[str]] = {}
    for pad, boom in bestanden:
        if pad.name == "__init__.py":
            continue
        relatief = pad.relative_to(REPO).as_posix()
        for mod, namen in _geimporteerd(pad, boom):
            doelen = {mod}
            doelen.update(f"{mod}.{naam}" for naam in namen if f"{mod}.{naam}" in bekend)
            for sub, heruitgevoerd in heruitvoer.get(mod, {}).items():
                if heruitgevoerd & set(namen):
                    doelen.add(sub)
            for doel in doelen:
                uit.setdefault(doel, set()).add(relatief)
    return {k: frozenset(v) for k, v in uit.items()}


def _aanroepers_van(module: str, eigen_bestand: str) -> frozenset[str]:
    """ALLE bestanden die deze module (transitief) gebruiken: de importeurs, hun importeurs, enzovoort.

    Transitief, omdat een pad pas dood is als ook niemand zijn importeurs aanroept: een nieuwe importeur van een
    importeur maakt het pad bereikbaar zonder dat de directe lijst verandert.
    """
    graaf = _importeurs()
    gezien: set[str] = set()
    wachtrij = [module]
    while wachtrij:
        huidig = wachtrij.pop()
        for bestand in graaf.get(huidig, ()):
            if bestand in gezien or bestand == eigen_bestand:
                continue
            gezien.add(bestand)
            wachtrij.append(_module_van(bestand))
    return frozenset(gezien)


def test_geen_model_gebouwd_langs_de_deur_om() -> None:
    nieuw = sorted(v for v in _alle_vondsten() if v not in BEKENDE_UITZONDERINGEN)

    assert nieuw == [], (
        "Een taalmodel wordt gebouwd of gekozen langs de deur om (ADR-041 B14). Een pad met tenantgegevens "
        "gebruikt `TenantTaalmodel(tenant_id)` uit `src/core/services/llm/tenant_deur.py`; een pad zonder "
        "tenantgegevens komt met een REDEN op de lijst. Gevonden: "
        f"{nieuw[:15]}"
    )


def test_de_uitzonderingslijst_is_niet_verouderd() -> None:
    gevonden = _alle_vondsten()

    verouderd = sorted(k for k in BEKENDE_UITZONDERINGEN if k not in gevonden)

    assert verouderd == [], (
        "Deze uitzonderingen vinden niets meer en horen uit de lijst (of de functienaam is veranderd): "
        f"{verouderd}"
    )


def test_elke_uitzondering_heeft_datum_categorie_en_reden() -> None:
    kaal = sorted(
        k
        for k, (datum, categorie, reden, symbool, aanroepers) in BEKENDE_UITZONDERINGEN.items()
        if not datum.startswith("20")
        or categorie not in {"systeem", "dood"}
        or len(reden.strip()) < 25
        or (categorie == "dood" and not symbool)  # geen aanroepers is een geldige uitkomst
    )

    assert kaal == []


def test_een_dood_pad_heeft_geen_nieuwe_aanroeper() -> None:
    afwijkend = {}
    for sleutel, (_datum, categorie, _reden, symbool, aanroepers) in BEKENDE_UITZONDERINGEN.items():
        if categorie != "dood" or symbool is None:
            continue
        werkelijk = _aanroepers_van(
            symbool, sleutel.split("::", 1)[0]
        )  # `symbool` is de modulenaam
        if werkelijk != aanroepers:
            afwijkend[sleutel] = sorted(werkelijk ^ aanroepers)

    assert afwijkend == {}, (
        "Een pad dat als dood is gemeten heeft een andere aanroeper dan vastgelegd; zet het eerst achter "
        f"de deur (`TenantTaalmodel`) en werk daarna de lijst bij: {afwijkend}"
    )


def test_controlegroep_de_scanner_ziet_wel_iets() -> None:
    assert len(_bestanden()) > 500
    assert len(_alle_vondsten()) > 10


#: `src/core/ai/router.py::AIRouter.route_to_model` kiest een VAST Gemini-model (`gemini-1.5-flash` of `-pro`),
#: buiten de keuze van de klant om. Gemeten 2026-10-20: de enige twee aanroepers zijn `agents/cva_agent.py` en
#: `agents/code_agent.py`, allebei dode paden (zie `BEKENDE_UITZONDERINGEN`). Komt er een aanroeper bij, dan faalt
#: deze test: het pad moet dan eerst het model van de tenant volgen.
AANROEPERS_VAN_DE_VASTE_GEMINIKEUZE = frozenset(
    {"src/core/agents/cva_agent.py", "src/core/agents/code_agent.py"}
)


def test_de_vaste_geminikeuze_van_ai_router_heeft_alleen_dode_aanroepers() -> None:
    aanroepers: set[str] = set()
    for pad in sorted(SRC.rglob("*.py")):
        relatief = pad.relative_to(REPO).as_posix()
        if "__pycache__" in pad.parts or relatief == "src/core/ai/router.py":
            continue
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        if any(
            isinstance(k, ast.Call)
            and isinstance(k.func, ast.Attribute)
            and k.func.attr == "route_to_model"
            for k in ast.walk(boom)
        ):
            aanroepers.add(relatief)

    assert aanroepers == AANROEPERS_VAN_DE_VASTE_GEMINIKEUZE, (
        "`AIRouter.route_to_model` kiest een vast Gemini-model buiten de keuze van de klant om; een nieuwe "
        f"aanroeper moet eerst het model van de tenant volgen: {sorted(aanroepers ^ AANROEPERS_VAN_DE_VASTE_GEMINIKEUZE)}"
    )


def test_de_llm_chatroute_staat_niet_in_de_app() -> None:
    """`src/core/llm/llm_endpoints.py` biedt `/api/v1/llm/chat` zonder tenant of model van de klant aan.

    Gemeten 2026-10-20: de echte app (`create_test_app()`, dezelfde fabriek als `src.main:app`) heeft die route
    niet; zonder token geven de wel aanwezige LLM-routes 401. Komt `chat` er ooit in, dan moet hij eerst via
    `TenantTaalmodel` lopen. Controlegroep: `/api/v1/llm/models` staat er wel.
    """
    from src.main import create_test_app

    paden = {getattr(r, "path", "") for r in create_test_app().routes}

    assert ("/api/v1/llm/models" in paden, "/api/v1/llm/chat" in paden) == (True, False)

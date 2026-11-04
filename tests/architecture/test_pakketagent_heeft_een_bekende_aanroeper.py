"""Alleen bekende plekken starten de skills uit de pakketcatalogus (pakketten nazorg, 2026-10-15).

Waarom deze controle bestaat. De schakelaar "pakket aan of uit voor deze klant" staat in EEN plek:
`POST /api/v1/agentic/packs/execute` (`agentic_domain_router.py`) geeft 403 `PACK_NOT_ENABLED` voor
een pakket dat uit staat. Dat is alleen een slot als elke andere manier om dezelfde agents te
starten dat slot niet kan omzeilen. Gemeten 2026-10-15: dat kan niet, want de skills uit
`config/agents` zijn alleen te instantieren via `EnterpriseCatalogLoader.get_agent_instance`, en dat
heeft in `src/` precies twee aanroepers (hieronder). De losse agentroutes (`/api/v1/agents/...`)
zoeken in de `AgentRegistry` en vinden de pakketskills daar niet (404); de supervisors voeren niets
uit (`aggregate_results([])`); `MultiPackAssembler` en `procedures/router.py` hebben geen aanroeper
of geven altijd 404.

Wat deze test bewaakt: een NIEUWE plek die een pakketskill of pakketrun kan starten valt hier op,
zodat iemand bewust beslist of de pakketschakelaar daar ook geldt. Een uitzondering staat in de
lijst met een reden. Wat telt als startpunt:

- een VERWIJZING (aanroep, alias, `to_thread(loader.get_agent_instance, ...)`, `partial`) naar een
  van `START_NAMEN`;
- een tekstconstante die een startnaam is (`getattr(loader, "get_agent_instance")`) of een modulepad
  onder `src.core.als.agents.skills.` (`importlib.import_module("...skills.dunning")`);
- een `import` uit `src.core.als.agents.skills` buiten dat pakket zelf (de klasse direct maken);
- ook `loader.py` zelf wordt gescand, en een nieuw bestand dat nog niet in git staat telt mee.

Wat deze test NIET bewaakt (benoemd, niet verzwegen): een startnaam die dynamisch wordt samengesteld
(`"get_agent" + "_instance"`, een naam uit configuratie), een andere manier om dezelfde skill te
bereiken die niet via de loader of de klasse loopt, en elke code buiten `src/` (scripts, tests). Twee
functies met dezelfde naam in een bestand delen een sleutel.

`dunning` is bewust een uitzondering: de debiteurenfunctie (Keten B) gebruikt dezelfde skill als
EIGEN klantfunctie met een eigen recht (`receivables:*`). De pakketschakelaar mag die niet
blokkeren; een klant zonder pakket `mkb.zero_admin` kan nog steeds herinneringen voorstellen.

Mutatiebewijs (kopie als terugweg, tijdelijk bestand onder `src/` met `git add -N`; NIET `tmp_*.py`,
dat staat in .gitignore en wordt dan niet gezien):
  ROOD: `loader.get_agent_instance("dunning", 1)` in een NIEUW bestand            -> failed
  ROOD: `orchestrator.run_pack_by_id(...)` in een NIEUW bestand                   -> failed
  ROOD: `get_agent_instance` in een tweede functie van `receivables/dependencies.py` -> failed
        (de sleutel is `bestand::functie`, niet het bestand)
  ROOD: alias `f = loader.get_agent_instance` zonder aanroep                      -> failed
  ROOD: `getattr(loader, "get_agent_instance")` in een NIEUW bestand              -> failed
  ROOD: `orchestrator.execute_pack(...)` in een NIEUW bestand                     -> failed
  ROOD: `from src.core.als.agents.skills.dunning import DunningSkill` (nieuw)     -> failed
  ROOD: `importlib.import_module("src.core.als.agents.skills.dunning")` (nieuw)   -> failed
  GROEN: dezelfde namen in een commentaarregel of docstring                       -> passed
  ROOD (staleness): een lijstregel waarvan de functie niet meer bestaat           -> failed
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: De namen die een pakketskill of pakketrun laten draaien.
START_NAMEN = frozenset(
    {"get_agent_instance", "run_pack", "run_pack_by_id", "execute_pack", "_execute_step"}
)

#: Skillklassen direct maken of laden buiten het pakket zelf telt ook als startpunt.
SKILL_MODULE = "src.core.als.agents.skills"
SKILL_PAKKET_MAP = "src/core/als/agents/skills/"

#: bestand::functie -> waarom die plek mag, met datum. Een uitzondering stelt de ene plek vrij.
KNOWN_AANROEPERS: dict[str, str] = {
    "src/core/als/agents/loader.py::get_agent_instance": (
        "2026-10-15: de loader zelf laadt de skillmodule op sleutel; de enige plek die dat mag"
    ),
    "src/core/als/enterprise/packs.py::_execute_step": (
        "2026-10-15: de pakketuitvoering zelf; de route staat achter PACK_NOT_ENABLED "
        "(agentic_domain_router.py, pakket aanzetten dag 1)"
    ),
    "src/core/api/v1/agentic/agentic_domain_router.py::execute_pack": (
        "2026-10-15: de enige route die een pakket start, met de schakelaar ervoor"
    ),
    "src/core/api/v1/receivables/dependencies.py::start_reminder_proposals": (
        "2026-10-15: dunning als eigen debiteurenfunctie met een eigen recht (receivables:*), "
        "geen onderdeel van de pakketschakelaar"
    ),
    "src/core/als/agents/workflow_stap.py::_heeft_skill": (
        "2026-10-24: alleen de vraag of er voor een bedrade sleutel een skillklasse bestaat (import, geen uitvoering); "
        "voert niets uit"
    ),
    "src/core/als/agents/workflow_stap.py::voer_agentstap_uit": (
        "2026-10-24: een agentstap in een workflow. De pakketschakelaar GELDT hier (`_pakket_staat_aan`, dezelfde "
        "tenant_pack_activations als PACK_NOT_ENABLED); `dunning` is een eigen klantfunctie (EIGEN_KLANTFUNCTIE) en "
        "valt er net als bij start_reminder_proposals buiten"
    ),
    "src/core/services/crediteuren_verwerking.py::_haal_agent": (
        "2026-10-24: de crediteurenagent start na een upload van een inkoopfactuur, als eigen crediteurenfunctie met een eigen "
        "recht (payables:write voor het uploaden, payables:approve voor het goedkeuren), zoals dunning; geen onderdeel van de "
        "pakketschakelaar. De start is verantwoord aan een gebruiker: zonder verantwoordelijke gebruiker doet de agent niets"
    ),
    "src/core/als/agents/loader.py::implemented_agent_keys": (
        "2026-10-15: importeert de skillmodules alleen om te vragen WELKE skills bestaan; "
        "instantieert en voert niets uit (docstring: bedoeld voor metingen en bewakers)"
    ),
    "src/core/procedures/multi_pack_assembler.py::run_procedure": (
        "2026-10-15: naamgelijkenis, een EIGEN `_execute_step` van MultiPackAssembler, niet die "
        "van DomainPackOrchestrator; de klasse heeft in src/ geen aanroeper (gemeten)"
    ),
    "src/domains/workflows/services.py::execute_workflow": (
        "2026-10-15: naamgelijkenis, een EIGEN `_execute_step` van WorkflowService (stappen via "
        "een router), niets met pakketskills te maken"
    ),
}

#: De interne ketting binnen `packs.py` (run_pack_by_id -> run_pack -> _execute_step, en het oude
#: losse pad `execute_pack` -> `_execute_with_retry` -> `_execute_single_agent`, dat in `src/`
#: geen aanroeper heeft; gemeten 2026-10-15). Ze geven door aan `_execute_step` en staan zelf niet
#: achter een schakelaar: de schakelaar zit in de route die `run_pack_by_id` aanroept. Een NIEUWE
#: functie in dit bestand die een startnaam raakt valt wel op.
INTERNE_DOORGIFTE = frozenset(
    f"src/core/als/enterprise/packs.py::{naam}"
    for naam in (
        "run_pack_by_id",
        "run_pack",
        "execute_pack",
        "_execute_with_retry",
        "_execute_single_agent",
        "_run_single_step",
        "uitvoeren",
    )
)


def _bronbestanden() -> list[str]:
    """Alle `.py` onder `src/`, ook nieuwe bestanden die nog niet in git staan (`-co`)."""
    uit = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "src"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return sorted(
        {
            f
            for f in uit
            if f.endswith(".py") and not f.startswith("src/tests/") and (REPO / f).is_file()
        }
    )


def _is_startpunt(knoop: ast.AST, pad: str) -> bool:
    if isinstance(knoop, ast.Attribute):
        return knoop.attr in START_NAMEN
    if isinstance(knoop, ast.Name):
        return knoop.id in START_NAMEN
    if isinstance(knoop, ast.Constant) and isinstance(knoop.value, str):
        tekst = knoop.value
        if tekst in START_NAMEN:
            return True
        return tekst.startswith(SKILL_MODULE + ".") and not pad.startswith(SKILL_PAKKET_MAP)
    if isinstance(knoop, ast.ImportFrom):
        module = knoop.module or ""
        return module.startswith(SKILL_MODULE) and not pad.startswith(SKILL_PAKKET_MAP)
    return False


def _aanroepen(pad: str) -> set[str]:
    """`bestand::functie` van elk startpunt; expliciete recursie per functie.

    `ast.walk` vanaf een functieknoop onderscheidt een geneste functie niet van zijn ouder
    (zie quality-gates.md, aanscherping 2026-09-18), dus de omsluitende functie wordt bijgehouden.
    Een docstring of commentaar is geen `ast.Name`, `ast.Attribute` of aparte tekstconstante van
    deze vorm; de docstring zelf is wel een `ast.Constant` maar is nooit exact een startnaam of een
    modulepad, dus hij telt niet mee.
    """
    boom = ast.parse((REPO / pad).read_text(encoding="utf-8", errors="replace"))
    gevonden: set[str] = set()

    def bezoek(knoop: ast.AST, functie: str) -> None:
        for kind in ast.iter_child_nodes(knoop):
            naam = functie
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                naam = kind.name
            if _is_startpunt(kind, pad):
                gevonden.add(f"{pad}::{functie or '<module>'}")
            bezoek(kind, naam)

    bezoek(boom, "")
    return gevonden


def _gevonden() -> set[str]:
    sleutels: set[str] = set()
    for pad in _bronbestanden():
        sleutels |= _aanroepen(pad)
    return sleutels - INTERNE_DOORGIFTE


def test_de_scan_ziet_de_bron() -> None:
    """Een lege bestandslijst laat de tests hieronder groen zonder iets te meten."""
    assert len(_bronbestanden()) > 1000


def test_de_scan_vindt_de_bekende_aanroepers() -> None:
    """Zonder dit kan een scan die niets vindt als 'geen nieuwe aanroepers' doorgaan."""
    assert set(KNOWN_AANROEPERS) <= _gevonden()


def test_er_zijn_geen_nieuwe_aanroepers_van_een_pakketskill() -> None:
    """Een nieuwe plek die een pakketskill of pakketrun start valt hier op."""
    nieuw = sorted(_gevonden() - set(KNOWN_AANROEPERS))
    assert not nieuw, (
        f"Nieuwe startpunten van een pakketskill ({sorted(START_NAMEN)} of een import uit "
        f"{SKILL_MODULE}): {nieuw}. Geldt de pakketschakelaar (PACK_NOT_ENABLED, "
        "agentic_domain_router.py) ook daar? Zo ja, zet de controle erin; zo nee, voeg de plek "
        "toe aan KNOWN_AANROEPERS met een reden en een datum."
    )


def test_een_uitzondering_die_niet_meer_bestaat_moet_uit_de_lijst() -> None:
    """Anders rot de lijst dicht en stelt hij een plek vrij die er niet meer is."""
    gevonden = _gevonden()
    verouderd = sorted(k for k in KNOWN_AANROEPERS if k not in gevonden)
    assert not verouderd, f"Staat in KNOWN_AANROEPERS maar wordt niet meer gevonden: {verouderd}"

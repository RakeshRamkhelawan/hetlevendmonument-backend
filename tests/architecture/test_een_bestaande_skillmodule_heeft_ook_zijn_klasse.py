"""Een skillmodule die bestaat MOET ook de klasse opleveren die de loader erin zoekt.

Achtergrond (2026-09-25). ``config/agents/mkb_admin_lite_dunningagent.yaml`` had
``class_name: "DunningAgentAgent"`` -- een dubbel achtervoegsel. De loader leidt daaruit
de sleutel ``dunning`` af (``.replace("agent", "")`` haalt BEIDE weg), vindt
``skills/dunning.py``, zoekt daarin ``DunningSkillSkill``, krijgt een ``AttributeError``
en valt terug op ``BaseSpecialistAgent``. Een volledig werkende skill werd daardoor nooit
geladen, en het enige spoor was een ``logger.debug``. Zie BE-AGT-068.

Deze bewaker doet wat de loader doet: hij IMPORTEERT de module en vraagt de klasse op met
``getattr``. Een eerdere versie las de klassen met ``ast.walk`` uit de broncode; dat is
TEKST waar STRUCTUUR hoort en week in twee richtingen af van ``getattr`` -- het vond een
klasse die in een functiebody genest zat (loader valt dan alsnog terug) en het miste een
re-export of alias op moduleniveau (loader slaagt dan juist). Zie
``.claude/rules/quality-gates.md`` en ``valkuil_ast_walk_duikt_functiebodies_in``.

Bereik, gemeten 2026-09-25: de bewaker bekijkt alleen configuraties waarvan de MODULE
bestaat. Dat zijn er 135, alle in de PLATTE configuratievorm -- geen enkele geneste
configuratie heeft vandaag een skillmodule, dus de geneste tak van ``_class_name_uit``
staat er voor toekomstige configuraties en is NIET door een mutatie gedekt. De 151
configuraties zonder module vallen er bewust buiten: dat is een andere kwestie (een
catalogusvermelding zonder implementatie) en een bewaker daarop zou vandaag per definitie
rood staan en elke merge stilleggen.

Mutatiebewijs (2026-09-25), in beide richtingen:
  voorwaarts -- ``class_name`` terug op ``DunningAgentAgent``: ROOD.
  voorwaarts -- ``DunningSkill`` hernoemd in ``skills/dunning.py``: ROOD.
  voorwaarts -- ``DunningSkill`` genest in een functiebody (de ast.walk-blindheid): ROOD.
  voorwaarts -- ``SKILLS_DIR`` naar een niet-bestaande map (zelfcontrole): ROOD.
  tegen      -- een configuratie zonder skillmodule toegevoegd: GROEN (hij mag niet
                verworden tot "elke configuratie moet een implementatie hebben").
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from src.core.als.agents.loader import EnterpriseCatalogLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config" / "agents"
SKILLS_DIR = REPO_ROOT / "src" / "core" / "als" / "agents" / "skills"

# Gemeten 2026-09-25: 135 configuraties hebben een bestaande skillmodule. De ondergrens
# ligt bewust lager zodat gewone opruiming hem niet raakt, en hoog genoeg dat een bewaker
# die per ongeluk niets meer bekijkt rood wordt in plaats van groen.
MINIMAAL_GECONTROLEERD = 100


def _class_name_uit(pad: Path) -> str:
    """Leidt class_name af zoals de loader dat doet, voor beide configuratievormen.

    Geen ``errors="ignore"``: deze repo is ASCII-only, dus die vlag kan hier niets redden
    en wel iets verbergen -- weggegooide bytes zouden een lege class_name opleveren en de
    configuratie zou stil uit de telling verdwijnen.
    """
    raw = yaml.safe_load(pad.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return ""
    if "agent_id" in raw:
        return str(raw.get("class_name") or "").strip()
    agent = raw.get("agent") or {}
    technical = raw.get("technical") or {}
    return str(agent.get("name") or technical.get("class_name") or "").strip()


def _configuraties() -> list[Path]:
    """Dezelfde achtervoegsels als ``AgentLoader._load_agents``: .yaml EN .yml."""
    return sorted([*CONFIG_DIR.glob("*.yaml"), *CONFIG_DIR.glob("*.yml")])


@pytest.mark.architecture
def test_elke_bestaande_skillmodule_levert_de_klasse_die_de_loader_zoekt() -> None:
    gemist: list[str] = []
    gecontroleerd = 0

    for pad in _configuraties():
        class_name = _class_name_uit(pad)
        if not class_name:
            continue

        # Exact de afleidingen uit loader.get_agent_instance -- AANGEROEPEN, niet
        # nagebouwd, zodat een wijziging daar deze bewaker meeneemt in plaats van hem
        # stil op de oude regel te laten toetsen.
        sleutel = EnterpriseCatalogLoader._normalize_agent_key(class_name)
        verwacht = EnterpriseCatalogLoader._skill_class_name(class_name)

        if not (SKILLS_DIR / f"{sleutel}.py").exists():
            continue
        gecontroleerd += 1

        module_naam = f"src.core.als.agents.skills.{sleutel}"
        try:
            module = importlib.import_module(module_naam)
        except ImportError as exc:
            gemist.append(
                f"{pad.name}: module '{module_naam}' bestaat als bestand maar is niet te "
                f"importeren ({type(exc).__name__}: {exc}). De loader valt hier terug op "
                f"BaseSpecialistAgent."
            )
            continue

        if getattr(module, verwacht, None) is None:
            gemist.append(
                f"{pad.name}: class_name '{class_name}' -> module '{module_naam}' bestaat, "
                f"maar levert geen '{verwacht}' op. De loader valt hier terug op "
                f"BaseSpecialistAgent."
            )

    assert gecontroleerd >= MINIMAAL_GECONTROLEERD, (
        f"De bewaker controleerde {gecontroleerd} configuraties, minder dan de ondergrens "
        f"{MINIMAAL_GECONTROLEERD}. Gemeten stand op 2026-09-25 was 135. Zo weinig betekent "
        f"dat CONFIG_DIR, SKILLS_DIR of het configuratieschema is veranderd -- zoek dat uit "
        f"voordat je dit getal aanpast."
    )
    assert not gemist, "Skillmodule bestaat maar levert zijn klasse niet:\n  " + "\n  ".join(gemist)

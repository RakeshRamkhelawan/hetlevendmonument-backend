"""Elk ORM-model staat in de centrale registratie (ADR-036 OP-147).

`src/core/database/import_all_models.py` is de plek waar elk model wordt geimporteerd zodat het
in `Base.metadata` terechtkomt. Staat een module daar niet in, dan is het model voor het hele
platform onzichtbaar op drie manieren tegelijk:

1. **`Base.metadata.create_all` maakt de tabel niet aan.** Elke testboom bouwt zo zijn schema,
   dus een test die het model gebruikt faalt met "no such table" -- tenzij een ander bestand
   het model toevallig al had geimporteerd. Dat maakt het foutbeeld volgordeafhankelijk.
2. **`alembic revision --autogenerate` ziet de tabel als OVERBODIG** en emitteert een `DROP`.
   Dat is niet theoretisch: precies zo zijn `tenants.prana_budget` en `prana_spent` ooit
   verdwenen (OP-140), en zonder deze guard was dat bij het opstellen van de baseline-migratie
   opnieuw gebeurd -- voor `skills`, `employee_skills` en `role_required_skills`.
3. **De driftmeting van OP-140 telt te laag.** `Base.metadata` is dan zelf incompleet, dus
   "modellen min keten" onderschat wat er ontbreekt.

**Gemeten 2026-08-17.** Vier modellen stonden niet in de registratie:
`skills`, `employee_skills`, `role_required_skills` (`src/core/models/hr_skills_models.py`, uit
BE-AGT-046) en `agent_twin_consent_events` (`src/core/api/v1/digital_twin/models.py`). Na
registratie ging `Base.metadata` van 182 naar 186 tabellen.

**Waarom dit onopgemerkt bleef.** In BE-AGT-046 is het symptoom omzeild in plaats van de
oorzaak opgelost: `tests/unit/tool_broker/test_hr_skill_gap.py` importeert de modellen op
MODULENIVEAU, met een comment dat `create_all` alleen ziet wat al geimporteerd is. Die omweg
werkte, dus niemand zocht verder. Deze guard vindt de oorzaak.

**Mutatiebewijs (2026-08-17), beide richtingen:**
- `import src.core.models.hr_skills_models` uit `import_all_models.py` gehaald -> ROOD met de
  drie tabelnamen en het bronbestand in de melding.
- `import src.core.api.v1.digital_twin.models` eruit -> ROOD met `agent_twin_consent_events`.
- Andere richting: ongewijzigd GROEN, en `test_the_guard_finds_real_models` bewijst dat de
  scan daadwerkelijk modellen vindt -- een lege scan maakt de eerste test trivially groen.

**Addendum 2026-09-02.** `agent_twin_consent_events` is verplaatst naar
`src/core/models/digital_twin_models.py`. De registratie in `import_all_models.py` stond op
`src.core.api.v1.digital_twin.models` (infra-laag importeert API-laag) -- een schending van
het `.importlinter`-contract "Infrastructuurlaag mag niet API-laag importeren" die zes weken
onopgemerkt bleef omdat geen enkele architecture-guard dat specifieke contract bewaakte. Deze
guard zelf hardcodeert geen pad (scant `__tablename__`/`Table(...)` generiek), dus de verplaatsing
raakt zijn logica niet -- alleen de historische padvermeldingen hierboven zijn nu gedateerd.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"

_TABLENAME = re.compile(r"__tablename__\s*=\s*[\"'](\w+)[\"']")

# Gedateerd 2026-08-17, reden per regel. Alleen namen die GEEN echt model zijn.
KNOWN_NOT_A_MODEL: dict[str, str] = {
    "my_table": (
        "voorbeeld in de docstring van `SoftDeleteMixin` (`src/core/database/soft_delete.py`), "
        "geen klasse die van Base erft"
    ),
}


def _table_calls(tekst: str) -> list[str]:
    """Tabellen die via `Table("naam", metadata, ...)` zijn gedefinieerd.

    De regex op `__tablename__` ziet die vorm NIET -- gemeten 2026-08-17: `user_roles`
    (`src/core/models/rbac_models.py`) staat wel in `Base.metadata` maar viel buiten de scan.
    Een niet-geregistreerde koppeltabel zou dus onzichtbaar zijn voor deze guard, precies de
    "TEKST doorzoeken waar STRUCTUUR getoetst moet worden"-vorm die
    `.claude/rules/quality-gates.md` beschrijft (Gate 2-review, ronde 1).
    """
    try:
        boom = ast.parse(tekst)
    except SyntaxError:
        return []
    namen: list[str] = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call) or not knoop.args:
            continue
        functie = knoop.func
        naam = functie.attr if isinstance(functie, ast.Attribute) else getattr(functie, "id", "")
        if naam != "Table":
            continue
        eerste = knoop.args[0]
        if isinstance(eerste, ast.Constant) and isinstance(eerste.value, str):
            namen.append(eerste.value)
    return namen


def _tablenames_in_src() -> tuple[dict[str, str], list[str]]:
    """(elke tabelnaam in `src/` met het bestand waarin hij staat, onleesbare paden).

    Bewust GEEN import van de modules: een module die niet geimporteerd WORDT is juist wat
    deze guard zoekt. `src/alembic/` valt erbuiten -- dat zijn migraties, geen modellen.

    Twee vormen, want een model kan op twee manieren een tabel declareren: een klasse met
    `__tablename__`, en een losse `Table(...)`-aanroep (koppeltabellen).
    """
    gevonden: dict[str, str] = {}
    fouten: list[str] = []
    for pad in _SRC.rglob("*.py"):
        if "alembic" in pad.parts:
            continue
        try:
            tekst = pad.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError as exc:
            fouten.append(f"{pad.relative_to(_REPO_ROOT).as_posix()}: {exc}")
            continue
        bron = pad.relative_to(_REPO_ROOT).as_posix()
        for naam in _TABLENAME.findall(tekst):
            gevonden.setdefault(naam.lower(), bron)
        for naam in _table_calls(tekst):
            gevonden.setdefault(naam.lower(), bron)
    return gevonden, fouten


def _geregistreerde_tabellen() -> set[str]:
    from src.core.database import import_all_models  # noqa: F401
    from src.core.database.database import Base

    return {naam.lower() for naam in Base.metadata.tables}


@pytest.mark.unit
class TestEveryModelReachesTheMetadata:
    def test_no_model_is_missing_from_import_all_models(self) -> None:
        """Een model dat niet geregistreerd is, is onzichtbaar voor tests EN voor Alembic."""
        in_src, _fouten = _tablenames_in_src()
        ontbreekt = {
            naam: bron
            for naam, bron in in_src.items()
            if naam not in _geregistreerde_tabellen() and naam not in KNOWN_NOT_A_MODEL
        }

        assert not ontbreekt, (
            "Deze modellen staan niet in `src/core/database/import_all_models.py`:\n"
            + "\n".join(f"  - {naam:38} {bron}" for naam, bron in sorted(ontbreekt.items()))
            + "\n\nGevolg: `create_all` maakt de tabel niet aan (tests falen "
            "volgordeafhankelijk) en `alembic autogenerate` ziet hem als overbodig en emitteert "
            "een DROP. Voeg de module toe aan de registratie."
        )


@pytest.mark.unit
class TestTheGuardMeasuresSomething:
    def test_the_guard_finds_real_models(self) -> None:
        """De tweede richting: een lege scan maakt de test hierboven trivially groen."""
        in_src, _fouten = _tablenames_in_src()

        assert len(in_src) >= 150, (
            f"Slechts {len(in_src)} `__tablename__`-definities gevonden in {_SRC}. Op "
            "2026-08-17 waren het er 186. Is de map verplaatst, of leest de scan iets anders?"
        )
        assert len(_geregistreerde_tabellen()) >= 150, (
            f"Slechts {len(_geregistreerde_tabellen())} tabellen in `Base.metadata`. Laadt "
            "`import_all_models` wel alles?"
        )

    def test_no_source_file_is_silently_unreadable(self) -> None:
        """Vangnet: een onleesbaar modelbestand mag de scan niet blind maken.

        De totaaldrempel hierboven (>=150) beschermt alleen tegen totale leegloop -- die
        wordt door de ~185 gezonde bestanden altijd gehaald. Het ene onleesbare bestand
        zou daardoor NOOIT gemeld worden als niet-geregistreerd, precies het defect dat
        deze guard moet vangen (zie test_no_model_is_missing_from_import_all_models).
        """
        _, fouten = _tablenames_in_src()
        assert not fouten, (
            "Deze bestanden onder src/ konden niet gelezen worden en zijn NIET "
            "gecontroleerd op een niet-geregistreerd model:\n"
            + "\n".join(f"  - {f}" for f in fouten)
        )

    def test_the_table_call_branch_is_load_bearing(self) -> None:
        """De AST-tak vindt iets dat de regex NIET vindt.

        Zonder deze test kan iemand `_table_calls` weghalen zonder dat er iets rood wordt: de
        regex dekt 185 van de 186 tabellen, dus de eerste test blijft groen. Gemeten
        2026-08-17: `user_roles` staat in `Base.metadata` maar heeft geen `__tablename__` --
        het is een `Table(...)`-koppeltabel. Dat is precies het gat waardoor een
        niet-geregistreerde koppeltabel onzichtbaar zou blijven.

        Een mutatietest was hier ongeldig: de `Table(`-aanroep hernoemen breekt de import van
        de module (NameError), dus dan meet je iets anders dan de guard.
        """
        bron = (_SRC / "core" / "models" / "rbac_models.py").read_text(encoding="utf-8-sig")

        via_regex = {n.lower() for n in _TABLENAME.findall(bron)}
        via_ast = {n.lower() for n in _table_calls(bron)}

        assert "user_roles" in via_ast, (
            "De AST-tak vindt `user_roles` niet meer. Is de vorm van de koppeltabel veranderd?"
        )
        assert "user_roles" not in via_regex, (
            "De regex vindt `user_roles` nu wel -- dan is deze test niet meer dragend en moet "
            "hij worden herzien in plaats van blijven staan."
        )
        assert "user_roles" in _geregistreerde_tabellen()

    def test_the_known_exception_is_not_stale(self) -> None:
        """Een uitzondering die geen `__tablename__` meer is, MOET uit de lijst."""
        in_src, _fouten = _tablenames_in_src()
        verdwenen = sorted(naam for naam in KNOWN_NOT_A_MODEL if naam not in in_src)

        assert not verdwenen, (
            f"Deze namen komen niet meer voor in `src/`: {verdwenen}. Haal ze uit "
            "KNOWN_NOT_A_MODEL."
        )

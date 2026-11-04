"""Benoemde kolommen bestaan aan het EIND van de migratieketen (SP-COUNCIL-GATE-001).

Aanleiding, gemeten 2026-08-15. Beide Gate 2-reviewers wezen dezelfde goedkoopste vals-groene
route aan: voeg een kolom toe aan een SQLAlchemy-model en sla de migratie over. Alle testbomen
bouwen hun schema met `Base.metadata.create_all` (`tests/fixtures/database.py:120`,
`tests/integration/conftest.py:231`), dus die zien de nieuwe kolom meteen. Staging en productie
draaien `alembic upgrade head` en krijgen daar een `UndefinedColumn`. Precies dat is met
`prana_budget`/`prana_spent` gebeurd: de migratie die ze aanmaakte staat in `archive/`, en
`a10bd0ad9807` liet ze door een autogenerate vallen.

**Waarom een NAAMLIJST en geen automatische vergelijking.** `alembic check` zou het volledige
gat afdekken maar is vandaag geen begaanbare poort: gemeten tegen een verse PostgreSQL na
`upgrade head` staan er 104 modeltabellen die de keten niet aanmaakt, 62 ontbrekende kolommen
en 22 kolommen die alleen in de database bestaan. Die schuld is repo-breed en heeft een eigen
registratie (ADR-036 OP-140). Een guard die daarop faalt zou elke merge blokkeren; een guard
over een expliciet genoemde verzameling blokkeert niets en bewaakt wel wat we toevoegen.

**Hoe hij meet.** Hij draait de HELE keten in offline-modus (`alembic upgrade head --sql`) in
een SUBPROCES en leest de DDL die daar uit komt. Drie eigenschappen die er los van elkaar toe
doen:

1. **Uitvoer, geen broncode.** `op.add_column`, `op.create_table` en raw SQL via `op.execute`
   tellen alle drie mee, en een migratie in `archive/` telt per definitie niet mee.
2. **EINDtoestand, niet 'komt ergens voor'.** De DDL wordt op volgorde gelezen en
   `ADD COLUMN` / `DROP COLUMN` / `DROP TABLE` worden verrekend. Een keten die de kolom
   toevoegt en later weer laat vallen is ROOD -- dat is geen theorie, `archive/a10bd0ad9807`
   doet precies die drop op `tenants.prana_spent`.
3. **Subproces met returncode-controle.** In de volledige suite (`-n 4`, 15.642 tests) gaf de
   eerste versie -- die alembic in-process draaide met `contextlib.redirect_stdout` -- drie
   errors die los en in kleinere combinaties niet reproduceerden. Een subproces heeft geen
   gedeelde stdout, geen gedeelde werkmap en geen gedeelde alembic-logconfiguratie. De
   returncode wordt EXPLICIET getoetst: een guard die die negeert, ziet bij een fout een lege
   uitvoer en wordt stil groen (gedocumenteerde valkuil in `.claude/rules/quality-gates.md`).

**Mutatiebewijs (2026-08-15/16), een regel per element van de verzameling:**
- `prana_budget` uit `20260815_tenant_prana_budget.py` gehaald -> ROOD op die kolom.
- `prana_spent` uit diezelfde migratie gehaald -> ROOD op die kolom.
- De hele migratie naar `archive/` verplaatst -> ROOD op beide.
- Een `op.drop_column("tenants", "prana_spent")` in een latere migratie -> ROOD op die kolom
  (bewijst eigenschap 2; de eerste versie bleef hier groen).
- Een `ALTER TABLE public.tenants DROP COLUMN prana_budget` (schema-gekwalificeerd) -> ROOD;
  zonder de naamnormalisatie bleef de guard hier groen (Gate 2-ronde 3, gemeten).
- Andere richting: met de migratie op zijn plek GROEN, dus "eis altijd rood" is geen oplossing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Expliciet benoemd, met de reden per regel. Uitbreiden zodra een kolom die de PRODUCTIECODE
# leest niet vanzelfsprekend in de keten staat -- niet als algemene schemaspiegel.
NAMED_COLUMNS: dict[tuple[str, str], str] = {
    ("tenants", "prana_budget"): (
        "PranaGuard.check_budget leest deze kolom; hij stond alleen in archive/698adff2b1af"
    ),
    ("tenants", "prana_spent"): (
        "PranaGuard.charge_prana schrijft deze kolom; idem -- ADR-036 D3/D7, OP-139"
    ),
}

_ADD = re.compile(r"\bALTER\s+TABLE\s+([\w.]+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE)
_DROP_COL = re.compile(
    r"\bALTER\s+TABLE\s+([\w.]+)\s+DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(\w+)", re.IGNORECASE
)
_DROP_TABLE = re.compile(r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w.]+)", re.IGNORECASE)
_CREATE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.]+)\s*\(", re.IGNORECASE)


def _offline_ddl() -> str:
    """De DDL van de volledige keten, gegenereerd in een subproces zonder database."""
    omgeving = dict(os.environ)
    # Offline-modus maakt geen verbinding; de URL bepaalt alleen het dialect. Expliciet zetten
    # zodat de test niet afhangt van een .env die in een git-worktree ontbreekt.
    omgeving["DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost:5432/offline"
    resultaat = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", "upgrade", "head", "--sql"],
        cwd=_REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert resultaat.returncode == 0, (
        "`alembic upgrade head --sql` faalde met returncode "
        f"{resultaat.returncode}. Zonder deze controle zou de guard een lege uitvoer krijgen "
        f"en stil groen worden.\n--- stderr ---\n{resultaat.stderr[-3000:]}"
    )
    return resultaat.stdout


def _eindtoestand(ddl: str) -> set[tuple[str, str]]:
    """De kolommen die na de HELE keten nog bestaan, in volgorde verrekend.

    Alleen `ALTER TABLE ... ADD COLUMN` en de CREATE TABLE-vorm worden geteld; drops halen ze
    er weer af. Zo betrapt de guard een kolom die wordt toegevoegd en later weer verdwijnt --
    precies wat er met `prana_spent` is gebeurd.
    """
    def _tab(naam: str) -> str:
        """`public.tenants` en `tenants` zijn dezelfde tabel.

        Gate 2-ronde 3 maat dit na: zonder deze normalisatie bleef de guard GROEN bij een
        `ALTER TABLE public.tenants DROP COLUMN prana_budget`, terwijl de kolom weg was.
        """
        return naam.rsplit(".", 1)[-1].lower()

    aanwezig: set[tuple[str, str]] = set()
    for tekst in ddl.split(";"):
        for tabel, kolom in _ADD.findall(tekst):
            aanwezig.add((_tab(tabel), kolom.lower()))
        for tabel, kolom in _DROP_COL.findall(tekst):
            aanwezig.discard((_tab(tabel), kolom.lower()))
        for (tabel,) in ((t,) for t in _DROP_TABLE.findall(tekst)):
            aanwezig = {(tb, kl) for tb, kl in aanwezig if tb != _tab(tabel)}
        creatie = _CREATE.search(tekst)
        if creatie:
            tabel = _tab(creatie.group(1))
            # Binnen een CREATE TABLE is elke regel die met een naam begint een kolom.
            binnenkant = tekst[creatie.end() :]
            for regel in binnenkant.split(","):
                naam = regel.strip().split()
                if naam and re.fullmatch(r"\w+", naam[0]):
                    aanwezig.add((tabel, naam[0].lower()))
    return aanwezig


@pytest.fixture(scope="module")
def kolommen() -> set[tuple[str, str]]:
    ddl = _offline_ddl()
    assert len(ddl) > 10_000, (
        f"De offline-uitvoer is maar {len(ddl)} tekens. De keten heeft niet gedraaid en dan "
        "toetst deze guard niets -- dit is de vacuum-vorm waar "
        ".claude/rules/quality-gates.md voor waarschuwt."
    )
    eind = _eindtoestand(ddl)
    assert len(eind) > 200, (
        f"Slechts {len(eind)} kolommen uit de DDL gelezen. De parser leest de uitvoer niet "
        "zoals verwacht; dan zegt een negatieve uitkomst niets."
    )
    return eind


@pytest.mark.unit
class TestEveryNamedColumnSurvivesTheChain:
    @pytest.mark.parametrize(("tabel", "kolom"), sorted(NAMED_COLUMNS))
    def test_the_column_exists_after_the_last_migration(
        self, kolommen: set[tuple[str, str]], tabel: str, kolom: str
    ) -> None:
        """Elk element van de verzameling krijgt zijn eigen regel -- en zijn eigen mutatie."""
        assert (tabel, kolom) in kolommen, (
            f"`alembic upgrade head` levert {tabel}.{kolom} niet op. Reden dat deze kolom "
            f"bewaakt wordt: {NAMED_COLUMNS[(tabel, kolom)]}. Let op: hij kan ook zijn "
            "toegevoegd en later weer gedropt -- deze guard toetst de EINDtoestand. De "
            "unittests slagen hier wel doorheen (create_all), staging en productie niet."
        )


@pytest.mark.unit
class TestTheGuardCannotPassOnAnAbsentColumn:
    def test_a_column_that_does_not_exist_is_not_found(
        self, kolommen: set[tuple[str, str]]
    ) -> None:
        """De andere richting: de parser mag niet alles 'aanwezig' verklaren."""
        assert ("tenants", "kolom_die_niet_bestaat") not in kolommen

    def test_a_table_that_does_not_exist_is_not_found(self, kolommen: set[tuple[str, str]]) -> None:
        """Een kolomnaam die wel bestaat maar in een ANDERE tabel telt niet mee."""
        assert ("tabel_die_niet_bestaat", "prana_budget") not in kolommen

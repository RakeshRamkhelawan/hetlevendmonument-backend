"""Elke tabel met klantgegevens krijgt Row Level Security in een migratie (brief 2026-10-21, ADR-036 OP-151).

**Waarom dit een tweede guard is.** `tests/integration/security/test_the_application_role_is_confined_to_its_tenant.py`
toetst hetzelfde tegen een ECHTE database, maar bouwt daarvoor de hele migratieketen en draait niet in de
testpoort. Een nieuwe tabel met een `tenant_id` zonder RLS zou dus pas bij een handmatige integratierun opvallen.
Deze guard draait zonder database.

**Wat hij meet.** Elke ORM-tabel met een `tenant_id` (of `contributed_by_tenant_id`) moet voorkomen in een migratie
die Row Level Security aanzet: als woord in een SQL-tekst met `ROW LEVEL SECURITY` of `CREATE POLICY`, of als
tekenreeks in een lijst in zo'n migratie (migraties die per tabel in een lus werken). Docstrings tellen niet mee en
`downgrade()` ook niet: een tabel die alleen in de terugweg genoemd wordt, heeft vooruit geen RLS.

**Wat hij NIET meet.** Dat de policy de JUISTE vorm heeft (dat doen de gedragstests van de integratietest) en
tabellen die alleen in een migratie bestaan en niet in een model. Gemeten op 2026-10-21 (8fdb38cb): 180
ORM-tabellen met een tenantkolom, 179 gedekt, alleen `audit_logs` niet (bewust, zie `KNOWN_ZONDER_RLS`).
Sinds 2026-10-24 (`20261024_audit_leesregel`) is ook `audit_logs` gedekt en is de uitzonderingslijst leeg.

**Mutatiebewijs:** `TestDeMeting` voert de meetfunctie uit op tijdelijke migratiebestanden, per element in beide
richtingen: RLS in `upgrade` -> gedekt; alleen in `downgrade`, alleen in een docstring of alleen als commentaar ->
NIET gedekt; een lijstgedreven migratie -> gedekt; een tabel zonder enige vermelding -> NIET gedekt.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VERSIES = REPO / "src" / "alembic" / "versions"

TENANTKOLOMMEN = ("tenant_id", "contributed_by_tenant_id")

#: Tabellen met een tenantkolom die BEWUST geen RLS hebben, met reden.
#: Leeg sinds migratie `20261024_audit_leesregel` (ADR-036 OP-246): `audit_logs` kreeg een leesregel per klant
#: en een open schrijfregel. Een nieuwe uitzondering vraagt een reden van minstens 25 tekens.
KNOWN_ZONDER_RLS: dict[str, str] = {}

#: Alleen `ENABLE`: `DISABLE ROW LEVEL SECURITY` en een kale `CREATE POLICY` (die niets doet zolang RLS niet
#: aanstaat) tellen niet als dekking (Gate 2 ronde 1, F8).
_RLS_AAN = re.compile(r"\bENABLE ROW LEVEL SECURITY\b", re.IGNORECASE)


def _orm_tenanttabellen() -> set[str]:
    from src.core.database import import_all_models  # noqa: F401
    from src.core.database.database import Base

    return {
        naam
        for naam, tabel in Base.metadata.tables.items()
        if any(kolom in tabel.columns for kolom in TENANTKOLOMMEN)
    }


def _tekenreeksen_vooruit(pad: Path) -> tuple[set[str], list[str]]:
    """(tekenreeksen in lijsten/tupels/sets/dict-sleutels, SQL-tekenreeksen met ENABLE RLS).

    Beide buiten docstrings en `downgrade()`. Een tabelnaam telt alleen als hij in zo'n SQL-tekenreeks staat of
    als ELEMENT van een lijst: een `op.create_table("x")` of een kolomnaam is een aanroepargument en telt niet
    (Gate 2 ronde 1, F7: eerder dekte een RLS-regel op een tabel elke andere tabelnaam in hetzelfde bestand).
    """
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    uitgesloten: set[int] = set()
    for knoop in ast.walk(boom):
        if isinstance(knoop, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            eerste = knoop.body[0] if knoop.body else None
            if (
                isinstance(eerste, ast.Expr)
                and isinstance(eerste.value, ast.Constant)
                and isinstance(eerste.value.value, str)
            ):
                uitgesloten.add(id(eerste.value))
        if isinstance(knoop, ast.FunctionDef) and knoop.name == "downgrade":
            uitgesloten.update(id(k) for k in ast.walk(knoop))

    def _tekst(k: ast.AST | None) -> str | None:
        if isinstance(k, ast.Constant) and isinstance(k.value, str) and id(k) not in uitgesloten:
            return k.value
        return None

    # Modulevariabelen met een tekenreeks (`_TABEL = "x"`): migraties noemen hun tabel zo en zetten RLS aan
    # met een f-string. Zo'n constante telt alleen als haar NAAM in een f-string met ENABLE RLS voorkomt.
    constanten: dict[str, str] = {}
    for knoop in boom.body:
        if (
            isinstance(knoop, ast.Assign)
            and len(knoop.targets) == 1
            and isinstance(knoop.targets[0], ast.Name)
            and isinstance(knoop.value, ast.Constant)
            and isinstance(knoop.value.value, str)
        ):
            constanten[knoop.targets[0].id] = knoop.value.value

    in_lijst: set[str] = set()
    sql: list[str] = []
    for k in ast.walk(boom):
        if id(k) in uitgesloten:
            continue
        if isinstance(k, (ast.List, ast.Tuple, ast.Set)):
            in_lijst.update(t for t in map(_tekst, k.elts) if t)
            # `_RLS_TABELLEN = (_RUNS, _AANNAMES)`: elementen die naar een tekenreeksconstante verwijzen.
            in_lijst.update(
                constanten[e.id] for e in k.elts if isinstance(e, ast.Name) and e.id in constanten
            )
        elif isinstance(k, ast.Dict):
            in_lijst.update(t for t in map(_tekst, k.keys) if t)
        elif isinstance(k, ast.JoinedStr):
            if any(_RLS_AAN.search(t) for t in map(_tekst, k.values) if t):
                for naam in (n for v in k.values for n in ast.walk(v) if isinstance(n, ast.Name)):
                    if naam.id in constanten:
                        in_lijst.add(constanten[naam.id])
        elif isinstance(k, ast.Call):
            # Een hulpfunctie als `_enable_rls("tabel", "policy")`: de letterlijke argumenten zijn de tabel.
            functie = k.func.id if isinstance(k.func, ast.Name) else getattr(k.func, "attr", "")
            if "rls" in functie.lower():
                in_lijst.update(t for t in map(_tekst, k.args) if t)
        tekst = _tekst(k)
        if tekst is not None and _RLS_AAN.search(tekst):
            sql.append(tekst)
    return in_lijst, sql


def gedekte_tabellen(orm_tabellen: set[str], versies: Path) -> set[str]:
    """De ORM-tabellen die in een RLS-migratie (vooruit) voorkomen."""
    gedekt: set[str] = set()
    for pad in sorted(versies.glob("*.py")):
        in_lijst, sql = _tekenreeksen_vooruit(pad)
        if not sql:
            continue
        for tabel in orm_tabellen:
            if tabel in in_lijst or any(re.search(rf"\b{re.escape(tabel)}\b", s) for s in sql):
                gedekt.add(tabel)
    return gedekt


class TestDeKlanttabellenHebbenRls:
    def test_elke_klanttabel_staat_in_een_rls_migratie_of_op_de_uitzonderingslijst(self) -> None:
        orm = _orm_tenanttabellen()

        zonder = sorted(orm - gedekte_tabellen(orm, VERSIES) - set(KNOWN_ZONDER_RLS))

        assert zonder == [], (
            "Tabellen met een tenantkolom die in GEEN migratie Row Level Security krijgen: "
            f"{zonder}. Zonder RLS rust de scheiding tussen klanten op de applicatiecode alleen. Voeg een "
            "migratie toe met `ENABLE ROW LEVEL SECURITY` en een policy, of zet de tabel met een REDEN op "
            "`KNOWN_ZONDER_RLS`."
        )

    def test_de_uitzonderingslijst_is_niet_verouderd(self) -> None:
        orm = _orm_tenanttabellen()
        gedekt = gedekte_tabellen(orm, VERSIES)

        verouderd = sorted(t for t in KNOWN_ZONDER_RLS if t not in orm or t in gedekt)

        assert verouderd == [], (
            f"Deze uitzonderingen hebben nu wel RLS of bestaan niet meer en horen van de lijst: {verouderd}"
        )

    def test_controlegroep_de_meting_ziet_veel_tabellen_en_bekende_voorbeelden(self) -> None:
        orm = _orm_tenanttabellen()
        gedekt = gedekte_tabellen(orm, VERSIES)

        assert (len(orm) > 150, len(gedekt) > 150, "users" in gedekt) == (True, True, True)


class TestDeMeting:
    """De meetfunctie op tijdelijke migraties: per element in beide richtingen."""

    @staticmethod
    def _migratie(map_: Path, tekst: str) -> None:
        (map_ / "a.py").write_text(tekst, encoding="utf-8")

    def test_rls_in_upgrade_telt_als_gedekt(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            'def upgrade():\n    op.execute("ALTER TABLE bonnen ENABLE ROW LEVEL SECURITY")\n'
            "def downgrade():\n    pass\n",
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == {"bonnen"}

    def test_alleen_in_downgrade_telt_niet(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            "def upgrade():\n    pass\n"
            "def downgrade():\n"
            '    op.execute("ALTER TABLE bonnen DISABLE ROW LEVEL SECURITY; DROP POLICY x ON bonnen")\n',
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == set()

    def test_alleen_in_een_docstring_telt_niet(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            '"""Tabel bonnen krijgt ROW LEVEL SECURITY, maar dat staat hier alleen in woorden."""\n'
            "def upgrade():\n    pass\n",
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == set()

    def test_alleen_als_commentaar_telt_niet(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            "def upgrade():\n    # ALTER TABLE bonnen ENABLE ROW LEVEL SECURITY\n    pass\n",
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == set()

    def test_een_lijstgedreven_migratie_telt_wel(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            '_TABELLEN = ["bonnen", "debiteuren"]\n'
            "def upgrade():\n"
            "    for t in _TABELLEN:\n"
            '        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")\n',
        )

        assert gedekte_tabellen({"bonnen", "debiteuren", "vergeten"}, tmp_path) == {
            "bonnen",
            "debiteuren",
        }

    def test_rls_op_een_tabel_dekt_een_andere_tabel_in_hetzelfde_bestand_niet(
        self, tmp_path: Path
    ) -> None:
        self._migratie(
            tmp_path,
            "def upgrade():\n"
            '    op.create_table("bonnen")\n'
            '    op.create_table("debiteuren")\n'
            '    op.execute("ALTER TABLE bonnen ENABLE ROW LEVEL SECURITY")\n',
        )

        assert gedekte_tabellen({"bonnen", "debiteuren"}, tmp_path) == {"bonnen"}

    def test_een_modulevariabele_in_een_fstring_met_enable_rls_telt_wel(
        self, tmp_path: Path
    ) -> None:
        self._migratie(
            tmp_path,
            '_TABEL = "bonnen"\n'
            '_ANDER = "debiteuren"\n'
            "def upgrade():\n"
            "    op.create_table(_ANDER)\n"
            '    op.execute(f"ALTER TABLE {_TABEL} ENABLE ROW LEVEL SECURITY")\n',
        )

        assert gedekte_tabellen({"bonnen", "debiteuren"}, tmp_path) == {"bonnen"}

    def test_een_hulpfunctie_met_rls_in_de_naam_telt_wel(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            "def _enable_rls(t, p):\n"
            '    op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")\n'
            "def upgrade():\n"
            '    op.create_table("debiteuren")\n'
            '    _enable_rls("bonnen", "pol")\n',
        )

        assert gedekte_tabellen({"bonnen", "debiteuren"}, tmp_path) == {"bonnen"}

    def test_disable_row_level_security_in_upgrade_telt_niet(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            'def upgrade():\n    op.execute("ALTER TABLE bonnen DISABLE ROW LEVEL SECURITY")\n',
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == set()

    def test_een_kale_create_policy_zonder_enable_telt_niet(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            'def upgrade():\n    op.execute("CREATE POLICY p ON bonnen USING (true)")\n',
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == set()

    def test_een_tabel_zonder_enige_vermelding_telt_niet(self, tmp_path: Path) -> None:
        self._migratie(
            tmp_path,
            'def upgrade():\n    op.execute("ALTER TABLE andere ENABLE ROW LEVEL SECURITY")\n',
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == set()

    def test_een_migratie_zonder_rls_dekt_niets_ook_als_de_naam_erin_staat(
        self, tmp_path: Path
    ) -> None:
        self._migratie(
            tmp_path,
            'def upgrade():\n    op.create_table("bonnen")\n    op.execute("CREATE INDEX i ON bonnen (id)")\n',
        )

        assert gedekte_tabellen({"bonnen"}, tmp_path) == set()


def test_elke_uitzondering_heeft_een_reden() -> None:
    """Geen `parametrize`: met een lege lijst zou pytest de test OVERSLAAN in plaats van slagen."""
    zonder_reden = sorted(t for t, reden in KNOWN_ZONDER_RLS.items() if len(reden.strip()) < 25)
    assert not zonder_reden, f"Uitzonderingen zonder reden van 25+ tekens: {zonder_reden}"

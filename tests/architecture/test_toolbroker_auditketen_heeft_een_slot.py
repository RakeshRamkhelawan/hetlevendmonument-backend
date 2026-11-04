"""De toolauditketen heeft een slot per klant, en de ketenvolgorde is eenduidig.

Bundel logboekketens (brief 2026-10-22), vondst Gate 2 op `6b615f1b`. `ToolAuditRepository.
log_execution` las de vorige hash in een aparte aanroep zonder slot, en zowel
`get_last_audit_hash` als `verify_chain_integrity` ordenden alleen op `timestamp`. Twee
gelijktijdige toolacties voor een klant konden zo de keten splitsen.

Waarom dit een EIGEN guard is naast `test_audit_chain_verification_backlog.py`: die guard ziet
alleen functies die al een `pg_advisory_xact_lock` hebben. Een schrijfpad ZONDER slot is voor
hem onzichtbaar -- precies de toestand van deze keten voor de fix. Deze guard zoekt daarom van
de andere kant: elke functie die een `ToolAuditLog`-rij bouwt MOET een slot nemen, DAARNA de
vorige hash lezen en pas dan de rij bouwen.

Net als de buurguard wordt de REGEL zelf op synthetische fragmenten getoetst (gevallen die
moeten falen, gevallen die moeten slagen), niet door productiecode te muteren. Het
mutatiebewijs op de echte code staat in het rapport van deze bundel.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_REPOSITORY = "src/core/tool_broker/audit_repository.py"

#: Aanroepen die SQL daadwerkelijk naar de database sturen (zie de buurguard).
SQL_UITVOERDERS = frozenset({"text", "execute", "exec_driver_sql", "scalar", "scalar_one"})

#: Functies waarvan elke `order_by` het `id` als tweede sleutel moet hebben.
KETEN_LEZERS = ("get_last_audit_hash", "verify_chain_integrity")

#: Naam van de aanroep die de vorige hash van de keten geeft.
VORIGE_HASH_LEZER = "get_last_audit_hash"

#: De rij die de keten bouwt.
RIJ_KLASSE = "ToolAuditLog"

#: De aanroep die de tijdstempel van de regel geeft (`datetime.now(timezone.utc)`).
TIJDSTEMPEL_BRON = "now"


def _eigen_knopen(functie: ast.AST) -> list[ast.AST]:
    """Alle knopen van deze functie, ZONDER de bodies van geneste functiedefinities."""
    resultaat: list[ast.AST] = []
    stapel: list[ast.AST] = [functie]
    eerste = True
    while stapel:
        knoop = stapel.pop()
        if not eerste and isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        eerste = False
        resultaat.append(knoop)
        stapel.extend(ast.iter_child_nodes(knoop))
    return resultaat


def _aanroepnaam(aanroep: ast.Call) -> str | None:
    doel = aanroep.func
    return doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", None)


def _functies(boom: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [k for k in ast.walk(boom) if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _slot_regel(functie: ast.AST) -> int | None:
    """De regel van de eerste ECHTE `pg_advisory_xact_lock`-uitvoering in deze functie."""
    regels: list[int] = []
    for knoop in _eigen_knopen(functie):
        if not isinstance(knoop, ast.Call) or _aanroepnaam(knoop) not in SQL_UITVOERDERS:
            continue
        for stuk in ast.walk(knoop):
            if (
                isinstance(stuk, ast.Constant)
                and isinstance(stuk.value, str)
                and "pg_advisory_xact_lock" in stuk.value
            ):
                regels.append(knoop.lineno)
                break
    return min(regels) if regels else None


def _aanroep_regel(functie: ast.AST, naam: str) -> int | None:
    """De regel van de eerste AANROEP met deze naam in deze functie."""
    regels = [
        k.lineno
        for k in _eigen_knopen(functie)
        if isinstance(k, ast.Call) and _aanroepnaam(k) == naam
    ]
    return min(regels) if regels else None


def _rij_bouwers(boom: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [f for f in _functies(boom) if _aanroep_regel(f, RIJ_KLASSE) is not None]


def beoordeel_schrijver(functie: ast.AST) -> list[str]:
    """Wat ontbreekt er aan deze functie die een `ToolAuditLog`-rij bouwt? Leeg is goed."""
    slot = _slot_regel(functie)
    vorige = _aanroep_regel(functie, VORIGE_HASH_LEZER)
    rij = _aanroep_regel(functie, RIJ_KLASSE)
    tijd = _aanroep_regel(functie, TIJDSTEMPEL_BRON)
    assert rij is not None
    gebreken: list[str] = []
    if slot is None:
        gebreken.append("neemt geen pg_advisory_xact_lock")
    elif slot > rij:
        gebreken.append("neemt het slot NA het bouwen van de rij")
    # De tijdstempel zit in de hash en hoort NA het slot (ADR-036 OP-110): binnen het slot is
    # elke volgende tijdstempel later dan die van de vorige schrijver.
    if tijd is None:
        gebreken.append(f"zet de tijdstempel niet zelf ({TIJDSTEMPEL_BRON})")
    elif slot is not None and tijd < slot:
        gebreken.append("zet de tijdstempel VOOR het slot")
    if vorige is None:
        gebreken.append(f"leest de vorige hash niet zelf ({VORIGE_HASH_LEZER})")
    elif slot is not None and vorige < slot:
        gebreken.append("leest de vorige hash VOOR het slot")
    return gebreken


def orderingen_zonder_id(boom: ast.AST) -> list[str]:
    """Elke `order_by` in de ketenlezers zonder een `id`-sleutel. Leeg is goed."""
    slecht: list[str] = []
    for functie in _functies(boom):
        if functie.name not in KETEN_LEZERS:
            continue
        for knoop in _eigen_knopen(functie):
            if not isinstance(knoop, ast.Call) or _aanroepnaam(knoop) != "order_by":
                continue
            heeft_id = any(
                isinstance(stuk, ast.Attribute) and stuk.attr == "id"
                for argument in [*knoop.args, *(k.value for k in knoop.keywords)]
                for stuk in ast.walk(argument)
            )
            if not heeft_id:
                slecht.append(f"{functie.name} (regel {knoop.lineno})")
    return slecht


def _git_grep_bestanden(patroon: str) -> list[str]:
    resultaat = subprocess.run(
        ["git", "grep", "-l", "-I", "-F", patroon, "--", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultaat.returncode not in (0, 1):
        raise AssertionError(
            f"`git grep` faalde (rc={resultaat.returncode}): {resultaat.stderr.strip()!r}. Een "
            "guard die de returncode negeert leest een lege uitvoer als 'niets gevonden'."
        )
    return sorted(r for r in resultaat.stdout.split("\n") if r.strip())


def _bron(*regels: str) -> str:
    return "async def f(self, s):\n" + "".join(f"    {r}\n" for r in regels)


_SLOT = 'await s.execute(text("SELECT pg_advisory_xact_lock(1)"))'
_TS = "ts = now()"
_VORIGE = "vorige = await self.get_last_audit_hash()"
_RIJ = "rij = ToolAuditLog(previous_hash=vorige)"

#: (naam, bron, verwachte gebreken). Beide richtingen: wat moet falen en wat moet slagen.
_SCHRIJVER_GEVALLEN: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("goede vorm", _bron(_SLOT, _TS, _VORIGE, _RIJ), ()),
    ("geen slot", _bron(_TS, _VORIGE, _RIJ), ("neemt geen pg_advisory_xact_lock",)),
    (
        "slot alleen in een docstring",
        _bron('"""Neemt pg_advisory_xact_lock."""', _TS, _VORIGE, _RIJ),
        ("neemt geen pg_advisory_xact_lock",),
    ),
    (
        "slot in een geneste functie telt niet",
        _bron("async def binnen():", "    " + _SLOT, _TS, _VORIGE, _RIJ),
        ("neemt geen pg_advisory_xact_lock",),
    ),
    (
        "slot na het bouwen van de rij",
        _bron(_TS, _VORIGE, _RIJ, _SLOT),
        (
            "neemt het slot NA het bouwen van de rij",
            "zet de tijdstempel VOOR het slot",
            "leest de vorige hash VOOR het slot",
        ),
    ),
    (
        "vorige hash voor het slot gelezen",
        _bron(_VORIGE, _SLOT, _TS, _RIJ),
        ("leest de vorige hash VOOR het slot",),
    ),
    (
        "tijdstempel voor het slot",
        _bron(_TS, _SLOT, _VORIGE, _RIJ),
        ("zet de tijdstempel VOOR het slot",),
    ),
    (
        "geen tijdstempel",
        _bron(_SLOT, _VORIGE, _RIJ),
        (f"zet de tijdstempel niet zelf ({TIJDSTEMPEL_BRON})",),
    ),
    (
        "vorige hash komt van de aanroeper",
        _bron(_SLOT, _TS, _RIJ),
        (f"leest de vorige hash niet zelf ({VORIGE_HASH_LEZER})",),
    ),
)


@pytest.mark.parametrize(
    ("naam", "bron", "verwacht"), _SCHRIJVER_GEVALLEN, ids=[g[0] for g in _SCHRIJVER_GEVALLEN]
)
def test_the_writer_rule_flags_exactly_the_missing_pieces(
    naam: str, bron: str, verwacht: tuple[str, ...]
) -> None:
    functie = ast.parse(bron).body[0]
    assert beoordeel_schrijver(functie) == list(verwacht), naam


_ORDER_GEVALLEN: tuple[tuple[str, str, int], ...] = (
    (
        "alleen tijdstempel",
        "def get_last_audit_hash(self):\n    return select(X).order_by(desc(X.timestamp))\n",
        1,
    ),
    (
        "tijdstempel en id",
        "def get_last_audit_hash(self):\n"
        "    return select(X).order_by(desc(X.timestamp), desc(X.id))\n",
        0,
    ),
    (
        "oplopend met id",
        "def verify_chain_integrity(self):\n"
        "    return select(X).order_by(X.timestamp.asc(), X.id.asc())\n",
        0,
    ),
    (
        "oplopend zonder id",
        "def verify_chain_integrity(self):\n    return select(X).order_by(X.timestamp.asc())\n",
        1,
    ),
    (
        "een andere functie telt niet",
        "def get_logs(self):\n    return select(X).order_by(desc(X.timestamp))\n",
        0,
    ),
)


@pytest.mark.parametrize(
    ("naam", "bron", "aantal"), _ORDER_GEVALLEN, ids=[g[0] for g in _ORDER_GEVALLEN]
)
def test_the_ordering_rule_requires_id_as_a_second_key(naam: str, bron: str, aantal: int) -> None:
    assert len(orderingen_zonder_id(ast.parse(bron))) == aantal, naam


def test_the_scan_finds_the_tool_audit_writer_at_all() -> None:
    """Vangnet: loopt de detectie leeg, dan bewaakt de test hieronder niets.

    Zonder dit vangnet laat een hernoemde klasse of een verplaatst bestand de bewaking stil
    slagen op een lege verzameling.
    """
    bestanden = _git_grep_bestanden(f"{RIJ_KLASSE}(")
    assert AUDIT_REPOSITORY in bestanden, (
        f"`{RIJ_KLASSE}(` komt niet meer voor in {AUDIT_REPOSITORY}: {bestanden}. Is de klasse "
        "hernoemd of het bestand verplaatst? Dan meet deze guard niets meer."
    )
    boom = ast.parse((REPO_ROOT / AUDIT_REPOSITORY).read_text(encoding="utf-8"))
    namen = sorted(f.name for f in _rij_bouwers(boom))
    assert namen == ["log_execution"], f"verwacht precies `log_execution`, gevonden {namen}"


def test_every_function_that_builds_a_tool_audit_row_takes_the_lock_first() -> None:
    """Elke bouwer van een `ToolAuditLog`-rij in `src/`: slot, dan vorige hash, dan de rij."""
    gebreken: list[str] = []
    for pad in _git_grep_bestanden(f"{RIJ_KLASSE}("):
        boom = ast.parse((REPO_ROOT / pad).read_text(encoding="utf-8"))
        for functie in _rij_bouwers(boom):
            for gebrek in beoordeel_schrijver(functie):
                gebreken.append(f"{pad}::{functie.name}: {gebrek}")
    assert not gebreken, (
        "Deze schrijvers van de toolauditketen zijn niet serialiseerbaar per klant: "
        f"{gebreken}. Twee gelijktijdige toolacties lezen dan dezelfde vorige hash en splitsen de "
        "keten (brief 2026-10-22). Neem eerst `pg_advisory_xact_lock(TOOL_AUDIT_LOCK_RUIMTE, "
        "tenant)`, lees dan `get_last_audit_hash()` en bouw dan de rij."
    )


def test_the_chain_readers_order_on_timestamp_and_id() -> None:
    """De schrijver ketent op (tijdstempel, id); de verifier loopt dezelfde volgorde."""
    boom = ast.parse((REPO_ROOT / AUDIT_REPOSITORY).read_text(encoding="utf-8"))
    gezien = sorted(f.name for f in _functies(boom) if f.name in KETEN_LEZERS)
    assert gezien == sorted(KETEN_LEZERS), (
        f"De ketenlezers {KETEN_LEZERS} staan niet meer in {AUDIT_REPOSITORY} (gevonden: {gezien}); "
        "dan meet deze test niets meer."
    )
    slecht = orderingen_zonder_id(boom)
    assert not slecht, (
        f"Deze lezers ordenen niet op `id` als tweede sleutel: {slecht}. Twee regels met dezelfde "
        "tijdstempel hebben dan een niet-vastliggende volgorde, en de verifier kan een gave keten "
        "als gebroken melden."
    )

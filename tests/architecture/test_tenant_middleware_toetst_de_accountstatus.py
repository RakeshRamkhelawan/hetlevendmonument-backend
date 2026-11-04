"""Elke route met een token loopt langs de accountcontrole (uitgeschakeld is uitgeschakeld).

Waarom: routes zonder gebruikersafhankelijkheid (zoeken, crag, evaluaties) lazen alleen het token
in `tenant_middleware`; een uitgezette gebruiker kwam er gewoon door (gemeten 2026-10-12). De
controle staat nu centraal in `TenantMiddleware.__call__`, en deze guard bewaakt dat zij daar blijft.

**Wat bewaakt wordt** (op STRUCTUUR via `ast`, niet op tekst):

1. `TenantMiddleware.__call__` roept `haal_account_status(...)` aan (een `Await` van een `Call`);
2. die aanroep staat VOOR `set_tenant_id(tenant_id)`: zonder die volgorde draait de rest van het
   verzoek al met tenantcontext voordat de status bekend is;
3. er is een `if` op `AccountStatus` waarvan de body een `return` heeft: weigeren, niet doorlaten;
4. `EXCLUDED_PREFIXES` is precies de bekende lijst: een prefix daar slaat de controle over, dus een
   nieuwe prefix moet bewust worden toegevoegd (hieronder, met reden);
5. de app voegt `TenantMiddleware` toe (`add_middleware(TenantMiddleware)`).

**Mutatiebewijs** (op kopieen van de bron, de echte boom blijft ongemoeid, beide richtingen): de
parametrisatie hieronder. Elke mutatie heeft een eigen regel; de LEGITIEME mutaties (andere
variabelenaam, extra regel ertussen) mogen NIET rood worden.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_MIDDLEWARE = _REPO / "src/core/middleware/tenant_middleware.py"
_MIDDLEWARE_CONFIG = _REPO / "src/core/api/setup/middleware_config.py"

#: Wat de controle overslaat. Allemaal zonder token-gebruik: gezondheid, metrics, documentatie.
KNOWN_EXCLUDED_PREFIXES = {
    "/health": "gezondheidscontrole, geen token",
    "/ready": "gereedheidscontrole, geen token",
    "/metrics": "metrics, geen token",
    "/docs": "documentatie, geen token",
    "/openapi.json": "schema, geen token",
}


def _functie(bron: str, klasse: str, naam: str) -> ast.AsyncFunctionDef:
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.ClassDef) and knoop.name == klasse:
            for kind in knoop.body:
                if isinstance(kind, ast.AsyncFunctionDef) and kind.name == naam:
                    return kind
    raise AssertionError(f"{klasse}.{naam} niet gevonden")


def _regel_van_aanroep(functie: ast.AST, naam: str, *, await_: bool) -> int | None:
    for knoop in ast.walk(functie):
        if await_:
            if (
                isinstance(knoop, ast.Await)
                and isinstance(knoop.value, ast.Call)
                and isinstance(knoop.value.func, ast.Name)
                and knoop.value.func.id == naam
            ):
                return knoop.lineno
        elif (
            isinstance(knoop, ast.Call)
            and isinstance(knoop.func, ast.Name)
            and knoop.func.id == naam
        ):
            return knoop.lineno
    return None


def _is_niet_actief_vergelijking(test: ast.expr) -> bool:
    """Precies `<iets> is not AccountStatus.ACTIEF` (omgekeerd of een andere status telt niet)."""
    return (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.IsNot)
        and isinstance(test.comparators[0], ast.Attribute)
        and test.comparators[0].attr == "ACTIEF"
        and isinstance(test.comparators[0].value, ast.Name)
        and test.comparators[0].value.id == "AccountStatus"
    )


def _weigert_bij_niet_actief(functie: ast.AST) -> bool:
    """Is er een `if ... is not AccountStatus.ACTIEF` waarvan de body een `return` bevat?"""
    for knoop in ast.walk(functie):
        if isinstance(knoop, ast.If) and _is_niet_actief_vergelijking(knoop.test):
            if any(isinstance(n, ast.Return) for b in knoop.body for n in ast.walk(b)):
                return True
    return False


def _controle_aanroep(functie: ast.AST) -> ast.Await | None:
    for knoop in ast.walk(functie):
        if (
            isinstance(knoop, ast.Await)
            and isinstance(knoop.value, ast.Call)
            and isinstance(knoop.value.func, ast.Name)
            and knoop.value.func.id == "haal_account_status"
        ):
            return knoop
    return None


def _namen(knoop: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(knoop) if isinstance(n, ast.Name)}


def _argumenten_komen_uit_het_token(functie: ast.AST) -> bool:
    """Eerste argument leest uit `payload`, tweede is de variabele `tenant_id`."""
    aanroep = _controle_aanroep(functie)
    if aanroep is None or not isinstance(aanroep.value, ast.Call):
        return False
    args = aanroep.value.args
    return (
        len(args) >= 2
        and "payload" in _namen(args[0])
        and isinstance(args[1], ast.Name)
        and args[1].id == "tenant_id"
    )


def _staat_in_een_dode_tak(functie: ast.AST) -> bool:
    """Staat de aanroep binnen een `if` met een constante voorwaarde (`if False:`)?"""
    aanroep = _controle_aanroep(functie)
    if aanroep is None:
        return False
    for knoop in ast.walk(functie):
        if isinstance(knoop, ast.If) and isinstance(knoop.test, ast.Constant):
            if any(n is aanroep for b in knoop.body + knoop.orelse for n in ast.walk(b)):
                return True
    return False


def _excluded_prefixes(bron: str) -> set[str]:
    gevonden: set[str] | None = None
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "EXCLUDED_PREFIXES" for t in knoop.targets
        ):
            gevonden = {
                e.value
                for e in ast.walk(knoop.value)
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    if gevonden is None:
        raise AssertionError("EXCLUDED_PREFIXES niet gevonden")
    return gevonden


def _voegt_tenantmiddleware_toe(bron: str) -> bool:
    for knoop in ast.walk(ast.parse(bron)):
        if (
            isinstance(knoop, ast.Call)
            and isinstance(knoop.func, ast.Attribute)
            and knoop.func.attr == "add_middleware"
            and any(isinstance(a, ast.Name) and a.id == "TenantMiddleware" for a in knoop.args)
        ):
            return True
    return False


def _meet(bron: str) -> tuple[bool, bool, bool, bool, bool]:
    """(controle aanwezig, voor set_tenant_id, weigert bij niet-actief, args uit token, levend)."""
    functie = _functie(bron, "TenantMiddleware", "__call__")
    controle = _regel_van_aanroep(functie, "haal_account_status", await_=True)
    zetten = _regel_van_aanroep(functie, "set_tenant_id", await_=False)
    return (
        controle is not None,
        controle is not None and zetten is not None and controle < zetten,
        _weigert_bij_niet_actief(functie),
        _argumenten_komen_uit_het_token(functie),
        controle is not None and not _staat_in_een_dode_tak(functie),
    )


# --- de echte boom -------------------------------------------------------------------------


def test_de_middleware_roept_de_accountcontrole_aan() -> None:
    assert _meet(_MIDDLEWARE.read_text(encoding="utf-8"))[0]


def test_de_controle_krijgt_sub_en_tenant_uit_het_geverifieerde_token() -> None:
    assert _meet(_MIDDLEWARE.read_text(encoding="utf-8"))[3]


def test_de_controle_staat_niet_in_een_dode_tak() -> None:
    assert _meet(_MIDDLEWARE.read_text(encoding="utf-8"))[4]


def test_de_accountcontrole_staat_voor_set_tenant_id() -> None:
    assert _meet(_MIDDLEWARE.read_text(encoding="utf-8"))[1]


def test_een_niet_actief_account_wordt_geweigerd_niet_doorgelaten() -> None:
    assert _meet(_MIDDLEWARE.read_text(encoding="utf-8"))[2]


def test_de_uitgezonderde_prefixen_zijn_de_bekende_lijst() -> None:
    assert _excluded_prefixes(_MIDDLEWARE.read_text(encoding="utf-8")) == set(
        KNOWN_EXCLUDED_PREFIXES
    ), "EXCLUDED_PREFIXES wijkt af: een nieuwe prefix slaat de accountcontrole over"


def test_de_app_voegt_de_tenantmiddleware_toe() -> None:
    assert _voegt_tenantmiddleware_toe(_MIDDLEWARE_CONFIG.read_text(encoding="utf-8"))


# --- de controles zelf, op gemuteerde kopieen (beide richtingen) --------------------------

_CONTROLE = (
    "account_status = await haal_account_status(\n"
    '                str(payload.get("sub") or ""),\n'
    "                tenant_id,\n"
    "                portal=is_portal_token(cast(Mapping[str, object], payload)),\n"
    "            )"
)
_ZETTEN = "            set_tenant_id(tenant_id)\n"
_WEIGER_EINDE = (
    "                await response(scope, receive, send)\n"
    "                return\n\n"
    "            # Set ContextVar"
)


def _controle_na_zetten(bron: str) -> str:
    zonder = bron.replace(_CONTROLE, "account_status = AccountStatus.ACTIEF")
    return zonder.replace(_ZETTEN, _ZETTEN + "            " + _CONTROLE + "\n", 1)


ALLES = (True, True, True, True, True)
IF_REGEL = "            if account_status is not AccountStatus.ACTIEF:"

MUTATIES: list[tuple[str, Callable[[str], str], tuple[bool, bool, bool, bool, bool]]] = [
    ("ongewijzigd", lambda b: b, ALLES),
    (
        "controle weg",
        lambda b: b.replace(_CONTROLE, "account_status = AccountStatus.ACTIEF"),
        (False, False, True, False, False),
    ),
    (
        "controle in een comment",
        lambda b: b.replace(
            _CONTROLE,
            "account_status = AccountStatus.ACTIEF  # await haal_account_status(payload, tenant_id)",
        ),
        (False, False, True, False, False),
    ),
    ("controle NA set_tenant_id", _controle_na_zetten, (True, False, True, True, True)),
    (
        "weigeren zonder return",
        lambda b: b.replace(
            _WEIGER_EINDE,
            "                await response(scope, receive, send)\n\n            # Set ContextVar",
        ),
        (True, True, False, True, True),
    ),
    (
        "omgekeerde voorwaarde (weigert alle gezonde accounts)",
        lambda b: b.replace(IF_REGEL, "            if account_status is AccountStatus.ACTIEF:"),
        (True, True, False, True, True),
    ),
    (
        "alleen UITGESCHAKELD weigeren (ONBEKEND loopt door)",
        lambda b: b.replace(
            IF_REGEL, "            if account_status is AccountStatus.UITGESCHAKELD:"
        ),
        (True, True, False, True, True),
    ),
    (
        "aanroep in een dode tak",
        lambda b: b.replace(_CONTROLE, "if False:\n                " + _CONTROLE),
        (True, True, True, True, False),
    ),
    (
        "vaste tenant in plaats van de tenant uit het token",
        lambda b: b.replace(
            'str(payload.get("sub") or ""),\n                tenant_id,\n',
            'str(payload.get("sub") or ""),\n                1,\n',
        ),
        (True, True, True, False, True),
    ),
    (
        "sub niet uit het token",
        lambda b: b.replace('str(payload.get("sub") or "")', '""'),
        (True, True, True, False, True),
    ),
    (
        "LEGITIEEM: andere variabelenaam",
        lambda b: b.replace("account_status =", "status_van_account =").replace(
            "account_status is", "status_van_account is"
        ),
        ALLES,
    ),
    (
        "LEGITIEEM: extra regel ertussen",
        lambda b: b.replace(_CONTROLE, 'logger.debug("x")\n            ' + _CONTROLE),
        ALLES,
    ),
]


@pytest.mark.parametrize(("naam", "mutatie", "verwacht"), MUTATIES, ids=[m[0] for m in MUTATIES])
def test_de_controles_zien_elke_mutatie(
    naam: str,
    mutatie: Callable[[str], str],
    verwacht: tuple[bool, bool, bool, bool, bool],
) -> None:
    bron = _MIDDLEWARE.read_text(encoding="utf-8")
    gemuteerd = mutatie(bron)
    if naam != "ongewijzigd":
        assert gemuteerd != bron, f"mutatie {naam} veranderde niets"

    assert _meet(gemuteerd) == verwacht, naam


@pytest.mark.parametrize(
    ("bron", "verwacht"),
    [
        ("EXCLUDED_PREFIXES = ['/health', '/ready']", {"/health", "/ready"}),
        (
            "EXCLUDED_PREFIXES = ['/health', '/ready', '/api/v1/search']",
            {"/health", "/ready", "/api/v1/search"},
        ),
        ("# EXCLUDED_PREFIXES = ['/x']\nEXCLUDED_PREFIXES = ['/health']", {"/health"}),
    ],
)
def test_de_prefixlezer_ziet_een_toegevoegde_prefix(bron: str, verwacht: set[str]) -> None:
    assert _excluded_prefixes(bron) == verwacht


@pytest.mark.parametrize(
    ("bron", "verwacht"),
    [
        ("app.add_middleware(TenantMiddleware)", True),
        ("# app.add_middleware(TenantMiddleware)", False),
        ("app.add_middleware(AndereMiddleware)", False),
    ],
)
def test_de_appcontrole_ziet_een_echte_toevoeging(bron: str, verwacht: bool) -> None:
    assert _voegt_tenantmiddleware_toe(bron) is verwacht

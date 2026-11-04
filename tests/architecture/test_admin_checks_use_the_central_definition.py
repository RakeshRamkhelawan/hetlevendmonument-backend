"""Geen enkele admin-check houdt zijn eigen rollijst (ADR-036 OP-40).

**Wat hier bewaakt wordt.** Sinds 2026-09-01 is `src/core/auth/dependencies.is_admin` DE
admin-definitie van de codebase. De zeven plekken die dat voorheen elk zelf beslisten, delegeren
er nu naar. Deze guard betrapt dat een van die zeven zijn eigen logica terugzet -- want dan
verschijnt de splitsing uit OP-40 opnieuw, en zwijgend: de code blijft werken, alleen de
antwoorden lopen weer uiteen.

**Twee eisen per plek, want een ervan alleen is te omzeilen.**

1. De functie ROEPT de centrale definitie aan. Zonder deze eis is "verwijder de check" een
   geldige oplossing.
2. De functie noemt ZELF geen beheerdersrolnaam. Zonder deze eis mag een functie de centrale
   definitie aanroepen en er daarna een eigen `or "system_admin" in roles` naast zetten -- de
   aanroep staat er dan, en de definitie is alsnog gesplitst.

**De docstring wordt uit de kopie verwijderd voor de analyse, en dat is hier niet theoretisch.**
De docstrings van vijf van deze zeven functies bevatten letterlijk de tekst
`role in ["admin", "system_admin"]`, omdat ze uitleggen wat er tot 2026-09-01 stond. Een guard die
de ruwe bron of `ast.dump()` doorzoekt, vindt die tekst en faalt op zijn eigen toelichting -- of,
erger, iemand haalt de toelichting weg om de guard groen te krijgen.
`test_the_docstring_exclusion_is_load_bearing` bewijst dat die uitsluiting daadwerkelijk werkt.

**Mutatiebewijs -- een regel per element van `ADMIN_CHECK_SITES`, gemeten 2026-09-01.**
Per plek is `if not is_admin(x)` vervangen door de oude eigen logica
`if not any(role in ["admin", "system_admin"] for role in (x.roles or []))`, telkens een tegelijk,
met een kopie van het bestand als terugweg (nooit `git checkout --`):

| Gemuteerde plek | Uitkomst van deze guard |
| --- | --- |
| `auth/dependencies.is_tenant_admin` | ROOD: 2 failed, 25 passed |
| `auth/dependencies.require_admin` | ROOD: 2 failed, 25 passed |
| `api/dependencies.require_admin_role` | ROOD: 2 failed, 25 passed |
| `api/dependencies.require_admin_user` | ROOD: 2 failed, 25 passed |
| `api/v1/tenant_management.require_admin` | ROOD: 2 failed, 25 passed |
| `api/v1/user_management.require_admin` | ROOD: 2 failed, 25 passed |
| `api/v1/admin.require_admin_role` | ROOD: 2 failed, 25 passed |

Achtste mutatie, op de OMGEKEERDE eis -- de tenant-grens mag NIET verbreden.
`tenant_management/crud_router.py::get_tenant` is "geconsolideerd" naar `is_admin(current_user)`,
precies de wijziging die verstandig UITZIET en cross-tenant leesrecht aan elke `tenantadmin` zou
geven. ROOD: 2 failed, 25 passed --
`test_the_cross_tenant_checks_did_not_widen_to_the_broad_definition[tenant_management/get_tenant]`
en de staleness-test vuren beide.

De andere richting, ook gemeten: aan `api/v1/admin/dependencies.py` is een NIEUWE dependency
`require_admin_voor_rapportage` toegevoegd die netjes `is_admin` aanroept, zelf geen rolnaam
noemt en de woorden "admin" en "system_admin" wel in zijn docstring heeft; daarna is hij aan
`ADMIN_CHECK_SITES` toegevoegd. Uitkomst: GROEN, 19 passed -- de guard betrapt hem niet.
(Die meting is gedaan toen deze guard nog 17 tests had; hij heeft er nu 27 door de
uitzonderingslijst hieronder. De eigenschap is dezelfde en staat permanent vast in
`test_the_analyzer_accepts_a_delegating_function`.) Zonder deze helft zou "weiger elke
nieuwe check" een geldige oplossing zijn en zou de guard de functionaliteit slopen. Die richting
staat bovendien permanent vast in `test_the_analyzer_accepts_a_delegating_function`, zodat hij
niet alleen op mijn eenmalige meting berust.

De ongemuteerde basis is 27 passed, en na herstel van elke mutatie opnieuw 27 passed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De namen die als "delegeert naar de centrale definitie" tellen. `is_tenant_admin` staat erbij
#: omdat hij sinds OP-40 zelf niets meer doet dan `is_admin` aanroepen; dertien aanroeppunten
#: gebruiken nog die naam.
_CENTRAL_NAMES = frozenset({"is_admin", "is_tenant_admin", "_is_tenant_admin"})

#: De rolnamen die een admin-check niet zelf mag noemen. Gelijk aan `ADMIN_ROLE_NAMES` plus de
#: schrijfwijzen die elders in de codebase in omloop zijn, zodat een terugval naar een van die
#: varianten ook wordt betrapt.
_ADMIN_ROLE_LITERALS = frozenset(
    {"admin", "system_admin", "tenantadmin", "tenant_admin", "TenantAdmin", "Admin"}
)

#: De expliciet benoemde verzameling die deze guard bewaakt: de zeven plekken uit ADR-036 OP-40.
#: Een tuple en geen glob, zodat in vijf seconden te zien is WAT er bewaakt wordt -- en zodat het
#: mutatiebewijs in de moduledocstring een regel per element kan hebben.
ADMIN_CHECK_SITES: tuple[tuple[str, str], ...] = (
    ("src/core/auth/dependencies.py", "is_tenant_admin"),
    ("src/core/auth/dependencies.py", "require_admin"),
    ("src/core/api/dependencies.py", "require_admin_role"),
    ("src/core/api/dependencies.py", "require_admin_user"),
    ("src/core/api/v1/tenant_management/dependencies.py", "require_admin"),
    ("src/core/api/v1/user_management/dependencies.py", "require_admin"),
    ("src/core/api/v1/admin/dependencies.py", "require_admin_role"),
)

_IDS = [f"{pad.rsplit('/', 2)[-2]}/{naam}" for pad, naam in ADMIN_CHECK_SITES]

#: Checks die hun EIGEN adminrol-logica houden, bewust, met datum en reden per regel. Gevonden
#: door de code-review op deze wijziging (2026-09-01) -- ze stonden niet in de OP-40-registerrij.
#:
#: De eerste vier poorten de TENANT-GRENS: ze staan voor een `TenantFilterBypass` of voor een
#: `override_tenant_id`. Ze verbreden naar `ADMIN_ROLE_NAMES` zou ELKE `tenantadmin` toegang tot
#: ANDERE tenants geven en daarmee ADR-005 breken. Dat is een andere vraag dan OP-40 ("mag deze
#: gebruiker beheren BINNEN zijn tenant") en vergt een eigen besluit van Rakesh.
KNOWN_UNCONSOLIDATED_ADMIN_CHECKS: dict[tuple[str, str], str] = {
    ("src/core/api/v1/tenant_management/crud_router.py", "get_tenant"): (
        "2026-09-01 -- poort op TenantFilterBypass: een admin mag hier ELKE tenant lezen. "
        "Verbreden naar tenantadmin/superuser geeft cross-tenant leesrecht (ADR-005)."
    ),
    ("src/core/api/v1/user_management/crud_router.py", "delete_user"): (
        "2026-09-01 -- poort op TenantFilterBypass: een admin mag hier een gebruiker in ELKE "
        "tenant verwijderen. Verbreden is hier het gevaarlijkst van de vier."
    ),
    ("src/core/api/admin_learning_endpoints.py", "_is_system_admin"): (
        "2026-09-01 -- bewust system_admin-only: _enforce_tenant_access laat hiermee een "
        "willekeurige tenant lezen. Consolideren zou dat aan elke tenantadmin geven."
    ),
    ("src/core/api/admin_digital_twin.py", "_is_system_admin"): (
        "2026-09-01 -- bewust system_admin-only: poort op de override_tenant_id-parameter, "
        "dus letterlijk de tenant-grens over."
    ),
    ("src/core/api/domain_packs.py", "require_domain_pack_admin"): (
        "2026-09-01 -- gebruikt de spelling 'tenant_admin' MET underscore, een vierde "
        "vocabulaire dat niet in ADMIN_ROLE_NAMES staat. Blind consolideren zou deze gebruikers "
        "juist toegang ONTNEMEN. Het besluit noemde 'tenantadmin' zonder underscore; de spelling "
        "gelijktrekken is een eigen wijziging met een eigen datamigratie-vraag."
    ),
    ("src/core/api/v1/company/board_router.py", "get_my_board_roles"): (
        "2026-09-01 -- geen autorisatiepoort maar een PROJECTIE: mapt rolnamen naar board-rollen "
        "voor weergave. Er wordt niets geweigerd, dus is_admin is hier niet het juiste gereedschap."
    ),
}

#: De vier uit de lijst hierboven die daadwerkelijk de tenant-grens poorten. Voor deze geldt een
#: EXTRA eis: ze mogen niet stilletjes naar de brede definitie verschuiven.
_CROSS_TENANT_CHECKS = tuple(
    sleutel
    for sleutel in KNOWN_UNCONSOLIDATED_ADMIN_CHECKS
    if sleutel[1] in {"get_tenant", "delete_user", "_is_system_admin"}
)


def _function(pad: str, naam: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    bestand = REPO_ROOT / pad
    # utf-8-sig: `src/core/api/domain_packs.py` begint met een BOM. Met kale utf-8 crasht
    # `ast.parse` daarop met "invalid non-printable character U+FEFF" -- gemeten 2026-09-01.
    tree = ast.parse(bestand.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == naam:
            return node
    raise AssertionError(
        f"`{naam}` bestaat niet meer in {pad}. Hernoemd of verplaatst? Werk ADMIN_CHECK_SITES "
        "bij -- een guard die zijn doel niet vindt, bewaakt niets."
    )


def _body_without_docstring(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    """De statements van de functie, met de docstring eruit.

    Zie de moduledocstring: vijf van de zeven docstrings citeren de oude rollijst letterlijk.
    """
    body = list(functie.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _calls_central_definition(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for statement in _body_without_docstring(functie):
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            aangeroepen = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if aangeroepen in _CENTRAL_NAMES:
                return True
    return False


def _own_role_literals(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    gevonden: list[str] = []
    for statement in _body_without_docstring(functie):
        for node in ast.walk(statement):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in _ADMIN_ROLE_LITERALS
            ):
                gevonden.append(node.value)
    return sorted(set(gevonden))


@pytest.mark.parametrize(("pad", "naam"), ADMIN_CHECK_SITES, ids=_IDS)
def test_every_admin_check_delegates_to_the_central_definition(pad: str, naam: str) -> None:
    """Elk van de zeven aanroeppunten vraagt het aan `is_admin`, en beslist het niet zelf."""
    functie = _function(pad, naam)

    assert _calls_central_definition(functie), (
        f"`{naam}` in {pad} roept `is_admin` (of de legacy-naam `is_tenant_admin`) niet aan. "
        "Dan beslist deze plek weer zelf wie beheerder is, en herleeft de splitsing uit ADR-036 "
        "OP-40: zeven checks in drie vocabulaires, waardoor een system_admin bij het ene endpoint "
        "wel en bij het andere niet binnenkomt."
    )


@pytest.mark.parametrize(("pad", "naam"), ADMIN_CHECK_SITES, ids=_IDS)
def test_no_admin_check_carries_its_own_role_names(pad: str, naam: str) -> None:
    """Aanroepen is niet genoeg: er mag ook geen eigen rollijst NAAST staan."""
    functie = _function(pad, naam)

    eigen = _own_role_literals(functie)

    assert not eigen, (
        f"`{naam}` in {pad} noemt zelf beheerdersrolnamen {eigen} in zijn body. Ook met een "
        "`is_admin`-aanroep erbij is de definitie dan weer gesplitst: een verscherping van "
        "`ADMIN_ROLE_NAMES` slaat deze plek stil over. Zet de rolnaam in `ADMIN_ROLE_NAMES` "
        "(src/core/auth/dependencies.py) en niet hier."
    )


_KNOWN_IDS = [f"{pad.rsplit('/', 2)[-2]}/{naam}" for pad, naam in KNOWN_UNCONSOLIDATED_ADMIN_CHECKS]


@pytest.mark.parametrize(("pad", "naam"), list(KNOWN_UNCONSOLIDATED_ADMIN_CHECKS), ids=_KNOWN_IDS)
def test_known_unconsolidated_checks_are_not_stale(pad: str, naam: str) -> None:
    """Een uitzondering die is opgelost MOET uit de lijst -- anders rot hij dicht.

    Zonder deze test blijft een regel staan nadat iemand de check heeft geconsolideerd of
    verwijderd, en dan suggereert de lijst schuld die er niet meer is.
    """
    functie = _function(pad, naam)
    eigen = _own_role_literals(functie)

    assert eigen, (
        f"`{naam}` in {pad} noemt geen eigen beheerdersrolnaam meer. Dan is deze uitzondering "
        "opgelost (of de functie doet iets anders) en hoort de regel uit "
        "KNOWN_UNCONSOLIDATED_ADMIN_CHECKS te verdwijnen. Reden die er nu bij staat: "
        f"{KNOWN_UNCONSOLIDATED_ADMIN_CHECKS[(pad, naam)]}"
    )


@pytest.mark.parametrize(
    ("pad", "naam"),
    list(_CROSS_TENANT_CHECKS),
    ids=[f"{pad.rsplit('/', 2)[-2]}/{naam}" for pad, naam in _CROSS_TENANT_CHECKS],
)
def test_the_cross_tenant_checks_did_not_widen_to_the_broad_definition(pad: str, naam: str) -> None:
    """De tenant-grens mag NIET naar `is_admin` verschuiven.

    Dit is de belangrijkste test in dit bestand. Deze vier checks poorten een
    `TenantFilterBypass` of een `override_tenant_id`. Ze accepteren vandaag alleen
    `{admin, system_admin}` respectievelijk `system_admin`. Zou iemand ze "voor de consistentie"
    naar `is_admin` laten delegeren, dan krijgt ELKE `tenantadmin` -- en elke superuser -- toegang
    tot de gegevens van ANDERE tenants. Dat is een ADR-005-breuk en het tegenovergestelde van wat
    OP-40 wilde bereiken.

    Deze test faalt dus bij een consolidatie die er verstandig UITZIET. Dat is de bedoeling:
    zo'n stap hoort een expliciet besluit van Rakesh te zijn, met een aanpassing van deze lijst.
    """
    functie = _function(pad, naam)

    assert not _calls_central_definition(functie), (
        f"`{naam}` in {pad} delegeert nu naar de BREDE definitie `is_admin`, maar deze check "
        "poort de tenant-grens. Daarmee krijgt elke tenantadmin toegang tot andere tenants "
        f"(ADR-005). Reden dat deze plek smal moet blijven: "
        f"{KNOWN_UNCONSOLIDATED_ADMIN_CHECKS[(pad, naam)]}"
    )


def test_the_docstring_exclusion_is_load_bearing() -> None:
    """Vangnet: de docstring-uitsluiting moet iets DOEN, anders is de guard vals-groen-gevoelig.

    Als niemand meer een oude rollijst in een docstring citeert, is `_body_without_docstring`
    ineens overbodig -- en dan valt het niet op wanneer hij stukgaat. Deze test faalt zodra dat
    gebeurt, zodat de uitsluiting bewust wordt verwijderd in plaats van stil te verdampen.
    """
    citerend = []
    for pad, naam in ADMIN_CHECK_SITES:
        docstring = ast.get_docstring(_function(pad, naam)) or ""
        if any(rol in docstring for rol in _ADMIN_ROLE_LITERALS):
            citerend.append(f"{pad}::{naam}")

    assert citerend, (
        "Geen enkele van de zeven docstrings citeert nog een beheerdersrolnaam. De "
        "docstring-uitsluiting in `_body_without_docstring` wordt dan niet meer uitgeoefend en "
        "kan stilletjes stukgaan. Verwijder hem bewust, of laat de toelichting staan."
    )


def _analyseer(bron: str) -> tuple[bool, list[str]]:
    functie = ast.parse(bron).body[0]
    assert isinstance(functie, (ast.FunctionDef, ast.AsyncFunctionDef))
    return _calls_central_definition(functie), _own_role_literals(functie)


def test_the_analyzer_accepts_a_delegating_function() -> None:
    """De andere richting, permanent vastgelegd: een correcte nieuwe check blijft groen.

    Zonder deze test is "betrap alles" een geldige guard, en dan blokkeert hij elke nieuwe
    admin-dependency in plaats van alleen de foute.
    """
    delegeert, eigen = _analyseer(
        "async def require_admin(user):\n"
        '    """Een nieuwe check die het netjes doet, met "admin" in de toelichting."""\n'
        "    if not is_admin(user):\n"
        "        raise HTTPException(status_code=403, detail='Admin access required')\n"
        "    return user\n"
    )

    assert delegeert is True, "Een functie die `is_admin` aanroept wordt niet herkend."
    assert eigen == [], (
        f"De analyse ziet {eigen} als eigen rollijst, terwijl die woorden alleen in de docstring "
        "en in een foutmelding staan. Dan betrapt de guard correcte code."
    )


def test_the_analyzer_rejects_an_inlined_role_list() -> None:
    """En de eerste richting, permanent vastgelegd: de oude vorm wordt wel betrapt."""
    delegeert, eigen = _analyseer(
        "async def require_admin(user):\n"
        '    """Toelichting zonder rolnamen."""\n'
        '    if not any(role in ["admin", "system_admin"] for role in (user.roles or [])):\n'
        "        raise HTTPException(status_code=403, detail='Admin access required')\n"
        "    return user\n"
    )

    assert delegeert is False, (
        "Een functie zonder `is_admin`-aanroep wordt ten onrechte goedgekeurd."
    )
    assert eigen == ["admin", "system_admin"], (
        f"De analyse vond {eigen} in een functie met een eigen rollijst in de body. Vindt hij die "
        "niet, dan is `test_no_admin_check_carries_its_own_role_names` vacuum."
    )

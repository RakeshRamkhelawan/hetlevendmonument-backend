"""Elke WebSocket-ingang die een token zelf leest, vraagt `token_mag_op_een_websocket` (portaaltoken weg).

Waarom: de WebSocket-ingangen lazen het token en toetsten `sub` tegen `users`, ook voor een
portaaltoken (`aud == "portal"`, `sub` is dan een `portal_users`-nummer). Gemeten 2026-10-13: een
portaalgebruiker kwam binnen als de medewerker met hetzelfde nummer, op alle vijf ingangen. Het was al
drie keer gebeurd dat een nieuwe token-lezer buiten een gedeelde controle viel (Gate 2, 2026-10-13).

**Wat bewaakt wordt** (op STRUCTUUR via `ast`, niet op tekst):

1. elk van de vijf WebSocket-ingangen hieronder bevat `if not await token_mag_op_een_websocket(...)`
   met een `return` of `raise` in de body (weigeren, niet doorlaten), niet in een dode tak;
2. elk bronbestand in `src/` dat `verify_token(` AANROEPT staat in precies een van de lijsten
   hieronder, met een reden: een NIEUWE token-lezer laat deze test falen tot hij is geclassificeerd;
3. geen enkele vermelding is verouderd (het bestand bestaat en roept `verify_token(` nog aan).

**Mutatiebewijs** (op kopieen van de echte bron, de echte boom blijft ongemoeid; beide richtingen):
de parametrisatie onderaan, per ingang: controle weg, omgekeerde voorwaarde, dode tak. De LEGITIEME
mutatie (extra lege regel) mag NIET rood worden.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
CONTROLE = "token_mag_op_een_websocket"

#: (bestand, klasse of None, functie): de WebSocket-ingangen die een token zelf lezen.
WS_INGANGEN: list[tuple[str, str | None, str]] = [
    ("src/core/auth/websocket_auth.py", "WebSocketAuthenticator", "authenticate"),
    ("src/core/auth/websocket_auth.py", "WebSocketAuthenticator", "authenticate_connected_user"),
    ("src/core/websocket/manager.py", "ConnectionManager", "connect"),
    ("src/core/api/v1/focus_builder/shared.py", None, "validate_ws_token"),
    ("src/core/api/v1/focus_builder/ws_dependencies.py", "WebSocketAuthHandler", "validate_token"),
]

#: Bestanden die `verify_token(` aanroepen en GEEN WebSocket-ingang zijn, met de reden.
HTTP_EN_OVERIGE_LEZERS: dict[str, str] = {
    "src/core/middleware/tenant_middleware.py": "de centrale controle: elk HTTP-verzoek met een token",
    "src/core/auth/dependencies.py": "get_current_user en get_current_user_id: weigeren een uitgezet account",
    "src/core/api/auth/router_token.py": "validate, verify-token en revoke: weigeren een uitgezet account",
    "src/core/auth/oauth2_service.py": "refresh weigert een uitgezet account; intrekken en claims lezen geven geen sessie uit",
    "src/core/api/dependencies.py": "doorverwijzing naar verify_token voor de focus-builder-ingangen hierboven",
    "src/core/auth/jwt_handler.py": "de verificatie zelf",
    "src/core/middleware/rate_limit_middleware.py": "leest alleen de tenant voor limieten, geeft geen toegang",
    "src/core/security/security_middleware.py": "leest alleen id en beveiligingsniveau, geeft geen toegang",
    "src/core/auth/auth_bearer.py": "geen aanroepers in src/ (gemeten 2026-10-13); valstrik, zie de nazorgbrief",
    "src/core/auth/token_refresh.py": "geen aanroepers in src/ (gemeten 2026-10-13); alleen unit-tests, zie de nazorgbrief",
}


def _bron(pad: str) -> str:
    return (_REPO / pad).read_text(encoding="utf-8")


def _functie(bron: str, klasse: str | None, naam: str) -> ast.AST:
    boom = ast.parse(bron)
    ouders: list[ast.AST] = [boom]
    if klasse is not None:
        ouders = [k for k in ast.walk(boom) if isinstance(k, ast.ClassDef) and k.name == klasse]
    for ouder in ouders:
        for kind in ast.walk(ouder):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)) and kind.name == naam:
                return kind
    raise AssertionError(f"{klasse}.{naam} niet gevonden")


def _is_controle_await(knoop: ast.AST) -> bool:
    return (
        isinstance(knoop, ast.Await)
        and isinstance(knoop.value, ast.Call)
        and isinstance(knoop.value.func, ast.Name)
        and knoop.value.func.id == CONTROLE
    )


def _weigert(functie: ast.AST) -> bool:
    """`if not await token_mag_op_een_websocket(...)` met een return/raise in de body, levend."""
    ouder: dict[int, ast.AST] = {}
    for knoop in ast.walk(functie):
        for kind in ast.iter_child_nodes(knoop):
            ouder[id(kind)] = knoop
    for knoop in ast.walk(functie):
        if not (
            isinstance(knoop, ast.If)
            and isinstance(knoop.test, ast.UnaryOp)
            and isinstance(knoop.test.op, ast.Not)
            and _is_controle_await(knoop.test.operand)
        ):
            continue
        if not any(isinstance(n, (ast.Return, ast.Raise)) for b in knoop.body for n in ast.walk(b)):
            continue
        omhoog = ouder.get(id(knoop))
        dood = False
        while omhoog is not None and omhoog is not functie:
            if isinstance(omhoog, ast.If) and isinstance(omhoog.test, ast.Constant):
                dood = True
            omhoog = ouder.get(id(omhoog))
        if not dood:
            return True
    return False


def _roept_verify_token_aan(bron: str) -> bool:
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.Call):
            f = knoop.func
            if (isinstance(f, ast.Attribute) and f.attr == "verify_token") or (
                isinstance(f, ast.Name) and f.id == "verify_token"
            ):
                return True
    return False


def _bestanden_die_verify_token_aanroepen() -> set[str]:
    # `git grep` is goedkoop; een repo-brede rglob+parse in een test laat een xdist-werker crashen.
    uit = subprocess.run(
        ["git", "grep", "-l", "verify_token(", "--", "src"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return {p for p in uit if p.endswith(".py") and _roept_verify_token_aan(_bron(p))}


# --- de echte boom -------------------------------------------------------------------------


@pytest.mark.parametrize(("pad", "klasse", "naam"), WS_INGANGEN)
def test_elke_websocketingang_weigert_via_de_gedeelde_controle(
    pad: str, klasse: str | None, naam: str
) -> None:
    assert _weigert(_functie(_bron(pad), klasse, naam)), f"{pad}::{klasse}.{naam}"


def test_elke_token_lezer_is_geclassificeerd() -> None:
    bekend = {pad for pad, _, _ in WS_INGANGEN} | set(HTTP_EN_OVERIGE_LEZERS)
    onbekend = sorted(_bestanden_die_verify_token_aanroepen() - bekend)

    assert not onbekend, (
        f"Nieuwe token-lezer(s) zonder classificatie: {onbekend}. Een WebSocket-ingang hoort in "
        "WS_INGANGEN (en vraagt token_mag_op_een_websocket); een HTTP-ingang in "
        "HTTP_EN_OVERIGE_LEZERS met de reden."
    )


def test_geen_vermelding_is_verouderd() -> None:
    gevonden = _bestanden_die_verify_token_aanroepen()
    verouderd = sorted(
        pad
        for pad in {p for p, _, _ in WS_INGANGEN} | set(HTTP_EN_OVERIGE_LEZERS)
        if pad not in gevonden
    )

    assert not verouderd, f"Vermeld maar roept verify_token( niet meer aan: {verouderd}"


# --- de controles zelf, op gemuteerde kopieen (beide richtingen) --------------------------


def _zonder_controle(b: str) -> str:
    return b.replace(CONTROLE, "iets_anders")


def _omgekeerd(b: str) -> str:
    return b.replace(f"if not await {CONTROLE}", f"if await {CONTROLE}")


def _dode_tak(b: str) -> str:
    return b.replace(f"if not await {CONTROLE}", f"if False and not await {CONTROLE}")


def _lege_regel_ervoor(b: str) -> str:
    # Met dezelfde inspringing als de `if`: anders is de kopie geen geldige Python meer.
    return re.sub(rf"^([ ]+)(if not await {CONTROLE})", r"\1pass\n\1\2", b, flags=re.MULTILINE)


MUTATIES: list[tuple[str, Callable[[str], str], bool]] = [
    ("controle weg", _zonder_controle, False),
    ("omgekeerde voorwaarde", _omgekeerd, False),
    ("dode tak", _dode_tak, False),
    ("LEGITIEEM: een extra regel ervoor", _lege_regel_ervoor, True),
]


@pytest.mark.parametrize(("pad", "klasse", "naam"), WS_INGANGEN)
@pytest.mark.parametrize(
    ("mutatie_naam", "mutatie", "verwacht"), MUTATIES, ids=[m[0] for m in MUTATIES]
)
def test_de_controle_ziet_elke_mutatie(
    pad: str,
    klasse: str | None,
    naam: str,
    mutatie_naam: str,
    mutatie: Callable[[str], str],
    verwacht: bool,
) -> None:
    bron = _bron(pad)
    gemuteerd = mutatie(bron)
    assert gemuteerd != bron, f"mutatie {mutatie_naam} veranderde niets in {pad}"

    try:
        gezien = _weigert(_functie(gemuteerd, klasse, naam))
    except SyntaxError:
        gezien = False

    assert gezien is verwacht, f"{pad}::{naam} onder '{mutatie_naam}'"


# --- de medewerkersingangen: `get_current_user`, `get_current_user_ws` en `get_current_user_id` ---
# Gate 2 (2026-10-13): `get_current_user_ws` en `get_current_user` lopen via `_get_user_from_token`;
# daar moet een portaaltoken met 401 geweigerd worden, anders wordt het een medewerker.

PORTAAL_HELPER = "_weiger_portaaltoken"
MEDEWERKERS_INGANGEN: list[tuple[str, str | None, str]] = [
    ("src/core/auth/dependencies.py", None, "_get_user_from_token"),
    ("src/core/auth/dependencies.py", None, "get_current_user_id"),
]


def _roept_levend_aan(functie: ast.AST, naam: str) -> bool:
    """Staat er een losse aanroep `naam(...)` in de functie, niet in een dode tak (`if False:`)?"""
    ouder: dict[int, ast.AST] = {}
    for knoop in ast.walk(functie):
        for kind in ast.iter_child_nodes(knoop):
            ouder[id(kind)] = knoop
    for knoop in ast.walk(functie):
        if not (
            isinstance(knoop, ast.Expr)
            and isinstance(knoop.value, ast.Call)
            and isinstance(knoop.value.func, ast.Name)
            and knoop.value.func.id == naam
        ):
            continue
        omhoog = ouder.get(id(knoop))
        dood = False
        while omhoog is not None and omhoog is not functie:
            if isinstance(omhoog, ast.If) and isinstance(omhoog.test, ast.Constant):
                dood = True
            omhoog = ouder.get(id(omhoog))
        if not dood:
            return True
    return False


def _helper_weigert(bron: str) -> bool:
    """`_weiger_portaaltoken` heeft `if is_portal_token(...)` met een `raise` in de body."""
    functie = _functie(bron, None, PORTAAL_HELPER)
    for knoop in ast.walk(functie):
        if (
            isinstance(knoop, ast.If)
            and any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "is_portal_token"
                for n in ast.walk(knoop.test)
            )
            and any(isinstance(n, ast.Raise) for b in knoop.body for n in ast.walk(b))
        ):
            return True
    return False


@pytest.mark.parametrize(("pad", "klasse", "naam"), MEDEWERKERS_INGANGEN)
def test_elke_medewerkersingang_weigert_een_portaaltoken(
    pad: str, klasse: str | None, naam: str
) -> None:
    assert _roept_levend_aan(_functie(_bron(pad), klasse, naam), PORTAAL_HELPER), naam


def test_de_helper_weigert_echt() -> None:
    assert _helper_weigert(_bron("src/core/auth/dependencies.py"))


def _helper_aanroep_weg(b: str) -> str:
    return b.replace(f"{PORTAAL_HELPER}(payload)", "iets_anders(payload)")


def _helper_aanroep_dode_tak(b: str) -> str:
    return re.sub(
        rf"^([ ]+){PORTAAL_HELPER}\(payload\)", rf"\1if False:\n\1    {PORTAAL_HELPER}(payload)", b,
        flags=re.MULTILINE,
    )


def _helper_aanroep_met_extra_regel(b: str) -> str:
    return re.sub(
        rf"^([ ]+){PORTAAL_HELPER}\(payload\)", rf"\1pass\n\1{PORTAAL_HELPER}(payload)", b,
        flags=re.MULTILINE,
    )


MEDEWERKERS_MUTATIES: list[tuple[str, Callable[[str], str], bool]] = [
    ("aanroep weg", _helper_aanroep_weg, False),
    ("aanroep in een dode tak", _helper_aanroep_dode_tak, False),
    ("LEGITIEEM: een extra regel ervoor", _helper_aanroep_met_extra_regel, True),
]


@pytest.mark.parametrize(("pad", "klasse", "naam"), MEDEWERKERS_INGANGEN)
@pytest.mark.parametrize(
    ("mutatie_naam", "mutatie", "verwacht"),
    MEDEWERKERS_MUTATIES,
    ids=[m[0] for m in MEDEWERKERS_MUTATIES],
)
def test_de_medewerkerscontrole_ziet_elke_mutatie(
    pad: str,
    klasse: str | None,
    naam: str,
    mutatie_naam: str,
    mutatie: Callable[[str], str],
    verwacht: bool,
) -> None:
    bron = _bron(pad)
    gemuteerd = mutatie(bron)
    assert gemuteerd != bron, f"mutatie {mutatie_naam} veranderde niets"

    try:
        gezien = _roept_levend_aan(_functie(gemuteerd, klasse, naam), PORTAAL_HELPER)
    except SyntaxError:
        gezien = False

    assert gezien is verwacht, f"{naam} onder '{mutatie_naam}'"


@pytest.mark.parametrize(
    ("naam", "mutatie"),
    [
        (
            "helper raise weg",
            lambda b: b.replace(
                'logger.info("Portaaltoken geweigerd op een medewerkersingang")\n        raise _credentials_exception()',
                'logger.info("Portaaltoken geweigerd op een medewerkersingang")\n        pass',
            ),
        ),
        ("is_portal_token vervangen", lambda b: b.replace("if is_portal_token(", "if iets_anders(")),
    ],
)
def test_de_helpercontrole_ziet_een_gemuteerde_helper(naam: str, mutatie: Callable[[str], str]) -> None:
    bron = _bron("src/core/auth/dependencies.py")
    gemuteerd = mutatie(bron)
    assert gemuteerd != bron, f"mutatie {naam} veranderde niets"

    assert _helper_weigert(gemuteerd) is False, naam

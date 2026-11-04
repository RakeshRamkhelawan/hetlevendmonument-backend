"""Een nieuwe authenticatie-ingang kan de intrekkingscontrole niet stil overslaan (OP-260).

**Waarom deze guard bestaat.** OP-188 zette de blacklistcontrole op EEN ingang. OP-260 vond
op 2026-09-19 dat er een tweede was die hem niet had -- `get_current_user_id`, met twaalf
rbac-endpoints eraan, juist die waarmee rollen en rechten worden uitgedeeld. Een ingetrokken
token werkte daar nog gewoon; gemeten met een echt verzoek tegen een echte database.

De reparatie zette de controle in een gedeelde `_weiger_als_ingetrokken`. Dat voorkomt
kopieerfouten, maar NIETS dwingt een nieuwe ingang af om die functie aan te roepen. Beide
Gate 2-reviewers wezen daar onafhankelijk op: zonder deze guard gebeurt OP-260 een derde
keer, en dan weer pas maanden later zichtbaar.

**Wat deze guard toetst.** Elke functie in `src/` die `verify_token(...)` aanroept en niet
`_weiger_als_ingetrokken(...)`, moet met reden in `KNOWN_ZONDER_INTREKKINGSCONTROLE` staan.
Een nieuwe zo'n functie is dus geblokkeerd tot iemand hem bewust opschrijft.

**De sleutel is `bestand::functie` en niet het bestand** -- ADR-036 OP-258 mat dat een lijst
met het BESTAND als sleutel de guard blind maakt op precies dat bestand: drie mutaties in
`crud_router.py` bleven groen omdat er al een legitieme uitzondering in dat bestand stond.

**Geneste functies worden met expliciete recursie bijgehouden**, niet met `ast.walk()` vanaf
een functieknoop: die onderscheidt een geneste functie niet van haar ouder.

Mutatiebewijs (2026-09-19, beide richtingen):
- een nieuwe functie in `src/` die `verify_token` aanroept en niet op de lijst staat -> ROOD;
- een regel uit de lijst halen terwijl de functie nog bestaat -> ROOD;
- een regel op de lijst laten staan die niet meer voorkomt -> ROOD via de staleness-test;
- ongemuteerd -> GROEN.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator

REPO_WORTEL = pathlib.Path(__file__).resolve().parents[2]
BRON = REPO_WORTEL / "src"

#: Functies die `verify_token` aanroepen zonder de intrekkingscontrole, met de reden.
#: Gedateerd 2026-09-19. Twee soorten, bewust uit elkaar gehouden.
KNOWN_ZONDER_INTREKKINGSCONTROLE: dict[str, str] = {
    # -- GEEN authenticatiebeslissing: introspectie, verversing, of alleen een veld lezen.
    "src/core/api/auth/router_token.py::validate_token": (
        "introspectie-endpoint; het antwoord IS de geldigheid, niet een toegangsbesluit"
    ),
    "src/core/api/auth/router_token.py::verify_token_endpoint": "idem introspectie",
    "src/core/api/auth/router_token.py::revoke_token_endpoint": (
        "moet juist met een (mogelijk al) ingetrokken token kunnen werken"
    ),
    "src/core/api/auth/router_token.py::_is_eigen_refresh_token": (
        "2026-10-14 (beveiligingsnazorg): leest alleen `sub` om te bepalen of het refresh-token van "
        "de uitloggende gebruiker is; het geeft geen toegang, en een al ingetrokken token intrekken "
        "is idempotent"
    ),
    "src/core/api/dependencies.py::verify_token": (
        "kale wrapper om jwt_handler.verify_token; de AANROEPER beslist over toegang"
    ),
    "src/core/auth/jwt_handler.py::JWTHandler.verify_token_with_blacklist": (
        "heeft zijn eigen blacklist-parameter; nul productie-aanroepers (OP-188)"
    ),
    "src/core/auth/oauth2_service.py::OAuth2Service.is_token_valid": (
        "raadpleegt de blacklist zelf; dit IS de introspectie"
    ),
    "src/core/auth/oauth2_service.py::OAuth2Service.extract_token_claims": (
        "leest claims, neemt geen besluit"
    ),
    "src/core/auth/oauth2_service.py::OAuth2Service.refresh_access_token": (
        "verversingsflow; controleert de blacklist apart (oauth2_service.py:210)"
    ),
    "src/core/auth/oauth2_service.py::OAuth2Service.revoke_token": "intrekken zelf",
    "src/core/auth/token_refresh.py::TokenRefreshService.refresh_token": "verversingsflow",
    "src/core/middleware/rate_limit_middleware.py"
    "::RateLimitMiddleware._extract_tenant_id_from_request": (
        "leest alleen de tenant voor de limietsleutel; geen toegangsbesluit"
    ),
    "src/core/middleware/tenant_middleware.py::TenantMiddleware.__call__": (
        "leidt alleen de tenant af; draait ook op paden zonder databasesessie"
    ),
    "src/core/security/security_middleware.py::SecurityMiddleware._extract_user_id": (
        "leest alleen sub voor logging/limieten; geen toegangsbesluit"
    ),
    # -- WEL een authenticatiebeslissing, en dus een GAT. Gemeten 2026-09-19, doorgegeven aan
    #    de regie voor een eigen brief. Deze regels horen te VERDWIJNEN als dat werk klaar is;
    #    de staleness-test hieronder dwingt dat af zodra de functie de controle wel krijgt.
    "src/core/auth/websocket_auth.py::WebSocketAuthenticator.authenticate": (
        "GAT: websocket-auth zonder blacklist. WebSocketAuthenticator heeft geen AsyncSession, "
        "dus dit is een ontwerpstap. Bovendien controleert een websocket alleen bij het "
        "OPZETTEN: een verbinding van voor de intrekking blijft open."
    ),
    "src/core/auth/websocket_auth.py::WebSocketAuthenticator.authenticate_connected_user": (
        "GAT: idem, zelfde klasse"
    ),
    "src/core/websocket/manager.py::ConnectionManager.connect": (
        "GAT: eigen inline websocket-auth zonder blacklist"
    ),
    "src/core/api/v1/focus_builder/shared.py::validate_ws_token": (
        "GAT: websocket-token zonder blacklist"
    ),
    "src/core/api/v1/focus_builder/ws_dependencies.py::WebSocketAuthHandler.validate_token": (
        "GAT: gaat via de kale wrapper in api/dependencies.py, dus zonder blacklist"
    ),
    "src/core/security/security_middleware.py::SecurityMiddleware._check_authentication": (
        "GAT: echte authenticatiebeslissing (aangeroepen op security_middleware.py:185), "
        "synchroon en zonder databasesessie -- zelfde ontwerpprobleem als de websockets"
    ),
    "src/core/auth/auth_bearer.py::get_current_user": (
        "GAT, maar DOOD: nul aanroepers in src/ (gemeten 2026-09-19). Heet wel "
        "get_current_user, dus de eerste importeur erft het gat."
    ),
}


def _functies(knoop: ast.AST, klasse: str | None = None) -> Iterator[tuple[str, ast.AST]]:
    """Loop de boom af en houd de omsluitende naam bij met EXPLICIETE recursie."""
    for kind in getattr(knoop, "body", []):
        if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
            naam = "%s.%s" % (klasse, kind.name) if klasse else kind.name
            yield naam, kind
            yield from _functies(kind, klasse)
        elif isinstance(kind, ast.ClassDef):
            yield from _functies(kind, kind.name)
        else:
            yield from _functies(kind, klasse)


def _roept_aan(functie: ast.AST, naam: str) -> bool:
    """True als deze functie ergens `naam(...)` aanroept. Toetst de AANROEP, niet de tekst."""
    for knoop in ast.walk(functie):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        if isinstance(doel, ast.Attribute) and doel.attr == naam:
            return True
        if isinstance(doel, ast.Name) and doel.id == naam:
            return True
    return False


def _gevonden() -> set[str]:
    """Alle `bestand::functie` die verify_token aanroepen zonder de intrekkingscontrole."""
    uit: set[str] = set()
    bestanden = 0
    for pad in BRON.rglob("*.py"):
        try:
            boom = ast.parse(pad.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as fout:
            raise AssertionError("Kan %s niet ontleden: %s" % (pad, fout)) from fout
        bestanden += 1
        rel = pad.relative_to(REPO_WORTEL).as_posix()
        for naam, functie in _functies(boom):
            if _roept_aan(functie, "verify_token") and not _roept_aan(
                functie, "_weiger_als_ingetrokken"
            ):
                uit.add("%s::%s" % (rel, naam))
    assert bestanden > 500, (
        "Maar %d bestanden gescand in %s. Dat is te weinig voor deze repo; de scan is stuk "
        "en een lege uitslag zou deze guard stilletjes groen houden." % (bestanden, BRON)
    )
    return uit


def test_geen_nieuwe_auth_ingang_zonder_intrekkingscontrole() -> None:
    """Een NIEUWE functie die verify_token aanroept moet bewust worden opgeschreven."""
    nieuw = sorted(_gevonden() - set(KNOWN_ZONDER_INTREKKINGSCONTROLE))
    assert not nieuw, (
        "Deze functies roepen `verify_token` aan zonder `_weiger_als_ingetrokken`:\n  %s\n\n"
        "Neemt die functie een TOEGANGSBESLUIT, roep dan `_weiger_als_ingetrokken(payload, db)` "
        "aan -- anders werkt een ingetrokken token daar gewoon (ADR-036 OP-260). Doet hij "
        "alleen introspectie, verversing of het lezen van een veld, zet hem dan met die reden "
        "in KNOWN_ZONDER_INTREKKINGSCONTROLE." % "\n  ".join(nieuw)
    )


def test_de_uitzonderingslijst_is_niet_verouderd() -> None:
    """Een uitzondering die is opgelost of hernoemd MOET van de lijst -- anders rot hij dicht."""
    gevonden = _gevonden()
    verdwenen = sorted(k for k in KNOWN_ZONDER_INTREKKINGSCONTROLE if k not in gevonden)
    assert not verdwenen, (
        "Deze regels staan op de uitzonderingslijst maar komen niet meer voor:\n  %s\n\n"
        "Ofwel de functie heeft de controle nu wel (mooi -- haal de regel weg), ofwel hij is "
        "hernoemd of verwijderd (haal hem ook weg). Een lijst die niet meekrimpt, verbergt "
        "op den duur een echt gat." % "\n  ".join(verdwenen)
    )

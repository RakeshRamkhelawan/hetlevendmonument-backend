"""Geen enkel tokenendpoint mag een token uitgeven zonder het wachtwoord te controleren (OP-61).

**Wat er stond.** `src/core/tool_broker/router.py::get_token` toetste uitsluitend
`len(request.password) >= 8` -- geen enkele controle tegen de database -- en zette het opgegeven
e-mailadres in het token. `auth/dependencies.py` lost de gebruiker daarna uit precies die claim op
en geeft de ECHTE databasegebruiker terug, met zijn rollen, tenant en `is_superuser`. Wie dat
endpoint kon bereiken kreeg een token dat als iedere andere gebruiker gold.

De guard ernaast vergeleek `settings.environment == "production"` exact, zonder `.lower()`, terwijl
`is_production()` in `shared/config.py` dat wel doet. Staging, blue en green vielen er dus buiten.

Het endpoint was niet geserveerd -- nul importeurs -- maar dat is geen borging: het stond een
enkele `include_router`-regel van bereikbaar zijn af. Beide blinde reviewers van 2026-08-06
adviseerden verwijderen. Dat is gebeurd; de echte inlogstroom is `/api/v1/auth/token`.

**Wat deze guard doet.** Een HTTP-ENDPOINT dat een toegangstoken teruggeeft MOET in diezelfde
functie het wachtwoord verifieren. Het onderscheid endpoint-versus-fabriek is de kern: de eerste
versie van deze guard keek naar elke functie en betrapte daarmee twaalf legitieme tokenfabrieken
(`jwt_handler.create_access_token` en soortgelijke). Die horen geen wachtwoord te kennen -- hun
aanroepers verifieren. Het risico zit bij wat van buiten bereikbaar is.

**Herziening 2026-08-09 (ADR-036 M-1). De guard onderzocht NUL endpoints.** Twee gaten tegelijk:

1. *Hij keek naar de verkeerde functienaam.* De kandidatenlijst kwam uit
   `git grep create_access_token`, maar de echte inlogstroom geeft zijn token uit via
   `oauth2_service.create_tokens`. Alle twaalf gevonden bestanden waren fabrieken zonder
   route-decorator, dus de guard doorliep een lege verzameling en meldde groen. Een vangnet dat
   BESTANDEN telt ziet dat niet -- daarom telt `test_the_guard_actually_examines_an_endpoint`
   nu ENDPOINTS.
2. *Hij toetste tekst in plaats van een handeling.* Zie `_aangeroepen_namen` voor de drie
   generaties en waarom alleen aanroep-positie telt.

**Mutatietest (2026-08-09, beide richtingen, 4/4 zoals verwacht):**

| Mutatie | Verwacht | Gemeten |
| --- | --- | --- |
| `verify_password` uit `router_login.py::login` gehaald | ROOD | ROOD |
| Een endpoint met alleen `raise ValueError("Could not authenticate user")` | ROOD | ROOD |
| Een endpoint met `password_hash = None` en `authenticate = False` als kale namen | ROOD | ROOD |
| LEGITIEM: een endpoint dat `authenticate_user(request)` AANROEPT | GROEN | GROEN |

De tweede en de derde zijn precies de twee omzeilingen die de vorige twee generaties van deze
guard doorlieten. Ze staan hier als tabel en niet als proza omdat de volgende lezer moet kunnen
zien WAAR de grens ligt zonder hem opnieuw uit te vinden.

**Bekend residu, expliciet en niet opgelost.** Dit blijft een naam-heuristiek: een helper die
`authenticate_user` heet en niets doet, houdt de guard groen. En een refactor naar een naam
buiten `_VERIFICATION_MARKERS` (bijvoorbeeld `_check_credentials`) maakt hem vals-positief.
Beide zijn inherent aan een statische toets. Ze staan hier zodat de volgende lezer ze niet
"oplost" met een regel in `KNOWN_EXEMPT` -- dat is precies hoe een guard leegloopt.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Wat als "het wachtwoord is echt gecontroleerd" telt. Bewust breed: het doel is een functie
#: betrappen die HELEMAAL niets verifieert, niet voorschrijven welke helper je gebruikt.
#:
#: `password_hash` en `get_user_by_email` stonden hier tot 2026-08-09 ook in en zijn eruit.
#: Dat zijn geen HANDELINGEN: `user.hashed_password` lezen of een gebruiker opzoeken verifieert
#: niets, en als marker maakten ze de guard blind voor precies het endpoint dat een gebruiker
#: ophaalt en daarna zonder controle een token uitgeeft.
_VERIFICATION_MARKERS = (
    "verify_password",
    "check_password",
    "authenticate",
    "verify_credentials",
    "pwd_context",
)

#: Functies die een toegangstoken uitgeven. `create_tokens` stond hier niet, en daardoor
#: onderzocht deze guard NUL endpoints: de echte inlogstroom (`api/auth/router_login.py::login`)
#: gebruikt `oauth2_service.create_tokens`, niet `create_access_token`. Gemeten 2026-08-09.
_TOKEN_MARKERS = ("create_access_token", "create_tokens")

#: Bestanden waar een tokenuitgifte zonder eigen wachtwoordcheck legitiem is, met reden per regel.
#: Was leeg tot 2026-08-26, en dat was tot dan bewust zo. De eerste versie van deze guard had
#: hier de tokenfabrieken in moeten zetten omdat hij ze ten onrechte betrapte. Door alleen naar
#: ENDPOINTS te kijken is die lijst niet meer nodig voor DIE fout -- een uitzonderingslijst die
#: je nodig hebt om je eigen valse positieven te onderdrukken is een teken dat de guard het
#: verkeerde meet. De regel hieronder is een ANDER geval: geen valse positief van de guard, maar
#: een endpoint dat ECHT en OPZETTELIJK geen wachtwoord controleert, omdat het per ontwerp geen
#: wachtwoord-gebaseerde authenticatie is.
#:
#: `src/core/api/v1/foundation/auth.py` (ADR-029, Foundation Portal, BE-EP-023, 2026-08-25):
#: magic-link-authenticatie. De veiligheidseigenschap komt niet van een wachtwoord maar van
#: het bezit van een cryptografisch willekeurig, eenmalig, 15-minuten-verlopend token dat per
#: e-mail naar een geverifieerd adres is gestuurd, atomisch verzilverd via
#: `UPDATE ... WHERE used_at IS NULL` (vervangingsbescherming). Dit is geen omissie die dit
#: OP-61-defect herhaalt (het oorspronkelijke lek accepteerde een e-mailadres UIT DE REQUEST
#: zonder enige verificatie) -- het bezit van het token IS de verificatie. Bestandsniveau (niet
#: functieniveau) is de granulariteit van deze lijst: heel `auth.py` is uitsluitend
#: magic-link-endpoints (`request_magic_link`, `verify_magic_link`, `logout`), geen enkele
#: functie erin gebruikt of behoort een wachtwoord te gebruiken.
KNOWN_EXEMPT: dict[str, str] = {
    "src/core/api/v1/foundation/auth.py": (
        "Magic-link auth (ADR-029/BE-EP-023): geen wachtwoord per ontwerp -- de "
        "veiligheid zit in het bezit van een eenmalig, verlopend, atomisch-verzilverd "
        "token, niet in een wachtwoordcontrole. Zie de module-docstring hierboven."
    ),
}



def _aangeroepen_namen(functie: ast.AST) -> set[str]:
    """De namen die deze functie daadwerkelijk AANROEPT (ADR-036 M-1, 2026-08-09).

    **Waarom niet meer op tekst, en ook niet op identifiers.** Er zijn hier drie generaties
    geweest, en elke opvolger deelde de blinde vlek van zijn voorganger:

    1. `naam in ast.dump(functie)` -- de dump rendert de DOCSTRING mee. Een endpoint dat
       "authenticate" alleen in zijn toelichting noemde, haalde de toets (OP-101).
    2. Docstring strippen en dan opnieuw `in ast.dump(...)` -- maar dat verwijdert alleen de
       BUITENSTE docstring. Elke andere string in de body telt nog mee, dus een gewone
       401-melding `detail="Could not authenticate user"` maakte de guard blind (M-1).
    3. Matchen op identifiers (`ast.Name.id`, `ast.Attribute.attr`) -- dan volstaat
       `password_hash = None` of een parameter die `authenticate` heet. Een NAAM is geen
       HANDELING.

    Daarom: alleen namen in AANROEP-positie. Van `pwd_context.verify(...)` tellen zowel
    `verify` als `pwd_context` mee -- de ontvanger van een methodeaanroep hoort erbij, anders
    vindt een marker als `pwd_context` nooit iets.
    """
    namen: set[str] = set()
    for knoop in ast.walk(functie):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        if isinstance(doel, ast.Attribute):
            namen.add(doel.attr)
            ontvanger = doel.value
            if isinstance(ontvanger, ast.Name):
                namen.add(ontvanger.id)
            elif isinstance(ontvanger, ast.Attribute):
                namen.add(ontvanger.attr)
        elif isinstance(doel, ast.Name):
            namen.add(doel.id)
    return namen


def _roept_iets_aan_met(functie: ast.AST, markers: tuple[str, ...]) -> bool:
    """Roept deze functie iets aan waarvan de naam een van `markers` bevat?

    Substring BINNEN een aangeroepen naam blijft toegestaan, zodat `authenticate_user(...)` als
    verificatie telt. Het verschil met vroeger is dat de tekst uit een STRING nooit meer
    meetelt -- alleen wat echt wordt aangeroepen.
    """
    namen = _aangeroepen_namen(functie)
    return any(marker in naam for naam in namen for marker in markers)

def _files_that_create_tokens() -> list[Path]:
    """Bronbestanden die `create_access_token` aanroepen, via `git grep` als bewijsbare superset.

    Bewust `git grep` en niet zelf alle bestanden inlezen: een test die de hele boom in Python
    leest heeft eerder een xdist-worker omgebracht, wat zich voordeed als willekeurige failures
    elders (ADR-036 OP-19/OP-46).

    **Beperking, gemeten en niet aangenomen.** `git grep` ziet alleen bestanden die in versiebeheer
    zitten. Een NIEUW, nog niet toegevoegd bestand valt er dus buiten: bij het mutatietesten bleef
    deze guard groen tot het mutantbestand met `git add -N` was aangemeld, en werd toen wel rood.
    In CI is dat geen gat -- daar is per definitie alles gecommit -- maar wie lokaal een nieuw
    endpoint schrijft krijgt de waarschuwing pas na `git add`.
    """
    result = subprocess.run(
        ["git", "grep", "-l", "-I", "-E", "|".join(_TOKEN_MARKERS), "--", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"`git grep` faalde (rc={result.returncode}): {result.stderr.strip()!r}. Een guard "
            "die de returncode negeert leest een lege uitvoer als 'niets gevonden' en meldt "
            "groen -- die faalvorm staat al in quality-gates.md."
        )
    return [REPO_ROOT / line for line in result.stdout.split("\n") if line.strip()]


def _is_http_endpoint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Heeft deze functie een route-decorator (`@router.post(...)`, `@app.get(...)`)?

    Dit onderscheid IS de guard. Een tokenfabriek zoals `jwt_handler.create_access_token` hoort
    geen wachtwoord te kennen -- zijn aanroepers verifieren. De eerste versie van deze test miste
    dat en betrapte twaalf legitieme fabrieken; dan zegt hij niets meer. Het risico zit bij een
    ENDPOINT: dat is van buiten bereikbaar en geeft het token aan de aanroeper terug.
    """
    for decorator in node.decorator_list:
        call = decorator.func if isinstance(decorator, ast.Call) else decorator
        if not isinstance(call, ast.Attribute):
            continue
        if call.attr not in {"get", "post", "put", "patch", "delete"}:
            continue
        target = call.value
        name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
        if "router" in name.lower() or "app" in name.lower():
            return True
    return False


def _parsed_token_creating_files() -> tuple[dict[Path, ast.AST], list[str]]:
    """Geparste AST per kandidaatbestand (uit _files_that_create_tokens), plus paden die
    niet gelezen/geparsed konden worden.

    Gedeeld door de twee functies hieronder die eerder allebei onafhankelijk (en stil)
    hun eigen parse-fouten wegslikten -- een bestand met een syntaxfout EN een
    ongeverifieerde tokenuitgifte erin viel zo buiten BEIDE scans zonder enige melding.
    """
    bomen: dict[Path, ast.AST] = {}
    fouten: list[str] = []
    for path in _files_that_create_tokens():
        try:
            bomen[path] = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {exc}")
    return bomen, fouten


def _functions_creating_tokens_without_verification(tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_http_endpoint(node):
            continue
        if not _roept_iets_aan_met(node, _TOKEN_MARKERS):
            continue
        if _roept_iets_aan_met(node, _VERIFICATION_MARKERS):
            continue
        offenders.append(node.name)
    return offenders


def _onderzochte_endpoints() -> list[str]:
    """De endpoints die deze guard DAADWERKELIJK beoordeelt.

    Bestaat omdat de guard tot 2026-08-09 nul endpoints onderzocht en toch groen meldde. Het
    vangnet eronder toetste alleen of er BESTANDEN waren die `create_access_token` noemen -- en
    die zijn er, twaalf stuks, allemaal tokenfabrieken zonder route-decorator. Een guard die
    een lege verzameling doorloopt is per definitie groen.
    """
    gevonden: list[str] = []
    bomen, _fouten = _parsed_token_creating_files()
    for pad, boom in bomen.items():
        for node in ast.walk(boom):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_http_endpoint(node) and _roept_iets_aan_met(node, _TOKEN_MARKERS):
                gevonden.append(f"{pad.relative_to(REPO_ROOT).as_posix()}::{node.name}")
    return gevonden


def test_the_scan_finds_token_creation_at_all() -> None:
    """Vangnet op de BESTANDEN. Nodig, maar aantoonbaar niet genoeg -- zie hieronder."""
    found = _files_that_create_tokens()

    assert found, (
        f"Geen enkel bestand in src/ roept {' of '.join(_TOKEN_MARKERS)} aan. Is de functie "
        "hernoemd? Zolang dit leeg terugkomt is de guard hieronder betekenisloos."
    )


def test_the_guard_actually_examines_an_endpoint() -> None:
    """Vangnet op het ANTWOORD: onderzoekt deze guard wel iets? (ADR-036 M-1)

    **Dit is de belangrijkste test in dit bestand, en hij ontbrak.** Op 2026-08-09 gemeten:
    de guard doorliep NUL endpoints en meldde daarmee vrolijk groen. De twaalf bestanden die
    `create_access_token` noemen zijn allemaal tokenfabrieken zonder route-decorator; de echte
    inlogstroom geeft zijn token uit via `oauth2_service.create_tokens` en viel dus volledig
    buiten de kandidatenlijst.

    Een guard die een lege verzameling doorloopt is per definitie groen. Dat is exact de
    faalvorm "de guard toetst de LIJST in plaats van het ANTWOORD" uit quality-gates.md, en
    het vangnet erboven ving hem niet -- dat telt bestanden, niet endpoints.
    """
    onderzocht = _onderzochte_endpoints()

    assert onderzocht, (
        "Deze guard onderzoekt geen enkel endpoint, en is daarmee betekenisloos ongeacht wat "
        f"hij meldt. Gezocht naar functies met een route-decorator die {_TOKEN_MARKERS} "
        "aanroepen. Is de tokenuitgifte naar een andere functienaam verhuisd? Vul dan "
        "_TOKEN_MARKERS aan."
    )


def test_no_candidate_file_is_silently_unparseable() -> None:
    """Vangnet: een onleesbaar/onparseerbaar kandidaatbestand mag beide scans hierboven en
    hieronder niet blind maken.

    Een bestand met een syntaxfout EN een ongeverifieerde tokenuitgifte erin zou zonder dit
    vangnet stil buiten zowel test_the_guard_actually_examines_an_endpoint als de eigenlijke
    wachtwoordcontrole vallen -- de twee bestaande "niet leeg"-vangnetten zien dat niet, want
    de overige kandidaatbestanden houden ze niet-leeg.
    """
    _, fouten = _parsed_token_creating_files()
    assert not fouten, (
        "Deze kandidaatbestanden konden niet gelezen/geparsed worden en zijn NIET "
        "gecontroleerd op een tokenuitgifte zonder wachtwoordverificatie:\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )


def test_no_endpoint_hands_out_a_token_without_checking_the_password() -> None:
    offenders: list[str] = []
    bomen, _fouten = _parsed_token_creating_files()
    for path, tree in bomen.items():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in KNOWN_EXEMPT:
            continue
        for name in _functions_creating_tokens_without_verification(tree):
            offenders.append(f"{relative}::{name}")

    assert not offenders, (
        f"Deze functies maken een toegangstoken aan zonder het wachtwoord te verifieren: "
        f"{sorted(offenders)}.\n\n"
        "Dat is geen theoretisch risico: `auth/dependencies.py` lost de gebruiker op uit de "
        "e-mailclaim in het token en geeft de ECHTE databasegebruiker terug, met zijn rollen en "
        "tenant. Een token dat zonder wachtwoordcontrole wordt uitgegeven geldt dus als iedere "
        "gebruiker die je kunt noemen (ADR-036 OP-61)."
    )


def test_the_removed_endpoint_has_not_returned() -> None:
    """Specifiek het endpoint dat op 2026-08-06 is verwijderd.

    Los van de heuristiek hierboven: dit pad had een eigen guard op de omgevingsnaam die
    hoofdlettergevoelig was, en dat soort constructies komt makkelijk terug via een oude branch.
    """
    router = REPO_ROOT / "src/core/tool_broker/router.py"
    if not router.exists():
        return

    source = router.read_text(encoding="utf-8")

    assert "/auth/token" not in source, (
        "`src/core/tool_broker/router.py` biedt weer een `/auth/token`-endpoint aan. Dat bestand "
        "wordt niet geserveerd, maar het staat een enkele `include_router`-regel van bereikbaar af. "
        "De echte inlogstroom is `/api/v1/auth/token` (ADR-036 OP-61)."
    )


def test_known_exempt_is_not_stale() -> None:
    """Een uitzondering die niet meer bestaat MOET eruit."""
    stale = [name for name in KNOWN_EXEMPT if not (REPO_ROOT / name).exists()]

    assert not stale, (
        f"Deze bestanden staan in KNOWN_EXEMPT maar bestaan niet meer: {stale}. Haal ze uit de "
        "lijst; anders suggereert die lijst een uitzondering die nergens op slaat."
    )

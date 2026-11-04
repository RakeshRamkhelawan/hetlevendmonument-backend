"""Twee invarianten rond `adopt_tenant` en de resterende kale bypass-blokken (OP-154).

**Waarom dit bestand bestaat.** Bij de Gate 2-review van stap 2 op 2026-09-15 is GEMETEN
dat het oude vocabulaire veiliger was dan het nieuwe op een punt dat niemand had bedacht:

    adopt_tenant(db, gevonden.tenant_id)  ->  adopt_tenant(db, 1)
    pytest tests/architecture/test_auth_router_queries_bypass_the_tenant_filter.py
    -> rc=0, 2 passed

`TenantFilterBypass()` heeft GEEN argument en dus geen aanvalsoppervlak. `adopt_tenant`
heeft er een, en dat argument bepaalt in zijn eentje in welke tenant de rest van het
verzoek draait. De bestaande guard keek er niet naar. Daarmee was de NOOIT-regel
"tenant_id nooit uit een request body" syntactisch te overtreden op het authenticatiepad
zonder dat iets het meldde.

**Mutatiebewijs, beide richtingen (2026-09-15):**

1. `adopt_tenant(db, gevonden.tenant_id)` -> `adopt_tenant(db, 1)` in `router_login.py`
   -> `test_de_aangenomen_tenant_is_geen_constante` ROOD met bestand en regel.
2. `-> adopt_tenant(db, form_data.tenant_id)` -> `test_de_aangenomen_tenant_komt_niet_uit_de_invoer`
   ROOD.
3. Ongewijzigd -> GROEN, en `test_de_meting_is_niet_leeg` bewaakt dat er uberhaupt
   `adopt_tenant`-aanroepen gevonden worden.
4. Een NIEUW kaal `TenantFilterBypass`-blok in `router_login.py`
   -> `test_geen_nieuwe_kale_bypass_op_het_authenticatiepad` ROOD.
5. Een bestaand blok uit `KNOWN_KALE_BYPASS` weggehaald -> `test_lijst_is_niet_verouderd`
   ROOD per element.

**Stand 2026-09-16: `KNOWN_KALE_BYPASS` IS LEEG.** Alle zeven blokken zijn omgezet (OP-154
stap 2b). Mutatie 5 hierboven is daarmee niet meer op een echt element uit te voeren; de
staleness-test blijft staan voor het geval er ooit weer een regel bij komt.

Dat leegraken maakte een ontwerpfout in het vangnet zichtbaar. `test_de_meting_is_niet_leeg`
eiste ook dat er nog minstens EEN kaal blok op het auth-pad bestond, als bewijs dat de
detectie werkte. Die eis houdt precies zolang het werk niet af is: hij dwong te kiezen
tussen een lege guard en een achtergelaten bypass. De detectie zit nu in
`_kale_bypass_in_boom()` en wordt getoetst op een SYNTHETISCH voorbeeld
(`test_de_detectie_werkt_nog`), in beide richtingen: een kaal blok wordt gevonden, een
`adopt_tenant`-blok niet.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
AUTH_PADEN = (
    SRC_DIR / "core" / "api" / "auth",
    SRC_DIR / "core" / "auth",
)

#: Namen waaruit een tenant NOOIT mag komen: dat is invoer van de aanvrager.
INVOERBRONNEN = frozenset(
    {"request", "form_data", "data", "payload", "body", "params", "query", "headers"}
)

# Gedateerd 2026-09-15. Kale `TenantFilterBypass`-blokken op het authenticatiepad die
# PUUR LEZEN. Die vallen buiten `test_bypass_lezen_en_schrijven_blijven_bij_elkaar` -- dat
# meet een andere invariant (lezen binnen, schrijven buiten) en ziet een puur lezend blok
# niet. Zonder deze lijst zouden ze bij stap 3 stil nul rijen gaan geven, zonder anker.
#
# Reden PER REGEL, met wat er stilvalt. Deze horen bij OP-154 stap 2b.
KNOWN_KALE_BYPASS: dict[tuple[str, str], str] = {
    # OPGELOST 2026-09-16 (OP-154 stap 2b): `router_password.py::forgot_password`.
    # Leest nu via `pre_auth_lookup` alleen `id` en `tenant_id`, neemt daarna de klant aan
    # en doet de auditregel binnen die klant. Onderweg gemeten en meteen hersteld: de oude
    # query gebruikte `scalar_one_or_none()` over ALLE klanten heen, terwijl `users.email`
    # alleen per klant uniek is -- twee klanten met hetzelfde adres gaven een
    # `MultipleResultsFound` die door de `except Exception` werd opgevangen, waarna de route
    # alsnog de neutrale melding gaf. Wachtwoordherstel was voor die gebruikers dus al stil
    # kapot, ook zonder de omschakeling.
    # OPGELOST 2026-09-16 (OP-154 stap 2b): `router_registration.py::register_user`.
    # Hier stond dat de registratie zou SLAGEN als de controle stilvalt. Nagemeten klopt
    # dat niet: `require_tenant_id()` staat boven het blok en werpt een fout als er geen
    # klantcontext is, dus die context staat er al. De omzeiling maakte de controle
    # PLATFORMBREED terwijl de database hem straks per klant afschermt -- de twee lagen
    # zouden tegengesteld werken. De omzeiling is weggehaald; de controle is nu
    # klantgebonden, precies wat `idx_user_tenant_email` ook afdwingt, en de
    # gebruikersenumeratie over een klantgrens is daarmee weg.
    # OPGELOST 2026-09-16 (OP-154 stap 2b): `router_token.py::validate_token` en
    # `::verify_token_endpoint`. Beide lezen nu via `pre_auth_lookup` alleen `id` en
    # `tenant_id` en nemen daarna de klant aan. De klant komt dus uit de DATABASE en niet
    # uit het token, ook al is dat geverifieerd. Meegenomen: beide comments beriepen zich
    # op `EXCLUDED_PREFIXES` van de tenant-middleware, en daar staat geen enkel auth-pad in
    # (nagemeten) -- de uitkomst klopte, het mechanisme niet.
    # OPGELOST 2026-09-16 (OP-154 stap 2b): `oauth2_service.py::refresh_access_token`,
    # `auth_service.py::get_user_by_id` en `::get_user_by_email`. Alle drie lezen nu via
    # `pre_auth_lookup` alleen `id` en `tenant_id` en laden de rij daarna binnen de
    # aangenomen klant -- inclusief de rollen, die dus AFGESCHERMD worden geladen in plaats
    # van via een omzeiling.
    #
    # `get_user_by_email` gebruikt `.one_or_none()` en nadrukkelijk niet `.first()`:
    # `users.email` is alleen uniek per klant, dus bij hetzelfde adres bij twee klanten is
    # er geen goed antwoord af te leiden. Luid falen is daar veiliger dan stil een klant
    # kiezen. Diezelfde afweging is op 2026-09-16 ook in `forgot_password` toegepast, nadat
    # ik daar eerst `.first()` had gezet en dat dezelfde dag heb teruggedraaid.
    #
    # DE LIJST IS HIERMEE LEEG. Dat is het doel van deze lijst: hij hoort te verdwijnen,
    # niet te blijven staan. `test_lijst_is_niet_verouderd` bewaakt dat er niets in staat
    # wat al is opgelost; `test_geen_nieuwe_kale_bypass_op_het_authenticatiepad` blokkeert
    # een nieuw geval.
}


def _python_bestanden() -> list[Path]:
    bestanden: list[Path] = []
    for map_ in AUTH_PADEN:
        if map_.exists():
            bestanden.extend(sorted(map_.rglob("*.py")))
    return bestanden


def _alle_bronbestanden() -> list[Path]:
    """Heel `src/`, want `adopt_tenant` wordt al lang niet meer alleen op het auth-pad gebruikt.

    Verbreed op 2026-09-17 (ADR-036, restlijst-punt D4). Tot die dag keken de twee
    `adopt_tenant`-guards hieronder alleen in `src/core/api/auth` en `src/core/auth` --
    de twee mappen waar het patroon is ontstaan. Gemeten op 2026-09-17: er zijn
    ZEVENENTWINTIG bestanden in `src/` die `adopt_tenant` noemen, waarvan er
    TWEEENTWINTIG buiten die twee mappen liggen (onder meer `app_lifespan.py`,
    `database/seed.py`, `services/tenant_service.py`, `auth/rbac.py`, `jobs/*.py`,
    `workers/workflow_worker.py`). Voor al die aanroepen bewaakte niets dat de tenant geen
    constante is en niet uit de invoer van de aanvrager komt -- precies de twee dingen
    waar deze guards voor bestaan.

    Het bereik is opzettelijk `src/` en niet alleen de bekende lijst: een lijst loopt
    achter zodra iemand een aanroeper toevoegt, en dat is exact hoe dit gat is ontstaan.

    De `TenantFilterBypass`-guards verderop houden wel het auth-bereik: die gaan over het
    authenticatiepad zelf en niet over `adopt_tenant`.
    """
    return sorted(SRC_DIR.rglob("*.py"))


def _adopt_tenant_aanroepen() -> list[tuple[str, int, ast.expr]]:
    """(bestand, regel, het TWEEDE argument) van elke `adopt_tenant(...)`-aanroep."""
    gevonden: list[tuple[str, int, ast.expr]] = []
    for pad in _alle_bronbestanden():
        tekst = pad.read_text(encoding="utf-8", errors="ignore")
        if "adopt_tenant" not in tekst:
            continue
        try:
            boom = ast.parse(tekst)
        except SyntaxError:  # pragma: no cover
            continue
        relatief = pad.relative_to(REPO_ROOT).as_posix()
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Call):
                continue
            functie = knoop.func
            naam = (
                functie.id
                if isinstance(functie, ast.Name)
                else functie.attr
                if isinstance(functie, ast.Attribute)
                else ""
            )
            if naam == "adopt_tenant" and len(knoop.args) >= 2:
                gevonden.append((relatief, knoop.lineno, knoop.args[1]))
    return gevonden


def _wortelnaam(knoop: ast.expr) -> str:
    """De naam waar een attribuutketen op begint: `a.b.c` -> `a`."""
    huidig: ast.expr = knoop
    while isinstance(huidig, ast.Attribute):
        huidig = huidig.value
    return huidig.id if isinstance(huidig, ast.Name) else ""


def test_de_aangenomen_tenant_is_geen_constante() -> None:
    """Een vaste waarde zet ELK verzoek in dezelfde tenant -- stil en catastrofaal."""
    fout = [
        f"  {bestand}:{regel}"
        for bestand, regel, arg in _adopt_tenant_aanroepen()
        if isinstance(arg, ast.Constant)
    ]
    assert not fout, (
        "`adopt_tenant` krijgt een CONSTANTE als tenant:\n"
        + "\n".join(fout)
        + "\n\nDan draait elk verzoek in die ene tenant, ongeacht wie er inlogt. De waarde "
        "hoort uit de zojuist gevonden gebruiker te komen (ADR-036 OP-154)."
    )


def test_de_aangenomen_tenant_komt_niet_uit_de_invoer() -> None:
    """CLAUDE.md NOOIT-lijst: tenant_id komt nooit uit een request body of formulier."""
    fout = [
        f"  {bestand}:{regel} (uit `{_wortelnaam(arg)}`)"
        for bestand, regel, arg in _adopt_tenant_aanroepen()
        if _wortelnaam(arg) in INVOERBRONNEN
    ]
    assert not fout, (
        "`adopt_tenant` krijgt een tenant die uit de INVOER van de aanvrager komt:\n"
        + "\n".join(fout)
        + "\n\nDaarmee kiest de aanvrager zelf in welke tenant zijn verzoek draait. De "
        "waarde hoort uit de database te komen, uit de zojuist gevonden gebruiker."
    )


def _kale_bypass_in_boom(boom: ast.AST, relatief: str) -> set[tuple[str, str]]:
    """De detectie zelf, losgekoppeld van het inlezen van bestanden.

    Losgekoppeld sinds 2026-09-16 zodat `test_de_detectie_werkt_nog` hem op een SYNTHETISCH
    voorbeeld kan draaien. Daarvoor leunde dat vangnet erop dat er nog een echt kaal blok
    op het auth-pad bestond -- en dat is precies wat deze iteratie moest opruimen. Een
    vangnet dat kapotgaat zodra het werk af is, dwingt je te kiezen tussen een lege guard en
    een achtergelaten bypass.
    """
    gevonden: set[tuple[str, str]] = set()
    for knoop in ast.walk(boom):
        if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(knoop):
            if not isinstance(sub, (ast.With, ast.AsyncWith)):
                continue
            for item in sub.items:
                aanroep = item.context_expr
                if not isinstance(aanroep, ast.Call):
                    continue
                functie = aanroep.func
                naam = (
                    functie.id
                    if isinstance(functie, ast.Name)
                    else functie.attr
                    if isinstance(functie, ast.Attribute)
                    else ""
                )
                if naam == "TenantFilterBypass":
                    gevonden.add((relatief, knoop.name))
    return gevonden


def _kale_bypass_functies() -> set[tuple[str, str]]:
    """Functies op het auth-pad met een `TenantFilterBypass`-blok."""
    gevonden: set[tuple[str, str]] = set()
    for pad in _python_bestanden():
        tekst = pad.read_text(encoding="utf-8", errors="ignore")
        if "TenantFilterBypass" not in tekst:
            continue
        try:
            boom = ast.parse(tekst)
        except SyntaxError:  # pragma: no cover
            continue
        gevonden |= _kale_bypass_in_boom(boom, pad.relative_to(REPO_ROOT).as_posix())
    return gevonden


def test_geen_nieuwe_kale_bypass_op_het_authenticatiepad() -> None:
    """Een NIEUW kaal bypass-blok wordt geblokkeerd.

    Deze blokken zetten alleen de APPLICATIEVE filter uit. Onder `sanskritisetu_app` blijft
    de database-policy gelden, dus ze geven straks nul rijen -- zonder foutmelding.
    """
    nieuw = _kale_bypass_functies() - set(KNOWN_KALE_BYPASS)
    assert not nieuw, (
        "Nieuw(e) kaal `TenantFilterBypass`-blok(ken) op het authenticatiepad:\n"
        + "\n".join(f"  {bestand}::{naam}()" for bestand, naam in sorted(nieuw))
        + "\n\nGebruik `pre_auth_lookup(db)` (en daarna `adopt_tenant`) in plaats van een "
        "kale bypass: die zet alleen de applicatieve filter uit, niet de database-policy."
    )


def test_lijst_is_niet_verouderd() -> None:
    """Een omgezet blok MOET uit de lijst -- anders rot die dicht."""
    verdwenen = [s for s in KNOWN_KALE_BYPASS if s not in _kale_bypass_functies()]
    assert not verdwenen, (
        "Deze staan in KNOWN_KALE_BYPASS maar hebben geen kaal bypass-blok meer:\n"
        + "\n".join(f"  {bestand}::{naam}()" for bestand, naam in sorted(verdwenen))
        + "\n\nOmgezet? Haal de regel uit de lijst."
    )


def test_de_meting_is_niet_leeg() -> None:
    """Zonder deze toets is 'vind niets, meld niets' een geldige oplossing."""
    assert _adopt_tenant_aanroepen(), (
        "Geen enkele `adopt_tenant`-aanroep gevonden op het authenticatiepad. De guard "
        "meet dan niets (hernoemde functie, verplaatste map, kapotte AST-toets)."
    )


def test_de_detectie_werkt_nog() -> None:
    """De andere helft van hetzelfde vangnet, maar op een SYNTHETISCH voorbeeld.

    Hier stond `assert _kale_bypass_functies()`: er moest nog minstens een echt kaal
    `TenantFilterBypass`-blok op het auth-pad bestaan, anders was de detectie kennelijk
    stuk. Die redenering hield precies zolang het werk niet af was. Op 2026-09-16 is het
    laatste blok omgezet en werd dit vangnet ROOD -- terwijl er niets mis was.

    Een vangnet dat je dwingt te kiezen tussen een lege guard en een achtergelaten bypass
    is het verkeerde vangnet. Het toetst nu de DETECTIE zelf, en dat werkt ongeacht hoeveel
    werk er nog ligt.
    """
    met_bypass = ast.parse(
        textwrap.dedent(
            """
            def zoek(db):
                with TenantFilterBypass():
                    return db.execute(q)
            """
        )
    )
    zonder_bypass = ast.parse(
        textwrap.dedent(
            """
            async def zoek(db):
                async with adopt_tenant(db, tenant_id):
                    return await db.execute(q)
            """
        )
    )

    assert _kale_bypass_in_boom(met_bypass, "proef.py") == {("proef.py", "zoek")}, (
        "De AST-detectie vindt een kaal `TenantFilterBypass`-blok niet meer. Zolang dat zo "
        "is, is `test_geen_nieuwe_kale_bypass_op_het_authenticatiepad` stil groen."
    )
    assert not _kale_bypass_in_boom(zonder_bypass, "proef.py"), (
        "De detectie meldt een `adopt_tenant`-blok als kale bypass. Dan zou elke correcte "
        "omzetting als overtreding worden gelezen."
    )

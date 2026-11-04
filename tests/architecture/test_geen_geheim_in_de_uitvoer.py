"""Geen geheim in de uitvoer, ook niet gedeeltelijk (CLAUDE.md NOOIT-lijst; brief 2026-10-23).

Een `print` of een logregel mag geen geheim tonen, en ook geen deel ervan: de eerste tekens van een
sleutel zijn al genoeg om een zoekruimte te verkleinen, en een logbestand leeft langer dan de sleutel.

**Wat de guard toetst (AST, geen tekstzoeken).** In elke uitvoeraanroep (`print`, `logger.x`, `log.x`,
`self.logger.x`, `logging.getLogger().x`, `sys.stderr.write`, `click.echo`, `console.print`) wordt elke waarde
nagelopen die in de uitvoer kan belanden, ook binnen `.format(...)`, `%`-dicts, lijsten, tuples, `*args`,
`extra={...}` en keyword-argumenten. Een waarde is een geheim als:

1. de NAAM een geheim noemt (`password`, `secret_key`, `api_key`, `access_token`, `hashed_password`, `new_hash`),
   ook als attribuut (`self.password`, `settings.SECRET_KEY`) of als sleutel (`d["password"]`,
   `os.getenv("ADMIN_PASSWORD")`);
2. de waarde HIER is gegenereerd door een geheimgenerator (`secrets.token_urlsafe`, `generate_secret_key`, ...) of
   een alias is van een geheim (`p = password`), ook via een tuple-toewijzing of een keten (`.upper()`);
3. er een SLICE van een waarde wordt getoond terwijl de aanroep zelf het woord secret/password/api key noemt.

Een functieaanroep geeft een geheim alleen door als hij het teruggeeft (`str`, `repr`, een methode erop,
`.format`); `len(x)`, `mask_secret(x)` en `verify(x, h)` leveren een ander ding op en tellen niet mee.

**Waarom geen tekstregel op het woord "token".** In dit project is `token` ook een RRULE-onderdeel, een
tokenbudget (`tokens_used`) en de `jti` van een JWT: een openbare id, geen geheim. Wie op het kale woord
zoekt krijgt tientallen valse alarmen en leert de guard te negeren. Zie `test_geheimnamen_bevatten_geen_kaal_token`.

**Een database-URL is een geheim** (er staat een wachtwoord in): `database_url`, `db_url`, `DATABASE_URL`,
`os.getenv("DATABASE_URL")` en `config.get_main_option("sqlalchemy.url")`. Toon hem alleen via
`database_url_zonder_wachtwoord()` (`src/core/utils/url_zonder_wachtwoord.py`). Ook de tekst van een `raise`
telt als uitvoer: een foutmelding komt in een log.

**Wat deze guard NIET dekt (bewust):** `repr(settings)`, `print(os.environ)`, `private_key_pem` en
`encryption_key`. Daarvoor is een eigen brief nodig.

**Alleen door git bijgehouden bestanden.** Zelfde reden als `test_jwt_ondertekenen_blijft_bij_de_fabriek.py`:
een genegeerd lokaal bestand (`.gitignore` regel `verify_*.py`; zo'n bestand stond hier ooit) is geen deel van de
codebase en laat de toets lokaal anders uitvallen dan op een schone machine.

**Sleutel van de uitzonderingslijst is `bestand::functie`**, nooit alleen het bestand (zie
`.claude/rules/quality-gates.md`, OP-258): een uitzondering stelt de ene plek vrij waarvoor een reden is
opgeschreven, niet elke plek in hetzelfde bestand.

**Mutatiebewijs (2026-10-23), beide richtingen, zie de klassen onderaan:** elke vorm hierboven heeft een test die
hem moet vinden (`TestDeGuardVindtWatHijMoetVinden`) en een test die een legitiem geval met rust laat
(`TestDeGuardLaatLegitiemeUitvoerMetRust`); een lek in een ANDERE functie van een bestand dat al op de lijst staat
wordt betrapt (`test_een_uitzondering_geldt_voor_de_functie_en_niet_voor_het_bestand`).
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

WORTEL = Path(__file__).resolve().parents[2]
MAPPEN = ("src", "scripts")

# De uitzonderingen zijn handmatig gedraaide hulpmiddelen waarvan het DOEL is dat een mens het NIEUW gegenereerde
# geheim overneemt. Gedateerd 2026-10-23. Niets roept ze automatisch aan: gemeten met
# `git grep -n "generate_secret_key|rotate_secret_key|rotate_db_credentials" -- .github Makefile docker-compose*.yml
# Dockerfile* scripts config` (geen treffer). Groeit deze lijst, dan hoort er een reden en een datum bij; verdwijnt
# een regel, dan moet hij hier ook weg (staleness-test).
BEKENDE_UITZONDERINGEN: dict[str, str] = {
    "src/scripts/generate_secret_key.py::<module>": (
        "Handmatige generator (`python -m src.scripts.generate_secret_key`): toont de NIEUWE sleutel zodat een mens hem "
        "kopieert. Geen bestaand geheim, geen automatische aanroeper (gemeten 2026-10-23)."
    ),
    "src/scripts/rotate_secret_key.py::rotate_secret_key": (
        "Handmatige rotatiehulp: toont de NIEUWE sleutel zodat een mens hem in zijn eigen omgeving zet. Geen automatische "
        "aanroeper (gemeten 2026-10-23)."
    ),
    "scripts/seed_db.py::seed_users": (
        "Handmatige seed voor een ontwikkeldatabase: genereert per testgebruiker een wachtwoord en toont het zodat een mens "
        "kan inloggen. Nieuw gegenereerd, geen bestaand geheim; geen automatische aanroeper (gemeten 2026-10-23)."
    ),
    "scripts/fix_admin_runtime.py::fix_admin_runtime": (
        "Handmatige hersteltool. Toont het wachtwoord ALLEEN als het zojuist is gegenereerd (ADMIN_RESET_PASSWORD niet gezet) "
        "zodat een mens het overneemt; een wachtwoord uit de omgeving wordt niet getoond (2026-10-23)."
    ),
    "scripts/reset_admin.py::reset_admin": (
        "Handmatige hersteltool. Toont het wachtwoord ALLEEN als het zojuist is gegenereerd (ADMIN_RESET_PASSWORD niet gezet) "
        "zodat een mens het overneemt; een wachtwoord uit de omgeving wordt niet getoond (2026-10-23)."
    ),
    "src/scripts/rotate_db_credentials.py::rotate_db_credentials": (
        "Handmatige rotatiehulp voor databasegegevens: toont het NIEUWE wachtwoord zodat een mens het instelt. Niet in de "
        "brief genoemd maar dezelfde soort als de generators hierboven; geen automatische aanroeper (gemeten 2026-10-23)."
    ),
}

_LOGMETHODEN = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)
_UITVOERFUNCTIES = frozenset(
    {
        "sys.stdout.write",
        "sys.stderr.write",
        "click.echo",
        "typer.echo",
        "console.print",
        "rich.print",
    }
)

# De NAAM van een variabele die een geheim IS. `key` en `token` staan hier bewust niet kaal in (cachesleutels, RRULE-
# onderdelen, jti), alleen samengestelde namen die het geheim zelf noemen. Wachtwoordhashes horen erbij: een hash is
# een offline-brekingsdoel.
_GEHEIMNAAM = re.compile(
    r"(^|_)(secret|secret_key|password|passwd|api_key|apikey|private_key)$"
    r"|^(access|refresh|bearer|auth|api|jwt)_token$"
    r"|_(access|refresh|bearer|auth|api|jwt)_token$"
    r"|^(hashed|hashed_pw|pw_hash|password_hash|new_hash|stored_hash)$"
    r"|(^|_)(database_url|db_url|database_uri|db_uri|dsn)$",
    re.IGNORECASE,
)
# Een naam die wel een geheimwoord bevat maar GEEN waarde is (hoeveel, hoe heet het, waar staat het).
_GEEN_WAARDE = re.compile(
    r"_(name|names|id|path|file|type|count|length|len|minutes|days|seconds|used|ref|loader|manager|service|config)$",
    re.IGNORECASE,
)
_GEHEIMTEKST = re.compile(r"(secret|password|passwd|api[ _]?key|private[ _]?key)", re.IGNORECASE)
_GENERATOR = re.compile(
    r"(token_(urlsafe|hex|bytes)|generate_(secret|random|key|password)|Fernet\.generate_key)",
    re.IGNORECASE,
)
# Builtins die een waarde ongewijzigd doorgeven: wat erin gaat, komt er in tekstvorm uit.
_DOORGEVERS = frozenset({"str", "repr", "bytes", "bytearray", "format", "ascii"})


_ENGINENAMEN = frozenset({"engine", "connectable", "bind", "db_engine", "async_engine"})


def _naam(knoop: ast.AST) -> str:
    """De naam van een variabele of attribuut; `str(x)` en `repr(x)` tellen als `x`."""
    if (
        isinstance(knoop, ast.Call)
        and isinstance(knoop.func, ast.Name)
        and knoop.func.id in {"str", "repr"}
    ):
        if knoop.args:
            return _naam(knoop.args[0])
    if isinstance(knoop, ast.Name):
        return knoop.id
    if isinstance(knoop, ast.Attribute):
        return knoop.attr
    return ""


def _gedotte_naam(knoop: ast.AST) -> str:
    if isinstance(knoop, ast.Name):
        return knoop.id
    if isinstance(knoop, ast.Attribute):
        voor = _gedotte_naam(knoop.value)
        return (voor + "." if voor else "") + knoop.attr
    return ""


def _is_geheimnaam(naam: str) -> bool:
    return bool(naam) and bool(_GEHEIMNAAM.search(naam)) and not _GEEN_WAARDE.search(naam)


def _is_geheime_sleutel(sleutel: str) -> bool:
    """De sleutel waaronder een geheim staat: `password`, `ADMIN_PASSWORD`, `DATABASE_URL`, `sqlalchemy.url`."""
    return _is_geheimnaam(sleutel) or sleutel == "sqlalchemy.url"


def _is_uitvoer(aanroep: ast.Call) -> bool:
    f = aanroep.func
    if isinstance(f, ast.Name):
        return f.id == "print"
    if not isinstance(f, ast.Attribute):
        return False
    if _gedotte_naam(f) in _UITVOERFUNCTIES:
        return True
    if f.attr not in _LOGMETHODEN:
        return False
    basis = f.value
    if isinstance(basis, ast.Call):  # logging.getLogger("x").info(...)
        return _gedotte_naam(basis.func).split(".")[-1] in {"getLogger", "get_logger"}
    naam = (
        basis.id
        if isinstance(basis, ast.Name)
        else (basis.attr if isinstance(basis, ast.Attribute) else "")
    )
    return "log" in naam.lower() or naam in {"console", "audit"}


def _const_geheimsleutel(k: ast.AST) -> bool:
    """`d["password"]`, `os.environ["ADMIN_PASSWORD"]`, `x.get("api_key")`, `os.getenv("X_SECRET")`."""
    if isinstance(k, ast.Subscript):
        if isinstance(k.slice, ast.Constant) and isinstance(k.slice.value, str):
            return _is_geheime_sleutel(k.slice.value)
        # `os.environ[naam]` met een naam uit een variabele (lus over omgevingsvariabelen): kan alles zijn.
        return _gedotte_naam(k.value).endswith("environ")
    if isinstance(k, ast.Call) and k.args and isinstance(k.func, ast.Attribute | ast.Name):
        dotted = _gedotte_naam(k.func)
        if dotted.split(".")[-1] in {"get", "getenv", "get_main_option"}:
            eerste = k.args[0]
            if isinstance(eerste, ast.Constant) and isinstance(eerste.value, str):
                return _is_geheime_sleutel(eerste.value)
            # `os.getenv(naam)` / `os.environ.get(naam)` met een onbekende naam. Een HOOFDLETTER-constante
            # (`_ROLLOUT_ENV`) is een vaste naam, geen lusvariabele.
            if isinstance(eerste, ast.Name) and re.fullmatch(r"_?[A-Z][A-Z0-9_]*", eerste.id):
                return False
            return dotted in {"os.getenv", "os.environ.get", "environ.get", "getenv"}
    return False


def _draagt_geheim(k: ast.AST, afgeleid: set[str]) -> str | None:
    """De naam van het geheim dat deze uitdrukking (geheel of gedeeltelijk) in de uitvoer brengt, of None.

    Een functieaanroep geeft een geheim alleen DOOR als hij het teruggeeft: `str(x)`, `repr(x)`, een methode op het
    geheim (`x.upper()`, `x.decode()`), `"...".format(x)`. Een gewone functie die het geheim als argument krijgt
    (`verify(password, h)`, `client.post(json={"password": p})`, `len(password)`, `mask_secret(password)`) geeft
    een ander ding terug en telt niet mee; anders wordt elke variabele die ergens uit een geheim is berekend een
    vals alarm.
    """
    if isinstance(k, ast.Constant | ast.Compare):
        return None
    if isinstance(k, ast.UnaryOp) and isinstance(k.op, ast.Not):
        return None
    if isinstance(k, ast.Name | ast.Attribute):
        naam = _naam(k)
        if _is_geheimnaam(naam) or (naam in afgeleid and not _GEEN_WAARDE.search(naam)):
            return naam
        if isinstance(k, ast.Attribute) and naam == "url" and _naam(k.value) in _ENGINENAMEN:
            return "engine.url"
        return _draagt_geheim(k.value, afgeleid) if isinstance(k, ast.Attribute) else None
    if isinstance(k, ast.Call):
        func = _gedotte_naam(k.func)
        if _GENERATOR.search(func):
            return func
        if _const_geheimsleutel(k):
            return "sleutel"
        argumenten = [*k.args, *[kw.value for kw in k.keywords]]
        if isinstance(k.func, ast.Name) and k.func.id in _DOORGEVERS:
            return next((h for a in argumenten if (h := _draagt_geheim(a, afgeleid))), None)
        if isinstance(k.func, ast.Attribute):
            if (h := _draagt_geheim(k.func.value, afgeleid)) is not None:
                return h
            if k.func.attr == "format":
                return next((h for a in argumenten if (h := _draagt_geheim(a, afgeleid))), None)
        return None
    if isinstance(k, ast.Subscript):
        if _const_geheimsleutel(k):
            return "sleutel"
        if isinstance(k.slice, ast.Constant) and isinstance(k.slice.value, str):
            # `d["password"]` is een geheim; `secret["line"]` kiest alleen een veld van een bevinding.
            return None
        return _draagt_geheim(k.value, afgeleid)
    if isinstance(k, ast.IfExp):
        # De voorwaarde bepaalt WELKE tekst er komt, niet wat er getoond wordt.
        return _draagt_geheim(k.body, afgeleid) or _draagt_geheim(k.orelse, afgeleid)
    for kind in ast.iter_child_nodes(k):
        if (h := _draagt_geheim(kind, afgeleid)) is not None:
            return h
    return None


def _bevat_geheim(knoop: ast.AST, afgeleid: set[str]) -> str | None:
    return _draagt_geheim(knoop, afgeleid)


def _afgeleide_namen(lichaam: list[ast.stmt]) -> set[str]:
    """Namen in DEZE functie (niet in geneste) die een geheim dragen: gegenereerd, of een alias ervan."""
    afgeleid: set[str] = set()
    toewijzingen: list[tuple[list[str], ast.AST]] = []

    def doelnamen(doel: ast.AST) -> list[str]:
        if isinstance(doel, ast.Name):
            return [doel.id]
        if isinstance(doel, ast.Tuple | ast.List):
            return [n for e in doel.elts for n in doelnamen(e)]
        return []

    def verzamel(stmts: list[ast.stmt]) -> None:
        for s in stmts:
            if isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            if isinstance(s, ast.Assign):
                for doel in s.targets:
                    if (
                        isinstance(doel, ast.Tuple)
                        and isinstance(s.value, ast.Tuple)
                        and len(doel.elts) == len(s.value.elts)
                    ):
                        for d, w in zip(doel.elts, s.value.elts, strict=True):
                            toewijzingen.append((doelnamen(d), w))
                    else:
                        toewijzingen.append((doelnamen(doel), s.value))
            elif isinstance(s, ast.AnnAssign) and s.value is not None:
                toewijzingen.append((doelnamen(s.target), s.value))
            for veld in ("body", "orelse", "finalbody"):
                kinderen = getattr(s, veld, None)
                if isinstance(kinderen, list):
                    verzamel([k for k in kinderen if isinstance(k, ast.stmt)])
            for handler in getattr(s, "handlers", []) or []:
                verzamel(handler.body)

    verzamel(lichaam)
    # Twee rondes: een alias van een alias.
    for _ in range(2):
        for namen, waarde in toewijzingen:
            if isinstance(waarde, ast.Await):
                waarde = waarde.value
            if _bevat_geheim(waarde, afgeleid):
                afgeleid.update(n for n in namen if not _GEEN_WAARDE.search(n))
    return afgeleid


def _toets_aanroep(aanroep: ast.Call, afgeleid: set[str]) -> str | None:
    """De reden als deze uitvoeraanroep een geheim toont, anders None."""
    delen = [*aanroep.args, *[kw.value for kw in aanroep.keywords]]
    tekst_noemt_geheim = any(
        isinstance(k, ast.Constant) and isinstance(k.value, str) and _GEHEIMTEKST.search(k.value)
        for d in delen
        for k in ast.walk(d)
    )
    for d in delen:
        gevonden = _bevat_geheim(d, afgeleid)
        if gevonden:
            return f"een geheim in de uitvoer ({gevonden})"
        if tekst_noemt_geheim:
            for k in ast.walk(d):
                if isinstance(k, ast.Subscript) and isinstance(k.slice, ast.Slice):
                    return f"een deel van een waarde naast een tekst over een geheim ({_naam(k.value) or 'waarde'}[...])"
    return None


def vind_geheimen_in_uitvoer(bron: str, pad: str) -> list[tuple[str, int, str]]:
    """`(bestand::functie, regelnummer, reden)` per plek die een geheim toont.

    Expliciete recursie over functies: `ast.walk` vanaf een functieknoop zou geneste functies als de
    ouder tellen en de sleutel van de uitzonderingslijst onbetrouwbaar maken.
    """
    boom = ast.parse(bron)
    gevonden: list[tuple[str, int, str]] = []

    def bezoek(knopen: list[ast.stmt], functie: str) -> None:
        afgeleid = _afgeleide_namen(knopen)
        for knoop in knopen:
            if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef):
                bezoek(knoop.body, knoop.name)
            elif isinstance(knoop, ast.ClassDef):
                bezoek(knoop.body, functie)
            else:
                uitvoer = [a for a in _aanroepen_zonder_geneste_functies(knoop) if _is_uitvoer(a)]
                for aanroep in [*uitvoer, *_raise_aanroepen(knoop)]:
                    reden = _toets_aanroep(aanroep, afgeleid)
                    if reden:
                        gevonden.append((f"{pad}::{functie}", aanroep.lineno, reden))

    bezoek(boom.body, "<module>")
    return gevonden


def _raise_aanroepen(knoop: ast.AST) -> list[ast.Call]:
    """De uitzonderingen die een `raise` opwerpt, zonder die in geneste functies: hun tekst komt in een log of foutmelding."""
    uitkomst: list[ast.Call] = []

    def loop(k: ast.AST) -> None:
        if isinstance(k, ast.Raise) and isinstance(k.exc, ast.Call):
            uitkomst.append(k.exc)
        for kind in ast.iter_child_nodes(k):
            if isinstance(kind, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            loop(kind)

    loop(knoop)
    return uitkomst


def _aanroepen_zonder_geneste_functies(knoop: ast.AST) -> list[ast.Call]:
    uitkomst: list[ast.Call] = []

    def loop(k: ast.AST) -> None:
        if isinstance(k, ast.Call):
            uitkomst.append(k)
        for kind in ast.iter_child_nodes(k):
            if isinstance(kind, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            loop(kind)

    loop(knoop)
    return uitkomst


def _te_scannen_bestanden() -> list[Path]:
    """Alleen bestanden die git BIJHOUDT (zie de moduledocstring)."""
    uitvoer = subprocess.run(
        ["git", "ls-files", "--", *[f"{m}/*.py" for m in MAPPEN]],
        cwd=WORTEL,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    paden = [WORTEL / regel.strip() for regel in uitvoer.splitlines() if regel.strip()]
    return [p for p in paden if p.suffix == ".py" and p.is_file()]


def _alle_plekken() -> list[tuple[str, int, str]]:
    plekken: list[tuple[str, int, str]] = []
    for bestand in _te_scannen_bestanden():
        pad = bestand.relative_to(WORTEL).as_posix()
        try:
            bron = bestand.read_text(encoding="utf-8")
            plekken.extend(vind_geheimen_in_uitvoer(bron, pad))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
    return plekken


def test_er_is_geen_geheim_in_de_uitvoer_buiten_de_bekende_uitzonderingen() -> None:
    nieuw = [p for p in _alle_plekken() if p[0] not in BEKENDE_UITZONDERINGEN]

    assert not nieuw, (
        "Deze plekken tonen een geheim of een deel ervan in print of log (CLAUDE.md: geheimen nooit tonen, ook niet "
        "gedeeltelijk). Meld alleen DAT er een geheim wordt gebruikt, zoals jwt_handler.py doet:\n"
        + "\n".join(f"  {sleutel}:{regel}  {reden}" for sleutel, regel, reden in nieuw)
    )


def test_bekende_uitzonderingen_zijn_niet_verouderd() -> None:
    gevonden = {p[0] for p in _alle_plekken()}
    verouderd = sorted(k for k in BEKENDE_UITZONDERINGEN if k not in gevonden)

    assert not verouderd, (
        "Deze uitzonderingen worden niet meer gevonden en moeten uit BEKENDE_UITZONDERINGEN, anders rot de lijst dicht: "
        + ", ".join(verouderd)
    )


def test_elke_uitzondering_heeft_een_reden_en_een_bestand_dat_bestaat() -> None:
    zonder_reden = [k for k, r in BEKENDE_UITZONDERINGEN.items() if len(r.strip()) < 30]
    zonder_bestand = [
        k for k in BEKENDE_UITZONDERINGEN if not (WORTEL / k.split("::")[0]).is_file()
    ]

    assert (zonder_reden, zonder_bestand) == ([], [])


def test_de_guard_leest_echte_bestanden() -> None:
    """Een lege verzameling maakt de eerste toets triviaal groen."""
    assert len(_te_scannen_bestanden()) > 500


# --- Mutatiebewijs, beide richtingen --------------------------------------------------------------------------------


def _vind(bron: str, pad: str = "src/x.py") -> list[str]:
    return [sleutel for sleutel, _, _ in vind_geheimen_in_uitvoer(bron, pad)]


class TestDeGuardVindtWatHijMoetVinden:
    def test_de_slice_van_een_gegenereerd_geheim_uit_de_brief(self) -> None:
        bron = (
            "import secrets\n"
            "def validate(v):\n"
            "    v = secrets.token_urlsafe(32)\n"
            '    print(f"INFO: Generated JWT secret for development: {v[:8]}...")\n'
        )

        assert _vind(bron) == ["src/x.py::validate"]

    def test_de_slice_van_een_geheimnaam_zonder_geheimtekst(self) -> None:
        bron = 'def f(api_key):\n    logger.info("sleutel eindigt op %s", api_key[-4:])\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_geheimnaam_in_een_fstring(self) -> None:
        bron = 'def f(secret_key):\n    logger.debug(f"gebruik {secret_key}")\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_geheimnaam_als_printf_argument(self) -> None:
        bron = 'def f(password):\n    log.warning("mislukt voor %s", password)\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_geheimnaam_via_samenvoegen(self) -> None:
        bron = 'def f(api_key):\n    print("key=" + api_key)\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_zojuist_gegenereerde_waarde_met_een_onschuldige_naam(self) -> None:
        bron = 'import secrets\ndef f():\n    sleutel = secrets.token_hex(16)\n    print(f"nieuw: {sleutel}")\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_str_om_het_geheim_helpt_niet(self) -> None:
        bron = 'def f(password):\n    logger.error("x %s", str(password)[:3])\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_lek_op_modulenivo_krijgt_de_sleutel_module(self) -> None:
        bron = 'secret_key = "x"\nprint(secret_key)\n'

        assert _vind(bron) == ["src/x.py::<module>"]

    def test_format_methode(self) -> None:
        bron = 'def f(password):\n    print("wachtwoord: {}".format(password))\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_procent_met_een_dict(self) -> None:
        bron = 'def f(password):\n    print("%(p)s" % {"p": password})\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_extra_van_een_logger(self) -> None:
        bron = 'def f(password):\n    logger.info("x", extra={"pw": password})\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_keyword_argument(self) -> None:
        bron = 'def f(password):\n    logger.info("x", pw=password)\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_lijst_of_tuple_in_print(self) -> None:
        bron = "def f(password):\n    print([password])\n    print((1, password))\n    print(*[password])\n"

        assert len(vind_geheimen_in_uitvoer(bron, "src/x.py")) == 3

    def test_een_alias_van_een_geheim(self) -> None:
        bron = "def f(password):\n    p = password\n    print(p)\n"

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_alias_van_een_alias_met_slice(self) -> None:
        bron = 'def f(password):\n    p = password\n    q = p\n    print(f"{q[:3]}")\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_gegenereerd_geheim_via_een_tuple_toewijzing(self) -> None:
        bron = "import secrets\ndef f():\n    k, j = secrets.token_hex(8), 1\n    print(k)\n"

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_gegenereerd_geheim_met_een_methode_erop(self) -> None:
        bron = "import secrets\ndef f():\n    k = secrets.token_hex(8).upper()\n    print(k)\n"

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_gegenereerd_geheim_direct_in_de_uitvoer(self) -> None:
        bron = "import secrets\ndef f():\n    print(secrets.token_hex(8))\n"

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_logger_via_getlogger(self) -> None:
        bron = 'import logging\ndef f(password):\n    logging.getLogger("x").info("%s", password)\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_logger_op_self(self) -> None:
        bron = 'class A:\n    def f(self, password):\n        self.logger.info("%s", password)\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_stderr_write_en_click_echo(self) -> None:
        bron = "import sys, click\ndef f(password):\n    sys.stderr.write(password)\n    click.echo(password)\n"

        assert len(vind_geheimen_in_uitvoer(bron, "src/x.py")) == 2

    def test_een_attribuut_met_geheimnaam(self) -> None:
        bron = "def f(self):\n    print(self.password)\n    print(settings.SECRET_KEY)\n"

        assert len(vind_geheimen_in_uitvoer(bron, "src/x.py")) == 2

    def test_een_geheim_via_een_constante_sleutel_of_de_omgeving(self) -> None:
        bron = (
            "import os\n"
            "def f(d):\n"
            '    print(d["password"])\n'
            '    print(os.getenv("ADMIN_PASSWORD"))\n'
            '    print(os.environ["X_SECRET_KEY"])\n'
        )

        assert len(vind_geheimen_in_uitvoer(bron, "src/x.py")) == 3

    def test_een_wachtwoordhash(self) -> None:
        bron = 'def f(new_hash, hashed):\n    print(f"hash: {new_hash}")\n    print(hashed[:10])\n'

        assert len(vind_geheimen_in_uitvoer(bron, "src/x.py")) == 2


class TestDeGuardLaatLegitiemeUitvoerMetRust:
    def test_de_jti_van_een_token_is_een_openbare_id(self) -> None:
        bron = (
            'def f(jti):\n    logger.info("Ingetrokken token geweigerd (jti=%s)", str(jti)[:8])\n'
        )

        assert _vind(bron) == []

    def test_een_tokenbudget_is_geen_geheim(self) -> None:
        bron = 'def f(tokens_used):\n    logger.debug(f"tokens={tokens_used}")\n'

        assert _vind(bron) == []

    def test_de_naam_van_een_geheim_is_geen_geheim(self) -> None:
        bron = 'def f(secret_name):\n    logger.debug(f"Loaded secret {secret_name} from Docker Secrets")\n'

        assert _vind(bron) == []

    def test_een_cachesleutel_met_de_naam_key_is_geen_geheim(self) -> None:
        bron = 'def f(key):\n    logger.debug(f"cache hit {key}")\n'

        assert _vind(bron) == []

    def test_een_melding_dat_er_een_gegenereerd_geheim_is_gebruikt(self) -> None:
        bron = (
            "import secrets\n"
            "def f():\n"
            "    v = secrets.token_urlsafe(32)\n"
            '    logger.warning("Using generated JWT secret for development (not logged for security)")\n'
            "    return v\n"
        )

        assert _vind(bron) == []

    def test_een_gegenereerde_waarde_in_een_andere_functie_telt_niet(self) -> None:
        bron = (
            "import secrets\n"
            "def maak():\n"
            "    sleutel = secrets.token_hex(16)\n"
            "    return sleutel\n"
            "def toon(sleutel):\n"
            '    print(f"nieuw: {sleutel}")\n'
        )

        assert _vind(bron) == []

    def test_een_geheimnaam_die_een_aantal_is(self) -> None:
        bron = (
            "def f(access_token_expire_minutes):\n"
            '    logger.info(f"verloopt over {access_token_expire_minutes}m")\n'
        )

        assert _vind(bron) == []

    def test_de_lengte_van_een_geheim_is_geen_geheim(self) -> None:
        bron = 'def f(password):\n    print(f"lengte {len(password)}", bool(password))\n'

        assert _vind(bron) == []

    def test_een_gemaskeerd_geheim_is_geen_geheim(self) -> None:
        bron = 'def f(password):\n    logger.info("x %s", mask_secret(password))\n'

        assert _vind(bron) == []

    def test_een_inhoudshash_is_geen_wachtwoordhash(self) -> None:
        bron = "def f(file_hash, content_hash):\n    print(file_hash, content_hash)\n"

        assert _vind(bron) == []

    def test_een_gegenereerde_openbare_id_is_geen_geheim(self) -> None:
        """Een kanaal-id of correlatie-id komt uit dezelfde generator maar wordt openbaar doorgegeven."""
        bron = (
            "import secrets\n"
            "def f():\n"
            "    channel_id = secrets.token_urlsafe(32)\n"
            '    logger.info(f"Webhook geregistreerd: channel={channel_id}")\n'
        )

        assert _vind(bron) == []

    def test_een_gewone_constante_sleutel_is_geen_geheim(self) -> None:
        bron = 'def f(d):\n    print(d["email"])\n    print(os.getenv("DATABASE_HOST"))\n'

        assert _vind(bron) == []

    def test_een_ander_uitvoerkanaal_zonder_geheim(self) -> None:
        bron = "import sys\ndef f(naam):\n    sys.stderr.write(naam)\n    other.info(naam)\n"

        assert _vind(bron) == []


class TestOmgevingsvariabelenMetEenWillekeurigeNaam:
    def test_een_lus_over_omgevingsvariabelen_toont_hun_waarde(self) -> None:
        bron = (
            "import os\n"
            "def f(namen):\n"
            "    for var in namen:\n"
            "        value = os.getenv(var)\n"
            '        print(f"{var}: {value[:30]}")\n'
        )

        assert _vind(bron) == ["src/x.py::f"]

    def test_environ_met_een_naam_uit_een_variabele(self) -> None:
        bron = "import os\ndef f(naam):\n    print(os.environ[naam])\n"

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_vaste_niet_geheime_omgevingsvariabele_mag(self) -> None:
        bron = 'import os\ndef f():\n    print(os.getenv("LOG_LEVEL"))\n    print(os.environ["HOME"])\n'

        assert _vind(bron) == []

    def test_alleen_tonen_dat_de_variabele_bestaat_mag(self) -> None:
        bron = (
            "import os\n"
            "def f(naam):\n"
            "    value = os.getenv(naam)\n"
            '    print(f"{naam}: {bool(value)}")\n'
        )

        assert _vind(bron) == []

    def test_een_vaste_naam_in_een_hoofdletterconstante_mag(self) -> None:
        bron = (
            "import os\n"
            "_ENV = \"ROLLOUT_PERCENTAGE\"\n"
            "def f():\n"
            "    raw = os.getenv(_ENV, \"0\")\n"
            "    logger.warning(\"x %r\", raw)\n"
        )

        assert _vind(bron) == []

    def test_de_url_van_een_engine(self) -> None:
        bron = 'def f(engine):\n    logger.info(f"engine: {engine.url}")\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_url_van_iets_anders_is_geen_engine(self) -> None:
        bron = 'def f(pagina):\n    logger.info(f"pagina: {pagina.url}")\n'

        assert _vind(bron) == []


class TestEenDatabaseUrlIsEenGeheim:
    def test_een_slice_van_een_database_url(self) -> None:
        bron = 'def f(database_url):\n    print(f"url: {database_url[:50]}")\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_database_url_in_een_logregel(self) -> None:
        bron = 'def f(db_url):\n    logger.info(f"Connecting to {db_url}")\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_de_database_url_uit_de_omgeving(self) -> None:
        bron = 'import os\ndef f():\n    print(os.getenv("DATABASE_URL"))\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_url_uit_de_alembic_config_in_een_foutmelding(self) -> None:
        bron = (
            "def f(config):\n"
            '    url = config.get_main_option("sqlalchemy.url")\n'
            '    raise ValueError(f"DATABASE_URL={url}")\n'
        )

        assert _vind(bron) == ["src/x.py::f"]

    def test_een_wachtwoord_in_een_foutmelding(self) -> None:
        bron = 'def f(password):\n    raise ValueError(f"mislukt met {password}")\n'

        assert _vind(bron) == ["src/x.py::f"]

    def test_via_de_hulpfunctie_is_het_geen_geheim(self) -> None:
        bron = (
            "def f(database_url):\n"
            '    print(f"url: {database_url_zonder_wachtwoord(database_url)}")\n'
            '    raise ValueError(f"mislukt voor {database_url_zonder_wachtwoord(database_url)}")\n'
        )

        assert _vind(bron) == []

    def test_een_raise_zonder_geheim_blijft_ongemoeid(self) -> None:
        bron = 'def f(naam):\n    raise ValueError(f"onbekende naam {naam}")\n'

        assert _vind(bron) == []


def test_een_aanwezigheidscontrole_toont_het_geheim_niet() -> None:
    """`'Found' if os.getenv('X_API_KEY') else 'Not Found'`: de voorwaarde is geen uitvoer."""
    bron = "import os\nprint(f\"KEY: {'Found' if os.getenv('X_API_KEY') else 'Not Found'}\")\n"

    assert _vind(bron) == []


def test_een_veld_van_een_bevinding_is_geen_geheim_maar_de_waarde_wel() -> None:
    bron = (
        "def f(secret):\n"
        '    regel = secret["line"]\n'
        '    waarde = secret["secret"]\n'
        '    print(f"regel {regel}")\n'
        '    print(f"waarde {waarde}")\n'
    )

    assert [r for _, r, _ in vind_geheimen_in_uitvoer(bron, "src/x.py")] == [5]


def test_een_url_met_een_onschuldig_token_is_geen_geheim() -> None:
    bron = 'def f(page_token):\n    url = f"http://x/list?next={page_token}"\n    print(url)\n'

    assert _vind(bron) == []


def test_een_url_met_een_token_uit_een_geheimnaam_toont_het_token() -> None:
    bron = 'def f(access_token):\n    url = f"http://x/me?token={access_token}"\n    print(url)\n'

    assert _vind(bron) == ["src/x.py::f"]


def test_een_uitzondering_geldt_voor_de_functie_en_niet_voor_het_bestand() -> None:
    """Muteren IN een bestand dat al op de lijst staat: een lek in een ANDERE functie wordt wel betrapt."""
    bron = (
        "def rotate_secret_key():\n"
        "    new_key = generate_secret_key()\n"
        '    print(f"nieuw: {new_key}")\n'
        "def andere_functie(password):\n"
        '    logger.info("login met %s", password)\n'
    )
    sleutels = _vind(bron, "src/scripts/rotate_secret_key.py")
    nieuw = [s for s in sleutels if s not in BEKENDE_UITZONDERINGEN]

    assert (sleutels, nieuw) == (
        [
            "src/scripts/rotate_secret_key.py::rotate_secret_key",
            "src/scripts/rotate_secret_key.py::andere_functie",
        ],
        ["src/scripts/rotate_secret_key.py::andere_functie"],
    )


def test_geheimnamen_bevatten_geen_kaal_token() -> None:
    """De naamregel is bewust smal; een kale `token` valt er niet onder."""
    assert not _GEHEIMNAAM.search("token")
    assert not _GEHEIMNAAM.search("key")
    assert _GEHEIMNAAM.search("access_token")
    assert _GEHEIMNAAM.search("jwt_secret")


@pytest.mark.parametrize(
    "bron",
    [
        "def f(x):\n    print(x[:8])\n",
        "def f(x):\n    logger.info(x)\n",
    ],
)
def test_uitvoer_zonder_geheim_blijft_ongemoeid(bron: str) -> None:
    assert _vind(bron) == []

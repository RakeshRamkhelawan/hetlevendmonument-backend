"""Architecture test: een env-variabele die een URL bevat moet ook echt parsen.

Achtergrond (2026-08-01):
Drie testbestanden uit april 2026 zetten dit op module-niveau:

    os.environ["REDIS_URL"] = "redis://localhost:6380  # Redis port updated from 6379 to 6380"

Het commentaar stond IN de string. Daardoor werd de `#` een URL-fragment, las urllib de
poort als `'6380  '` en gooide `ValueError: Port could not be cast to integer value`.
Omdat het een module-level toewijzing is, vergiftigde alleen al het IMPORTEREN van zo'n
bestand de omgeving van de hele pytest-worker: elke module die daarna een Redis-client
bouwde, klapte eruit. `src/core/learning/worker.py` doet dat bij import, dus dat leverde
8 collectie-errors op in een compleet ander testbestand.

Waarom dit vier maanden onzichtbaar bleef: `tests/core/` draaide in geen enkele
standaardsuite. Zodra die map onder de CI-gate kwam (OP-11), viel het meteen om.

Waarom een defensieve `.strip()` niet helpt: `src/core/learning/worker.py` deed al
`os.getenv("REDIS_URL", ...).strip()`. De spaties zaten MIDDEN in de waarde, voor de `#`,
dus strippen aan de uiteinden verandert niets. Alleen echt parsen vangt dit.
"""

import ast
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

SCAN_ROOTS = (Path("src"), Path("tests"))

# Env-namen waarvan de waarde een URL hoort te zijn.
URL_ENV_SUFFIXES = ("_URL", "_URI", "_DSN", "_ENDPOINT")

# Waarden die bewust geen echte URL zijn (placeholders in config-tests).
ALLOWED_NON_URL_VALUES = {"", "changeme", "test", "dummy", "none", "null"}


def _looks_like_url_env(name: str) -> bool:
    return name.upper().endswith(URL_ENV_SUFFIXES)


def _url_problem(value: str) -> str | None:
    """Return een probleemomschrijving als deze waarde geen bruikbare URL is."""
    if value.strip().lower() in ALLOWED_NON_URL_VALUES:
        return None
    if "${" in value or "{" in value:
        return None  # template/format-string, wordt elders ingevuld
    if "#" in value:
        return (
            "bevat een '#'; urllib maakt daar een fragment van, waardoor host/poort "
            "stilletjes afgekapt of onparsebaar worden (commentaar hoort BUITEN de string)"
        )
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        return f"urlparse faalt: {exc}"
    try:
        parsed.port  # noqa: B018 -- property met validatie, niet zomaar een attribuut
    except ValueError as exc:
        return f"poort is ongeldig: {exc}"
    if parsed.scheme and not parsed.netloc and not parsed.path:
        return "schema aanwezig maar geen host of pad"
    return None


def _string_env_assignments(tree: ast.Module) -> list[tuple[int, str, str]]:
    """(regel, envnaam, waarde) voor os.environ[...] = "literal" en setenv("X", "literal")."""
    found: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        # os.environ["NAAM"] = "waarde"  /  os.environ.setdefault("NAAM", "waarde")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "environ"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    found.append((node.lineno, target.slice.value, node.value.value))

        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", "")
            if fname in ("setenv", "setdefault") and len(node.args) >= 2:
                name_arg, value_arg = node.args[0], node.args[1]
                if (
                    isinstance(name_arg, ast.Constant)
                    and isinstance(name_arg.value, str)
                    and isinstance(value_arg, ast.Constant)
                    and isinstance(value_arg.value, str)
                ):
                    found.append((node.lineno, name_arg.value, value_arg.value))

    return found


@lru_cache(maxsize=1)
def _url_env_assignments() -> tuple[tuple[tuple[str, int, str, str], ...], tuple[str, ...]]:
    """(pad, regel, envnaam, waarde) voor elke URL-achtige env-toewijzing in SCAN_ROOTS.

    Twee optimalisaties, nodig omdat SCAN_ROOTS ~4150 bestanden bevat:

    1. **Goedkope voorfilter voor de AST-parse.** `ast.parse` is het dure deel; het
       inlezen van de tekst is dat niet. Een bestand zonder het woord `environ` of
       `setenv` kan per definitie geen match bevatten (zie `_string_env_assignments`:
       het zoekt uitsluitend `os.environ[...]`-subscripts en `setenv`/`setdefault`-calls).
       Zulke bestanden worden dus niet geparseerd.
    2. **Eén keer scannen voor beide tests.** Ze deden allebei dezelfde wandeling.
       In een xdist-run landen ze mogelijk op verschillende workers en helpt de cache
       niet; in een seriële run halveert dit het werk.

    Achtergrond: deze guard duurde 14,0s tot de opschoning van `.git/info/exclude`
    (OP-17) 1816 eerder verborgen bestanden zichtbaar maakte -- daarna 48,6s, tegen een
    suite-timeout van 60. Dat is precies het soort marge dat later als "flaky test"
    wordt afgedaan, dus meteen aangepakt.
    """
    results: list[tuple[str, int, str, str]] = []
    fouten: list[str] = []

    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                fouten.append(f"{path.as_posix()}: {exc}")
                continue
            if "environ" not in text and "setenv" not in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                fouten.append(f"{path.as_posix()}: {exc}")
                continue
            for lineno, name, value in _string_env_assignments(tree):
                if _looks_like_url_env(name):
                    results.append((path.as_posix(), lineno, name, value))

    return tuple(results), tuple(fouten)


def test_all_scanned_files_could_be_read_and_parsed() -> None:
    """Vangnet: een onleesbaar/onparseerbaar bestand mag de scan hieronder niet blind maken.

    De bestaande vangnettest (test_scan_actually_finds_env_assignments) toetst een
    TOTAAL (>=10). Dat totaal wordt door de duizenden gezonde bestanden altijd gehaald,
    dus het ene overgeslagen bestand -- juist het bestand met de kapotte URL -- blijft
    daaronder onzichtbaar. Dit vangnet toetst per bestand.
    """
    _, fouten = _url_env_assignments()
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd "
        "op een onparsebare URL-env-toewijzing:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_env_url_assignments_in_python_are_parseable() -> None:
    """Geen enkele URL-achtige env-toewijzing in src/ of tests/ mag onparsebaar zijn."""
    violations: list[str] = []

    resultaten, _ = _url_env_assignments()
    for path_str, lineno, name, value in resultaten:
        problem = _url_problem(value)
        if problem:
            violations.append(f"{path_str}:{lineno} {name} -- {problem}\n      {value!r}")

    assert not violations, (
        "Onparsebare URL-waarde in een env-toewijzing. Zo'n waarde vergiftigt de hele "
        "procesomgeving zodra de module wordt geimporteerd:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_env_url_values_in_dotenv_files_are_parseable() -> None:
    """Dezelfde eis voor .env-bestanden -- die raken productie direct."""
    violations: list[str] = []
    pattern = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$")

    for env_file in sorted(Path(".").glob(".env*")):
        if env_file.is_dir():
            continue
        # Backups worden door niets geladen; ze rood laten staan levert alleen ruis op.
        # NB: .env.local.bak2/.bak3 bevatten wel degelijk een onparsebare Redis-URL -- het
        # wachtwoord bevat '+' en '/' zonder percent-encoding, waardoor urllib de poort
        # niet kan lezen. Wie zo'n backup terugzet, krijgt een worker die niet start.
        # Gemeld in de final-approver brief van ADR-036 Fase B dag 1.
        if ".bak" in env_file.name:
            continue
        try:
            regels = env_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as exc:
            violations.append(f"{env_file.name}: kon niet als UTF-8 gelezen worden ({exc})")
            continue
        for i, line in enumerate(regels, 1):
            if line.lstrip().startswith("#"):
                continue
            match = pattern.match(line)
            if not match:
                continue
            name, value = match.group(1), match.group(2).strip().strip('"').strip("'")
            if not _looks_like_url_env(name):
                continue
            problem = _url_problem(value)
            if problem:
                violations.append(f"{env_file.name}:{i} {name} -- {problem}")

    assert not violations, "Onparsebare URL in een .env-bestand:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


def test_scan_actually_finds_env_assignments() -> None:
    """Vangnet tegen een vacuum-pass als het AST-patroon niet meer matcht."""
    resultaten, _ = _url_env_assignments()
    total = len(resultaten)

    assert total >= 10, (
        f"Verwacht minimaal 10 URL-achtige env-toewijzingen in de codebase, gevonden "
        f"{total} -- de scan matcht het patroon niet meer."
    )

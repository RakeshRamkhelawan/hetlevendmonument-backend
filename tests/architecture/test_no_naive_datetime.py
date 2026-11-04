"""Preventie-test: geen naive datetime.now()/datetime.utcnow() in src/ (CLAUDE.md).

AUDIT-SINGLE-TENANT-DB01 S7. CLAUDE.md verbiedt datetime.now() en
datetime.utcnow() zonder timezone.utc -- naive datetimes veroorzaken
inconsistente audit-timestamps en TZ-vergelijkingsbugs.

AST-gebaseerd (S7 review-fix): de oorspronkelijke regex-implementatie miste
`import datetime as dt; dt.now()`-aliasing en spatie-varianten zoals
`datetime.now( )`. AST-detectie is immuun voor whitespace en volgt de
daadwerkelijke import-bindingen (incl. aliases), maar dekt geen volledig
dynamische reflectie zoals `getattr(datetime, "now")()` -- dat patroon komt
niet voor in deze codebase en is ongebruikelijk genoeg om buiten scope te
laten (vergelijkbaar met de scope-grens in test_dramatiq_actors_tenant_id.py).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path("src")

# Bestanden die legitiem datetime.now()/utcnow() documenteren of testen (geen
# violation). Geen huidige uitzonderingen nodig -- lijst blijft leeg tenzij een
# echte false-positive optreedt.
_EXEMPT_FILES: frozenset[str] = frozenset()


def _datetime_aliases(tree: ast.Module) -> set[str]:
    """Vind lokale namen die naar de datetime-module of -klasse verwijzen.

    Dekt `import datetime`, `import datetime as dt`, `from datetime import datetime`,
    en `from datetime import datetime as dt2`.
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "datetime":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "datetime":
            for alias in node.names:
                if alias.name == "datetime":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _is_naive_now_call(node: ast.Call, aliases: set[str]) -> bool:
    """True als dit een `<alias>.now()` of `<alias>.utcnow()` aanroep is zonder argumenten."""
    if node.args or node.keywords:
        return False  # heeft argumenten (bijv. timezone.utc) -- toegestaan
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in ("now", "utcnow"):
        return False
    target = node.func.value
    # <alias>.now() -- bijv. `datetime.now()` na `from datetime import datetime`
    if isinstance(target, ast.Name) and target.id in aliases:
        return True
    # <alias>.datetime.now() -- bijv. `datetime.datetime.now()` na `import datetime`
    if (
        isinstance(target, ast.Attribute)
        and target.attr == "datetime"
        and isinstance(target.value, ast.Name)
        and target.value.id in aliases
    ):
        return True
    return False


#: Zoveel .py-bestanden stonden er op 2026-09-08 onder src/. Vloer met ruimte: een
#: verplaatste of hernoemde SRC_ROOT mag de scan niet stil laten leeglopen -- dit
#: bestand had voorheen HELEMAAL GEEN vloer, in tegenstelling tot de rest van de
#: rookmeldersaudit-reeks.
_MINIMUM_SRC_FILES = 1500


def _scan_src_for_naive_datetime() -> tuple[list[str], list[str]]:
    """(violations, fouten).

    Voorheen: `errors="ignore"` op de lezing (verbergt een echte encodingfout i.p.v.
    hem te melden) en een kale `except SyntaxError: continue` zonder telling -- een
    bestand dat niet leest/parseert werd stil overgeslagen, ook al bewaakt deze guard
    een expliciete CLAUDE.md NOOIT-regel (datetime.now()/utcnow() zonder timezone.utc).
    """
    violations: list[str] = []
    fouten: list[str] = []
    for src_file in SRC_ROOT.rglob("*.py"):
        if str(src_file) in _EXEMPT_FILES:
            continue
        try:
            tekst = src_file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            fouten.append(f"{src_file}: {exc}")
            continue
        try:
            tree = ast.parse(tekst)
        except SyntaxError as exc:
            fouten.append(f"{src_file}: {exc}")
            continue
        aliases = _datetime_aliases(tree)
        if not aliases:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_naive_now_call(node, aliases):
                attr = node.func.attr  # type: ignore[attr-defined]
                violations.append(f"{src_file}:{node.lineno}: naive datetime.{attr}() call")

    return violations, fouten


def test_no_source_file_is_silently_unreadable_or_unparseable() -> None:
    """Vangnet: een overgeslagen bestand mag hier niet stil verdwijnen."""
    _, fouten = _scan_src_for_naive_datetime()
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd "
        "op een naive datetime-aanroep:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_the_scan_actually_scans_files() -> None:
    """Vangnet: een verplaatste/hernoemde SRC_ROOT zou de scan stil laten leeglopen."""
    aantal = len(list(SRC_ROOT.rglob("*.py")))
    assert aantal >= _MINIMUM_SRC_FILES, (
        f"Slechts {aantal} bestanden gevonden onder {SRC_ROOT} (verwacht "
        f">= {_MINIMUM_SRC_FILES}). Is SRC_ROOT verplaatst of hernoemd? Dan controleert "
        "deze guard niets meer."
    )


def test_no_naive_datetime_in_src() -> None:
    """datetime.now()/utcnow() zonder timezone.utc zijn verboden in src/ (CLAUDE.md)."""
    violations, _ = _scan_src_for_naive_datetime()

    assert not violations, (
        "datetime.now()/utcnow() zonder timezone.utc gevonden (CLAUDE.md verbod):\n"
        + "\n".join(violations)
    )

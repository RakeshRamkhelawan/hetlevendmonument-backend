#!/usr/bin/env python3
"""
Scan Python codebase for Any usage, split into two counts that share one code path.

  violations   -- Any zonder structurele reden EN zonder acknowledgement. Moet 0 zijn.
  acknowledged -- Any met een acknowledgement-marker. Dit is het ratel-getal: het kan
                  alleen dalen door code te veranderen, want een marker weghalen zonder
                  de annotatie te fixen maakt het een violation.

Beide getallen komen uit dezelfde scan, zodat ze niet uit elkaar kunnen lopen.

De toets of er een `Any` op een regel staat gaat over het CODE-deel van die regel, niet
over het commentaar. Gemeten 2026-09-10 (develop e71cc3c5): 743 van de 7860 geboekte
regels, over 250 bestanden, telden alleen mee omdat het woord "Any" in de TODO-comment
zelf stond op een regel zonder annotatie -- `scripts/inject_any_todos.py` stempelt die
comment ook op een sluitende haakjesregel. Zie `_comment_spans()`. De schuld werd daar
niet kleiner van; de meting werd juist.

Determinisme is hier een eis, niet een bijkomstigheid: de gate in check_any_gate.py
vergelijkt het totaal met een vastgelegde baseline. Twee eerdere constructies lieten dat
totaal verschuiven op een ONVERANDERDE working tree (gemeten 2026-08-13, 34 -> 36):
  - scan_file() ving elke leesfout op en gaf [] terug, dus een tijdelijk onleesbaar
    bestand telde stil als nul (deze repo staat in OneDrive; hydratatie is zo'n fout);
  - get_candidate_files() viel bij een grep-timeout stil terug op een filesystem-walk
    over een andere bestandsset.
Beide zijn nu harde fouten. Zie BE-CI-006.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCAN_DIRS = ["src"]  # tests en frontend uitgesloten -- alleen build-code
EXCLUDE_PARTS = {"__pycache__", ".venv", ".tmp", ".mypy", ".pytest", ".ruff", "archive", "alembic"}

# Structureel: Any is hier de juiste annotatie en blijft dat. Telt in GEEN van beide
# getallen mee -- dit is geen schuld.
STRUCTURAL_PATTERNS = [
    r"\*args:\s*Any",
    r"\*\*kwargs:\s*Any",
    r"__a?exit__",
    r"__getattr__",
    r"__setattr__",
    r"__call__",
    r"Any\s*=\s*None",
    r"typing\.cast\(.*Any",
    r"isinstance\(.*,\s*Any",
    r"Protocol",
    r"@abstractmethod",
    r"overload",
    # Callable[..., Any] is correct for decorator wrappers and generic callbacks
    r"Callable\[.*,\s*Any\]",
    r"Callable\[\.\.\.,\s*Any\]",
]

# Acknowledgement: schuld die BEWUST geboekt is. Telt mee in het ratel-getal, want anders
# zou `inject_any_todos.py --apply` de teller met een commentaarregel kunnen verlagen --
# precies wat er in juli gebeurde (BE-CI-002/003 stempelden 331 regels en rapporteerden 0).
ACKNOWLEDGEMENT_PATTERNS = [
    r"->\s*Any\s*#",
    r"#\s*type:\s*ignore",
    r"#\s*TODO.*Any",
    r"#\s*FIXME.*Any",
    r"#\s*HACK.*Any",
    r"#\s*replace.*Any.*type",
]

# Behouden zodat bestaande aanroepers van is_legitimate()/LEGIT_RE blijven werken.
LEGITIMATE_PATTERNS = STRUCTURAL_PATTERNS + ACKNOWLEDGEMENT_PATTERNS

STRUCTURAL_RE = re.compile("|".join(STRUCTURAL_PATTERNS), re.IGNORECASE)
ACKNOWLEDGEMENT_RE = re.compile("|".join(ACKNOWLEDGEMENT_PATTERNS), re.IGNORECASE)
LEGIT_RE = re.compile("|".join(LEGITIMATE_PATTERNS), re.IGNORECASE)
TODO_RE = re.compile(r"#\s*(TODO|FIXME|HACK).*Any|#\s*replace.*Any.*type", re.IGNORECASE)
IMPORT_RE = re.compile(r"^\s*(from typing import|import .*Any|from .* import .*Any)")
STRING_START_RE = re.compile(r'^\s*([rfbu]*"""|[rfbu]*\'\'\'|[rfbu]*"|[rfbu]*\')')
ANY_WORD_RE = re.compile(r"\bAny\b")


@dataclass
class AnyUsage:
    file: Path
    line_no: int
    line: str
    category: str
    acknowledged: bool
    recommendation: str = ""


class UnreadableFileError(RuntimeError):
    """Een bestand kon niet gelezen worden.

    Bestaat om te voorkomen dat een leesfout stil als "nul usages" doorgaat. Zie de
    moduledocstring: dat was de oorzaak van een teller die op een onveranderde boom
    verschoof.
    """


def category_for_line(line: str) -> str:
    if "dict[" in line or "list[" in line or "Sequence[" in line or "Iterable[" in line:
        return "generic"
    if "-> Any" in line:
        return "return_type"
    if ": Any" in line:
        return "annotation"
    if "= Any" in line or ": Any =" in line:
        return "assignment"
    return "other"


def get_recommendation(category: str) -> str:
    recs = {
        "generic": "Replace with concrete TypedDict or custom generic parameter",
        "return_type": "Specify actual return type; use union types if multiple",
        "annotation": "Replace with specific type (str, int, dict[str, X], BaseModel, etc.)",
        "assignment": "Use Optional[ConcreteType] or union type with None",
        "other": "Review and replace with concrete type",
    }
    return recs.get(category, "Review and replace with concrete type")


def is_structural(line: str) -> bool:
    """Any is op deze regel de juiste annotatie; geen schuld, telt nergens mee."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return True
    return bool(STRUCTURAL_RE.search(line))


def is_acknowledged(line: str) -> bool:
    """Deze regel boekt zijn Any bewust als schuld (TODO/FIXME/type: ignore)."""
    return bool(ACKNOWLEDGEMENT_RE.search(line))


def is_legitimate(line: str) -> bool:
    """Structureel OF geboekt. Behouden voor bestaande aanroepers."""
    return is_structural(line) or is_acknowledged(line)


_FSTRING_START = getattr(tokenize, "FSTRING_START", None)
_FSTRING_END = getattr(tokenize, "FSTRING_END", None)


def _string_literal_line_numbers(content: str) -> set[int]:
    """Return 1-based line numbers that are inside string literals.

    Een f-string wordt behandeld als EEN aaneengesloten span, van FSTRING_START tot
    FSTRING_END. Dat is nodig omdat `tokenize` f-strings per Python-versie anders opdeelt:
    tot 3.11 is een f-string een enkel STRING-token dat al zijn regels dekt, vanaf 3.12 valt
    hij uiteen in FSTRING_START / FSTRING_MIDDLE / expressietokens / FSTRING_END.

    De vorige implementatie voegde in dat tweede geval alleen de regels toe waar een token
    BEGINT, en kwam daardoor op een andere set. Gemeten op 2026-08-13 in
    src/core/agents/agent_factory.py: 266 string-regels op 3.13 tegen 452 op 3.10, wat 9
    tegen 5 getelde Any-regels opleverde. Over de hele repo was dat 7896 lokaal (3.13) tegen
    7892 op de CI-runner (3.11) -- de ratel sloeg rood aan op een verschil dat niets met de
    code te maken had.

    De 3.11-semantiek is hier de norm: de hele f-string is stringinhoud. Een annotatie kan
    daar toch niet staan, dus de conservatieve kant kost niets.
    """
    return _tokenize_once(content)[0]


def _comment_spans(content: str) -> dict[int, list[tuple[int, int]]]:
    """Per regelnummer (1-based) de kolomspans van de comments op die regel.

    Bestaat omdat de teller naar CODE moet kijken en niet naar commentaar. Gemeten
    2026-09-10 op develop e71cc3c5: van de 7860 geboekte regels waren er 743 (over 250
    bestanden) alleen geteld omdat het woord "Any" in de TODO-comment zelf stond, op
    regels zonder enige annotatie -- `scripts/inject_any_todos.py` stempelt die comment
    ook op een sluitende haakjesregel. Het instrument telde daarmee zijn eigen stempel.
    """
    return _tokenize_once(content)[1]


def _tokenize_once(content: str) -> tuple[set[int], dict[int, list[tuple[int, int]]]]:
    """Een tokenize-pas, twee uitkomsten: de stringregels en de comment-spans.

    Waarom EEN pas (Gate-2-bevinding 2026-09-10): twee losse passes maakten de volledige
    scan van src+scripts ruwweg 80 procent duurder (gemeten door de reviewer: 4,12 s voor
    een pas, 7,64 s voor de scan) en die scan draait bij elke commit via de pre-commit-hook
    en drie keer in CI.

    Foutgedrag, en de twee helften verschillen bewust:

      - de STRINGREGELS houden wat er voor het foutpunt is gevonden. Dat was het gedrag
        voor 2026-09-10 en het is de conservatieve kant: een regel die als stringinhoud
        geldt, wordt niet geteld.
      - de COMMENT-SPANS worden bij een fout LEEGGEGOOID. Zonder dat zou de aanroeper de
        gedeeltelijke spans van voor het foutpunt toepassen, en hoe ver de tokenizer komt
        voor hij struikelt verschilt per Python-versie (tot 3.11 een Python-tokenizer,
        vanaf 3.12 een C-tokenizer). De ratel eist exacte gelijkheid met een vastgelegde
        baseline, dus een versieafhankelijk foutpad is precies het incident van 2026-08-13
        opnieuw. Leeg betekent: de aanroeper valt terug op de RUWE regel en telt een echte
        annotatie dus toch.
    """
    string_lines: set[int] = set()
    spans: dict[int, list[tuple[int, int]]] = {}
    try:
        # Diepte, want vanaf 3.12 mogen f-strings genest worden.
        fstring_depth = 0
        fstring_start_line = 0
        for tok in tokenize.generate_tokens(io.StringIO(content).readline):
            if tok.type == tokenize.STRING:
                string_lines.update(range(tok.start[0], tok.end[0] + 1))
            elif tok.type == tokenize.COMMENT:
                spans.setdefault(tok.start[0], []).append((tok.start[1], tok.end[1]))
            elif _FSTRING_START is not None and tok.type == _FSTRING_START:
                if fstring_depth == 0:
                    fstring_start_line = tok.start[0]
                fstring_depth += 1
            elif _FSTRING_END is not None and tok.type == _FSTRING_END:
                fstring_depth = max(0, fstring_depth - 1)
                if fstring_depth == 0:
                    string_lines.update(range(fstring_start_line, tok.end[0] + 1))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        spans = {}
    return string_lines, spans


def code_part_of(line: str, spans: list[tuple[int, int]]) -> str:
    """De regel zonder zijn comments, zodat `Any` in commentaartekst niet meetelt."""
    for start, end in sorted(spans, reverse=True):
        line = line[:start] + line[end:]
    return line


def has_todo_on_line_or_previous(lines: list[str], idx: int) -> bool:
    for offset in range(0, 3):
        check_idx = idx - offset
        if check_idx < 0:
            continue
        if TODO_RE.search(lines[check_idx]):
            return True
    return False


def scan_file(path: Path) -> list[AnyUsage]:
    """Alle niet-structurele Any-regels in een bestand, elk gemarkeerd als geboekt of niet.

    Raises:
        UnreadableFileError: als het bestand niet te lezen is. Bewust GEEN lege lijst --
            dat maakte een leesfout onzichtbaar en de teller onbetrouwbaar.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UnreadableFileError(f"{path}: {type(exc).__name__}: {exc}") from exc

    # split("\n") en NIET splitlines(): `str.splitlines()` splitst ook op form feed,
    # vertical tab, de vier tekens x1c tot x1e, x85, en de twee Unicode-scheidingstekens 2028 en 2029, terwijl tokenize alleen op \n
    # splitst. Een enkele form feed in een bestand schoof daardoor alle regelnummers op,
    # waarna de comment-span van regel N+1 op regel N werd toegepast -- en dan verdwijnt
    # een ECHTE annotatie uit de telling terwijl de spookregel juist WEL wordt geteld:
    # precies de twee richtingen die deze scanner hoort te scheiden. Gemeten door de
    # Gate-2-reviewer op 2026-09-10 met een geconstrueerd bestand; op de huidige repo nul
    # treffers van die tekens in 2156 bestanden, dus het was latent en niet actief.
    lines = content.split("\n")
    string_lines, comment_spans = _tokenize_once(content)
    usages: list[AnyUsage] = []

    for idx, line in enumerate(lines):
        if "Any" not in line:
            continue
        # Only flag standalone `Any` (typing.Any), not identifiers like AnyUsage.
        # De toets gaat over het CODE-deel: `Any` in de TODO-comment zelf is geen
        # annotatie. Zie _comment_spans() voor de meting achter deze regel.
        if not ANY_WORD_RE.search(code_part_of(line, comment_spans.get(idx + 1, []))):
            continue
        # Skip import lines
        if IMPORT_RE.search(line):
            continue
        # Skip string literals (including multi-line docstrings)
        if (idx + 1) in string_lines:
            continue
        # Structurele gevallen vallen volledig weg; geboekte gevallen blijven staan en
        # worden gemarkeerd, zodat ze in het ratel-getal meetellen.
        if is_structural(line):
            continue
        acknowledged = is_acknowledged(line) or has_todo_on_line_or_previous(lines, idx)
        category = category_for_line(line)
        usages.append(
            AnyUsage(
                file=path,
                line_no=idx + 1,
                line=line.strip(),
                category=category,
                acknowledged=acknowledged,
                recommendation=get_recommendation(category),
            )
        )

    return usages


def repo_root() -> Path:
    """De repo-root, zodat het resultaat niet van de cwd afhangt."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def get_candidate_files(scan_dirs: list[str] | None = None) -> list[Path]:
    """Alle GETRACKTE Python-bestanden onder scan_dirs, gesorteerd, repo-relatief.

    Uit de git-index en niet van het bestandssysteem. Dat is een bewuste keuze:

      - Een filesystem-walk neemt untracked en genegeerde bestanden mee. Die staan lokaal
        wel en in CI niet, dus dan meet de gate op twee machines twee verschillende dingen.
      - De vorige grep-variant had een timeout van 60 seconden en viel bij het verstrijken
        daarvan stil terug op een walk over een andere bestandsset. Onder belasting gaf
        dezelfde boom daardoor een ander totaal.
      - `git ls-files` sorteert zelf al, maar sorted() maakt dat expliciet in plaats van
        afhankelijk van een implementatiedetail.

    Raises:
        subprocess.CalledProcessError: als git niet beschikbaar is of dit geen repo is.
            Bewust geen terugval -- een tweede codepad betekent een tweede getal.
    """
    dirs = SCAN_DIRS if scan_dirs is None else scan_dirs
    result = subprocess.run(
        ["git", "ls-files", "-z", "--full-name", "--", *[f"{d}/*.py" for d in dirs]],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_root(),
    )
    candidates = []
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        path = Path(entry)
        if any(part in EXCLUDE_PARTS for part in path.parts):
            continue
        candidates.append(path)
    return sorted(candidates)


MODE_VIOLATIONS = "violations"
MODE_ACKNOWLEDGED = "acknowledged"
MODES = (MODE_VIOLATIONS, MODE_ACKNOWLEDGED)


def scan_paths(paths: Iterable[Path]) -> list[AnyUsage]:
    """Scan een reeks bestanden en geef alle niet-structurele Any-regels terug.

    Propageert UnreadableFileError bewust: een bestand dat wegvalt zou het totaal
    verlagen zonder dat iemand het ziet.
    """
    usages: list[AnyUsage] = []
    for path in paths:
        usages.extend(scan_file(path))
    return usages


def select(usages: Iterable[AnyUsage], mode: str) -> list[AnyUsage]:
    """Filter een scanresultaat op een van de twee modi.

    Dit is het enige punt waar de twee getallen uit elkaar gaan; ze komen uit dezelfde
    scan en kunnen dus niet uit elkaar lopen.
    """
    if mode == MODE_VIOLATIONS:
        return [u for u in usages if not u.acknowledged]
    if mode == MODE_ACKNOWLEDGED:
        return [u for u in usages if u.acknowledged]
    raise ValueError(f"onbekende mode: {mode!r} (kies uit {', '.join(MODES)})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan src/ op Any-gebruik en rapporteer beide tellers."
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        type=Path,
        help="Schrijf een markdown-rapport naar PATH. Zonder deze vlag wordt er GEEN "
        "bestand geschreven (het script liet eerder ongevraagd een rapport in de "
        "repo-root achter, ook bij --help).",
    )
    args = parser.parse_args()

    # Paden uit get_candidate_files() zijn repo-relatief; lees ze ook daar vandaan.
    os.chdir(repo_root())

    print("Finding candidate files...")
    candidates = get_candidate_files()
    print(f"Found {len(candidates)} tracked candidate files")

    all_usages = scan_paths(candidates)
    file_counts: dict[Path, int] = {}
    for usage in all_usages:
        file_counts[usage.file] = file_counts.get(usage.file, 0) + 1

    without_todo = select(all_usages, MODE_VIOLATIONS)
    with_todo = select(all_usages, MODE_ACKNOWLEDGED)

    # Group by file for report
    files_without = {}
    for u in without_todo:
        files_without.setdefault(u.file, []).append(u)

    out_lines = [
        "# Any Usage Scan Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Files with Any usage:** {len(file_counts)}",
        f"**Total Any usages found:** {len(all_usages)}",
        f"**Violations (no acknowledgement):** {len(without_todo)}  <- moet 0 zijn",
        f"**Acknowledged (TODO/type: ignore):** {len(with_todo)}  <- ratel-getal",
        "",
        "---",
        "",
    ]

    if files_without:
        out_lines.append("## Files with Any usage missing TODO comment")
        out_lines.append("")
        # Sort files by count desc
        for file_path, usages in sorted(files_without.items(), key=lambda x: -len(x[1])):
            out_lines.append(f"### `{file_path}` ({len(usages)}x)")
            out_lines.append("")
            for u in usages:
                out_lines.append(f"- **Line {u.line_no}** (`{u.category}`)")
                out_lines.append("  ```python")
                out_lines.append(f"  {u.line}")
                out_lines.append("  ```")
                out_lines.append(f"  -> *{u.recommendation}*")
                out_lines.append("")

    if with_todo:
        out_lines.append("---")
        out_lines.append("")
        out_lines.append("## Files with Any usage + TODO (good)")
        out_lines.append("")
        files_with = {}
        for u in with_todo:
            files_with.setdefault(u.file, []).append(u)
        for file_path in sorted(files_with):
            out_lines.append(f"- `{file_path}` ({len(files_with[file_path])}x)")

    out_lines.append("")
    out_lines.append("---")
    out_lines.append("")
    out_lines.append("## Summary by Category (missing TODO)")
    out_lines.append("")
    from collections import Counter

    cats = Counter(u.category for u in without_todo)
    for cat, cnt in cats.most_common():
        pct = (cnt / len(without_todo) * 100) if without_todo else 0
        out_lines.append(f"- **{cat}:** {cnt} ({pct:.1f}%)")

    out_lines.append("")
    out_lines.append("---")
    out_lines.append("")
    out_lines.append("## Top 10 Files by Count (missing TODO)")
    out_lines.append("")
    for file_path, usages in sorted(files_without.items(), key=lambda x: -len(x[1]))[:10]:
        out_lines.append(f"- `{file_path}`: {len(usages)} usages")

    if args.report:
        args.report.write_text("\n".join(out_lines), encoding="utf-8")
        print(f"\n[OK] Report written to {args.report}")

    print(f"Total Any usages: {len(all_usages)}")
    print(f"Violations (mode={MODE_VIOLATIONS}): {len(without_todo)}")
    print(f"Acknowledged (mode={MODE_ACKNOWLEDGED}): {len(with_todo)}")


if __name__ == "__main__":
    main()

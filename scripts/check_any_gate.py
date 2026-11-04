#!/usr/bin/env python3
"""
Any-type gate met twee tellers en een ratel.

  --mode violations   (default)  Any zonder structurele reden en zonder acknowledgement.
                                 Moet 0 zijn. Dit is de poort die nieuwe schuld weert.
  --mode acknowledged            Any-regels met een acknowledgement (TODO/type: ignore).
                                 Dit is het ratel-getal: vastgelegd in een baseline die
                                 alleen met een zichtbare regel in de diff kan bewegen.

Pre-commit hook (configured in .pre-commit-config.yaml):
    entry: python scripts/check_any_gate.py --fail
    pass_filenames: true
    files: ^(src|scripts)/

CI usage (gewijzigde bestanden, blokkerend):
    python scripts/check_any_gate.py --fail <bestanden>

CI usage (de ratel, blokkerend):
    python scripts/check_any_gate.py --mode acknowledged \
        --baseline docs/any_type_baseline.json

Baseline bijwerken (na een daling, of na bewust geboekte schuld):
    python scripts/check_any_gate.py --mode acknowledged \
        --write-baseline docs/any_type_baseline.json

Waarom --baseline in BEIDE richtingen faalt: een daling die niet wordt vastgelegd laat het
getal weer omhoog kruipen zonder dat iemand het ziet. Falen bij een daling is precies het
moment waarop de ratel vastklikt. Zie BE-CI-006.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows terminals that default to cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue]

_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))
from scan_any_usage import (  # type: ignore  # noqa: E402
    EXCLUDE_PARTS,
    MODE_VIOLATIONS,
    MODES,
    AnyUsage,
    get_candidate_files,
    repo_root,
    scan_paths,
    select,
)

DEFAULT_SCAN_DIRS = ["src", "scripts"]


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_PARTS for part in path.parts)


def collect_paths(inputs: list[str], scan_dirs: list[str]) -> list[Path]:
    """Bestanden om te scannen.

    Zonder argumenten: alle getrackte Python-bestanden onder scan_dirs. Met argumenten:
    de opgegeven bestanden, en voor een directory de getrackte bestanden daaronder. In
    alle gevallen via de git-index, zodat lokaal en CI dezelfde set zien.
    """
    if not inputs:
        return get_candidate_files(scan_dirs)

    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            paths.extend(get_candidate_files([path.as_posix().rstrip("/")]))
        elif path.suffix == ".py":
            paths.append(path)
    return [p for p in paths if not _is_excluded(p)]


def per_file_counts(usages: list[AnyUsage]) -> dict[str, int]:
    """Aantal per bestand, met posix-paden zodat de baseline op Windows en Linux gelijk is."""
    counts: dict[str, int] = {}
    for usage in usages:
        key = usage.file.as_posix()
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_baseline(mode: str, scan_dirs: list[str], usages: list[AnyUsage]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "scan_dirs": sorted(scan_dirs),
        "total": len(usages),
        "per_file": per_file_counts(usages),
    }


def _format_movers(baseline_per_file: dict[str, int], current: dict[str, int]) -> list[str]:
    """De bestanden die bewogen zijn, grootste verschil eerst.

    Zonder dit is een afwijking op een getal van duizenden niet te debuggen.
    """
    keys = set(baseline_per_file) | set(current)
    deltas = []
    for key in keys:
        was = baseline_per_file.get(key, 0)
        now = current.get(key, 0)
        if was != now:
            deltas.append((abs(now - was), key, was, now))
    deltas.sort(reverse=True)
    return [f"    {key}: {was} -> {now}" for _, key, was, now in deltas[:20]]


def compare_with_baseline(
    baseline_path: Path, mode: str, scan_dirs: list[str], usages: list[AnyUsage]
) -> int:
    """Strikte vergelijking. Retourneert de exit-code."""
    if not baseline_path.exists():
        print(f"FAIL: baseline-bestand bestaat niet: {baseline_path}")
        print(f"  Leg de huidige stand vast: python {Path(__file__).name} --mode {mode} "
              f"--write-baseline {baseline_path}")
        return 1

    data = json.loads(baseline_path.read_text(encoding="utf-8"))

    recorded_mode = data.get("mode")
    if recorded_mode is None:
        print(f"FAIL: {baseline_path} heeft geen 'mode'-veld.")
        print("  Een baseline zonder mode is niet te vergelijken -- de twee tellers meten")
        print("  verschillende dingen. Leg hem opnieuw vast met --write-baseline.")
        return 1
    if recorded_mode != mode:
        print(f"FAIL: baseline is vastgelegd voor mode '{recorded_mode}', gevraagd is '{mode}'.")
        return 1

    recorded_dirs = data.get("scan_dirs")
    if recorded_dirs is not None and sorted(recorded_dirs) != sorted(scan_dirs):
        print(
            f"FAIL: baseline dekt {sorted(recorded_dirs)}, deze run scant {sorted(scan_dirs)}."
        )
        print("  Verschillende scope betekent een ander getal; dat is geen regressie maar")
        print("  een appels-met-peren-vergelijking.")
        return 1

    baseline_total = data.get("total", 0)
    total = len(usages)
    print(f"Baseline ({mode}): {baseline_total}; gemeten: {total}")

    if total == baseline_total:
        return 0

    richting = "gestegen" if total > baseline_total else "GEDAALD"
    print(f"\nFAIL: het aantal is {richting} van {baseline_total} naar {total}.")
    movers = _format_movers(data.get("per_file", {}), per_file_counts(usages))
    if movers:
        print("  Bewogen bestanden (max 20):")
        for line in movers:
            print(line)

    if total > baseline_total:
        print("\n  Omhoog betekent nieuwe schuld. Fix de annotatie, of boek de stijging")
        print("  bewust door de baseline bij te werken -- dat wordt een reviewbare regel.")
    else:
        print("\n  Omlaag is goed nieuws, maar moet worden vastgeklikt: zolang de baseline")
        print("  hoger staat kan het getal ongemerkt terugkruipen.")
    print(
        f"  Vastleggen: python {Path(__file__).name} --mode {mode} "
        f"--write-baseline {baseline_path}"
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Any-type gate: weert nieuwe Any en houdt de geboekte schuld op slot."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Python-bestanden of directories. Zonder argumenten: src/ en scripts/.",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default=MODE_VIOLATIONS,
        help=f"Welke teller (default: {MODE_VIOLATIONS}).",
    )
    parser.add_argument(
        "--fail",
        action="store_true",
        help="Exit non-zero zodra er iets gevonden is (alleen zinvol bij --mode violations).",
    )
    parser.add_argument(
        "--baseline",
        metavar="PATH",
        type=Path,
        help="Vergelijk het totaal STRIKT met dit baseline-bestand: elke afwijking, "
        "omhoog of omlaag, is een fout.",
    )
    parser.add_argument(
        "--write-baseline",
        metavar="PATH",
        type=Path,
        help="Schrijf de huidige stand naar dit bestand in plaats van te vergelijken.",
    )
    args = parser.parse_args()

    # get_candidate_files() levert repo-relatieve paden; lees ze ook daar vandaan.
    os.chdir(repo_root())

    # Normaliseer de scope-namen: 'src' en 'src/' moeten dezelfde baseline matchen, anders
    # is de scope-controle zelf een bron van vals-rode builds.
    scan_dirs = sorted(p.rstrip("/\\") for p in args.paths) if args.paths else DEFAULT_SCAN_DIRS
    paths = collect_paths(args.paths, scan_dirs)
    if not paths:
        print("Geen Python-bestanden om te scannen.")
        return 0

    # Een UnreadableFileError wordt bewust NIET gevangen: een bestand dat wegvalt zou het
    # totaal verlagen en de gate stil groen maken. Zie scan_any_usage.scan_file().
    usages = select(scan_paths(paths), args.mode)

    if args.write_baseline:
        baseline = build_baseline(args.mode, scan_dirs, usages)
        args.write_baseline.write_text(
            json.dumps(baseline, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        print(f"Baseline geschreven: {args.write_baseline} (mode={args.mode}, "
              f"total={baseline['total']})")
        return 0

    if args.mode == MODE_VIOLATIONS:
        for usage in usages:
            safe_line = usage.line.strip().replace("", "").replace("", "")[:100]
            print(f"{usage.file}:{usage.line_no}: [ANN-ANY] {safe_line}")

    exit_code = 0
    if args.baseline:
        exit_code = compare_with_baseline(args.baseline, args.mode, scan_dirs, usages)

    if args.mode == MODE_VIOLATIONS and usages:
        print(
            f"\n[ANN-ANY GATE] {len(usages)} Any annotation(s) without TODO(TYPE).\n"
            "Fix options:\n"
            "  1. Replace with a concrete type.\n"
            "  2. Add: # TODO(TYPE): replace Any with concrete type\n"
            "  3. Add: # type: ignore[misc]  (for justified exceptions)\n"
            "Batch-annotate existing baseline:\n"
            "  python scripts/inject_any_todos.py --apply\n"
        )
        if args.fail and exit_code == 0:
            exit_code = 1
    elif exit_code == 0 and not args.baseline:
        print(f"Any-type gate ({args.mode}): {len(usages)} gevonden.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

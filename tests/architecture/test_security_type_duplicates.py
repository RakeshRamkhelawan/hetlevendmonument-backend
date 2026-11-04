"""
Architecture guard: ThreatLevel mag slechts op 1 plek gedefinieerd zijn.

TODO(SP-BACKLOG): Consolideer ThreatLevel duplicaten in src/core/security/.
Drie concurrerende definities gevonden tijdens Gate 2 review (2026-06-13):
  - src/core/security/types.py         (str-based, canonical)
  - src/core/security/security_manager.py  (int-based)
  - src/core/security/security_monitor.py  (str-based, geen INFO)

Test wordt GROEN zodra security_manager en security_monitor hun eigen
ThreatLevel-definitie vervangen door een import vanuit security.types.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SECURITY_PKG = Path(__file__).parents[2] / "src" / "core" / "security"


def _count_threatlevel_class_defs() -> tuple[list[str], list[str], int]:
    """(bestanden die ThreatLevel definieren, parse-fouten, aantal gescand)."""
    files_with_def: list[str] = []
    fouten: list[str] = []
    gescand = 0
    for py_file in _SECURITY_PKG.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{py_file.name}: {exc}")
            continue
        gescand += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ThreatLevel":
                files_with_def.append(py_file.name)
                break
    return sorted(files_with_def), fouten, gescand


def test_the_scan_actually_scans_files() -> None:
    """Vangnet: een onleesbaar/onparseerbaar bestand mag deze guard niet blind maken.

    Een bestand met een syntaxfout en een DERDE ThreatLevel-definitie erin zou stil
    buiten de scan vallen, en een lege of verplaatste map zou de eis hieronder triviaal
    laten slagen.
    """
    _, fouten, gescand = _count_threatlevel_class_defs()
    assert gescand >= 20, (
        f"Slechts {gescand} bestanden gescand onder {_SECURITY_PKG} -- dat lijkt een "
        "(bijna) lege map. Deze guard controleert dan vrijwel niets."
    )
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd "
        "op een ThreatLevel-duplicaat:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_threatlevel_has_single_definition() -> None:
    """ThreatLevel mag slechts in 1 bestand gedefinieerd zijn (types.py).

    TODO(SP-BACKLOG): security_manager.py en security_monitor.py moeten
    hun eigen ThreatLevel verwijderen en importeren vanuit src.core.security.types.
    """
    files, _fouten, _gescand = _count_threatlevel_class_defs()
    assert files == ["types.py"], (
        f"ThreatLevel gedefinieerd in meerdere bestanden: {files}. "
        "Canonical definitie is src/core/security/types.py. "
        "Verwijder duplicaten uit security_manager.py en security_monitor.py."
    )

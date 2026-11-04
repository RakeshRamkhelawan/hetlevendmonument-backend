"""FA-002: HTTPException(5xx) met detail=str(e) of f-string lek in src/core/api/v1/.

OWASP A5 -- Sensitive Data Exposure: stack traces en interne foutberichten
mogen niet teruggegeven worden aan clients.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _ROOT / "src" / "core" / "api" / "v1"


def _is_info_leak_5xx(call: str) -> bool:
    if not re.search(r"status_code\s*=\s*5\d\d", call):
        return False
    if re.search(r"detail\s*=\s*str\(", call):
        return True
    # detail=f"...{e}...", detail=f"...{exc}...", detail=f"...{err}..."
    if re.search(r"detail\s*=\s*f[\"']", call) and re.search(r"\{(?:e|exc|err)[}:]", call):
        return True
    return False


def _find_5xx_leak_violations(path: Path) -> tuple[list[str], list[str], int]:
    """(violaties, onleesbare paden, aantal gescand)."""
    # Line-by-line: verzamel elke raise HTTPException als een enkele aanroep
    # door haakjes te tellen. Geen DOTALL-spanning over meerdere aanroepen.
    violations = []
    fouten: list[str] = []
    gescand = 0
    for f in path.rglob("*.py"):
        try:
            lines = f.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            fouten.append(f"{f}: {exc}")
            continue
        gescand += 1
        i = 0
        while i < len(lines):
            if "HTTPException" in lines[i] and "raise" in lines[i]:
                call = lines[i]
                depth = call.count("(") - call.count(")")
                j = i + 1
                while depth > 0 and j < len(lines):
                    call += "\n" + lines[j]
                    depth += lines[j].count("(") - lines[j].count(")")
                    j += 1
                if _is_info_leak_5xx(call):
                    violations.append(f"{f}:{i + 1}")
                i = j
            else:
                i += 1
    return violations, fouten, gescand


def test_no_httpexception_5xx_with_info_leak_in_v1() -> None:
    """HTTPException(5xx) met detail=str(e) of detail=f'...{e}...' is verboden.

    Fix: logger.error('...', exc_info=True)
         raise HTTPException(status_code=500, detail='Internal error') from e
    """
    violations, fouten, gescand = _find_5xx_leak_violations(_TARGET)
    assert gescand >= 300, (
        f"Slechts {gescand} bestanden gescand onder {_TARGET} -- dat lijkt een (bijna) "
        "lege boom. Deze guard controleert dan vrijwel niets."
    )
    assert not fouten, (
        "Deze bestanden konden niet gelezen worden en zijn NIET gecontroleerd op een "
        "5xx-informatielek:\n" + "\n".join(f"  - {f}" for f in fouten)
    )
    assert violations == [], (
        f"HTTPException(5xx) met informatielek gevonden ({len(violations)} hits) -- "
        "OWASP A5. Fix: vervang detail=str(e)/f-string door detail='Internal error'.\n"
        + "\n".join(str(v) for v in violations[:10])
    )

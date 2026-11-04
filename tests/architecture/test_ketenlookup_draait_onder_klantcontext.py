"""Elke SCHRIJVERSlookup op `audit_logs` draait onder `ketencontext` (Gate 2 F1, ADR-036 OP-246).

Sinds de leesregel op `audit_logs` ziet een schrijver met de context van klant A de keten van klant B niet. Een lookup
`select(AuditLog.audit_hash)` zonder `async with ketencontext(...)` ketent dan aan NIETS en splitst de keten stil.
De guard telt per bronbestand (alleen de schrijvers, `prev_result`; de lezers in `hash_chain`, `audit_verification` en `verify` draaien bewust onder de context van de lezer) de lookups en de `ketencontext`-blokken: er mogen er niet meer lookups zijn dan blokken.

**De ondergrens.** Op 2026-10-24 waren het zes bestanden met precies een lookup. Een scan die minder dan zes bestanden
vindt, zoekt in de verkeerde map of herkent de vorm niet meer, en is dan groen om de verkeerde reden.

**Mutatiebewijs (2026-10-24):** het blok in `audit_service.py` teruggebracht tot de kale lookup -> ROOD; een
`async with ketencontext` weggehaald in `audit.py` -> ROOD; ongewijzigd -> GROEN.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIMUM_BESTANDEN = 6
LOOKUP = re.compile(
    r"prev_result = await [\w\.]+\.execute\(\s*select\(\s*AuditLog\.audit_hash\s*\)"
)
BLOK = re.compile(r"async with ketencontext\(")


def _schone_git_omgeving() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _bestanden_met_lookup() -> list[str]:
    resultaat = subprocess.run(
        ["git", "grep", "--no-index", "-l", "-F", "prev_result = await", "--", "src/"],
        cwd=REPO_ROOT,
        env=_schone_git_omgeving(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultaat.returncode in (0, 1), resultaat.stderr
    return sorted(r for r in resultaat.stdout.split("\n") if r.strip())


def _zonder_blok(tekst: str) -> bool:
    return len(LOOKUP.findall(tekst)) > len(BLOK.findall(tekst))


def test_the_scan_has_a_floor() -> None:
    gevonden = _bestanden_met_lookup()
    assert len(gevonden) >= MINIMUM_BESTANDEN, (
        f"Slechts {len(gevonden)} bestanden met een ketenlookup gevonden, verwacht minstens {MINIMUM_BESTANDEN}: {gevonden}"
    )


def test_the_check_recognises_a_bare_lookup_and_a_wrapped_one() -> None:
    kaal = "prev_result = await db.execute(select(AuditLog.audit_hash).where(a))\n"
    ingepakt = "async with ketencontext(db, t):\n    prev_result = await db.execute(select(AuditLog.audit_hash))\n"
    assert (_zonder_blok(kaal), _zonder_blok(ingepakt)) == (True, False)


def test_every_chain_lookup_runs_under_ketencontext() -> None:
    zonder = [
        naam
        for naam in _bestanden_met_lookup()
        if _zonder_blok((REPO_ROOT / naam).read_text(encoding="utf-8", errors="replace"))
    ]
    assert not zonder, (
        f"Deze bestanden zoeken de vorige ketenhash zonder `ketencontext`: {zonder}. Onder de leesregel op audit_logs ziet "
        "een schrijver met de context van een andere klant die keten niet, en splitst de keten stil. Zie "
        "`src/core/governance/ketencontext.py`."
    )

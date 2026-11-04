"""Niets schrijft ongehashte rijen in `audit_logs` (ADR-036 OP-108, Fase D).

**De bevinding, gemeten 2026-08-09 tijdens BE-AGT-045 slotdag.** Twee plekken doen een RAUWE
`INSERT INTO audit_logs` zonder `audit_hash` en zonder `previous_hash`:

- `src/core/copilot/api/contest_service.py` -- wanneer iemand een besluit aanvecht;
- `src/core/governance/retention_cleanup.py` -- bij elke opruimronde.

`HashChainVerifier.verify_chain` stopt bij de EERSTE afwijking en geeft dan terug. Een
ongehashte rij breekt de keten van die tenant dus permanent vanaf dat punt. Gevolg: in elke
omgeving waar de retentie-opruiming ooit heeft gedraaid, meldt `/api/v1/compliance/integrity/verify`
"gebroken" op zo'n oude regel en BEREIKT hij de nieuwere regels nooit.

**Waarom dit hier staat en niet is gefixt.** De scope-grens van BE-AGT-045 slotdag omvat acht
blokkers; deze bevinding valt daarbuiten. Maar hij mag niet stil blijven liggen, want hij
ondermijnt de opbrengst van H-2: daar is het bewijs van een HITL-beslissing aan de keten
gebonden, en die binding is end-to-end pas waarneembaar als de keten die regel ook BEREIKT.

Dit is een GROENE guard met een gedateerde uitzonderingslijst plus staleness-test, zoals
`.claude/rules/quality-gates.md` voorschrijft voor een bevinding die bewust naar een latere fase
gaat. Een opzettelijk RODE test zou hier de merge van iedereen blokkeren voor iets dat maanden
oud is.

**Mutatietest (2026-08-09, beide richtingen):**
- Een `INSERT INTO audit_logs`-string toegevoegd aan `src/core/governance/audit.py` -> ROOD.
- LEGITIEM: dezelfde tekst in een comment -> ROOD (bewust: dit is een tekst-guard over SQL, en
  een SQL-string in een comment is hier niet te onderscheiden zonder de SQL te parsen; de
  uitzonderingslijst vangt de bekende gevallen af).
- Een van de twee bekende bestanden uit de lijst gehaald -> ROOD, dus de lijst doet iets.
- Een bestand in de lijst dat GEEN insert meer heeft -> ROOD op de staleness-test.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De vorm die de scan zoekt, over BEIDE regels heen: `INSERT\s+INTO` matcht ook een `INSERT INTO`
#: dat over twee regels is gebroken, wat de eerdere `git grep` (per regel) miste.
RAUWE_INSERT = re.compile(r"INSERT\s+INTO\s+(?:public\.)?\"?audit_logs\b", re.IGNORECASE)

#: De ondergrens van de scan (OP-108, 2026-10-23). Gemeten op `df79d145`: 55 bestanden in `src/`
#: noemen `audit_logs`. De drempel staat ruim eronder, zodat gewone opruiming hem niet raakt,
#: maar een kapotte scan (andere map, andere tabelnaam, mislukte `git grep`) wel.
MINIMUM_BESTANDEN_MET_TABELNAAM = 30

#: Een bestand dat de tabelnaam bewust bevat: het model. Hernoemd of verplaatst, dan moet
#: iemand deze guard bijwerken in plaats van hem stil leeg te laten lopen.
BEKEND_BESTAND_MET_TABELNAAM = "src/core/governance/models.py"

#: Bestanden die vandaag een rauwe INSERT in `audit_logs` doen zonder de hashketen te vullen,
#: met datum en reden per regel.
#: OP-114 (2026-08-26): `enhanced_auth_deprecated.py`/`enhanced_auth.py` (het dode module-paar
#: dat hier stond) en hun drie testbestanden zijn verwijderd -- de SEC-K1/SEC-K3-eigenschappen
#: die `test_enhanced_auth_no_seeding.py` pinde, zijn onafhankelijk en grondiger gedekt door
#: `src/core/auth/jwt_handler.py`'s eigen testsuite (test_jwt_secret_validation.py e.a.).
KNOWN_UNHASHED_WRITERS: dict[str, str] = {}


def _schone_git_omgeving() -> dict[str, str]:
    """De omgeving zonder `GIT_*`, zodat git de map uit `cwd` neemt en niet uit `GIT_DIR`."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _bestanden_met_tabelnaam() -> list[str]:
    """Bronbestanden in `src/` die `audit_logs` noemen, via `git grep`.

    Bewust `git grep` en niet zelf de boom inlezen: een test die alle getrackte bestanden in
    Python leest heeft eerder een xdist-worker omgebracht (ADR-036 OP-19/OP-46). Alleen de
    (weinige) bestanden die de tabelnaam noemen worden daarna ingelezen.
    """
    resultaat = subprocess.run(
        ["git", "grep", "--no-index", "-l", "-I", "-i", "-F", "audit_logs", "--", "src/"],
        cwd=REPO_ROOT,
        env=_schone_git_omgeving(),
        capture_output=True,
        text=True,
        check=False,
    )
    if resultaat.returncode not in (0, 1):
        raise AssertionError(
            f"`git grep` faalde (rc={resultaat.returncode}): {resultaat.stderr.strip()!r}. Een "
            "guard die de returncode negeert leest een lege uitvoer als 'niets gevonden'."
        )
    return sorted(r for r in resultaat.stdout.split("\n") if r.strip())


def _bestanden_met_rauwe_audit_insert() -> list[str]:
    """Bronbestanden met een rauwe `INSERT INTO audit_logs`, ook over twee regels gebroken."""
    gevonden = [
        naam
        for naam in _bestanden_met_tabelnaam()
        if RAUWE_INSERT.search((REPO_ROOT / naam).read_text(encoding="utf-8", errors="replace"))
    ]
    return sorted(gevonden)


def test_the_scan_has_a_floor_on_the_real_repository() -> None:
    """De ondergrens (OP-108): met een lege `KNOWN_UNHASHED_WRITERS` toetste niets meer de scan.

    Een lege uitzonderingslijst is de GOEDE toestand, en dan kan `test_the_scan_still_finds_the_
    known_writers` niets meer bewijzen. Deze test kijkt daarom naar wat er bewust WEL staat: de
    tabelnaam in het model, en een minimum aantal bestanden dat de naam noemt. Een scan die in
    een verkeerde map zoekt, een andere tabelnaam gebruikt of stil niets teruggeeft, valt hier.
    """
    gevonden = _bestanden_met_tabelnaam()
    assert BEKEND_BESTAND_MET_TABELNAAM in gevonden, (
        f"De scan vindt `audit_logs` niet meer in {BEKEND_BESTAND_MET_TABELNAAM} (gevonden: "
        f"{len(gevonden)} bestanden). Is het model hernoemd of de scan stuk? In het tweede "
        "geval bewaakt `test_no_new_raw_audit_log_insert` niets."
    )
    assert len(gevonden) >= MINIMUM_BESTANDEN_MET_TABELNAAM, (
        f"Slechts {len(gevonden)} bestanden in src/ noemen `audit_logs`; op 2026-10-23 waren het "
        f"er 55. Is de scan stuk of is er echt code verdwenen? Eerst meten, niet de drempel "
        "verlagen."
    )


def test_the_scan_recognises_a_raw_insert_in_every_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De scan zelf, op een wegwerpmap (`git grep --no-index`): wat hij moet vinden en wat niet.

    Dit is de positieve controle die ontbrak: zonder een bekende schrijver in de echte boom
    bewijst alleen een synthetische repository dat de regex en de aanroep nog werken.
    """
    src = tmp_path / "src"
    src.mkdir()
    moet_vinden = {
        "gewoon.py": 'db.execute("INSERT INTO audit_logs (a) VALUES (1)")\n',
        "hoofdletters.py": 'q = "insert   into AUDIT_LOGS (a) values (1)"\n',
        "gebroken.py": 'q = """INSERT INTO\n    audit_logs (a) VALUES (1)"""\n',
        "schema.py": 'q = "INSERT INTO public.audit_logs (a) VALUES (1)"\n',
        "aanhalingstekens.py": "q = 'INSERT INTO \"audit_logs\" (a) VALUES (1)'\n",
    }
    moet_missen = {
        "lezen.py": 'q = "SELECT * FROM audit_logs"\n',
        "andere_tabel.py": 'q = "INSERT INTO audit_logs_archief (a) VALUES (1)"\n',
        "anders.py": 'q = "INSERT INTO tool_audit_logs (a) VALUES (1)"\n',
    }
    for naam, inhoud in {**moet_vinden, **moet_missen}.items():
        (src / naam).write_text(inhoud, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)

    gevonden = _bestanden_met_rauwe_audit_insert()

    assert gevonden == sorted(f"src/{naam}" for naam in moet_vinden)


def test_the_scan_still_finds_the_known_writers() -> None:
    """Vangnet: vindt de scan de bekende gevallen nog?

    Zonder deze toets zou een hernoemde tabel of een andere SQL-vorm de guard stilzwijgend
    leegmaken -- groen omdat hij niets meer HERKENT, niet omdat er niets meer fout is. Dat is
    de vacuumval die deze sprintdag drie keer heeft opgeleverd.
    """
    gevonden = set(_bestanden_met_rauwe_audit_insert())
    ontbreekt = sorted(set(KNOWN_UNHASHED_WRITERS) - gevonden)

    assert not ontbreekt, (
        f"Deze bekende schrijvers vindt de scan niet meer: {ontbreekt}. Of ze zijn gerepareerd "
        "(haal ze dan uit KNOWN_UNHASHED_WRITERS), of de scan meet niets meer. In het tweede "
        "geval bewaakt de test hieronder niets."
    )


def test_no_new_raw_audit_log_insert() -> None:
    """Nieuwe ongehashte schrijvers zijn geblokkeerd."""
    nieuw = sorted(set(_bestanden_met_rauwe_audit_insert()) - set(KNOWN_UNHASHED_WRITERS))

    assert not nieuw, (
        f"Deze bestanden doen een rauwe INSERT in `audit_logs`: {nieuw}.\n\n"
        "`HashChainVerifier.verify_chain` stopt bij de EERSTE afwijking. Een rij zonder "
        "`audit_hash` breekt de keten van die tenant daarmee permanent vanaf dat punt, en alles "
        "wat erna komt wordt nooit meer geverifieerd -- inclusief het art.-14-bewijs van een "
        "HIGH-risk goedkeuring.\n\n"
        "Gebruik `AuditService.log_event()` (die vult de keten) in plaats van rauwe SQL."
    )


def test_known_unhashed_writers_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET eruit, anders rot de lijst dicht."""
    gevonden = set(_bestanden_met_rauwe_audit_insert())
    opgelost = sorted(
        naam
        for naam in KNOWN_UNHASHED_WRITERS
        if naam not in gevonden and (REPO_ROOT / naam).exists()
    )

    assert not opgelost, (
        f"Deze bestanden staan in KNOWN_UNHASHED_WRITERS maar doen geen rauwe INSERT meer: "
        f"{opgelost}. Haal ze uit de lijst; anders suggereert die lijst een probleem dat er "
        "niet meer is, en dat verbergt de dag waarop OP-108 daadwerkelijk gesloten is."
    )

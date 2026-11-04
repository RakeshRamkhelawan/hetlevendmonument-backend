"""Tests voor scripts/check_any_gate.py -- de twee tellers en de ratel.

Mutatiebewijs (BE-CI-006, vereist door .claude/rules/quality-gates.md):

  - test_baseline_lower_fails      muteert de baseline OMLAAG -> gate rood (nieuwe schuld)
  - test_baseline_higher_fails     muteert de baseline OMHOOG -> gate rood (daling niet
                                   vastgeklikt). Dit is de assertie die vroeger het
                                   tegenovergestelde vastlegde ("INFO", exit 0) en waardoor
                                   het getal ongemerkt kon terugkruipen.
  - test_baseline_equal_passes     de legitieme kant: gelijk mag NIET rood zijn, anders is
                                   "weiger alles" een geldige oplossing.
  - test_unreadable_file_raises    muteert de leesbaarheid van een bestand -> fout in plaats
                                   van een stil lager getal. Dit is de regressietest op het
                                   incident van 2026-08-13 (34 -> 36 op een onveranderde
                                   working tree).
  - test_acknowledged_counts_a_marked_line / test_violations_ignores_a_marked_line
                                   muteren dezelfde regel met en zonder marker: de ene
                                   teller moet hem zien, de andere niet. Zonder dit paar
                                   zou een comment de ratel kunnen verlagen.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("scripts/check_any_gate.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _write_baseline(tmp_path: Path, total: int, mode: str = "acknowledged") -> Path:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"mode": mode, "scan_dirs": ["src"], "total": total, "per_file": {}}),
        encoding="utf-8",
    )
    return baseline_path


def _measure(mode: str) -> int:
    """Het huidige getal, gemeten met dezelfde codepad als de gate zelf."""
    sys.path.insert(0, "scripts")
    from scan_any_usage import get_candidate_files, scan_paths, select  # noqa: PLC0415

    return len(select(scan_paths(get_candidate_files(["src"])), mode))


@pytest.mark.unit
class TestCheckAnyGateRatchet:
    """De ratel faalt in BEIDE richtingen; gelijk blijft groen."""

    def test_baseline_equal_passes(self, tmp_path: Path) -> None:
        """Gelijk aan de baseline is groen -- anders blokkeert de gate al het werk."""
        total = _measure("acknowledged")
        baseline = _write_baseline(tmp_path, total)
        result = _run("--mode", "acknowledged", "--baseline", str(baseline), "src")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_baseline_lower_fails(self, tmp_path: Path) -> None:
        """Meer dan de baseline is nieuwe schuld -> rood."""
        baseline = _write_baseline(tmp_path, _measure("acknowledged") - 1)
        result = _run("--mode", "acknowledged", "--baseline", str(baseline), "src")
        assert result.returncode == 1
        assert "gestegen" in result.stdout

    def test_baseline_higher_fails(self, tmp_path: Path) -> None:
        """Minder dan de baseline moet OOK rood: een daling die niet wordt vastgelegd
        laat het getal ongemerkt terugkruipen. Dit is de ratel."""
        baseline = _write_baseline(tmp_path, _measure("acknowledged") + 1)
        result = _run("--mode", "acknowledged", "--baseline", str(baseline), "src")
        assert result.returncode == 1
        assert "GEDAALD" in result.stdout

    def test_baseline_without_mode_fails(self, tmp_path: Path) -> None:
        """Een baseline zonder mode is niet te vergelijken -- de tellers meten iets anders."""
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"total": 0}), encoding="utf-8")
        result = _run("--mode", "acknowledged", "--baseline", str(baseline), "src")
        assert result.returncode == 1
        assert "geen 'mode'-veld" in result.stdout

    def test_baseline_with_other_scope_fails(self, tmp_path: Path) -> None:
        """Baseline over src/ vergelijken met een run over src+scripts is appels/peren."""
        baseline = _write_baseline(tmp_path, _measure("acknowledged"))
        result = _run("--mode", "acknowledged", "--baseline", str(baseline))
        assert result.returncode == 1
        assert "baseline dekt" in result.stdout

    def test_write_baseline_then_check_is_green(self, tmp_path: Path) -> None:
        """--write-baseline levert een bestand waarmee de gate meteen groen is."""
        baseline = tmp_path / "written.json"
        assert (
            _run("--mode", "acknowledged", "--write-baseline", str(baseline), "src").returncode == 0
        )
        data = json.loads(baseline.read_text(encoding="utf-8"))
        assert data["mode"] == "acknowledged"
        assert data["total"] == _measure("acknowledged")
        assert _run("--mode", "acknowledged", "--baseline", str(baseline), "src").returncode == 0


@pytest.mark.unit
class TestScannerHonesty:
    """De scanner mag een bestand nooit stil als nul tellen."""

    def test_unreadable_file_raises(self) -> None:
        """Een onleesbaar pad geeft een fout, geen lege lijst.

        Regressie op 2026-08-13: scan_file() ving elke exception en gaf [] terug, waardoor
        het totaal op een onveranderde working tree van 34 naar 36 verschoof zodra een
        bestand weer leesbaar werd.
        """
        sys.path.insert(0, "scripts")
        from scan_any_usage import UnreadableFileError, scan_file  # noqa: PLC0415

        with pytest.raises(UnreadableFileError):
            scan_file(Path("src/dit-bestand-bestaat-niet.py"))

    def test_acknowledged_counts_a_marked_line(self, tmp_path: Path) -> None:
        """Een regel MET marker telt in het ratel-getal."""
        sys.path.insert(0, "scripts")
        from scan_any_usage import scan_file, select  # noqa: PLC0415

        target = tmp_path / "sample.py"
        target.write_text(
            "def f(x: Any) -> None:  # TODO(TYPE): replace Any with concrete type\n",
            encoding="utf-8",
        )
        usages = scan_file(target)
        assert len(select(usages, "acknowledged")) == 1
        assert len(select(usages, "violations")) == 0

    def test_violations_counts_an_unmarked_line(self, tmp_path: Path) -> None:
        """Dezelfde regel ZONDER marker telt als violation en niet als geboekte schuld."""
        sys.path.insert(0, "scripts")
        from scan_any_usage import scan_file, select  # noqa: PLC0415

        target = tmp_path / "sample.py"
        target.write_text("def f(x: Any) -> None:\n", encoding="utf-8")
        usages = scan_file(target)
        assert len(select(usages, "violations")) == 1
        assert len(select(usages, "acknowledged")) == 0

    # Een meerregelige f-string, opgebouwd zodat de regelnummers eenduidig zijn:
    #   1: x = f"""
    #   2: {1 + 1}
    #   3: some: Any
    #   4: """
    MULTILINE_FSTRING = 'x = f"""\n{1 + 1}\nsome: Any\n"""\n'

    def test_a_multiline_fstring_is_one_string_span(self) -> None:
        """Alle regels van een f-string gelden als stringinhoud, op ELKE Python-versie.

        `tokenize` deelt f-strings per versie anders op: tot 3.11 is het een enkel
        STRING-token dat al zijn regels dekt, vanaf 3.12 valt hij uiteen in FSTRING_START /
        FSTRING_MIDDLE / expressietokens / FSTRING_END. De oude implementatie voegde in dat
        tweede geval alleen de regels toe waar een token BEGINT en kwam op een andere set.

        Gemeten 2026-08-13 in src/core/agents/agent_factory.py: 266 string-regels op 3.13
        tegen 452 op 3.10, dus 9 tegen 5 getelde Any-regels. Repo-breed 7896 lokaal tegen
        7892 op de CI-runner (3.11), waardoor de ratel rood sloeg op een verschil dat niets
        met de code te maken had.
        """
        sys.path.insert(0, "scripts")
        from scan_any_usage import _string_literal_line_numbers  # noqa: PLC0415

        assert {1, 2, 3, 4} <= _string_literal_line_numbers(self.MULTILINE_FSTRING)

    def test_any_inside_a_multiline_fstring_is_not_counted(self, tmp_path: Path) -> None:
        """De gedragskant van de vorige test: zo'n regel mag in geen van beide tellers zitten."""
        sys.path.insert(0, "scripts")
        from scan_any_usage import scan_file  # noqa: PLC0415

        target = tmp_path / "fstring.py"
        target.write_text(self.MULTILINE_FSTRING, encoding="utf-8")
        assert scan_file(target) == []

    def test_a_real_annotation_next_to_an_fstring_is_still_counted(self, tmp_path: Path) -> None:
        """De andere richting: de f-string-uitzondering mag niet de hele module dempen.

        Zonder deze assertie zou "beschouw alles als string" ook groen zijn, en dan telt de
        gate niets meer.
        """
        sys.path.insert(0, "scripts")
        from scan_any_usage import scan_file, select  # noqa: PLC0415

        target = tmp_path / "mixed.py"
        target.write_text(f"{self.MULTILINE_FSTRING}def f(y: Any) -> None:\n", encoding="utf-8")
        assert len(select(scan_file(target), "violations")) == 1

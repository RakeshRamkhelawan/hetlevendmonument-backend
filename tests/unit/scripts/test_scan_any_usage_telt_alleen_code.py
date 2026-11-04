"""Tests voor scripts/scan_any_usage.py -- de teller kijkt naar CODE, niet naar comments.

Waarom dit bestand bestaat (gemeten 2026-09-10 op develop e71cc3c5). De ratel
`check_any_gate.py --mode acknowledged` stond op 7860. Van die 7860 waren er 743,
verdeeld over 250 bestanden, geen schuld maar een meetfout: `scripts/inject_any_todos.py`
heeft `# TODO(TYPE): replace Any with concrete type` ook gestempeld op regels zonder
annotatie (bijvoorbeeld een sluitende haakjesregel), en `scan_file` toetste `Any` tegen de
HELE regel. Het woord "Any" in de comment-tekst zelf maakte de regel daarmee tot schuld:
het instrument telde zijn eigen stempel. Dat is het patroon
"meetinstrumenten die hun eigen falen niet zien" uit .claude/skills/valkuilen/SKILL.md.

Mutatiebewijs in BEIDE richtingen, zoals .claude/rules/quality-gates.md eist -- zonder de
tweede helft is "tel niets" een geldige oplossing en meet de poort niets meer:

  - test_een_comment_zonder_annotatie_telt_niet   de foute kant: alleen "Any" in de
                                                  comment -> NUL getelde regels.
  - test_een_echte_annotatie_met_marker_telt_wel  de legitieme kant: `dict[str, Any]` in
                                                  de code met dezelfde marker -> geteld en
                                                  geboekt.
  - test_een_type_ignore_met_echte_any_telt_wel   tweede legitieme vorm: de andere
                                                  acknowledgement-marker.
  - test_een_annotatie_zonder_marker_is_een_violation
                                                  de scheiding tussen de twee tellers
                                                  blijft intact: zonder marker is het geen
                                                  geboekte schuld maar een violation.
  - test_een_tokenizefout_valt_terug_op_de_ruwe_regel
                                                  gemeten 2026-09-10: `except
                                                  (tokenize.TokenizeError, ...)` verwees
                                                  naar een attribuut dat niet bestaat
                                                  (Python 3.13.7 en 3.11: `TokenError`),
                                                  dus een bestand met een openstaande accolade
                                                  gaf `AttributeError` in plaats van de
                                                  bedoelde terugval. De pre-commit-hook
                                                  draait op net-bewerkte bestanden, dus dat
                                                  pad is bereikbaar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "scripts")

from scan_any_usage import ANY_WORD_RE, _comment_spans, code_part_of, scan_file  # noqa: E402


def _schrijf(tmp_path: Path, bron: str) -> Path:
    pad = tmp_path / "voorbeeld.py"
    pad.write_text(bron, encoding="utf-8")
    return pad


@pytest.mark.unit
class TestDeTellerKijktNaarCode:
    """Het woord Any in een comment is geen annotatie."""

    def test_een_comment_zonder_annotatie_telt_niet(self, tmp_path: Path) -> None:
        """De sluitende haakjesregel uit inject_any_todos.py is geen schuld."""
        pad = _schrijf(
            tmp_path,
            "CONFIG = dict(\n    a=1,\n)  # TODO(TYPE): replace Any with concrete type\n",
        )
        assert scan_file(pad) == []

    def test_een_echte_annotatie_met_marker_telt_wel(self, tmp_path: Path) -> None:
        """De legitieme kant: annotatie in de code, marker in de comment -> geboekt."""
        pad = _schrijf(
            tmp_path,
            "from typing import Any\n\n"
            "payload: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type\n",
        )
        usages = scan_file(pad)
        assert [(u.line_no, u.acknowledged) for u in usages] == [(3, True)]

    def test_een_type_ignore_met_echte_any_telt_wel(self, tmp_path: Path) -> None:
        """Tweede acknowledgement-vorm; ook hier zit de Any in de code."""
        pad = _schrijf(
            tmp_path,
            "from typing import Any\n\n"
            "def bewerk(waarde: Any) -> int:  # type: ignore[misc]\n"
            "    return 1\n",
        )
        usages = scan_file(pad)
        assert [(u.line_no, u.acknowledged) for u in usages] == [(3, True)]

    def test_een_annotatie_zonder_marker_is_een_violation(self, tmp_path: Path) -> None:
        """De twee tellers blijven gescheiden: geen marker betekent niet geboekt."""
        pad = _schrijf(
            tmp_path,
            "from typing import Any\n\npayload: dict[str, Any] = {}\n",
        )
        usages = scan_file(pad)
        assert [(u.line_no, u.acknowledged) for u in usages] == [(3, False)]

    def test_een_tokenizefout_valt_terug_op_de_ruwe_regel(self, tmp_path: Path) -> None:
        """Een half bewerkt bestand geeft geen AttributeError, en verliest de regel niet.

        Twee dingen tegelijk, want ze horen bij hetzelfde foutpad. De AttributeError-kant:
        `except (tokenize.TokenizeError, ...)` verwees naar een attribuut dat niet bestaat,
        dus deze invoer gaf een AttributeError in plaats van de bedoelde terugval. De
        terugval-kant: bij een tokenize-fout worden de comment-spans LEEGGEGOOID (zie
        `_tokenize_once`), dus de spookcomment op regel 3 wordt hier NIET gestript en de
        regel telt op de ruwe tekst. Dat is bewust de veilige kant; hoe ver de tokenizer
        komt voor hij struikelt verschilt per Python-versie, en de ratel eist exacte
        gelijkheid met de baseline.
        """
        pad = _schrijf(
            tmp_path,
            "from typing import Any\n\n"
            "x: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type\n",
        )
        assert _comment_spans(pad.read_text(encoding="utf-8")) == {}
        usages = scan_file(pad)
        assert [(u.line_no, u.acknowledged) for u in usages] == [(3, True)]

    def test_een_hekje_in_een_stringliteral_is_geen_comment(self) -> None:
        """Waarom tokenize en niet `line.split("#")[0]`.

        Met een naieve splitsing op het eerste hekje verdwijnt de hele annotatie uit het
        codedeel. Deze test houdt die vereenvoudiging tegen, en doet dat op
        `code_part_of()` zelf en niet op `scan_file()`: die laatste slaat een regel die
        binnen een STRING-token valt in zijn geheel over (de regel hieronder bevat een
        stringliteral en wordt dus toch niet geteld). Dat is een grovere regel dan nodig
        en hij kan een echte annotatie meenemen; hoeveel van de 699 zo overgeslagen
        regels een echte annotatie dragen is op 2026-09-10 NIET vastgesteld -- zie de
        ADR-036-rij OP-232. Wie dat wil meten moet de positie van `Any` vergelijken met
        de KOLOMspans van de STRING-tokens, niet met het regelnummer.
        """
        regel = 'def f(x: Any = "#geen-comment") -> None:  # TODO(TYPE): replace Any'
        spans = _comment_spans(regel + "\n    return None\n")
        code = code_part_of(regel, spans.get(1, []))
        assert "#geen-comment" in code
        assert "TODO" not in code
        assert ANY_WORD_RE.search(code) is not None

    def test_een_form_feed_schuift_de_regelnummers_niet(self, tmp_path: Path) -> None:
        """De regelbron moet dezelfde nummering hebben als tokenize.

        Gevonden door de Gate-2-reviewer op 2026-09-10: `str.splitlines()` splitst ook op
        form feed en vijf andere tekens, `tokenize` alleen op \\n. Een enkele form feed
        schoof daarmee alle regelnummers op, waarna de comment-span van regel N+1 op regel
        N werd toegepast. Gevolg was de omkering van precies deze twee richtingen: de
        ECHTE annotatie viel uit de telling en de spookregel werd wel geteld. Op de
        huidige repo nul treffers, dus latent -- maar dit is de enige plek die een
        annotatie kan laten verdwijnen, en daar hoort een test op.
        """
        pad = _schrijf(
            tmp_path,
            "from typing import Any\n"
            "\x0c\n"
            "z: dict[str, Any] = {}\n"
            "w = 1  # TODO(TYPE): replace Any with concrete type\n",
        )
        usages = scan_file(pad)
        assert [(u.line_no, u.acknowledged) for u in usages] == [(3, False)]

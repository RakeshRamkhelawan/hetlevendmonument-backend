"""`status` en `whois` melden ongevraagd wat goedgekeurd is en blijft liggen (SP-WF-001 dag 1b).

WAAROM DIT BESTAAT
------------------
`approved[sha]` in het gatebestand en de stand van `origin/develop` staan volledig los van
elkaar. Niets verbindt ze, dus een goedkeuring kan blijven liggen zonder dat iets dat zegt.
Gemeten: `839d98e1` stond een dag goedgekeurd en ongepusht, en dat kwam alleen aan het licht
doordat een sessie bij ANDER werk de commitlijst natelde. Een goedkeuring die niemand inlost
is geen restpunt maar een gat in de keten: de poort is gedraaid, de tweede hand heeft
getekend, en er staat niets op `develop`.

`status` en `whois` staan al in de openingsronde van elke sessie, dus daar hoort het signaal.

WAARTEGEN WORDT GEMETEN, EN WAAROM DAT DE LOKALE REF IS
-------------------------------------------------------
Niet `git ls-remote` maar de LOKALE `origin/develop`-ref. De keuze gaat over de
faalRICHTING, niet over snelheid:

- lokale ref verouderd -> een GELANDE sha wordt alsnog gemeld. Vals alarm, luid, je kijkt
  en het is klaar.
- `ls-remote` bij een haperend netwerk -> geen uitspraak, dus GEEN waarschuwing, en precies
  dan mis je de sha die een dag blijft liggen.

Een controle hoort luid te falen en niet stil. De uitvoer drukt daarom af tegen welke sha is
gemeten, zodat een vals alarm leesbaar is in plaats van verwarrend.

DRIE UITKOMSTEN, EN ZE BETEKENEN NIET HETZELFDE
-----------------------------------------------
- voorouder van de lokale `origin/develop` -> GELAND, zwijgen.
- bestaat lokaal, geen voorouder          -> BLIJFT LIGGEN, melden.
- bestaat lokaal HELEMAAL NIET            -> ONBEPAALD, apart melden.

Die derde krijgt een eigen kop in de uitvoer en wordt NIET bij "blijft liggen" gezet. Een
sha die je niet kunt vinden als "niet geland" presenteren is een bewering die je niet kunt
waarmaken -- dat is de vorm waar dit project structureel op stukloopt.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_WORTEL = Path(__file__).resolve().parents[3]
_SCRIPT = _WORTEL / "scripts" / "push_gate.py"


def _laad_module():
    """`scripts/` is geen pakket, dus laden op pad -- zelfde aanpak als
    `tests/architecture/test_niemand_keurt_zijn_eigen_push_goed.py`."""
    spec = importlib.util.spec_from_file_location("push_gate_1b_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["push_gate_1b_test"] = module
    spec.loader.exec_module(module)
    return module


POORT = _laad_module()
WAARSCHUW_NA = POORT.WAARSCHUW_NA
_blijft_liggen = POORT._blijft_liggen

GELAND = "a" * 40
BLIJFT_LIGGEN = "b" * 40
ONBEKEND = "c" * 40


def _tijdstip(uren_geleden: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=uren_geleden)).isoformat()


def _gate(**goedkeuringen: str) -> dict:
    return {
        "coordinator": {"session": "regie", "since": _tijdstip(48)},
        "approved": {
            sha: {"by": "iemand", "approved_at": wanneer, "note": ""}
            for sha, wanneer in goedkeuringen.items()
        },
    }


def _status(sha: str) -> bool | None:
    """Vervangt de git-aanroep: geen echte repo nodig, en geen `git init` in tmp_path."""
    return {GELAND: True, BLIJFT_LIGGEN: False, ONBEKEND: None}[sha]


class TestWelkeGoedkeuringenBlijvenLiggen:
    def test_een_niet_gelande_sha_verschijnt(self) -> None:
        liggen, onbepaald = _blijft_liggen(_gate(**{BLIJFT_LIGGEN: _tijdstip(3)}), _status)

        assert [s for s, _ in liggen] == [BLIJFT_LIGGEN]
        assert onbepaald == []

    def test_een_gelande_sha_verschijnt_NIET(self) -> None:
        """De belangrijkste helft. Zonder deze is 'meld alles' een geldige oplossing, en
        dan is de waarschuwing binnen een week ruis die niemand meer leest."""
        liggen, onbepaald = _blijft_liggen(_gate(**{GELAND: _tijdstip(3)}), _status)

        assert liggen == []
        assert onbepaald == []

    def test_een_onbekende_sha_staat_APART_en_niet_bij_blijft_liggen(self) -> None:
        liggen, onbepaald = _blijft_liggen(_gate(**{ONBEKEND: _tijdstip(3)}), _status)

        assert liggen == [], "een sha die lokaal niet bestaat is GEEN vastgestelde achterstand"
        assert [s for s, _, _ in onbepaald] == [ONBEKEND]


class TestDeUurgrensDoetIetsInBEIDERichtingen:
    """Een grens die per ongeluk NOOIT vuurt is niet van een werkende grens te
    onderscheiden. Tijdgrenzen zijn in dit project al twee keer stil verkeerd gebleken,
    dus beide kanten staan hier."""

    def test_jonger_dan_de_grens_verschijnt_niet(self) -> None:
        liggen, _ = _blijft_liggen(_gate(**{BLIJFT_LIGGEN: _tijdstip(0.25)}), _status)

        assert liggen == []

    def test_ouder_dan_de_grens_verschijnt_wel(self) -> None:
        net_erover = WAARSCHUW_NA.total_seconds() / 3600 + 0.05
        liggen, _ = _blijft_liggen(_gate(**{BLIJFT_LIGGEN: _tijdstip(net_erover)}), _status)

        assert [s for s, _ in liggen] == [BLIJFT_LIGGEN]


class TestDeWaarschuwingIsNietTeMissen:
    """Hij staat BOVENAAN. Een rustige regel onderaan wordt overgeslagen op precies de
    ochtend dat het ertoe doet."""

    @pytest.fixture(autouse=True)
    def _eigen_gatebestand(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        bestand = tmp_path / "gate.json"
        bestand.write_text(json.dumps(_gate(**{BLIJFT_LIGGEN: _tijdstip(3)})), encoding="utf-8")
        monkeypatch.setattr(POORT, "GATE_PATH", bestand)
        # De naad zit sinds de batching op `_landingsstatussen` (een aanroep voor
        # alle shas) en niet meer op een functie per sha.
        monkeypatch.setattr(
            POORT, "_landingsstatussen", lambda shas, basis: {s: _status(s) for s in shas}
        )
        monkeypatch.setattr(POORT, "_lokale_develop", lambda: "d" * 40)

    def test_status_zet_de_waarschuwing_bovenaan(self, capsys: pytest.CaptureFixture) -> None:
        POORT.cmd_status(None)  # type: ignore[arg-type]
        regels = [r for r in capsys.readouterr().out.splitlines() if r.strip()]

        assert "BLIJFT LIGGEN" in regels[0], f"eerste regel was: {regels[0]!r}"
        assert any(BLIJFT_LIGGEN[:12] in r for r in regels)

    def test_whois_zet_de_waarschuwing_bovenaan(self, capsys: pytest.CaptureFixture) -> None:
        POORT.cmd_whois(None)  # type: ignore[arg-type]
        regels = [r for r in capsys.readouterr().out.splitlines() if r.strip()]

        assert "BLIJFT LIGGEN" in regels[0], f"eerste regel was: {regels[0]!r}"

    def test_de_uitvoer_noemt_waartegen_is_gemeten(self, capsys: pytest.CaptureFixture) -> None:
        """Zonder dit is een vals alarm door een verouderde ref niet te herkennen."""
        POORT.cmd_status(None)  # type: ignore[arg-type]
        uit = capsys.readouterr().out

        assert "d" * 12 in uit, "de sha van de lokale origin/develop-ref hoort in de uitvoer"

    def test_de_exitcode_blijft_0(self, capsys: pytest.CaptureFixture) -> None:
        """Geen exitcode wijzigen: aanroepers rekenen op 0, en dan wordt de waarschuwing
        een storing in plaats van een signaal."""
        assert POORT.cmd_status(None) == 0  # type: ignore[arg-type]
        capsys.readouterr()


class TestDeBatchingZelfKlopt:
    """De tests hierboven vervangen `_landingsstatussen` door een tabel, dus de BATCHING
    zelf -- het ingewikkeldste deel -- zou daarmee ongetest blijven.

    Deze klasse draait hem tegen de ECHTE repo, want dat is de enige producent die telt.
    De drie shas zijn zo gekozen dat ze niet verouderen:
      `origin/develop` zelf   -> altijd voorouder van zichzelf  -> GELAND
      `HEAD` van deze tak     -> ligt voor op origin/develop    -> BLIJFT LIGGEN
      een verzonnen sha       -> bestaat niet                   -> NIET VAST TE STELLEN

    Geen `git init` in tmp_path: dat herinitialiseert onder de pre-push hook de ECHTE repo
    (gedocumenteerde valkuil). Deze test draait bewust in de repo waar hij staat.
    """

    @staticmethod
    def _sha(rev: str) -> str:
        import subprocess

        uit = subprocess.run(
            ["git", "rev-parse", rev], capture_output=True, text=True, check=True
        )
        return uit.stdout.strip()

    def test_alle_drie_de_uitkomsten_op_de_echte_repo(self) -> None:
        basis = self._sha("refs/remotes/origin/develop")
        geland = basis
        blijft_liggen = self._sha("HEAD")
        verzonnen = "d" * 40

        if blijft_liggen == basis:
            pytest.skip("deze tak ligt niet voor op origin/develop; geen niet-gelande sha")

        uitkomst = POORT._landingsstatussen([geland, blijft_liggen, verzonnen], basis)

        assert uitkomst[geland] is True
        assert uitkomst[blijft_liggen] is False
        assert uitkomst[verzonnen] is None, (
            "een sha die niet bestaat moet NIET VAST TE STELLEN opleveren. Wordt dit False, "
            "dan meldt de waarschuwing hem als achterstand -- een bewering die niet waar te "
            "maken is. Wordt het True, dan zwijgt de waarschuwing over een echte achterstand."
        )

    def test_zonder_basis_is_niets_vast_te_stellen(self) -> None:
        """Geen lokale origin/develop-ref -> geen uitspraak, en zeker geen 'alles geland'."""
        uitkomst = POORT._landingsstatussen(["e" * 40], None)

        assert uitkomst == {"e" * 40: None}


class TestEenKapotteTimestampWordtGEMELDenNietOvergeslagen:
    """Gevonden door de Gate 2-code-review, en het was de ergste vorm die er is.

    De eerste versie deed `continue` bij een lege of onparseerbare `approved_at`. De rij
    verdween dan zonder enige uitvoer -- stil falen op precies de plek die stil falen moest
    opvangen. Het gatebestand is gedeeld JSON dat met de hand bewerkt wordt (de eigen
    historie bevat een handmatig gecorrigeerde notitie), dus dit pad is niet theoretisch.
    """

    def test_een_ontbrekende_approved_at_verdwijnt_niet(self) -> None:
        data = {"approved": {BLIJFT_LIGGEN: {"by": "iemand"}}}

        liggen, onbepaald = _blijft_liggen(data, _status)

        assert liggen == []
        assert [s for s, _, _ in onbepaald] == [BLIJFT_LIGGEN]
        assert "geen approved_at" in onbepaald[0][2]

    def test_een_onleesbare_approved_at_verdwijnt_niet(self) -> None:
        data = {"approved": {BLIJFT_LIGGEN: {"by": "iemand", "approved_at": "gisteren"}}}

        liggen, onbepaald = _blijft_liggen(data, _status)

        assert liggen == []
        assert [s for s, _, _ in onbepaald] == [BLIJFT_LIGGEN]
        assert "onleesbaar" in onbepaald[0][2], (
            "de reden moet zeggen WAT er mis is, anders weet de lezer niet of hij moet "
            "fetchen of het gatebestand moet repareren"
        )


def test_een_kapotte_approved_sectie_laat_de_controle_niet_crashen() -> None:
    """Toegevoegd bij het hertyperen: `approved` hoort een dict te zijn, maar het
    gatebestand wordt met de hand bewerkt. Een lijst of een string mag geen traceback
    geven -- dan valt de controle weg op precies het moment dat het bestand aandacht
    nodig heeft."""
    for kapot in ([], "nee", 42, None):
        liggen, onbepaald = _blijft_liggen({"approved": kapot}, _status)
        assert (liggen, onbepaald) == ([], []), f"struikelde over {kapot!r}"

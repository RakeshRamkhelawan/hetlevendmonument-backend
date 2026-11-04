"""`push_gate.py approve` weigert de auteur van de commit (2026-09-18).

WAAROM DEZE BEWAKER BESTAAT
---------------------------
De pushgoedkeuring gaat uit van twee partijen: de een schrijft, de ander keurt goed. Met
een enkele sessie was `approve --by <jezelf>` een handtekening die je aan jezelf gaf --
gemeten: op 2026-09-17/18 acht keer gebeurd, telkens netjes vermeld in de notitie en
telkens zonder dat er iets werd gecontroleerd.

Het kon ook niet anders, want er was geen FEIT waaraan de auteur te herkennen was: een
goedkeuringsrij bevatte alleen `{approved_at, by, note}`, en git kan de sessies niet
onderscheiden (elke commit in deze repo heeft auteur `toets <t@t.t>`). Daarom is er eerst
een `request`-commando bijgekomen dat de aanvrager EN zijn werkmap vastlegt; deze bewaker
ziet erop toe dat `approve` die twee ook echt gebruikt.

**Waarom de werkmap en niet alleen de naam.** Een sessienaam is geen identiteit: bij een
resume krijgt dezelfde sessie een andere naam (gemeten 2026-09-15: `org-93` kwam terug als
`org-03`). Zonder de werkmapcontrole zou een hernoemde sessie haar eigen werk alsnog
kunnen goedkeuren.

OPZET, EN WAT DEZE TEST BEWUST NIET TOETST
------------------------------------------
De functies worden rechtstreeks aangeroepen met een eigen gate-bestand in `tmp_path`, en
`monkeypatch.chdir()` zet een ECHTE werkmap -- `_werkmap()` leest die zelf, dus de
identiteit die bewaakt wordt is niet weggemockt. Alleen `_resolve_sha` is vervangen: die
roept `git rev-parse` aan, en in een tijdelijke map is geen repo. Dat hoort ook niet bij
het onderwerp van deze test. Er wordt GEEN `git init` in `tmp_path` gedaan -- gemeten
valkuil: `git init` onder de pre-push hook herinitialiseerde de ECHTE repo.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakt element)
--------------------------------------------------------------------------
    approve ZONDER voorafgaande request            -> GEWEIGERD (rc=1)
    de AUTEUR keurt zichzelf goed (zelfde naam)    -> GEWEIGERD (rc=1)
    andere naam, ZELFDE werkmap                    -> GEWEIGERD (rc=1)
    andere naam, ANDERE werkmap                    -> TOEGESTAAN (rc=0) met `authored_by`
    `--human` zonder aanvraag                      -> GEWEIGERD (rc=1)
    `--human` MET aanvraag, zelfde werkmap         -> TOEGESTAAN (rc=0), `by_human` vast
Ook gedraaid tegen het echte script met het echte gate-bestand, met herstel achteraf.

MUTATIEBEWIJS OP HET WERKMAPVELD (2026-09-19, SP-WF-001 dag 2)
--------------------------------------------------------------
    `"worktree": _werkmap()` weggehaald uit het approved-blok -> 2 failed, 7 passed
    `"worktree": aanvraag["worktree"]` (werkmap van de AUTEUR
    gekopieerd in plaats van die van de goedkeurder)          -> 2 failed, 7 passed
    ongemuteerd                                               -> 9 passed
De tweede is de mutatie waar het om gaat: hij houdt een test die alleen op AANWEZIGHEID
toetst groen. Daarom staat er een tweede test die eist dat de twee werkmappen VERSCHILLEN.

Twee valkuilen uit dit mutatiewerk, allebei van de schrijver zelf:
- De eerste poging verving de string `"worktree": _werkmap(),` zonder anker. Die staat OOK
  in `cmd_request` (push_gate.py:347), dus de mutatie haalde BEIDE werkmapvelden weg en gaf
  `KeyError: 'worktree'` -- 6 failures in plaats van 2. Een mutatie moet net zo gericht zijn
  als de assertie die hem moet vangen; anker op een omliggende regel.
- `test_..._VERSCHILLEN` stond aanvankelijk GROEN terwijl het veld nog niet bestond:
  `rij.get("worktree")` gaf `None` en `None != <pad>` is vanzelf waar. Een assertie op een
  VERSCHIL moet eerst het BESTAAN eisen, anders is hij leeg precies wanneer het misgaat.

De naamcontrole bleef bij de eerste ronde GROEN onder zijn eigen mutatie: alle gevallen
lieten de auteur goedkeuren vanuit dezelfde map, dus de werkmapcontrole ving het al af.
`test_dezelfde_naam_vanuit_een_andere_werkmap_wordt_ook_geweigerd` is daarvoor
toegevoegd -- twee controles vragen twee tests.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_WORTEL = Path(__file__).resolve().parents[2]
_SCRIPT = _WORTEL / "scripts" / "push_gate.py"

_SHA = "0" * 40


def _laad_module():
    """`scripts/` is geen pakket, dus laden op pad."""
    spec = importlib.util.spec_from_file_location("push_gate_voor_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["push_gate_voor_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def poort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """De module met een eigen gate-bestand, plus twee werkmappen."""
    module = _laad_module()
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"coordinator": None, "approved": {}}), encoding="utf-8")
    monkeypatch.setattr(module, "GATE_PATH", gate)
    monkeypatch.setattr(module, "LOCK_PATH", tmp_path / "gate.lock")
    monkeypatch.setattr(module, "_resolve_sha", lambda _rev: _SHA)

    auteur = tmp_path / "worktree-auteur"
    goedkeurder = tmp_path / "worktree-goedkeurder"
    for m in (auteur, goedkeurder):
        m.mkdir()
    return SimpleNamespace(
        module=module, gate=gate, auteur=auteur, goedkeurder=goedkeurder, mp=monkeypatch
    )


def _vraag_aan(poort, sessie: str, vanuit: Path) -> int:
    poort.mp.chdir(vanuit)
    return poort.module.cmd_request(SimpleNamespace(sha=_SHA, session=sessie))


def _keur_goed(poort, door: str, vanuit: Path, mens: bool = False) -> int:
    poort.mp.chdir(vanuit)
    return poort.module.cmd_approve(
        SimpleNamespace(sha=_SHA, by=door, note="toets", human=mens)
    )


def test_zonder_aanvraag_kan_niemand_goedkeuren(poort) -> None:
    """Geen vastgelegde auteur betekent geen controleerbare tweede partij."""
    assert _keur_goed(poort, "sessie-B", poort.goedkeurder) == 1

    opgeslagen = json.loads(poort.gate.read_text(encoding="utf-8"))
    assert not opgeslagen.get("approved"), "er is goedgekeurd zonder bekende auteur"


def test_de_auteur_kan_zichzelf_niet_goedkeuren(poort) -> None:
    _vraag_aan(poort, "sessie-A", poort.auteur)

    assert _keur_goed(poort, "sessie-A", poort.auteur) == 1

    opgeslagen = json.loads(poort.gate.read_text(encoding="utf-8"))
    assert not opgeslagen.get("approved"), (
        "De auteur heeft zijn eigen commit goedgekeurd. Een tweede handtekening van "
        "dezelfde hand is geen tweede handtekening."
    )


def test_de_goedkeuring_legt_de_werkmap_van_de_GOEDKEURDER_vast(poort) -> None:
    """De handhaving werkte, de vastlegging niet (ADR SP-WF-001 dag 2, 2026-09-19).

    `cmd_approve` VERGELIJKT de werkmap van de goedkeurder met die van de aanvrager en
    weigert bij gelijkheid -- dat is bewezen door de tests hierboven. Maar het record dat
    daarna wordt weggeschreven bevatte alleen `by`, `authored_by`, `by_human`, `note` en
    `approved_at`. Wie het bestand later leest, ziet WIE tekende maar niet DAT die
    onafhankelijk was.

    Gemeten op 2026-09-19 in het echte gate-bestand: de aanvraagsleutels zijn
    ['requested_at', 'session', 'worktree'], de goedkeuringssleutels
    ['approved_at', 'authored_by', 'by', 'by_human', 'note']. De sessie die dit vond had
    zelf twee keer vanuit een andere map getekend zonder dat het record dat liet zien.

    Waarom dit NU telt: er komt een hashketen over dit bestand. Een keten verzegelt wat
    er staat. Staat de onafhankelijkheid er niet in, dan is het gat niet gedicht maar
    ondertekend.
    """
    _vraag_aan(poort, "sessie-A", poort.auteur)
    assert _keur_goed(poort, "sessie-B", poort.goedkeurder) == 0

    rij = json.loads(poort.gate.read_text(encoding="utf-8"))["approved"][_SHA]

    assert "worktree" in rij, (
        "De goedkeuring legt de werkmap van de goedkeurder niet vast. Het record toont "
        "dan wie tekende, niet dat die uit een andere map kwam -- en dat laatste is wat "
        "de goedkeuring geldig maakt. Sleutels nu: %s" % sorted(rij)
    )
    assert rij["worktree"] == str(poort.goedkeurder.resolve()), (
        "De vastgelegde werkmap is niet die van de goedkeurder maar %r." % rij["worktree"]
    )


def test_de_vastgelegde_werkmappen_van_auteur_en_goedkeurder_VERSCHILLEN(poort) -> None:
    """Niet de aanwezigheid van een string telt, maar dat de twee uit elkaar liggen.

    Zonder deze test zou `"worktree": aanvraag["worktree"]` -- de werkmap van de AUTEUR
    kopieren in plaats van die van de goedkeurder opschrijven -- de test hierboven groen
    houden. Dat is precies de vorm waar deze reeks vandaag drie keer op is gestruikeld:
    een assertie die de aanwezigheid toetst in plaats van de eigenschap.
    """
    _vraag_aan(poort, "sessie-A", poort.auteur)
    assert _keur_goed(poort, "sessie-B", poort.goedkeurder) == 0

    opgeslagen = json.loads(poort.gate.read_text(encoding="utf-8"))
    aanvraag = opgeslagen["requested"][_SHA]["worktree"]
    rij = opgeslagen["approved"][_SHA]

    # Eerst bestaan, dan verschillen. Zonder deze regel is de assertie hieronder LEEG als
    # het veld ontbreekt (`None != <pad>` is vanzelf waar) -- gemeten: deze test stond
    # groen terwijl de fix er nog niet was.
    assert "worktree" in rij, "geen werkmap in de goedkeuring; sleutels: %s" % sorted(rij)
    goedkeuring = rij["worktree"]

    assert goedkeuring != aanvraag, (
        "De werkmap in de goedkeuring is dezelfde als die in de aanvraag (%r). Dan legt "
        "het record de onafhankelijkheid niet vast maar herhaalt het de auteur." % aanvraag
    )


def test_een_hernoemde_sessie_wordt_herkend_aan_haar_werkmap(poort) -> None:
    """De helft die een naamswijziging bij een resume afdekt."""
    _vraag_aan(poort, "sessie-A", poort.auteur)

    assert _keur_goed(poort, "sessie-A-na-resume", poort.auteur) == 1

    opgeslagen = json.loads(poort.gate.read_text(encoding="utf-8"))
    assert not opgeslagen.get("approved"), (
        "Een sessie die onder een andere naam terugkwam keurde haar eigen werk goed. "
        "De naam is geen identiteit; de werkmap wel."
    )


def test_dezelfde_naam_vanuit_een_andere_werkmap_wordt_ook_geweigerd(poort) -> None:
    """De NAAMcontrole los, want de werkmapcontrole dekte hem af.

    Dit geval ontbrak in de eerste versie van deze bewaker, en het mutatiebewijs liet dat
    zien: met alleen de drie tests hierboven bleef hij GROEN toen ik de naamcontrole uit
    `approve` haalde -- de auteur keurde daar immers goed vanuit dezelfde map, dus de
    werkmapcontrole ving het al. Twee controles, twee tests.

    Het geval is echt: een sessie kan van worktree wisselen, of twee sessies kunnen
    dezelfde naam voeren nadat er een is hernoemd.
    """
    _vraag_aan(poort, "sessie-A", poort.auteur)

    assert _keur_goed(poort, "sessie-A", poort.goedkeurder) == 1

    opgeslagen = json.loads(poort.gate.read_text(encoding="utf-8"))
    assert not opgeslagen.get("approved"), (
        "Dezelfde sessienaam keurde haar eigen commit goed vanuit een andere map. De "
        "werkmap is de sterkste identiteit, maar de naam blijft een zelfstandige controle."
    )


def test_een_mens_aan_de_prompt_mag_wel_vanuit_dezelfde_werkmap(poort) -> None:
    """`--human` is de uitzondering, en hij is smal.

    De werkmapcontrole bestaat om te voorkomen dat een SESSIE zichzelf goedkeurt. Keurt
    een mens goed aan de permissieprompt, dan draait het commando weliswaar vanuit de
    werkmap van de auteur maar komt de toestemming van iemand anders. Zonder deze
    uitzondering kan een enkele sessie helemaal niet meer pushen, ook niet met Rakesh
    erbij -- dan is de controle een blokkade geworden.

    De aanvraag-eis blijft WEL gelden, dus ook hier ligt vast wie de commit schreef.
    """
    _vraag_aan(poort, "sessie-A", poort.auteur)

    assert _keur_goed(poort, "rakesh", poort.auteur, mens=True) == 0

    rij = json.loads(poort.gate.read_text(encoding="utf-8"))["approved"][_SHA]
    assert rij["by_human"] is True, (
        "Een menselijke goedkeuring is niet als zodanig vastgelegd; achteraf is dan niet "
        "te zien of de werkmapcontrole terecht is overgeslagen."
    )
    assert rij["authored_by"] == "sessie-A"


def test_een_mens_kan_niet_goedkeuren_zonder_aanvraag(poort) -> None:
    """De uitzondering geldt NIET voor de aanvraag-eis -- anders is de auteur weer onbekend."""
    assert _keur_goed(poort, "rakesh", poort.auteur, mens=True) == 1

    assert not json.loads(poort.gate.read_text(encoding="utf-8")).get("approved")


def test_een_andere_sessie_mag_wel_goedkeuren(poort) -> None:
    """De tegenrichting: zonder deze helft zou 'weiger alles' een geldige oplossing zijn."""
    _vraag_aan(poort, "sessie-A", poort.auteur)

    assert _keur_goed(poort, "sessie-B", poort.goedkeurder) == 0

    rij = json.loads(poort.gate.read_text(encoding="utf-8"))["approved"][_SHA]
    assert rij["by"] == "sessie-B"
    assert rij["authored_by"] == "sessie-A", (
        "De goedkeuring legt niet vast WIE de commit schreef. Zonder dat is achteraf niet "
        "na te gaan of er werkelijk twee partijen aan te pas kwamen."
    )

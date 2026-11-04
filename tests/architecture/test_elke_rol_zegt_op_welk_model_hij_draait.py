"""Elke rol behalve de regie noemt zijn model. Een ontbrekend veld erft stilzwijgend.

**Waarom deze bewaker bestaat, gemeten 2026-09-28.**

Rakesh' besluit staat in het ontwerp: de regie draait op Opus, de andere sessies zet hij
zelf op Sonnet. Daarom kregen de rolbestanden bewust GEEN `model:`-veld -- een veld daar zou
zijn instelling per sessie overschrijven.

Precies dat weglaten sloeg terug. Een rol die als subagent wordt gestart en geen `model:`
heeft, erft het model van wie hem start. Op 2026-09-28 startte de regie acht rollen vanuit
een Opus-sessie: alle acht draaiden op Opus, samen ongeveer een miljoen tokens. Niemand
merkte het drie uur lang; het kwam pas aan het licht doordat Rakesh toevallig meekeek.

De reparatie is niet "eraan denken". Eraan denken is precies wat drie uur lang niet werkte.

**Waarom `regie` de uitzondering is en blijft.** Die sessie opent Rakesh zelf en zet hij
bewust op Opus. Een `model:`-veld in dat bestand zou zijn keuze overschrijven -- de
spiegelbeeldfout, en het plan waarschuwde daar al voor. Het is dus geen vergeten regel maar
de enige plek waar het veld schade zou doen.

**Wat deze test NIET kan.** Hij toetst wat er in het bestand STAAT, niet welk model er
werkelijk antwoordde. Een rol die de regie start met een expliciete modelkeuze erbij
overschrijft dit veld alsnog -- dat is toegestaan en bewust. Deze bewaker sluit alleen de
STILLE erfenis uit: de vorm waarin niemand een keuze maakt.

Mutatiebewijs (2026-09-28), beide richtingen, een regel per element van de benoemde
verzameling -- vijftien rolbestanden, 0 afwijkend:

    `model: sonnet` weggehaald bij acceptant     -> ROOD  ("noemt geen model")
    ... idem voor elk van de veertien rollen     -> ROOD  (14 van 14 betrapt)
    `model: opus` gezet bij bouwer               -> ROOD  ("moet sonnet zijn")
    `model:` toegevoegd aan regie.md             -> ROOD  ("overschrijft Rakesh' keuze")
    een nieuw rolbestand zonder model            -> ROOD
    de boom zoals hij is                         -> GROEN

De derde en vierde regel zijn de tegenkant: zonder die twee zou "zet overal een model
neer" een geldige oplossing zijn, en dan is de regie-sessie stil op Sonnet gezet.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLMAP = REPO_ROOT / ".claude" / "agents"

# De rollen die met OPZET geen `model:`-veld dragen, en dus erven van wie ze start.
#
# **Waarom dit een lijst met redenen is en niet een enkele naam (bijgewerkt 2026-09-28).**
# De eerste versie kende maar een uitzondering, `regie`, en eiste van alle andere veertien
# rollen letterlijk `sonnet`. Rakesh heeft die vraag daarna heropend: "ik wil dat je
# onderzoekt welke rol toch welk model wenselijk is, indien nodig laat je het model open,
# zodat ze altijd van jou overerven."
#
# Daarmee verbood deze bewaker precies de uitkomst die de opdrachtgever wilde -- een rol op
# "open" zetten maakte hem rood. Een bewaker die de opdracht blokkeert is geen bewaker maar
# een obstakel.
#
# Wat hij WEL moet blijven vangen is de fout waarvoor hij gemaakt is: de STILLE erfenis. Op
# 2026-09-28 startte de regie acht rollen vanuit een Opus-sessie; geen van de vijftien
# rolbestanden had een model-veld, dus alle acht erfden Opus, samen ongeveer een miljoen
# tokens, en drie uur lang merkte niemand het. Het verschil met "open" zoals Rakesh het
# bedoelt is dat de keuze dan OPGESCHREVEN staat.
#
# Daarom: erven mag, maar alleen met een reden in deze lijst. Wie een rol wil laten erven,
# zet hem hier met de reden erbij. Een leeg veld zonder rij hier blijft een fout.
ROL_ERFT_BEWUST: dict[str, str] = {
    "regie": (
        "Rakesh opent deze sessie zelf en zet hem bewust op Opus. Een veld hier zou zijn "
        "keuze overschrijven -- de spiegelbeeldfout."
    ),
}

# Het model voor een rol die er WEL een noemt. Zolang er een onderzoek loopt naar welke rol
# welk model verdient, is dit de afspraak en niet de uitkomst: Rakesh zet de andere sessies
# op Sonnet. Blijkt uit dat onderzoek dat een rol een zwaarder model verdient, dan is dat
# een besluit van Rakesh en verhuist die rol naar ROL_ERFT_BEWUST of krijgt hij hier een
# eigen regel.
VERPLICHT_MODEL = "sonnet"

MODEL_REGEL = re.compile(r"^model:[ \t]*(\S+)[ \t]*$", re.MULTILINE)


def _getrackte_rollen() -> set[str]:
    """De rolnamen die git KENT."""
    uit = subprocess.run(
        ["git", "ls-files", ".claude/agents/*.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {Path(r).stem for r in uit.stdout.split("\n") if r.strip()}


def _rolbestanden() -> list[Path]:
    """Alle rolbestanden OP SCHIJF.

    **Waarom schijf en niet `git ls-files`, gemeten in het mutatiebewijs.** De eerste versie
    las alleen wat git kende. Een NIEUW rolbestand is nog niet getrackt, dus die versie liet
    precies het geval door waar dit het vaakst misgaat: een rol die er vandaag bijkomt. Die
    mutatie kwam GROEN terug terwijl hij rood hoorde te zijn.

    Dat het bestand daarnaast ook in git moet staan, bewaakt
    `test_elk_rolbestand_staat_ook_echt_in_git` hieronder -- een rol die alleen hier op
    schijf staat, bestaat voor niemand anders.
    """
    paden = sorted((REPO_ROOT / ".claude" / "agents").glob("*.md"))
    assert paden, "geen enkel rolbestand gevonden -- dan meet deze test niets"
    return paden


def _kopmodel(pad: Path) -> str | None:
    """Het model uit de YAML-kop, of None als het veld ontbreekt.

    Leest ALLEEN de kop tussen de eerste twee `---`-regels. Een `model:` in de lopende
    tekst eronder is uitleg en geen instelling; die meetellen zou een bestand groen maken
    op een zin die niets doet.
    """
    regels = pad.read_text(encoding="utf-8").split("\n")
    if not regels or regels[0].strip() != "---":
        return None
    try:
        eind = next(i for i in range(1, len(regels)) if regels[i].strip() == "---")
    except StopIteration:
        return None
    treffer = MODEL_REGEL.search("\n".join(regels[1:eind]))
    return treffer.group(1) if treffer else None


def test_elke_gestarte_rol_noemt_expliciet_sonnet() -> None:
    """Een rol zonder `model:` erft het model van wie hem start -- stil en onbedoeld."""
    ontbreekt: list[str] = []
    verkeerd: list[str] = []

    for pad in _rolbestanden():
        naam = pad.stem
        if naam in ROL_ERFT_BEWUST:
            continue
        model = _kopmodel(pad)
        if model is None:
            ontbreekt.append(naam)
        elif model != VERPLICHT_MODEL:
            verkeerd.append("%s heeft model: %s" % (naam, model))

    problemen = []
    if ontbreekt:
        problemen.append(
            "noemt geen model (%d): %s -- deze erven stil het model van de startende sessie"
            % (len(ontbreekt), ", ".join(sorted(ontbreekt)))
        )
    if verkeerd:
        problemen.append("moet %s zijn: %s" % (VERPLICHT_MODEL, ", ".join(sorted(verkeerd))))

    assert not problemen, (
        "Rolbestanden zonder expliciet model. Gemeten 2026-09-28: acht rollen gestart vanuit "
        "een Opus-sessie draaiden alle acht op Opus, samen circa een miljoen tokens, drie uur "
        "lang onopgemerkt.\n" + "\n".join(problemen)
    )


def test_de_regie_zet_zichzelf_niet_op_een_model() -> None:
    """De tegenkant: "zet overal een model neer" mag geen geldige oplossing zijn.

    Rakesh opent de regie-sessie zelf en kiest daar bewust Opus. Een `model:`-veld in dat
    bestand overschrijft die keuze -- dan staat de regie stil op Sonnet en is de bewaker
    hierboven de oorzaak van het volgende defect in plaats van de reparatie ervan.
    """
    fout = []
    for naam in sorted(ROL_ERFT_BEWUST):
        pad = ROLMAP / ("%s.md" % naam)
        assert pad.exists(), "rol %s bestaat niet meer -- werk ROL_ERFT_BEWUST bij" % naam
        model = _kopmodel(pad)
        if model is not None:
            fout.append("%s heeft model: %s" % (naam, model))

    assert not fout, (
        "Deze rol opent Rakesh zelf en zet hij zelf op een model. Een veld hier overschrijft "
        "die keuze: %s" % ", ".join(fout)
    )


def test_elk_rolbestand_staat_ook_echt_in_git() -> None:
    """Een rol die alleen op deze schijf staat, bestaat voor niemand anders.

    Lokaal ziet zo'n bestand er identiek uit aan een getrackt bestand, en elke controle die
    met `Path.exists()` werkt keurt hem goed. Zie `.claude/rules/git-safety.md` en de eerder
    gemeten variant hiervan bij `check_instructielaag.py`.
    """
    getrackt = _getrackte_rollen()
    los = sorted(p.stem for p in _rolbestanden() if p.stem not in getrackt)
    assert not los, (
        "rolbestand(en) niet in git: %s -- voor elke andere sessie bestaan ze niet" % ", ".join(los)
    )


def test_de_uitzonderingslijst_verwijst_niet_naar_een_verdwenen_rol() -> None:
    """Een uitzondering die niets meer vrijstelt, hoort weg -- anders rot hij dicht."""
    bestaand = {p.stem for p in _rolbestanden()}
    verdwenen = sorted(set(ROL_ERFT_BEWUST) - bestaand)
    assert not verdwenen, "ROL_ERFT_BEWUST noemt een rol die niet meer bestaat: %s" % ", ".join(
        verdwenen
    )


def test_elke_erfende_rol_draagt_een_reden() -> None:
    """Erven mag, maar niet stil. Een rij zonder reden is de oude fout met een vinkje erbij.

    De hele aanleiding voor deze bewaker was dat veertien rollen stilzwijgend Opus erfden.
    Als "open" een toegestane keuze wordt, is de reden het enige dat een keuze van een
    vergissing onderscheidt -- en een reden van drie woorden is geen reden.
    """
    zonder = sorted(naam for naam, reden in ROL_ERFT_BEWUST.items() if len(reden.strip()) < 40)
    assert not zonder, (
        "deze rol(len) erven zonder opgeschreven reden: %s -- dat is stille erfenis met een "
        "vinkje ervoor" % ", ".join(zonder)
    )

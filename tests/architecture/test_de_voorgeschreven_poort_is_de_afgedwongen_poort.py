"""Het poortcommando in CLAUDE.md moet zijn wat de pre-push hook afdwingt.

**Waarom deze guard bestaat (gemeten 2026-09-17).** CLAUDE.md schreef de volledige poort
voor MET `--ignore=tests/core/agents/test_focus_builder_chat_agent.py`, terwijl
`scripts/hooks/pre-push` diezelfde poort draaide ZONDER die vlag. Beide heten "de poort".
Gevolg: een sessie draaide het voorgeschreven commando, kreeg groen op 16595 tests, en werd
bij de push afgerekend op 16599. Een tweede sessie mat een dag lang 16571/16586 handmatig
tegen 16599 in de hook zonder te zien dat zij twee verschillende verzamelingen vergeleek.
Niets werd rood; er was geen enkel signaal dat de twee uit elkaar liepen.

**Wat deze guard NIET doet, en waarom niet.** Hij vergelijkt de hook NIET met de CI-stap in
`ci-feature.yml`. Die draait bewust een andere verzameling (ook `tests/safety` en
`tests/ml`, met `-n 2` en een eigen `--ignore`), dus gelijkheid eisen zou een onware
invariant vastleggen. De koppeling tussen de CI-stap en `GATE_IGNORES` wordt al bewaakt door
`test_the_gate_dirs_match_the_ci_step` in `test_disabled_tests_do_not_grow.py`. Deze guard
dekt het gat dat daarnaast open lag: het VOORGESCHREVEN commando tegen het AFGEDWONGEN
commando.

Hij kijkt ook bewust niet naar `docs/agent-briefs/`. Daar staat het commando tientallen
keren als HISTORISCH verslag van een run; die moeten juist niet meelopen. Een guard die op
tekst in de hele boom zoekt zou daarop stuk lopen -- de bekende valkuil dat een guard TEKST
doorzoekt waar hij STRUCTUUR moet toetsen.

Mutatiebewijs (2026-09-17), een regel per element en in beide richtingen, met een KOPIE
als terugweg en nooit via `git checkout`. CLAUDE.md noemt het commando TWEE keer, dus elke
mutatie is op BEIDE vermeldingen tegelijk gedaan -- anders meet je de controle binnen het
bestand in plaats van de kruiscontrole met de hook:

    map erbij (250 en 506)          -> 1 failed  ..._dezelfde_mappen_als_claude_md
    --ignore erbij (250 en 506)     -> 1 failed  ..._sluit_precies_uit_wat_claude_md_uitsluit
    -n 4 naar -n 8 (250 en 506)     -> 1 failed  ..._met_dezelfde_instellingen_als_claude_md
    --timeout 60 naar 30 (250, 506) -> 1 failed  ..._met_dezelfde_instellingen_als_claude_md
    alleen regel 506 gewijzigd      -> 3 failed  (de vermeldingen zijn het onderling oneens)
    ongemuteerd en hersteld         -> 3 passed

De eerste ronde van dit bewijs muteerde maar EEN van de twee vermeldingen. Toen vielen bij
elke mutatie alle drie de tests, wat eruitzag als bewijs maar het niet was: die mutaties
raakten de kruiscontrole nooit, alleen de vergelijking van regel 250 met regel 506. Dat is
dezelfde vorm als "twee bronnen maskeren een enkele mutatie".
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
PRE_PUSH = REPO_ROOT / "scripts" / "hooks" / "pre-push"

#: De mappen die de volledige poort draait. Staat hier expliciet zodat het mutatiebewijs
#: een regel PER ELEMENT kan hebben in plaats van een vage "de verzamelingen zijn gelijk".
VERWACHTE_POORTMAPPEN = ("tests/unit", "tests/architecture", "tests/core", "tests/contracts")


def _voeg_vervolgregels_samen(tekst: str) -> str:
    """Plak regels die met een backslash doorlopen aan elkaar.

    De hook schrijft het commando over twee regels; zonder dit ziet een tokenizer
    `-n 4 --timeout=60` niet en meet de guard te weinig terwijl hij groen meldt.
    """
    return re.sub(r"\\\s*\n\s*", " ", tekst)


def _poortaanroepen(pad: Path) -> list[list[str]]:
    """ALLE pytest-aanroepen van de volledige poort uit `pad`, elk als token-lijst.

    Herkend aan de vier poortmappen op een regel, want dat is wat deze poort
    onderscheidt van `pytest tests/unit/` en van de integratiesuite.
    """
    # Backticks weg voor het tokeniseren. In CLAUDE.md staat het commando op een plek in
    # PROZA, tussen backticks; zonder dit plakt de sluit-backtick aan het laatste woord en
    # leest de guard `--ignore=x` als `--ignore=x\`` -- een verschil dat er niet is. Gemeten
    # 2026-09-17 tijdens het mutatiebewijs: dat gaf een valse melding dat de twee
    # vermeldingen in CLAUDE.md het onderling oneens waren.
    tekst = _voeg_vervolgregels_samen(pad.read_text(encoding="utf-8")).replace("`", " ")
    kandidaten = [
        regel
        for regel in tekst.splitlines()
        if "pytest" in regel
        and all(m in regel for m in VERWACHTE_POORTMAPPEN)
        and not regel.strip().startswith("#")
    ]
    assert kandidaten, (
        f"Geen poortaanroep gevonden in {pad.name}. Deze guard meet dan NIETS terwijl hij "
        "groen zou melden, dus dit is een fout en geen overslaan. Draait de poort daar "
        "niet meer, of heet hij anders? Werk dan deze guard bij."
    )
    return [shlex.split(regel, posix=True) for regel in kandidaten]


def _kenmerken(tokens: list[str]) -> tuple[tuple[str, ...], frozenset[str], str | None, str | None]:
    """De vier eigenschappen waarop twee poortaanroepen gelijk moeten zijn."""
    return (
        _mappen(tokens),
        _uitsluitingen(tokens),
        _vlagwaarde(tokens, "-n"),
        _vlagwaarde(tokens, "--timeout"),
    )


def _de_ene_poortaanroep(pad: Path) -> list[str]:
    """De geldende poortaanroep uit `pad`.

    CLAUDE.md noemt het commando op meer dan een plek (regel 250 in het codeblok en
    regel 506 in de absolute regels). Dat is geen fout: het zijn allebei instructies aan
    de lezer, en dus moeten ze allebei kloppen. Deze functie eist daarom niet EEN
    vermelding maar dat alle vermeldingen HETZELFDE zeggen -- dat dekt ook de drift
    tussen die twee plekken onderling, die anders ongemerkt kan ontstaan.
    """
    aanroepen = _poortaanroepen(pad)
    eerste = _kenmerken(aanroepen[0])
    for volgende in aanroepen[1:]:
        assert _kenmerken(volgende) == eerste, (
            f"{pad.name} noemt het poortcommando meer dan eens, en die vermeldingen zijn "
            f"het onderling ONEENS:\n  {eerste}\n  {_kenmerken(volgende)}\n"
            "Wie de ene leest draait iets anders dan wie de andere leest."
        )
    return aanroepen[0]


def _mappen(tokens: list[str]) -> tuple[str, ...]:
    return tuple(t for t in tokens if t.startswith("tests/") and not t.startswith("tests/unit/"))


def _uitsluitingen(tokens: list[str]) -> frozenset[str]:
    return frozenset(t.split("=", 1)[1] for t in tokens if t.startswith("--ignore="))


def _vlagwaarde(tokens: list[str], vlag: str) -> str | None:
    """De waarde van `vlag`, zowel als `--x=1` als als `-n 4` geschreven."""
    for i, t in enumerate(tokens):
        if t == vlag and i + 1 < len(tokens):
            return tokens[i + 1]
        if t.startswith(vlag + "="):
            return t.split("=", 1)[1]
    return None


def test_de_hook_draait_dezelfde_mappen_als_claude_md() -> None:
    """De voorgeschreven en de afgedwongen poort dekken dezelfde mappen."""
    voorgeschreven = _mappen(_de_ene_poortaanroep(CLAUDE_MD))
    afgedwongen = _mappen(_de_ene_poortaanroep(PRE_PUSH))
    assert voorgeschreven == afgedwongen, (
        "CLAUDE.md schrijft andere poortmappen voor dan scripts/hooks/pre-push afdwingt:\n"
        f"  CLAUDE.md : {voorgeschreven}\n"
        f"  pre-push  : {afgedwongen}\n"
        "Wie het voorgeschreven commando draait krijgt dan groen op een andere verzameling "
        "dan waar de push op afrekent, en niets meldt dat."
    )
    assert voorgeschreven == VERWACHTE_POORTMAPPEN, (
        f"De poort draait {voorgeschreven}, deze guard verwacht {VERWACHTE_POORTMAPPEN}. "
        "Is er bewust een map bij gekomen, werk dan VERWACHTE_POORTMAPPEN bij -- die staat "
        "hier expliciet zodat het mutatiebewijs een regel per map kan hebben."
    )


def test_de_hook_sluit_precies_uit_wat_claude_md_uitsluit() -> None:
    """Dit is het gat dat op 2026-09-17 gemeten werd: een vlag aan een kant."""
    voorgeschreven = _uitsluitingen(_de_ene_poortaanroep(CLAUDE_MD))
    afgedwongen = _uitsluitingen(_de_ene_poortaanroep(PRE_PUSH))
    assert voorgeschreven == afgedwongen, (
        "De uitsluitingen lopen uiteen tussen het voorgeschreven en het afgedwongen "
        "poortcommando:\n"
        f"  alleen in CLAUDE.md : {sorted(voorgeschreven - afgedwongen)}\n"
        f"  alleen in pre-push  : {sorted(afgedwongen - voorgeschreven)}\n"
        "Precies deze vorm kostte op 2026-09-17 een dag: twee sessies vergeleken 16595 met "
        "16599 zonder te zien dat het twee verzamelingen waren."
    )


def test_de_hook_draait_met_dezelfde_instellingen_als_claude_md() -> None:
    """Workers en timeout bepalen mee OF de poort slaagt, niet alleen hoe snel."""
    voorgeschreven = _de_ene_poortaanroep(CLAUDE_MD)
    afgedwongen = _de_ene_poortaanroep(PRE_PUSH)
    for vlag in ("-n", "--timeout"):
        assert _vlagwaarde(voorgeschreven, vlag) == _vlagwaarde(afgedwongen, vlag), (
            f"{vlag} verschilt tussen CLAUDE.md en de pre-push hook: "
            f"{_vlagwaarde(voorgeschreven, vlag)!r} tegen {_vlagwaarde(afgedwongen, vlag)!r}. "
            "Dat is geen smaakverschil: -n 8 put op deze suite het geheugen uit en laat "
            "workers sterven (ADR-036 OP-19), en een kortere timeout maakt trage tests rood."
        )

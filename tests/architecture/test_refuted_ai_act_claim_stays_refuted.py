"""De weerlegde AI-Act-art.-19-claim mag niet terugkomen (ADR-036 OP-27, ronde 5).

**De claim.** Vier documenten en een moduledocstring stelden dat AI Act art. 19 "de invoer die
tot het resultaat leidde" als verplicht logveld noemt, met een bewaarvloer van zes maanden. Bij de
bron nagemeten is dat onjuist: art. 12(3) eist invoer-logging uitsluitend voor high-risk systemen
uit Annex III punt 1(a) (biometrische identificatie) en dit systeem valt onder punt 4
(personeelsbeheer); art. 19 gaat over de BEWAARTERMIJN en noemt invoer niet. Wat overblijft is
art. 12(2): logging die risico-identificatie en toezicht mogelijk maakt.

**Waarom dit een guard verdient en geen opsomming in een reviewdocument.** De claim stuurde het
ontwerp vier reviewrondes lang de verkeerde kant op ("de invoer moet leesbaar blijven, want de wet
eist het"). Bij het opruimen ging de TELLING drie keer mis: 13, toen 27, toen 35, en na het
aanvullen van de ADR 44. Elke keer omdat het zoekpatroon een spelling miste -- eerst `art.-12/19`
met koppelteken, daarna `.claude/` en `.github/` buiten de zoekmap. Een handmatig uitgeschreven
regelnummerlijst is dus precies het instrument dat hier al drie keer heeft gefaald; dit is de
meting die in de plaats komt.

**Waarom een EXACTE telling per bestand en geen bestandsnaam-allowlist.** Vier bestanden bevatten
de claim legitiem, namelijk als onderdeel van de weerlegging zelf. Zou de allowlist alleen
bestandsnamen bevatten, dan kon in juist die bestanden een NIEUWE levende claim bijkomen zonder
dat de guard iets merkt -- en dat zijn de gezaghebbende bronnen (de ADR, de feature-doc). Met een
exacte telling trapt zowel een nieuwe claim (telling te hoog) als het weghalen van de weerlegging
(telling te laag) erin.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De claimvormen. Dit patroon is VIJF keer te kort gebleken en is daarom bewust ruim: elk
#: `art`-woord gevolgd door hoogstens 14 tekens uit een citatievorm (cijfers, spaties, `/`, `()`,
#: `.`, `-`) en dan `19` als los getal.
#:
#: Wat elke eerdere, nauwere versie miste, in de volgorde waarin het gebeurde:
#:   1. `art. 19` alleen                    -> miste `art.-12/19` met koppelteken (13 -> 27)
#:   2. plus `12/19`                        -> miste `.claude/` en `.github/` buiten de zoekmap (27 -> 35)
#:   3. plus die twee mappen                -> na het aanvullen van de ADR 44
#:   4. `12/19` als vaste samentrekking     -> miste `art. 12/14/19` in de feature-doc-kop
#: Die vierde is gevonden door de kop te LEZEN, niet door deze guard -- exact het patroon dat deze
#: guard moet doorbreken, en dus de reden dat hij nu op citatie-VORM zoekt in plaats van op een
#: opsomming van bekende spellingen.
#:
#: `test_the_pattern_does_not_match_the_surviving_citations` houdt hem eerlijk in de andere
#: richting: `art. 12(2)`, `art. 12(3)`, `ADR-019` en jaartallen mogen niet matchen.
#:
#: **Het citatiewoord is een OPSOMMING, geen `[a-z]*` (Gate 2 ronde 6, F4).** De eerdere versie
#: `art[a-z]*` matchte binnen willekeurige woorden: `part 19`, `start 19 workers`, `chart 19`,
#: `quarter 19`, `partition 19`, `third-party 19 packages`, `artifacts/19`, `artifact 19`.
#:
#: Een `\b` ervoor haalt de eerste zeven weg maar niet de laatste twee, en dat is geen detail:
#: `artifact 19` is STRUCTUREEL niet te onderscheiden van `artikel 19`. Een vormregel kan dit dus
#: niet oplossen -- het onderscheid is lexicaal. Daarom staat er nu een opsomming van de
#: citatiewoorden (`art`, `artikel`, `article`) in plaats van een wildcard. Dat is dezelfde
#: correctie die deze sprint drie keer eerder nodig was: niet toetsen hoe iets ERUITZIET, maar
#: waar het VANDAAN komt -- hier: is dit het woord `artikel` of een willekeurig woord dat
#: toevallig met `art` begint.
#:
#: Waarom een vals positief hier duurder is dan hij lijkt: de foutmelding schrijft als remedie
#: voor om het bestand met een telling in `ALLOWED_CLAIM_COUNTS` te zetten. Daarmee wast een vals
#: positief zich met een verzonnen reden de allowlist in, en staat een ECHTE claim in dat bestand
#: daarna een bump verderop -- onzichtbaar.
#:
#: Gemeten na deze wijziging: alle spellingen in `test_the_prefilter_is_a_superset_of_the_pattern`
#: matchen nog, de tien valse positieven zijn weg, en de tellingen per bestand in
#: `ALLOWED_CLAIM_COUNTS` zijn ONGEWIJZIGD -- dat laatste is het bewijs dat de versmalling geen
#: echte claim heeft laten vallen, want elke afwijking zou hier een failure geven.
CLAIM_PATTERN = re.compile(
    r"\bart(?:ikel|icle)?\.?[\s-]{0,3}[\d\s/(),.-]{0,14}\b19\b(?![0-9])",
    re.IGNORECASE,
)

#: Alleen tekstuele bestandssoorten. Een binair bestand kan de claim niet dragen en zou de scan
#: alleen ruis geven.
SCANNED_SUFFIXES = (".py", ".md", ".yml", ".yaml", ".ts", ".tsx", ".json", ".txt")

#: Dit bestand bevat de claimvormen noodzakelijkerwijs -- in het patroon en in de controlestrings
#: van het vangnet hieronder. Het staat daarom buiten de scan. Dat is een bewuste blinde vlek van
#: exact een bestand, en `test_only_this_guard_is_excluded_from_the_scan` houdt hem op een.
SELF = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()

#: Bestand -> (verwacht aantal treffers, reden met datum).
#:
#: Gemeten 2026-08-04 op commit `2940dccf`. Elke treffer is met de hand gelezen en geclassificeerd
#: als WEERLEGGING (mag blijven) of LEVENDE CLAIM (moet weg); alleen de eerste categorie staat
#: hier. Wijzigt een telling, dan is dat een beslissing die iemand expliciet moet opschrijven.
ALLOWED_CLAIM_COUNTS: dict[str, tuple[int, str]] = {
    "docs/adr/036-REGISTER-OVERIG-EN-AFGEROND.md": (
        3,
        "2026-09-19 -- ontstaan bij de SPLITSING van het register op instructie van Rakesh. De "
        "zes treffers die tot die dag in ADR-036 stonden, staan sindsdien verdeeld over twee "
        "bestanden: 3 hier en 3 in de ADR. Gemeten met exact het patroon van deze guard, direct "
        "na de splitsing: er is geen tekst herschreven, alleen verplaatst. De rijen die hierheen "
        "gingen (onder meer de OP-27-weerlegging en de OP-33-correctie) beschrijven onverkort "
        "dat de art.-19-claim ONJUIST is; dat is de eigenschap die deze guard bewaakt en die is "
        "door het verplaatsen niet veranderd.",
    ),
    "docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md": (
        3,
        "**6 -> 3, gemeten 2026-09-19 bij de splitsing van het register.** De andere drie staan "
        "nu in `036-REGISTER-OVERIG-EN-AFGEROND.md`; samen nog steeds zes, en alle zes nog "
        "steeds een weerlegging. Wat hieronder staat is de toelichting van voor de splitsing en "
        "beschrijft waar die zes vandaan kwamen. "
        "2026-08-04 -- 2x in de OP-27-rij (de weerlegging: 'Art. 19 noemt invoer niet'), 3x in de "
        "art.-17(3)(b)-alinea die het gevolg van het intrekken beschrijft, en sinds ronde 6 1x in "
        "de OP-33-CORRECTIE, die de eigen enumeratiefout vergelijkt met de art.-19-claim "
        "('dezelfde categorie: een telling die als volledig werd gepresenteerd terwijl hij een "
        "steekproef was'). Alle zes beschrijven dat de claim ONJUIST is. "
        "**7 -> 6, gemeten 2026-09-10 (pre-existing op develop 98e72440, ontdekt tijdens ander "
        "werk, dit is de eerste run van deze guard sinds de wijziging).** De OP-36-rij is op "
        "2026-09-09 volledig herschreven ('premisse gecorrigeerd 2026-09-09'): de oude conclusie "
        "die de zin 'nu de art.-19-plicht is ingetrokken' droeg, bleek zelf op een foute aanname "
        "te rusten (de aangenomen orchestrator DSARService is dode code) en is vervangen door een "
        "andere bevinding (hash-keten-integriteit, GDPR art. 17(3)(b)-uitzondering, verwijzing "
        "naar OP-226). De herschreven rij noemt art. 19 nergens meer -- geverifieerd met "
        "CLAIM_PATTERN op de huidige tekst, 0 treffers in de OP-36-rij. Dit is dus geen "
        "verzwakte weerlegging naast een levende claim (het gevaar dat deze test bewaakt), maar "
        "het verdwijnen van een hele, achterhaalde alinea inclusief haar destijds-juiste "
        "referentie. Zie ADR-036 OP-36.",
    ),
    "docs/reports/ADR-036_NAMETING_74_RIJEN_2026-08-31.md": (
        5,
        "2026-08-31 -- de nameting van de 74 registerrijen. 2x in de OP-27-sectie (de weerlegging "
        "zelf: art. 12(3) eist invoer-logging alleen voor Annex III 1(a), art. 19 gaat over "
        "bewaartermijn en noemt invoer niet, met de bronlink) en 3x in de OP-36-sectie, die "
        "vaststelt dat het intrekken van de art.-19-bewaargrond in die rij TERECHT was, opnieuw "
        "met bronlink. Alle vijf beschrijven dat de claim onjuist is; geen van vijf voert hem op "
        "als grond. Met de hand gelezen op 2026-08-31.",
    ),
    "docs/backend/features/BE-AGT-045-payload-pseudonimisering.md": (
        3,
        "2026-08-04 -- 2x in par. 2, die de oude claim citeert en regel voor regel weerlegt (het "
        "citaat en de weerlegging horen bij elkaar), plus 1x in de ronde-5-sectie die het GEVOLG "
        "van het intrekken beschrijft. De kop van dit document zei tot 2026-08-04 nog "
        "'AI Act art. 12/14/19' -- die spelling miste het patroon, en is gevonden door de kop te "
        "lezen. Nu 'art. 12(2) en art. 14'.",
    ),
    "docs/backend/review/review-BE-AGT-045.md": (
        5,
        "2026-08-04 -- 2x in de vastlegging DAT de claim in ronde 3 is weerlegd (met citaat), plus "
        "3x in par. 7 die beschrijft waar de claim in ronde 5 nog stond en hoe vaak de telling "
        "misging. Dat is het bewijsspoor van de correctie zelf.",
    ),
    "src/core/tool_broker/redaction.py": (
        2,
        "2026-08-04 -- de moduledocstring benoemt de eerdere onjuiste claim expliciet en zet hem "
        "recht. Dat hoort in de module te staan waar de afweging is gemaakt, zodat een volgende "
        "lezer niet opnieuw concludeert dat de wet leesbare invoer eist.",
    ),
    "docs/agent-briefs/generated/2026-08-03-sprint-dag-adr036-op27-payload-pseudonimisering.md": (
        3,
        "2026-08-04 -- HISTORISCHE brief van voor de weerlegging. Deze documenteert de fout zoals "
        "hij gemaakt is; hem herschrijven zou het bewijsspoor uitwissen. Niet aanpassen.",
    ),
    "docs/agent-briefs/generated/2026-08-04-overdracht-adr036-op27.md": (
        2,
        "2026-08-04 -- de overdracht voert de weerlegging op als les ('vijf keer een oorzaak "
        "beredeneerd waar meten mogelijk was'). Historisch document, niet aanpassen.",
    ),
    "docs/reports/AUDIT-BE-AGT-045-bottom-up-2026-08-05.md": (
        1,
        "2026-08-05 -- de bottom-up audit verwijst in laag 4 naar het INTREKKEN van de plicht "
        "('met het intrekken van de art.-19-plicht is er ook geen bewaargrond meer'), als reden "
        "waarom `hitl_tickets.payload` geen bewaargrond heeft. Beschrijft dus dat de claim onjuist "
        "is. Deze guard betrapte dit document bij het toevoegen -- dat is precies waarvoor hij "
        "bestaat, en het is het vierde geval waarin hij mij heeft gecorrigeerd.",
    ),
    "docs/agent-briefs/generated/2026-08-04-overdracht-adr036-ronde5-verwerkt.md": (
        1,
        "2026-08-04 -- de OP-36-samenvatting verwijst naar het INTREKKEN van de claim ('nu de "
        "art.-19-plicht is ingetrokken bestaat er geen bewaargrond meer'). Beschrijft dus dat de "
        "claim onjuist is. Deze vermelding is ook het bewijs dat de blinde vlek uit "
        "`_candidate_files` echt bestaat: de guard zag dit bestand pas na `git add`.",
    ),
    "docs/onderzoek-ai-verordening-hr-pakket-hoog-risico.md": (
        1,
        "2026-10-13 -- noemt art. 19 als bewaartermijn van logs (regel 301: de aanbieder bewaart "
        "logs minstens zes maanden), niet als onderbouwing van de digest. Gemeten met exact het "
        "patroon van deze guard: 1 treffer, met de hand gelezen. Het document is niet herschreven "
        "om de guard te ontwijken.",
    ),
    "docs/onderzoek-bewaarplicht-en-opgeheven-klanten.md": (
        2,
        "2026-10-13 -- noemt art. 19 als bewaartermijn van logs, niet als onderbouwing van de "
        "digest: 1x in de opsomming van wat art. 19 eist (regel 85, minstens zes maanden voor de "
        "aanbieder) en 1x in de vraag of art. 12, 19 en 73 voor ons gelden als het HR-pakket "
        "hoog-risico is (regel 148). Gemeten met exact het patroon van deze guard: 2 treffers, "
        "met de hand gelezen. Het document is niet herschreven om de guard te ontwijken.",
    ),
}


#: Grof voorfilter voor `git grep`. Elke treffer van `CLAIM_PATTERN` bevat per definitie de
#: letterlijke tekens `19`, dus een bestand zonder `19` kan de claim niet bevatten. Dat maakt dit
#: een bewijsbare SUPERSET van de echte zoekopdracht -- en die eigenschap is de enige reden dat een
#: voorfilter hier mag: een filter dat NAUWER is dan het patroon zou precies de "token te kort"-fout
#: opnieuw bouwen die deze guard moet voorkomen.
#: `test_the_prefilter_is_a_superset_of_the_pattern` dwingt het af.
_PREFILTER = "19"


def _candidate_files() -> list[str]:
    """Getrackte tekstbestanden die het voorfilter halen, via `git grep`.

    **Waarom niet elk getrackt bestand in Python lezen -- gemeten 2026-08-04.** De eerste versie
    las alle 12.508 getrackte bestanden en regex-scande ze. Dat duurde 44,7 seconden (de
    langzaamste test van de hele suite) en LIET EEN XDIST-WORKER CRASHEN: `worker 'gw3' crashed
    while running test_no_refuted_claim_outside_the_allowlist`. Pytest meldt dan de test die die
    worker toevallig uitvoerde als FAILED -- exact het beeld uit CLAUDE.md OP-19, en de reden dat
    de suite drie runs lang op een ANDERE test leek te falen. De guard was dus zelf de oorzaak van
    zijn eigen "flakiness".

    `git grep` doet hetzelfde werk in ~1 seconde omdat het in C gebeurt en niets in Python-geheugen
    houdt. `-I` slaat binaire bestanden over.

    Bewust `git grep` en niet `rg`: `.git/info/exclude` heeft in dit project eerder 1816 GETRACKTE
    bestanden onzichtbaar gemaakt voor `rg` (OP-17), en een scan die bestanden mist meldt niets en
    lijkt daarmee groen.

    **Blinde vlek, expliciet:** `git grep` zoekt alleen in GETRACKTE bestanden. Een nieuw bestand
    met de claim wordt dus pas gezien na `git add`. Dat gold ook voor de vorige versie (`git
    ls-files`), dus het is geen regressie -- maar het betekent dat deze guard de claim in de
    REPOSITORY bewaakt en niet in een werkmap. Voor CI (verse checkout) is dat hetzelfde; lokaal
    moet je stagen voordat de guard je nieuwe bestand meeneemt.
    """
    completed = subprocess.run(
        [
            "git",
            "grep",
            "-l",
            "-I",
            "-F",
            _PREFILTER,
            "--",
            *(f"*{suffix}" for suffix in SCANNED_SUFFIXES),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,  # exit 1 = geen treffers, en dat is geen fout
    )
    if completed.returncode not in (0, 1):
        raise RuntimeError(f"git grep faalde ({completed.returncode}): {completed.stderr.strip()}")
    return [path for path in completed.stdout.splitlines() if path and path != SELF]


#: Hoever een treffer van `CLAIM_PATTERN` VOOR zijn `19` kan beginnen. Het langste geval: `artikel` (3+4 tekens) of
#: `article`, een punt, drie scheidingstekens, veertien tekens uit de klasse en dan `19` = 3+4+1+3+14 = 25 tekens
#: ervoor. 32 laat ruim marge; `test_the_window_is_wide_enough_for_the_longest_match` bouwt het langste geval en
#: dwingt het af, zodat een ruimer patroon dit getal niet stil te klein maakt.
_WINDOW_BEFORE = 32
#: Na de `19` is `(?![0-9])` nodig plus de woordgrens: een paar tekens context, anders ziet de regex een kunstmatig
#: einde van de tekst. Extra tekens kunnen geen treffer toevoegen (elke treffer eindigt op een `19`).
_WINDOW_AFTER = 6


def _count_claims(text: str) -> int:
    """Het aantal treffers van `CLAIM_PATTERN`, zonder de hele tekst met de regex af te lopen.

    **Gemeten 2026-10-24 (waar de tijd zat):** `git grep` 0,9 s, de 1858 bestanden lezen 0,9 s, de regex over die 172 MB
    5,4 tot 5,9 s. De regex wordt dus de bottleneck doordat hij elk teken als mogelijk begin van `art` probeert.

    Elke treffer eindigt op de letterlijke tekens `19` en begint hoogstens `_WINDOW_BEFORE` tekens daarvoor. De regex
    draait daarom alleen op de vensters rond elke `19`, overlappende vensters samengevoegd, met `pos`/`endpos` op de
    ECHTE tekst: `` ziet dan de echte tekens ervoor en het tellen (niet-overlappend, hebzuchtig) blijft zoals
    `findall` over de hele tekst. Het aantal is daarmee gelijk aan `len(CLAIM_PATTERN.findall(text))`;
    `test_the_windowed_count_equals_the_full_scan` toetst dat op gevallen die het kunnen breken (aansluitende treffers,
    een treffer die over een regeleinde loopt, een woord dat net voor het venster begint).
    """
    posities: list[int] = []
    start = text.find(_PREFILTER)
    while start != -1:
        posities.append(start)
        start = text.find(_PREFILTER, start + 1)
    if not posities:
        return 0
    vensters: list[list[int]] = []
    for positie in posities:
        begin = max(0, positie - _WINDOW_BEFORE)
        einde = min(len(text), positie + len(_PREFILTER) + _WINDOW_AFTER)
        if vensters and begin <= vensters[-1][1]:
            vensters[-1][1] = max(vensters[-1][1], einde)
        else:
            vensters.append([begin, einde])
    return sum(len(CLAIM_PATTERN.findall(text, begin, einde)) for begin, einde in vensters)


@lru_cache(maxsize=1)
def _claim_counts() -> Mapping[str, int]:
    """Per bestand het aantal treffers van de claimvormen.

    Gecacht: vier tests hebben deze meting nodig. De uitkomst is binnen een run constant, want de
    tests wijzigen geen bestanden -- gemeten met een `git status --porcelain`-watcher over een
    volledige run: nul wijzigingen.
    """
    counts: dict[str, int] = {}
    for path in _candidate_files():
        full = REPO_ROOT / path
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = _count_claims(text)
        if found:
            counts[path] = found
    return counts


def test_the_pattern_still_matches_every_spelling_of_the_claim() -> None:
    """Vangnet: een stukgelopen patroon maakt deze guard stil groen.

    Vier controlestrings, een per spelling die in de praktijk is voorgekomen. Zonder deze test kan
    iemand het patroon vernauwen en dan meldt de scan nul treffers -- wat leest als "opgeruimd".
    """
    controls = {
        "art. 19": "AI Act art. 19 noemt de invoer",
        "art.-19": "de art.-19-traceerbaarheid blijft intact",
        "12/19": "waarop het art.-12/19-argument rust",
        "artikel 19": "artikel 19 van de AI-verordening",
    }
    missed = sorted(name for name, text in controls.items() if not CLAIM_PATTERN.search(text))

    assert not missed, (
        f"CLAIM_PATTERN vindt deze spellingen niet meer: {missed}. Zolang dat zo is meldt de scan "
        "te weinig treffers en lijkt de claim opgeruimd terwijl hij er staat. Dit is precies hoe "
        "de telling 13 -> 27 -> 35 -> 44 ging."
    )


def test_the_prefilter_is_a_superset_of_the_pattern() -> None:
    """Het `git grep`-voorfilter mag NOOIT nauwer zijn dan `CLAIM_PATTERN`.

    De scan leest alleen bestanden die het voorfilter halen. Zou dat filter iets missen wat het
    patroon wel vindt, dan is de guard stil blind -- en dat is exact de "token te kort"-fout die
    deze guard moet voorkomen, dan ingebouwd in de guard zelf.

    Het bewijs is structureel: elke treffer van `CLAIM_PATTERN` eindigt op de letterlijke tekens
    `19`, en het voorfilter zoekt precies die tekens. Deze test toetst dat op elke spelling die in
    de praktijk is voorgekomen, zodat een latere patroonwijziging die de eigenschap breekt hier
    omvalt in plaats van in stilte.
    """
    spellings = [
        "AI Act art. 19 noemt de invoer",
        "de art.-19-traceerbaarheid blijft intact",
        "waarop het art.-12/19-argument rust",
        "artikel 19 van de AI-verordening",
        "AI Act art. 12/14/19; AVG art. 4(5)",
    ]
    without_prefilter = []
    for text in spellings:
        match = CLAIM_PATTERN.search(text)
        assert match is not None, f"controlestring matcht niet meer: {text!r}"
        if _PREFILTER not in match.group(0):
            without_prefilter.append((text, match.group(0)))

    assert not without_prefilter, (
        f"Deze treffers bevatten het voorfilter {_PREFILTER!r} niet: {without_prefilter}. Dan slaat "
        "`git grep` bestanden over die het patroon wel zou vinden, en meldt de guard niets terwijl "
        "de claim er staat. Pas het voorfilter aan (ruimer, nooit nauwer) of haal het weg."
    )
    assert _PREFILTER in CLAIM_PATTERN.pattern, (
        f"Het patroon eist de tekens {_PREFILTER!r} niet meer letterlijk, dus het voorfilter is "
        "geen bewijsbare superset meer."
    )


def test_the_pattern_does_not_match_the_surviving_citations() -> None:
    """Vangnet in de andere richting: art. 12(2) en art. 12(3) zijn de JUISTE verwijzingen.

    Een guard die ook de correcte onderbouwing verwerpt, wordt uitgezet in plaats van vervuld.

    De tweede helft van de lijst is de F4-klasse uit Gate 2 ronde 6: `art` binnen een gewoon woord.
    Die matchten allemaal voordat er een `\\b` voor `art` stond. Ze staan hier omdat een vals
    positief in deze guard zich via de voorgeschreven remedie de allowlist inwast -- en dan is een
    echte claim in datzelfde bestand een bump verderop onzichtbaar.
    """
    correct = [
        "art. 12(2) vraagt logging die risico-identificatie mogelijk maakt",
        "art. 12(3) eist invoer-logging alleen voor Annex III punt 1(a)",
        "ADR-019 auditketen",
        "gemeten in 2019 en 1975",
        # F4: `art` binnen een woord -- geen juridische verwijzing.
        "part 19 of the payload",
        "start 19 workers",
        "chart 19 shows the trend",
        "quarter 19 was profitable",
        "partition 19 is full",
        "third-party 19 packages",
        "artifacts/19",
        "artifact 19 uploaded",
        "restart, 19 retries",
        "quartz 19",
    ]
    false_positives = sorted(text for text in correct if CLAIM_PATTERN.search(text))

    assert not false_positives, (
        f"CLAIM_PATTERN verwerpt correcte tekst: {false_positives}. De juiste onderbouwing is "
        "art. 12(2); die moet vrij te schrijven zijn, anders wordt deze guard een blokkade op het "
        "goede antwoord."
    )


def test_only_this_guard_is_excluded_from_the_scan() -> None:
    """De blinde vlek blijft exact een bestand groot."""
    assert SELF == "tests/architecture/test_refuted_ai_act_claim_stays_refuted.py", (
        f"De uitsluiting is verschoven naar {SELF}. Deze guard mag alleen ZICHZELF overslaan; "
        "elke andere uitsluiting maakt een levende claim onzichtbaar."
    )


def test_no_refuted_claim_outside_the_allowlist() -> None:
    """De weerlegde claim staat alleen nog in bestanden die de weerlegging documenteren."""
    counts = _claim_counts()
    offenders = sorted(path for path in counts if path not in ALLOWED_CLAIM_COUNTS)

    assert not offenders, (
        "Deze bestanden noemen AI Act art. 19 (of de samentrekking 12/19) als onderbouwing, "
        "terwijl die claim is weerlegd:\n\n"
        + "\n".join(f"  {p} ({counts[p]}x)" for p in offenders)
        + "\n\nDe juiste verwijzing is art. 12(2) -- logging die risico-identificatie en toezicht "
        "mogelijk maakt -- of de product-afweging (een keyed digest houdt het log forensisch "
        "bruikbaar en herhaling zichtbaar). Beschrijft het bestand juist DAT de claim onjuist is, "
        "zet hem dan met datum, reden en verwachte telling in ALLOWED_CLAIM_COUNTS."
    )


def test_allowlisted_files_have_exactly_the_expected_count() -> None:
    """Een nieuwe claim in een toegestaan bestand is ook een overtreding."""
    counts = _claim_counts()
    wrong = sorted(
        (path, entry[0], counts.get(path, 0))
        for path, entry in ALLOWED_CLAIM_COUNTS.items()
        if counts.get(path, 0) != entry[0]
    )

    assert not wrong, (
        "De telling wijkt af van wat is vastgelegd:\n\n"
        + "\n".join(f"  {p}: verwacht {e}, gevonden {g}" for p, e, g in wrong)
        + "\n\nMEER dan verwacht: er is een nieuwe levende claim bijgekomen in een bestand dat de "
        "claim alleen mocht WEERLEGGEN. MINDER dan verwacht: de weerlegging is (deels) verwijderd, "
        "en dan kan de onjuiste conclusie opnieuw getrokken worden. Beide vragen een besluit, geen "
        "stille aanpassing van het getal."
    )


def test_the_allowlist_has_no_stale_entries() -> None:
    """Een bestand dat de claim niet meer bevat, hoort niet meer in de lijst."""
    counts = _claim_counts()
    stale = sorted(
        path
        for path in ALLOWED_CLAIM_COUNTS
        if not (REPO_ROOT / path).exists() or path not in counts
    )

    assert not stale, (
        f"Deze vermeldingen hebben geen treffer meer (of het bestand bestaat niet): {stale}. "
        "Haal ze uit ALLOWED_CLAIM_COUNTS, anders rot de lijst dicht en dekt hij op termijn iets "
        "anders dan hij beweert."
    )


def test_the_windowed_count_equals_the_full_scan() -> None:
    """De snelle telling geeft hetzelfde getal als `findall` over de hele tekst, ook op de lastige gevallen.

    Mutatiebewijs (2026-10-24): `_WINDOW_BEFORE = 4` -> de gevallen met een lange aanloop worden rood; `_WINDOW_AFTER =
    0` -> de woordgrens-gevallen rood. De tegenrichting is hetzelfde getal op gewone tekst zonder `19`.
    """
    gevallen = [
        "AI Act art. 19 noemt de invoer",
        "art. 12/14/19; AVG art. 4(5)",
        "artikel 19 en artikel 19 nog eens",
        "art. 12/19 19",  # hebzuchtig: een treffer, niet twee
        "xart. 19",  # `\b` voor `art` geldt niet: geen treffer
        "art.\n19 over een regeleinde",
        "art. 19\n\nart. 19",
        "article  19-2",  # `19-2`: geen cijfer direct na de 19
        "art. 190 is geen 19",  # `(?![0-9])`
        "geen enkel getal hier",
        "1919 en 19 en art 19",
        "x" * 40 + "art. 19" + "y" * 40,
        "19" * 30,
        "art. 19" * 8,
        "",
    ]
    afwijkend = [
        (tekst, _count_claims(tekst), len(CLAIM_PATTERN.findall(tekst)))
        for tekst in gevallen
        if _count_claims(tekst) != len(CLAIM_PATTERN.findall(tekst))
    ]

    assert not afwijkend, f"de venstertelling wijkt af van de volledige scan: {afwijkend}"


def test_the_windowed_count_equals_the_full_scan_on_random_text() -> None:
    """Dezelfde eis op willekeurige tekst uit precies de tekens waar het patroon van leeft (vaste seed)."""
    import random

    generator = random.Random(20261024)
    alfabet = [
        "art",
        "artikel",
        "article",
        ".",
        " ",
        "-",
        "/",
        "(",
        ")",
        ",",
        "1",
        "9",
        "19",
        "\n",
        "x",
        "12",
    ]
    afwijkend = []
    for _ in range(3000):
        tekst = "".join(generator.choice(alfabet) for _ in range(generator.randint(0, 40)))
        if _count_claims(tekst) != len(CLAIM_PATTERN.findall(tekst)):
            afwijkend.append(tekst)

    assert not afwijkend, (
        f"{len(afwijkend)} willekeurige teksten wijken af, bijvoorbeeld {afwijkend[:3]!r}"
    )


def test_the_window_is_wide_enough_for_the_longest_match() -> None:
    """Het langste geval dat het patroon toestaat valt binnen `_WINDOW_BEFORE` tekens voor de `19`."""
    langste = "artikel." + "-" * 3 + "1" * 13 + "-" + "19"
    treffer = CLAIM_PATTERN.search(langste)

    assert treffer is not None and treffer.start() == 0, "het langste geval matcht niet meer"
    assert len(langste) - len("19") <= _WINDOW_BEFORE

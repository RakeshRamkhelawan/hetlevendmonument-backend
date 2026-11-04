#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
import re
from pathlib import Path
from typing import cast


def _configure_stdio() -> None:
    """Force UTF-8 on stdout/stderr for the CLI run (Windows console is cp1252).

    Called from main(), NOT at module level. At module level this rewrapping made the
    module unimportable from a test: pytest replaces sys.stdout with its own capture
    object, the wrapper takes over its .buffer, and the test run dies with
    "ValueError: I/O operation on closed file" during teardown (measured 2026-08-31 with
    a probe test that only did spec.loader.exec_module on this file). The doc gate needs
    unit tests (OP-42), so the side effect has to be opt-in.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            setattr(sys, name, io.TextIOWrapper(buffer, encoding="utf-8", errors="replace"))


"""
validate_feature_docs.py

Checks that every FE-* and BE-* ID registered in their respective ID-REGISTRY.md has:
  1. A spec file in the appropriate features directory.
  2. A ## Trainingssamenvatting section with at least one flow (line "- Actor:").
  3. (Frontend only) A user guide file in docs/user-guide/frontend/. The backend
     workflow (FEATURE_DOC_WORKFLOW.md, 3-step: spec -> review -> register) does
     not mandate a user guide, so this check does not apply to BE-* IDs.
  4. (Backend only) A review file whose status is APPROVED. Preferred form is an
     explicit, machine-readable line "STATUS: APPROVED" (see classify_review_status);
     reviews without that line fall back to a free-text scan.

A registry row whose path column is a bare path OUTSIDE its own features directory is
reported as [EXTERN] instead (see extern_target): an ADR addendum or an agent brief is
not a backend feature artefact with endpoints, schemas and error statuses, so checks 2
and 4 do not apply to it. It is NOT skipped silently -- the named file must exist at the
named path, and a review file that IS present must still say APPROVED.

Exit code 0 = all good
Exit code 1 = one or more IDs have incomplete documentation

Usage:
    python scripts/validate_feature_docs.py
"""

ROOT = Path(__file__).parent.parent

# IDs met een gedateerde, goedgekeurde uitzondering. Zie het bestand zelf voor de regels:
# een ID daar rapporteert als [PENDING] en laat de gate niet falen; elk ander incompleet
# ID faalt wel. Zonder dit stond de gate permanent rood op bekende gevallen, en een gate
# die altijd rood staat leest niemand meer (OP-11, 2026-07-31).
EXCEPTIONS_FILE = ROOT / "docs/backend/features/DOC-GATE-EXCEPTIONS.md"

# --- Reviewstatus (ADR-036 OP-42) --------------------------------------------------
#
# Deze poort toetste de reviewstatus met re.search(r"(?<!NOT )APPROVED", content). Dat
# is een poort die vrije TEKST scant in plaats van een machineleesbaar veld -- dezelfde
# faalvorm als OP-101, waar ast.dump() de docstring meerenderde. De lookbehind vangt
# alleen het ENGELSE "NOT APPROVED" met exact een spatie, terwijl de reviewdocumenten in
# dit project Nederlandstalig zijn. Gemeten (2026-08-31): "NIET APPROVED",
# "niet APPROVED", "nog niet APPROVED", "NOT_APPROVED" en "NON-APPROVED" gaven allemaal
# GROEN. De poort was daarmee op precies het praktijkgeval een herinnering, geen poort.
#
# Twee lagen, in deze volgorde:
#   1. Een expliciet, machineleesbaar veld "STATUS: <verdict>" -- als dat er staat, is
#      dat de waarheid en wordt de tekst niet meer geraadpleegd.
#   2. Alleen als het veld ontbreekt: de vrije-tekst-scan, nu met een ontkenningscheck
#      die niet op een lookbehind van vaste lengte leunt.
# Laag 2 blijft nodig omdat GEEN van de bestaande backend-reviews het veld heeft. Precieze
# getallen, want twee bronnen spraken elkaar hier tegen (Gate 2): docs/backend/review bevat
# 462 markdown-bestanden, waarvan 459 de naamvorm review-BE-*.md hebben. De andere drie
# zijn `code-review-BE-UTL-041.md`, `subagent-code-review-SP-FB-001.md` en
# `subagent-quality-review-SP-FB-001.md` -- een eerdere versie van deze comment noemde ze
# alle drie `subagent-*`, en dat is voor een van de drie onjuist. De poort en de
# [NOTE]-regel kijken naar die 459; zonder terugval zouden ze
# in een keer allemaal rood gaan. Zie docs/backend/FEATURE_DOC_WORKFLOW.md voor de overgang.

REVIEW_STATUS_APPROVED = "APPROVED"
REVIEW_STATUS_REJECTED = "REJECTED"
REVIEW_STATUS_UNKNOWN = "UNKNOWN"

# Case-SENSITIEF, want "Status:" komt case-insensitief honderden keren voor in deze
# bestanden -- ook als PER-BEVINDING-status ("**Status:** OPGELOST"), en dat is niet het
# eindverdict. Gemeten 2026-08-31 over alle 564 bestanden in docs/backend/review en
# docs/frontend/review: 0 regels beginnen met een hoofdletter-"STATUS:", dus deze
# sleutel botst vandaag met geen enkel bestaand document.
REVIEW_STATUS_FIELD_RE = re.compile(
    r"^[ \t]*(?:\*\*|__)?STATUS(?:\*\*|__)?[ \t]*:[ \t]*(.+?)[ \t]*$",
    re.MULTILINE,
)

# De woordenlijst komt uit de reviewer-prompt zelf (docs/backend/FEATURE_DOC_WORKFLOW.md:
# "EINDOORDEEL: APPROVED / APPROVED WITH MINOR GAPS / NEEDS REVISION / BLOCKED"),
# aangevuld met de vormen die in docs/backend/review daadwerkelijk voorkomen.
REVIEW_STATUS_REJECTING_VALUES = (
    "NOT APPROVED",
    "NOT_APPROVED",
    "NOT-APPROVED",
    "NIET APPROVED",
    "NIET_APPROVED",
    "NIET-APPROVED",
    "NON APPROVED",
    "NON_APPROVED",
    "NON-APPROVED",
    "CHANGES REQUESTED",
    "CHANGES_REQUESTED",
    "NEEDS REVISION",
    "NEEDS_REVISION",
    "BLOCKED",
    "REJECTED",
    "DEFERRED",
    "PENDING",
    "AFGEWEZEN",
)
# EXACTE lijst, geen `startswith` (Gate 2, 2026-08-31). De eerste versie deed
# `normalized.startswith("APPROVED")` en dat is fail-OPEN: gemeten passeerden
# `APPROVED_NOT_YET`, `APPROVED PENDING FIXES`, `APPROVED/BLOCKED` en -- het ergste --
# de niet-ingevulde template uit onze eigen reviewer-prompt
# (`STATUS: <APPROVED | APPROVED WITH MINOR GAPS | CHANGES_REQUESTED | ...>`), omdat de
# normalisatie `<` en `|` in spaties verandert. Een LLM die een placeholder echoot in
# plaats van invult is een bekende faalvorm, en die hoort dicht te vallen, niet open.
# De drie "APPROVED WITH ..."-vormen staan er los in omdat FEATURE_DOC_WORKFLOW.md ze
# expliciet als goedgekeurd aanmerkt.
REVIEW_STATUS_APPROVING_VALUES = frozenset(
    {
        "APPROVED",
        "APPROVED WITH MINOR GAPS",
        "APPROVED WITH MINOR ISSUES",
        "APPROVED WITH NOTES",
        "GOEDGEKEURD",
    }
)

# Een ontkenning telt alleen binnen dezelfde zinsnede. Zonder die grens zou
# "Geen risico's. **APPROVED**." (docs/backend/review/review-BE-CFG-016.md) geweigerd
# worden op een ontkenning die over een echte goedkeuring niets zegt.
#
# GEEN newline in deze verzameling (Gate 2, 2026-08-31). Stond die erin, dan bestond een
# ontkenning die door een regelafbreking van het woord gescheiden is niet meer:
# "de spec is nog niet\nAPPROVED" gaf GROEN. Dat is dezelfde faalvorm als de lookbehind
# die hier gerepareerd wordt -- toen "de scheiding moet exact een spatie zijn", nu "de
# scheiding mag geen regeleinde zijn". Reviews in dit project worden op ~100 kolommen
# gewrapt, dus dat geval is niet exotisch. Gemeten: newline eruit halen wijzigt 0 van de
# 564 verdicts in het bestaande corpus.
REVIEW_SEGMENT_BOUNDARY_CHARS = ".!?;:|"
# Geen lookbehind: die heeft in Python een vaste lengte en dekt "nog niet " dus niet.
# De laatste alternatief vangt "NOT_APPROVED" en "NON-APPROVED", waar de scheiding geen
# woordgrens is die \b ziet (underscore is een woordteken).
REVIEW_NEGATION_RE = re.compile(
    r"\bnot\b|\bnon\b|\bniet\b|(?:NOT|NIET|NON)[\s_-]*$",
    re.IGNORECASE,
)
# `geen`, `nooit` en `zonder` stonden hier ook, en dat was FOUT (Gate 2, onafhankelijke
# ronde 2026-08-31). Het zijn in Nederlandse reviewproza geen ontkenning VAN APPROVED, en
# ze veroorzaakten gemeten valse afwijzingen: `**Eindoordeel:** geen blokkers, APPROVED`
# en `Zonder open CRITICAL, APPROVED` werden beide REJECTED -- een blokkerende poortfout
# op een echt goedgekeurde review, met een melding die het omgekeerde zegt van de
# waarheid. Erger dan het gat dat deze module dicht. Gemeten na verwijdering: 0 van de
# 564 bestaande reviews wijzigt van verdict, en alle negatieve testvormen blijven falen
# doordat de anker-alternatief het werk doet.


#: Het vinkje dat 30 bestaande reviews naast APPROVED zetten. Alleen DIT teken mag door de
#: normalisatie worden weggestreken; elk ander niet-ASCII-teken in een verdict maakt de waarde
#: onbekend. Gemeten 2026-08-31 over de 564 bestanden in docs/backend/review en
#: docs/frontend/review: 40 bevatten U+2705 ergens, 30 ervan grenzend aan APPROVED, en 0
#: bevatten een kruis- of waarschuwingsglyph. Zonder die asymmetrie te sluiten zou
#: "STATUS: [kruisje] APPROVED" als goedkeuring gelden, omdat het kruisje net zo hard
#: weggestreken wordt als het vinkje.
REVIEW_STATUS_TOLERATED_GLYPHS = ("\u2705",)  # U+2705 WHITE HEAVY CHECK MARK


def normalize_review_status_value(value: str) -> str:
    """Maak een verdict-waarde vergelijkbaar: geen markdown, geen emoji, hoofdletters.

    30 echte reviewbestanden zetten het vinkje-emoji U+2705 naast APPROVED (criterium:
    grenzend aan het woord; 40 bestanden bevatten het teken ergens), en verdicts staan vaak
    vet of tussen backticks. Underscore en koppelteken blijven staan, want "NOT_APPROVED" en
    "NON-APPROVED" moeten herkenbaar blijven.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_ -]+", " ", value)
    return " ".join(cleaned.split()).upper()


def _has_unexpected_non_ascii(value: str) -> bool:
    """True als het verdict niet-ASCII bevat dat geen getolereerd vinkje is."""
    return any(ord(teken) > 127 for teken in value if teken not in REVIEW_STATUS_TOLERATED_GLYPHS)


def _classify_explicit_status_field(values: list[str]) -> tuple[str, str]:
    """Classificeer de expliciete STATUS-regel(s). Onbekende waarde = GEEN goedkeuring.

    Fail-secure: bij een waarde die niet in de woordenlijst staat weigert de poort met
    UNKNOWN in plaats van door te vallen naar de vrije tekst. Anders is het veld met een
    typefout weer net zo omzeilbaar als de tekstscan die het vervangt.

    De goedkeurende kant toetst op VOLLEDIGE gelijkheid, de afwijzende kant op `startswith`.
    Die asymmetrie is opzettelijk: bij afwijzen is meer weigeren veilig ("BLOCKED -- twee
    CRITICAL open" hoort te weigeren), bij goedkeuren is meer toelaten juist het gat.

    De afwijzende woordenlijst bepaalt alleen de MELDING, niet de uitkomst: een waarde die
    er niet in staat valt door naar de gelijkheidstoets en wordt daar UNKNOWN, dus ook
    blokkerend. Dat is met opzet zo, maar het betekent dat een element toevoegen of
    weghalen geen enkele test van uitkomst laat wisselen (gemeten Gate 2, 2026-08-31).
    """
    if not values:
        # Onbereikbaar via de enige aanroeper, maar deze functie is fail-secure of niets:
        # zonder deze tak gaf een lege lijst APPROVED, omdat de for-body dan niet loopt en
        # de functie doorviel naar de slotregel (gemeten Gate 2, 2026-08-31).
        return REVIEW_STATUS_UNKNOWN, "geen leesbare STATUS-waarde in het veld"
    for raw in values:
        normalized = normalize_review_status_value(raw)
        if any(normalized.startswith(v) for v in REVIEW_STATUS_REJECTING_VALUES):
            return REVIEW_STATUS_REJECTED, f"expliciet STATUS-veld zegt {raw.strip()!r}"
        if _has_unexpected_non_ascii(raw):
            return REVIEW_STATUS_UNKNOWN, (
                f"expliciet STATUS-veld bevat onverwachte niet-ASCII tekens: {raw.strip()!r}"
            )
        if normalized not in REVIEW_STATUS_APPROVING_VALUES:
            return REVIEW_STATUS_UNKNOWN, (
                f"expliciet STATUS-veld heeft de onbekende waarde {raw.strip()!r}; gebruik "
                "exact APPROVED, APPROVED WITH MINOR GAPS, CHANGES_REQUESTED, NEEDS REVISION "
                "of BLOCKED -- zonder toelichting op dezelfde regel"
            )
    return REVIEW_STATUS_APPROVED, "expliciet STATUS-veld zegt APPROVED"


def strip_code_blocks(review_content: str) -> str:
    """Vervang de INHOUD van code-blocks door leegte, met behoud van het regelaantal.

    Beide lagen zijn anders markdown-blind, en dat is gemeten (Gate 2, 2026-08-31): een
    `STATUS: APPROVED` in een fenced block won van een echt `NIET APPROVED` in de proza
    eronder, en een `APPROVED` in een SQL-voorbeeld maakte de vrije-tekstlaag groen. Dit is
    dezelfde klasse fout als de bug die deze module repareert -- tekst lezen waar structuur
    telt. Gemeten: strippen wijzigt 0 van de 564 verdicts in het bestaande corpus (36
    bestanden hebben een fenced block; in geen enkel bestand staat ALLE `APPROVED` erin).

    Regelaantal blijft gelijk zodat regelnummers in meldingen blijven kloppen.

    Bijwerking, gemeten en geaccepteerd (Gate 2, 2026-08-31): de heuristiek voor een
    INGESPRONGEN blok (vier spaties of een tab, geen lijstteken) blankt ook de
    vervolgregel van een lijstitem. Een gewrapt verdict (`- Eindoordeel:` op de ene regel,
    `    APPROVED WITH MINOR GAPS` op de volgende) verdwijnt daardoor stil. Richting is
    veilig -- weglaten leidt tot weigeren, niet tot doorlaten -- en het raakt 0 van de 564
    bestaande reviews, maar het is meer dan de naam van deze functie belooft.
    """
    regels = review_content.split("\n")
    resultaat: list[str] = []
    in_fence = False
    fence_teken = ""
    for regel in regels:
        gestript = regel.strip()
        if not in_fence and (gestript.startswith("```") or gestript.startswith("~~~")):
            in_fence, fence_teken = True, gestript[:3]
            resultaat.append("")
            continue
        if in_fence:
            resultaat.append("")
            if gestript.startswith(fence_teken):
                in_fence = False
            continue
        # Ingesprongen code-block (vier spaties of een tab), maar geen lijst-item.
        if (regel.startswith("    ") or regel.startswith("\t")) and not gestript.startswith(
            ("-", "*", "+", "|", ">")
        ):
            resultaat.append("")
            continue
        resultaat.append(regel)
    return "\n".join(resultaat)


#: Hoeveel niet-lege regels vanaf het begin als "de kop van het document" gelden voor het
#: STATUS-veld. FEATURE_DOC_WORKFLOW.md eist het veld op de EERSTE regel; de implementatie is
#: iets ruimer zodat een titelregel of frontmatter ervoor mag staan. Ruimer dan dit is een gat:
#: gemeten bij Gate 2 accepteerde de eerste versie het veld op regel 501 van 501, waardoor een
#: STATUS-regel diep in een bijlage het echte verdict in de kop kon overrulen.
REVIEW_STATUS_FIELD_MAX_LINES = 15


def _document_kop(review_content: str) -> str:
    """De eerste REVIEW_STATUS_FIELD_MAX_LINES niet-lege regels, met lege regels behouden."""
    resultaat: list[str] = []
    niet_leeg = 0
    for regel in review_content.split("\n"):
        resultaat.append(regel)
        if regel.strip():
            niet_leeg += 1
            if niet_leeg >= REVIEW_STATUS_FIELD_MAX_LINES:
                break
    return "\n".join(resultaat)


def free_text_says_approved(review_content: str) -> bool:
    """True zodra er een 'APPROVED' staat dat niet ontkend wordt in zijn eigen zinsnede."""
    for match in re.finditer(r"APPROVED", review_content):
        start = match.start()
        segment_start = (
            max(
                (review_content.rfind(char, 0, start) for char in REVIEW_SEGMENT_BOUNDARY_CHARS),
                default=-1,
            )
            + 1
        )
        if not REVIEW_NEGATION_RE.search(review_content[segment_start:start]):
            return True
    return False


def classify_review_status(review_content: str) -> tuple[str, str]:
    """Geef (status, reden) voor een reviewdocument.

    status is REVIEW_STATUS_APPROVED, REVIEW_STATUS_REJECTED of REVIEW_STATUS_UNKNOWN.
    Alleen APPROVED laat de poort door.

    Mutatie-getest in beide richtingen (gemeten 2026-08-31, 36 tests in
    tests/unit/scripts/test_validate_feature_docs_review_status.py):
      (a) de OUDE semantiek terugzetten -- `re.search(r"(?<!NOT )APPROVED", ...)` als enige
          toets -> ROOD, 25 failed / 29 passed.
      (b) deze functie vervangen door `return REVIEW_STATUS_REJECTED, ...` ("weiger alles")
          -> ROOD, 21 failed / 33 passed. Zonder die tweede richting zou een poort die
          simpelweg alles weigert een geldige oplossing lijken.
      Ongemuteerd: 54 passed.

      Deze getallen zijn HERMETEN op 2026-08-31 na de tweede ronde. Er stond eerst
      "14 failed / 22 passed", "18 failed / 18 passed" en "36 passed", en dat was niet meer
      waar: het testbestand is daarna gegroeid van 209 naar 325 regels zonder dat de getallen
      opnieuw zijn gemeten. Een onafhankelijke reviewer heeft dat betrapt. Wie deze getallen
      wijzigt: hermeet ze, of laat de exacte tellingen weg en noem alleen het commando.

      Let op bij het herhalen van (a): de module VOLLEDIG terugzetten op `f6747afa` geeft geen
      bruikbare meting, want dan bestaan `classify_review_status` en `_heeft_status_veld` niet
      en faalt de COLLECTIE. Muteer alleen de semantiek, niet de API.

    Beide lagen lezen de tekst ZONDER code-blocks (zie strip_code_blocks) en het veld wordt
    alleen in de kop van het document gezocht (REVIEW_STATUS_FIELD_MAX_LINES). Zonder die twee
    grenzen won een `STATUS: APPROVED` in een voorbeeldblok van het echte verdict eronder --
    gemeten bij Gate 2.
    """
    leesbaar = strip_code_blocks(review_content)

    explicit_values = REVIEW_STATUS_FIELD_RE.findall(_document_kop(leesbaar))
    if explicit_values:
        return _classify_explicit_status_field(explicit_values)

    # Een STATUS-veld BUITEN de kop is een fout, niet een goedkeuring: de kop zegt dan in proza
    # "**Eindoordeel:** NIET APPROVED" en veertig regels lager staat een `STATUS: APPROVED`, en
    # de vrije-tekst-terugval zou die regel alsnog als een niet-ontkend "APPROVED" lezen.
    # Fail-secure met UNKNOWN. Gemeten: 0 van de 564 bestaande reviews heeft ergens een veld,
    # dus deze tak raakt vandaag geen enkel bestand.
    #
    # WAT DEZE TAK NIET DEKT, en dat is gemeten en niet weggelaten (onafhankelijke Gate 2,
    # 2026-08-31). Hij ziet alleen de hoofdletter-`STATUS:`-spelling. Deze twee vormen halen de
    # poort nog steeds GROEN terwijl de kop weigert:
    #   - `**Status:** APPROVED` als laatste regel van een lang document
    #   - `De enum ContentStatus.APPROVED wordt gebruikt.` onder een kop die CHANGES_REQUESTED zegt
    # Ik heb BEIDE structurele uitwegen gemeten en beide breken echte documenten, dus ze zijn
    # niet genomen:
    #   - een afwijzende waarde in de kop laten winnen: 56 van de 564 reviews klappen om naar
    #     REJECTED, want een legitiem goedgekeurde review vermeldt in zijn kop vaak "ronde 1
    #     CHANGES_REQUESTED".
    #   - elk goedkeurend verdict-label buiten de kop als misplaatst veld behandelen: 36 van de
    #     564 klappen om naar UNKNOWN, want in dit corpus staat het echte verdict-label
    #     regelmatig onder regel 15.
    # De enige sluiting die dit restrisico wel wegneemt is het STATUS-veld zelf, en daarvoor is
    # de ratchet in tests/unit/scripts/test_validate_feature_docs_review_status.py de weg.
    # Zolang die ratchet niet op 0 staat, is dit restrisico er.
    if REVIEW_STATUS_FIELD_RE.search(leesbaar):
        return REVIEW_STATUS_UNKNOWN, (
            "er staat een STATUS-veld, maar niet in de kop van het document (eerste "
            f"{REVIEW_STATUS_FIELD_MAX_LINES} niet-lege regels). Zet het bovenaan, zodat het "
            "verdict niet afhangt van waar in het bestand iemand kijkt"
        )

    if free_text_says_approved(leesbaar):
        return (
            REVIEW_STATUS_APPROVED,
            "geen STATUS-veld; vrije-tekst-terugval vond een niet-ontkend 'APPROVED'",
        )
    return (
        REVIEW_STATUS_REJECTED,
        "geen STATUS-veld en de vrije-tekst-terugval vond geen niet-ontkend 'APPROVED'",
    )


def load_exceptions() -> set[str]:
    """IDs uit de fenced code blocks onder '## Openstaand' in EXCEPTIONS_FILE."""
    if not EXCEPTIONS_FILE.exists():
        return set()
    text = EXCEPTIONS_FILE.read_text(encoding="utf-8")
    # Alleen de sectie Openstaand telt -- de historie-tabel eronder niet.
    head, _, _ = text.partition("## Opgelost")
    ids: set[str] = set()
    in_block = False
    for line in head.splitlines():
        if line.startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            candidate = line.strip()
            if re.match(r"^(FE|BE)-[A-Z]+-\d+$", candidate):
                ids.add(candidate)
    return ids


CONFIG = {
    "FE": {
        "registry": ROOT / "docs/frontend/features/ID-REGISTRY.md",
        "features_dir": ROOT / "docs/frontend/features",
        "reviews_dir": ROOT / "docs/frontend/review",
        "user_guide_dir": ROOT / "docs/user-guide/frontend",
        "id_pattern": r"^FE-[A-Z]+-\d{3}$",
        "file_col_idx": 3,  # 0-indexed column for filename in registry
    },
    "BE": {
        "registry": ROOT / "docs/backend/features/ID-REGISTRY.md",
        "features_dir": ROOT / "docs/backend/features",
        "reviews_dir": ROOT / "docs/backend/review",
        "user_guide_dir": ROOT / "docs/user-guide/backend",
        "id_pattern": r"^BE-[A-Z]+-\d{3}$",
        "file_col_idx": 2,  # 0-indexed column for filename/path in registry
    },
}


def extern_target(prefix: str, raw_path: str) -> str | None:
    """De padwaarde als deze registerrij BUITEN zijn eigen features-map wijst, anders None.

    None betekent: behandel de rij als een gewone feature-spec, dus via de bestaande weg
    (basisnaam opzoeken in `features_dir`). Een waarde betekent: de rij wijst een artefact
    aan dat GEEN feature-spec is -- een ADR-addendum, een agent-brief -- en dat is een eigen
    categorie, geen ontbrekend specbestand.

    Waarom dit GEEN stille `continue` is (zoals de `src/`- en `tests/`-tak hierboven, die de
    rij volledig laat verdwijnen): dan kan iedereen de poort omzeilen door een echte
    feature-spec buiten `features/` neer te leggen. Een EXTERN-rij blijft zichtbaar in de
    uitvoer, het aangewezen bestand moet echt bestaan (`_check_extern_entry`), en een
    reviewbestand dat er wel is wordt nog steeds op APPROVED getoetst.

    De cel moet EEN pad-token zijn. Bevat hij witruimte, dan is het proza met een pad aan het
    eind -- dat komt echt voor: de BE-AGT-045-rij heeft een verhaal van 4000 tekens in de
    padkolom omdat de naamkolom is doorgelopen. Voor die vorm blijft de bestaande
    basisnaam-route gelden, precies zoals vandaag; hem als EXTERN behandelen zou de poort op
    een niet-bestaand "pad" laten falen op een rij die vandaag passeert.
    """
    if raw_path.split() != [raw_path]:
        return None
    normalized = raw_path.replace("\\", "/")
    if "/" not in normalized:
        return None
    features_dir = cast(Path, CONFIG[prefix]["features_dir"])
    home = features_dir.relative_to(ROOT).as_posix() + "/"
    if normalized.startswith(home):
        return None
    return normalized


def parse_registry(prefix: str) -> list[dict]:
    """Return list of {id, name, sprint, file, extern} from the Geregistreerde IDs table."""
    conf = CONFIG[prefix]
    registry_path = conf["registry"]

    if not registry_path.exists():
        print(f"[ERROR] Registry not found for {prefix}: {registry_path}")
        return []

    entries = []
    content = registry_path.read_text(encoding="utf-8")

    for line in content.splitlines():
        stripped = line.strip()

        # Check if we are in a table row
        if stripped.startswith("|") and re.search(
            conf["id_pattern"], stripped.split("|")[1].strip()
        ):
            parts = [p.strip() for p in stripped.split("|")]
            parts = [p for p in parts if p]  # remove empty strings from leading/trailing |

            if len(parts) >= 4:
                item_id = parts[0]
                # Skip reserved or placeholder entries
                if "###" in item_id or "Gereserveerd" in stripped:
                    continue

                file_val = parts[conf["file_col_idx"]]
                # Clean up file_val (might be a full path or have backticks)
                file_val = file_val.replace("`", "")

                # Skip entries pointing to source or test files -- not doc specs
                raw_path = file_val.strip()
                if (
                    raw_path.startswith("src/")
                    or raw_path.startswith("src\\")
                    or raw_path.startswith("tests/")
                    or raw_path.startswith("tests\\")
                ):
                    continue

                if "/" in file_val:
                    file_val = file_val.split("/")[-1]

                entries.append(
                    {
                        "id": item_id,
                        "name": parts[1],
                        "sprint": parts[2] if len(parts) > 2 else "Unknown",
                        "file": file_val,
                        "prefix": prefix,
                        "extern": extern_target(prefix, raw_path),
                    }
                )

    return entries


def derive_guide_name(prefix: str, spec_filename: str) -> str | None:
    """
    FE-PAGE-006-compliance-hub.md -> compliance-hub.md
    BE-MID-001-audit-logging-middleware.md -> audit-logging-middleware.md
    """
    pattern = rf"^{prefix}-[A-Z]+-\d{{3}}-(.+)$"
    match = re.match(pattern, spec_filename)
    if match:
        return match.group(1)
    return None


def _check_extern_entry(entry: dict, extern: str) -> list[str]:
    """Toets een registerrij die een artefact BUITEN zijn eigen features-map aanwijst.

    Wat hier WEL wordt getoetst:
      - het aangewezen bestand bestaat op het genoemde pad (anders faalt de poort);
      - is er een reviewbestand voor dit ID, dan moet dat APPROVED zijn.

    Wat hier NIET wordt getoetst, en waarom: de Trainingssamenvatting en de VERPLICHTING van
    een review. Beide horen bij een backend-feature-spec met endpoints, schema's en
    foutstatussen (docs/backend/FEATURE_DOC_WORKFLOW.md). Een ADR-addendum of een
    final-approver-brief is dat niet, en er een leeg mini-format op plakken maakt de
    documentatie slechter, niet beter.

    De review blijft wel voorwaardelijk getoetst: een externe rij hoeft geen review te hebben,
    maar een review die CHANGES_REQUESTED zegt mag nooit stilzwijgend genegeerd worden.
    """
    errors: list[str] = []
    if not (ROOT / extern).is_file():
        errors.append(f"    MISSING EXTERN FILE: {extern}")
    errors.extend(_check_backend_review(entry, required=False))
    return errors


def _check_backend_review(entry: dict, required: bool) -> list[str]:
    """Toets het reviewbestand van een BE-ID. `required=False`: ontbreken mag, afwijzen niet."""
    if entry["prefix"] != "BE":
        return []
    conf = CONFIG[entry["prefix"]]
    reviews_dir = cast(Path, conf["reviews_dir"])
    review_file = f"review-{entry['id']}.md"
    review_path = reviews_dir / review_file
    if not review_path.exists():
        if not required:
            return []
        return [
            f"    MISSING REVIEW     : {reviews_dir.relative_to(ROOT).as_posix()}/{review_file}"
        ]
    # Een leesfout hier is fail-SECURE en dus een poortfout, geen traceback. De
    # niet-blokkerende adoptie-melding vangt `OSError` ook (`_heeft_status_veld`), maar
    # dit is het pad dat de EXITCODE bepaalt en het was onafgeschermd -- de afscherming
    # zat op de tak die het minst uitmaakt (onafhankelijke Gate 2, 2026-08-31). Op
    # OneDrive-paden is een leesfout niet theoretisch.
    try:
        review_content = review_path.read_text(encoding="utf-8", errors="replace")
    except OSError as fout:
        return [f"    UNREADABLE REVIEW  : {review_file}: {type(fout).__name__}"]
    status, reason = classify_review_status(review_content)
    if status == REVIEW_STATUS_REJECTED:
        return [f"    NOT APPROVED       : {review_file}: {reason}"]
    if status == REVIEW_STATUS_UNKNOWN:
        return [f"    STATUS UNCLEAR     : {review_file}: {reason}"]
    return []


def check_entry(entry: dict) -> list[str]:
    """Return list of error strings for this entry (empty = all good)."""
    errors = []
    conf = CONFIG[entry["prefix"]]
    extern = entry.get("extern")
    if extern is not None:
        return _check_extern_entry(entry, extern)
    spec_path = conf["features_dir"] / entry["file"]

    # Check 1: spec file exists
    if not spec_path.exists():
        errors.append(
            f"    MISSING SPEC FILE  : {conf['features_dir'].relative_to(ROOT)}/{entry['file']}"
        )
        return errors

    content = spec_path.read_text(encoding="utf-8")

    # Check 2: Trainingssamenvatting section present
    has_section = bool(
        re.search(r"^#{1,6}\s.*trainingssamenvatting", content, re.IGNORECASE | re.MULTILINE)
    )
    if not has_section:
        errors.append("    MISSING            : Trainingssamenvatting heading in spec")
    else:
        # Flexible check for Actor lines (list or table)
        has_actor = bool(re.search(r"(?:-|\*\*|\*|\|)\s*Actor", content, re.IGNORECASE))
        if not has_actor:
            errors.append(
                "    INCOMPLETE         : Trainingssamenvatting has no flows "
                "(missing 'Actor' line/cell)"
            )

    # Check 3: user guide exists -- FRONTEND ONLY.
    # User guides are a frontend-workflow requirement (5-step). The backend
    # workflow (docs/backend/FEATURE_DOC_WORKFLOW.md, 3-step: spec -> review ->
    # register) never mandated a user guide; requiring one for BE-* IDs made the
    # script fail on every backend ID regardless of correctness (pre-existing
    # tooling-vs-process mismatch, resolved 2026-07-06).
    guide_name = derive_guide_name(entry["prefix"], entry["file"])
    if guide_name and entry["prefix"] == "FE":
        guide_path = conf["user_guide_dir"] / guide_name
        if not guide_path.exists():
            # Special case: some guides might be named differently or shared
            # We only report if a guide name was derived but file is missing
            errors.append(
                f"    MISSING USER GUIDE : {conf['user_guide_dir'].relative_to(ROOT)}/{guide_name}"
            )

    # Check 4: (Backend only) Review exists and is APPROVED
    errors.extend(_check_backend_review(entry, required=True))

    return errors


def _heeft_status_veld(path: Path) -> bool:
    """True als dit reviewbestand een expliciet STATUS-veld in zijn kop heeft.

    Faalt NOOIT op een leesfout. Zonder deze afscherming maakte een `PermissionError` op een
    van de 459 bestanden een verder GESLAAGDE run tot een traceback met exitcode != 0 --
    gemeten bij Gate 2, en op OneDrive-paden is een leesfout niet theoretisch. Een onleesbaar
    bestand geldt als "geen veld": dat telt hoogstens mee in een niet-blokkerende melding.
    """
    try:
        inhoud = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(REVIEW_STATUS_FIELD_RE.search(_document_kop(strip_code_blocks(inhoud))))


def report_review_status_field_adoption() -> None:
    """Meld hoeveel backend-reviews nog op de vrije-tekst-terugval leunen.

    Bewust NIET blokkerend: geen van de bestaande reviews heeft het STATUS-veld, en een
    poort die in een keer 462 documenten rood zet, wordt uitgezet in plaats van gevolgd
    (dezelfde afweging als bij de uitzonderingslijst, OP-11). Deze regel maakt de
    overgang zichtbaar zonder het verkeer stil te leggen.
    """
    # CONFIG is een kale dict, dus mypy leidt hier "object" af; cast houdt de teller op
    # de bestaande 11 in dit bestand in plaats van 12 (gemeten in-repo, 2026-08-31).
    reviews_dir = cast(Path, CONFIG["BE"]["reviews_dir"])
    without_field = [
        path.name
        for path in sorted(reviews_dir.glob("review-BE-*.md"))
        if not _heeft_status_veld(path)
    ]
    if not without_field:
        return
    print(
        f"[NOTE] {len(without_field)} backend-review(s) hebben nog geen expliciete "
        "'STATUS: <verdict>'-regel; daar valt de poort terug op de vrije-tekst-scan "
        "(ADR-036 OP-42, niet blokkerend)."
    )
    print("       Nieuwe reviews: zie docs/backend/FEATURE_DOC_WORKFLOW.md, stap 2.")


def main() -> None:
    _configure_stdio()
    all_entries = []
    for prefix in CONFIG:
        all_entries.extend(parse_registry(prefix))

    if not all_entries:
        print("[ERROR] No entries found in the registries. Check format.")
        sys.exit(1)

    print(f"Feature docs validation -- {len(all_entries)} registered IDs\n")
    print(f"{'ID':<16} {'Name':<40} {'Sprint':<15} Result")
    print("-" * 100)

    failures = 0
    seen_specs: set[str] = set()
    exceptions = load_exceptions()
    pending = 0
    extern = 0
    resolved_exceptions: list[str] = []

    # Sort all_entries by ID for consistent output
    all_entries.sort(key=lambda x: x["id"])

    for entry in all_entries:
        spec_key = f"{entry['prefix']}:{entry['extern'] or entry['file']}"
        if spec_key in seen_specs:
            print(f"{'[OK]':<6} {entry['id']:<16} {entry['name']:<40} (shared spec)")
            continue
        seen_specs.add(spec_key)

        errors = check_entry(entry)
        is_excepted = entry["id"] in exceptions

        if errors and is_excepted:
            pending += 1
            print(f"[PENDING] {entry['id']:<14} {entry['name']:<40} {entry['sprint']}")
            for err in errors:
                print(err)
        elif errors:
            failures += 1
            print(f"[FAIL] {entry['id']:<16} {entry['name']:<40} {entry['sprint']}")
            for err in errors:
                print(err)
        elif entry["extern"] is not None:
            extern += 1
            print(f"[EXTERN] {entry['id']:<14} {entry['name']:<40} -> {entry['extern']}")
        else:
            if is_excepted:
                resolved_exceptions.append(entry["id"])
            print(f"[OK]   {entry['id']:<16} {entry['name']:<40} {entry['sprint']}")

    print("\n" + "=" * 100)

    if resolved_exceptions:
        print(
            f"[PENDING-RESOLVED] {len(resolved_exceptions)} ID(s) staan nog op de "
            f"uitzonderingslijst maar zijn nu compleet: {', '.join(resolved_exceptions)}."
        )
        print(f"    Verwijder ze uit {EXCEPTIONS_FILE.relative_to(ROOT)} (blokkeert niets).")

    if pending:
        print(
            f"[PENDING] {pending} ID(s) met een gedateerde uitzondering in "
            f"{EXCEPTIONS_FILE.relative_to(ROOT)} -- niet blokkerend, wel openstaand."
        )

    if extern:
        print(
            f"[EXTERN] {extern} ID(s) wijzen naar een artefact BUITEN hun features-map "
            "(ADR-addendum, agent-brief). Van die rijen is alleen gecontroleerd dat het "
            "genoemde bestand bestaat, plus de reviewstatus als er een review is -- geen "
            "Trainingssamenvatting, want dat zijn geen feature-specs."
        )

    report_review_status_field_adoption()

    if failures == 0:
        complete = len(all_entries) - pending
        print(f"[PASS] {complete} van {len(all_entries)} IDs volledig gedocumenteerd.")
        if pending:
            print("       Geen NIEUWE incomplete IDs. Sprint day may be closed.")
        else:
            print("       Sprint day may be closed.")
        sys.exit(0)
    else:
        print(f"[FAIL] {failures} ID(s) have incomplete documentation.")
        print("\nRequired for each ID:")
        print("  1. Spec file in docs/[frontend|backend]/features/")
        print("  2. Trainingssamenvatting section with at least one 'Actor:' flow")
        print("  3. (FE only) User guide in docs/user-guide/frontend/")
        print("  4. (BE only) APPROVED review file in docs/backend/review/")
        sys.exit(1)


if __name__ == "__main__":
    main()

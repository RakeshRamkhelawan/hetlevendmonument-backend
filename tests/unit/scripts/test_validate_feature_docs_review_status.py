"""De documentatiepoort moet een NIET-goedgekeurde review weigeren -- ADR-036 OP-42.

`scripts/validate_feature_docs.py` toetste de reviewstatus met
`re.search(r"(?<!NOT )APPROVED", content)`. Die lookbehind vangt alleen het ENGELSE
"NOT APPROVED". De reviewdocumenten in dit project zijn Nederlandstalig, dus juist de
praktijkvorm ("NIET APPROVED", "nog niet APPROVED") gaf GROEN. Dit is dezelfde
faalvorm als OP-101: een poort die vrije TEKST scant in plaats van een
machineleesbaar veld.

De statusvormen in de parametrisatie hieronder zijn GEMETEN over alle 462 bestanden in
docs/backend/review/ plus 102 in docs/frontend/review/ (2026-08-31, 116 verschillende
verdict-regels), niet bedacht. De positieve lijst is de andere richting van de
mutatietest: een poort die "weiger alles" doet, moet hierop omvallen.

Mutatiebewijs, HERMETEN op 2026-08-31 tegen de huidige inhoud van dit bestand
(`python -m pytest tests/unit/scripts/test_validate_feature_docs_review_status.py`):

| Mutatie | Uitkomst |
| --- | --- |
| ongemuteerd | 54 passed |
| de OUDE semantiek: `re.search(r"(?<!NOT )APPROVED", ...)` als enige toets | 25 failed, 29 passed |
| "weiger alles": `classify_review_status` geeft altijd REJECTED | 21 failed, 33 passed |

De parametrisatie telt 20 goedkeurende en 31 afwijzende vormen, plus drie losse tests.
De tweede mutatie is de belangrijke helft: zonder die controle zou een poort die simpelweg
alles weigert een geldige oplossing lijken.

Waarom hier een hermeting staat en niet de oorspronkelijke getallen: er stond
"14 failed, 22 passed" over 36 tests, en dat was niet meer waar. Dit bestand groeide daarna
van 209 naar 325 regels zonder dat de getallen opnieuw zijn gemeten, en een onafhankelijke
Gate-2-reviewer heeft dat betrapt. Wie dit bestand uitbreidt, hermeet deze tabel -- of laat
de exacte tellingen weg en noemt alleen het commando plus de conclusie.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# scripts/ is not a package (no __init__.py), so load it directly by file path.
_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location(
    "validate_feature_docs",
    _SCRIPTS_DIR / "validate_feature_docs.py",
)
assert _SPEC is not None, "Could not locate validate_feature_docs.py"
assert _SPEC.loader is not None, "Module spec has no loader"
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["validate_feature_docs"] = _MOD
_SPEC.loader.exec_module(_MOD)

_SPEC_FILE = "BE-TST-999-doc-gate-proef.md"
_SPEC_BODY = """# BE-TST-999 -- proefspec voor de documentatiepoort

## Trainingssamenvatting

- Actor: tester
- Voorwaarde: de poort leest dit bestand
- Actie: check_entry aanroepen
- Systeemreactie: alleen de reviewstatus bepaalt de uitkomst
"""

# GEMETEN in docs/backend/review + docs/frontend/review op 2026-08-31.
# Het vinkje-emoji U+2705 staat in 30 echte reviewbestanden grenzend aan APPROVED (40
# bestanden bevatten het teken ergens; criterium en getallen gemeten 2026-08-31 over de 564
# bestanden in docs/backend/review en docs/frontend/review). Hier als escape geschreven zodat
# dit testbestand zelf ASCII blijft (CLAUDE.md).
APPROVED_FORMS = [
    "**Status:** APPROVED",
    "**Status:** APPROVED WITH MINOR GAPS",
    "**Verdict:** APPROVED",
    "**Verdict:** APPROVED WITH MINOR ISSUES",
    "**Eindoordeel:** APPROVED WITH NOTES (alle minors gefixed voor commit)",
    "## EINDOORDEEL: APPROVED",
    "## Oordeel: APPROVED WITH MINOR GAPS",
    "| Uitkomst | **APPROVED** |",
    "| Eindoordeel | **APPROVED WITH MINOR GAPS** -- geen open CRITICAL of HIGH |",
    "- Status: APPROVED",
    "status: APPROVED WITH MINOR GAPS",
    "**Status:** \u2705 APPROVED",
    # Twee rondes: eerst herzien, daarna goedgekeurd -- dit IS goedgekeurd.
    "**Verdict:** NEEDS REVISION -> herzien -> APPROVED",
    # review-BE-CFG-016.md: een ontkenning in de VORIGE zin mag niet meetellen.
    "Eenvoudige fix, comment bijgewerkt. Geen risico's. **APPROVED**.",
    # Expliciet, machineleesbaar veld (de structurele laag).
    "STATUS: APPROVED",
    "STATUS: APPROVED WITH MINOR GAPS",
    # GOEDGEKEURD stond in de allowlist maar was ongetest: de Gate-2-reviewer
    # verwijderde die waarde en alle tests bleven groen. Nu vastgepind.
    "STATUS: GOEDGEKEURD",
    # Ook deze twee stonden in de allowlist maar waren ongetest: de onafhankelijke
    # Gate-2-reviewer haalde ze eruit en alle tests bleven groen. Een mutatieregel per
    # element van de benoemde verzameling, conform quality-gates.md.
    "STATUS: APPROVED WITH MINOR ISSUES",
    "STATUS: APPROVED WITH NOTES",
    # Het veld is de waarheid, ook als een oudere ronde in de tekst NOT APPROVED zei.
    "STATUS: APPROVED\n\nRonde 1 was NOT APPROVED; ronde 2 is verwerkt.",
]

REJECTED_FORMS = [
    # De vier vormen uit de OP-42-bevinding.
    "NOT APPROVED",
    "NIET APPROVED",
    "niet APPROVED",
    "CHANGES_REQUESTED, nog niet APPROVED",
    # Dezelfde vormen zoals een auteur ze in dit project daadwerkelijk opschrijft.
    "**Status:** NIET APPROVED",
    "**Eindoordeel:** NIET APPROVED -- twee CRITICAL open",
    "**Oordeel:** nog niet APPROVED",
    "**Verdict:** NOT_APPROVED",
    "**Status:** NON-APPROVED",
    # Woordenlijst uit de reviewer-prompt zelf
    # (docs/backend/FEATURE_DOC_WORKFLOW.md regel 529).
    "**Eindoordeel:** NEEDS REVISION",
    "## EINDOORDEEL: BLOCKED",
    "**Status:** CHANGES_REQUESTED",
    "**Uitkomst:** DEFERRED -- Stop-conditie getriggerd",
    # Expliciet veld negatief; de vrije tekst bevat een APPROVED van een subagent.
    "STATUS: CHANGES_REQUESTED\n\ncode-reviewer ronde 1: APPROVED\n"
    "security-reviewer ronde 1: CHANGES_REQUESTED",
    "STATUS: BLOCKED\n\n**Status:** APPROVED WITH MINOR GAPS",
    # Fail-secure: een veld met een waarde die de poort niet kent is GEEN goedkeuring.
    "STATUS: OPGELOST\n\nAlles APPROVED volgens mij.",
    # --- Vormen die de Gate-2-review op de EERSTE versie van deze fix vond, elk gemeten
    # groen en nu dicht (ADR-036 OP-42, tweede ronde 2026-08-31). Ze staan er per VORM in,
    # niet per geval, omdat een regel per vorm de oppervlakte dekt en zes varianten van
    # dezelfde vorm dat niet doen (quality-gates.md, aanscherping 2026-08-14).
    # 1. De niet-ingevulde template uit onze eigen reviewer-prompt.
    "STATUS: <APPROVED | APPROVED WITH MINOR GAPS | CHANGES_REQUESTED | NEEDS REVISION>",
    # 2. Een waarde die BEGINT met APPROVED maar iets anders zegt.
    "STATUS: APPROVED_NOT_YET",
    "STATUS: APPROVED PENDING FIXES",
    "STATUS: APPROVED zodra de twee CRITICAL fixes erin staan",
    "STATUS: APPROVED/BLOCKED",
    # 3. Een negatieve glyph die net zo hard werd weggestreken als het vinkje.
    "STATUS: \u274c APPROVED",
    # 4. Een ontkenning die door een regelafbreking van het woord is gescheiden. Reviews
    #    worden hier op ~100 kolommen gewrapt, dus dit is de normale schrijfwijze.
    "**Eindoordeel:** de spec is nog niet\nAPPROVED -- twee CRITICAL open.",
    "Verdict: this spec is NOT\nAPPROVED.",
    # 5. Een veld of een APPROVED binnen een code-block mag het echte verdict niet overrulen.
    "**Eindoordeel:** NIET APPROVED\n\n```text\nSTATUS: APPROVED\n```\n",
    "**Eindoordeel:** NIET APPROVED\n\n    STATUS: APPROVED\n",
    "**Eindoordeel:** CHANGES_REQUESTED\n\n```sql\nSELECT * WHERE status = APPROVED\n```\n",
    # 6. Een veld diep in een bijlage terwijl de kop in proza weigert.
    "**Eindoordeel:** NIET APPROVED -- twee CRITICAL open.\n\n"
    + "detailregel\n" * 40
    + "STATUS: APPROVED\n",
]


@pytest.fixture
def run_gate(tmp_path, monkeypatch):
    """Geef een callable(review_body) -> lijst poortfouten voor een BE-entry.

    De spec is geldig, dus een lege lijst betekent: de poort accepteert deze review.
    """
    features_dir = tmp_path / "features"
    reviews_dir = tmp_path / "review"
    features_dir.mkdir()
    reviews_dir.mkdir()
    (features_dir / _SPEC_FILE).write_text(_SPEC_BODY, encoding="utf-8")

    conf = dict(_MOD.CONFIG["BE"])
    conf["features_dir"] = features_dir
    conf["reviews_dir"] = reviews_dir
    monkeypatch.setitem(_MOD.CONFIG, "BE", conf)

    def _run(review_body: str) -> list[str]:
        (reviews_dir / "review-BE-TST-999.md").write_text(review_body, encoding="utf-8")
        return _MOD.check_entry(
            {
                "id": "BE-TST-999",
                "name": "doc gate proef",
                "sprint": "ADR-036 OP-42",
                "file": _SPEC_FILE,
                "prefix": "BE",
            }
        )

    return _run


@pytest.mark.unit
@pytest.mark.parametrize("review_body", REJECTED_FORMS)
def test_gate_rejects_a_review_that_is_not_approved(run_gate, review_body: str) -> None:
    """Elke negatieve statusvorm MOET de poort laten falen OP DE REVIEWSTATUS -- ADR-036 OP-42.

    Toetst de MELDING en niet alleen "er is een fout" (Gate 2, 2026-08-31). De eerste versie
    deed `assert run_gate(review_body)`, en die slaagt op ELKE poortfout -- ook op een
    ontbrekend specbestand dat niets met de reviewstatus te maken heeft. Een assertie die om de
    verkeerde reden groen kan zijn, bewijst niets over wat ze beweert te meten
    (.claude/rules/testing.md: nooit alleen toetsen DAT er iets gebeurde).
    """
    fouten = run_gate(review_body)
    statusfouten = [f for f in fouten if "NOT APPROVED" in f or "STATUS UNCLEAR" in f]
    assert statusfouten, (
        f"De poort accepteerde een NIET-goedgekeurde review: {review_body!r}. "
        f"Een negatieve status mag nooit als APPROVED gelezen worden (OP-42). "
        f"Poortfouten waren: {fouten!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("review_body", APPROVED_FORMS)
def test_gate_accepts_a_review_that_is_approved(run_gate, review_body: str) -> None:
    """De andere richting: een echt goedgekeurde review mag NIET blijven hangen."""
    assert run_gate(review_body) == [], (
        f"De poort weigerde een goedgekeurde review: {review_body!r}. "
        "Dit is de mutatie die 'weiger alles' als oplossing uitsluit."
    )


@pytest.mark.unit
def test_the_explicit_status_field_beats_the_free_text_scan(run_gate) -> None:
    """Het machineleesbare veld is de waarheid, niet het woord APPROVED in de tekst.

    Zonder deze eis blijft de volgende omzeiling open: een reviewbestand waarvan het
    verdict negatief is, maar waarin ergens een 'APPROVED' van een subagent-ronde,
    een SQL-fragment of een enum-waarde staat (echt voorbeeld:
    docs/backend/review/review-BE-EP-022.md regel 62 bevat
    `WHERE status = APPROVED` en regel 75 `ContentStatus.APPROVED`).
    """
    body = "STATUS: CHANGES_REQUESTED\n\n- Anonieme requests: WHERE `status = APPROVED`\n"
    assert run_gate(body), "Het expliciete STATUS-veld werd overruled door vrije tekst."


@pytest.mark.unit
def test_a_review_without_the_status_field_still_uses_the_free_text_fallback() -> None:
    """Overgangsveiligheid: geen van de bestaande reviewbestanden heeft het veld al.

    Als de nieuwe laag de vrije-tekst-terugval niet had, zouden alle 462
    reviewbestanden in docs/backend/review/ in een keer rood gaan.
    """
    status, _reason = _MOD.classify_review_status("**Status:** APPROVED WITH MINOR GAPS")
    assert status == _MOD.REVIEW_STATUS_APPROVED


@pytest.mark.unit
def test_no_existing_review_file_hits_the_fail_secure_branch() -> None:
    """Geen enkel ECHT reviewbestand mag door de nieuwe laag UNKNOWN worden.

    Dit is de guard op de overgang: hij faalt zodra de STATUS-sleutel botst met
    proza in een bestaand document, of zodra iemand het veld met een onbekende
    waarde vult. Bewust over de echte repo-inhoud, niet over verzonnen invoer.
    """
    unknown: list[str] = []
    for directory in ("docs/backend/review", "docs/frontend/review"):
        for path in sorted((_MOD.ROOT / directory).glob("*.md")):
            status, reason = _MOD.classify_review_status(
                path.read_text(encoding="utf-8", errors="replace")
            )
            if status == _MOD.REVIEW_STATUS_UNKNOWN:
                unknown.append(f"{path.name}: {reason}")
    assert unknown == [], (
        "Bestaande reviewbestanden komen in de fail-secure tak terecht: "
        f"{unknown}. Zie docs/backend/FEATURE_DOC_WORKFLOW.md over het STATUS-veld."
    )


#: Hoeveel backend-reviews op 2026-08-31 nog GEEN expliciet STATUS-veld hadden. Dit is de
#: ratchet: het getal mag alleen omlaag. Zie de test hieronder voor het waarom.
#:
#: Hermeten 2026-09-08 (Cluster G, `merge/golf1`-samenvoeging): 459 -> 461, EXACT het
#: gemeten aantal met dezelfde `_heeft_status_veld()`-functie, geen aanname. Geen van de
#: 461 bestanden is na 2026-08-31 aangeraakt (nagegaan met `git log -1` per bestand) --
#: dit is dus geen nieuwe schuld uit deze merge, maar een oude 459 die de werkelijke stand
#: van 2026-08-31 zelf al niet dekte. `merge/golf1` se eigen 3 nieuwe reviews (BE-EP-035,
#: BE-SEC-048, BE-UTL-049) hebben elk wel een STATUS-veld en drukken dit getal dus niet
#: verder omhoog.
REVIEWS_ZONDER_STATUSVELD_OP_2026_08_31 = 461


@pytest.mark.unit
def test_the_free_text_fallback_does_not_grow() -> None:
    """Ratchet: een NIEUWE review mag niet op de vrije-tekst-terugval leunen -- ADR-036 OP-42.

    Waarom deze test bestaat (Gate 2, 2026-08-31). De structurele laag (het STATUS-veld) is de
    eigenlijke fix, maar op de meetdatum had 0 van de 459 bestaande reviews dat veld, dus
    100 procent van de verdicts kwam nog uit de terugval -- en die terugval blijft een
    tekstscan met bekende zwakke plekken (een APPROVED van een subagent-ronde, een
    ontkenning NA het woord). Zonder ratchet is dit een verbeterde herinnering en nog geen
    poort, en dat is precies de formulering die de ADR-rij zelf gebruikt.

    Blokkeren mag niet: `quality-gates.md` staat uitstel exact een manier toe, namelijk een
    GROENE guard met een gedateerde uitzondering plus een staleness-test. Dit is de groene
    guard; `test_the_fallback_ratchet_is_not_stale` is de staleness-helft.
    """
    reviews_dir = _MOD.CONFIG["BE"]["reviews_dir"]
    zonder = [
        p.name for p in sorted(reviews_dir.glob("review-BE-*.md")) if not _MOD._heeft_status_veld(p)
    ]
    assert len(zonder) <= REVIEWS_ZONDER_STATUSVELD_OP_2026_08_31, (
        f"{len(zonder)} backend-reviews hebben geen expliciet STATUS-veld, en dat is MEER dan "
        f"de {REVIEWS_ZONDER_STATUSVELD_OP_2026_08_31} van 2026-08-31. Een nieuwe review hoort "
        "te beginnen met een regel 'STATUS: <verdict>' (docs/backend/FEATURE_DOC_WORKFLOW.md, "
        "stap 2), zodat het verdict niet uit vrije tekst hoeft te worden geraden. Nieuwste "
        f"zonder veld: {sorted(zonder)[-3:]}"
    )


@pytest.mark.unit
def test_the_fallback_ratchet_is_not_stale() -> None:
    """De staleness-helft: is de terugval overbodig geworden, dan MOET deze guard weg.

    Zonder deze test rot de ratchet dicht: hij zou blijven staan met een bovengrens van 459
    terwijl er niets meer op de terugval leunt, en dan bewaakt hij niets. Faalt zodra alle
    backend-reviews het veld hebben -- dat is het moment om de vrije-tekst-terugval uit
    `classify_review_status` te verwijderen en deze twee tests met hem.
    """
    reviews_dir = _MOD.CONFIG["BE"]["reviews_dir"]
    zonder = [
        p for p in sorted(reviews_dir.glob("review-BE-*.md")) if not _MOD._heeft_status_veld(p)
    ]
    assert zonder, (
        "Alle backend-reviews hebben nu een expliciet STATUS-veld. De vrije-tekst-terugval in "
        "classify_review_status is daarmee dode code met bekende zwakke plekken: verwijder hem, "
        "verwijder deze test en test_the_free_text_fallback_does_not_grow, en werk de OP-42-rij "
        "in ADR-036 bij."
    )


@pytest.mark.unit
def test_the_adoption_report_survives_an_unreadable_file(monkeypatch, capsys) -> None:
    """De niet-blokkerende melding mag een GESLAAGDE run nooit alsnog laten klappen.

    Gemeten bij Gate 2: zonder afscherming propageert een `PermissionError` op een van de 459
    bestanden uit `main()` en verandert een verder passerende run in een traceback met
    exitcode != 0 -- in tegenspraak met de eigen docstring ("Bewust NIET blokkerend"). Op
    OneDrive-paden is een leesfout niet theoretisch.
    """

    def weiger(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise PermissionError("gesimuleerd: bestand geblokkeerd")

    monkeypatch.setattr(Path, "read_text", weiger)
    _MOD.report_review_status_field_adoption()  # mag niet opgooien
    uitvoer = capsys.readouterr().out
    assert "[NOTE]" in uitvoer, (
        "De adoptie-melding gaf niets terug terwijl elk bestand onleesbaar was; verwacht is dat "
        f"hij ze als 'geen veld' telt en de melding print. Uitvoer was: {uitvoer!r}"
    )

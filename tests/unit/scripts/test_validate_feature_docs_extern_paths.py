"""Een registerrij die BUITEN zijn features-map wijst is een eigen categorie, geen gat.

`docs/backend/features/ID-REGISTRY.md` wijst voor BE-AGT-062 het bestand
`docs/adr/031-addendum-fase5-autonomy-ladder-scope.md` aan. Dat bestand BESTAAT, maar
`scripts/validate_feature_docs.py` nam de basisnaam en zocht hem in
`docs/backend/features/` -- daar staat hij niet, dus MISSING SPEC FILE en exitcode 1. Dat is
een categoriseringsfout: een ADR-addendum is geen backend-feature-artefact met endpoints,
schema's en foutstatussen, dus de Trainingssamenvatting- en review-eis horen er niet op.

De verleiding was een stille `continue` (zoals de bestaande `src/`- en `tests/`-tak). Dat is
NIET gedaan, want dan omzeilt iedereen de poort door een echte feature-spec buiten
`features/` neer te leggen. In plaats daarvan: een ZICHTBARE categorie `[EXTERN]`, waarbij
het genoemde bestand echt moet bestaan en een AANWEZIG reviewbestand nog steeds APPROVED
moet zeggen.

MUTATIEBEWIJS -- gemeten 2026-09-01 met
`python -m pytest tests/unit/scripts/test_validate_feature_docs_extern_paths.py -q`
(mutaties in `scripts/validate_feature_docs.py`, teruggezet uit een KOPIE, niet via
`git checkout --`):

| Mutatie | Gemeten uitkomst |
| --- | --- |
| ongemuteerd | 12 passed |
| `_check_extern_entry` -> `return []` (de stille `continue`) | 2 failed, 10 passed |
| `extern_target` -> `return None` (categorie bestaat niet, oude gedrag) | 6 failed, 6 passed |
| `extern_target` -> `return raw_path` voor ELKE rij ("alles is extern") | 7 failed, 5 passed |
| `_check_backend_review(..., required=False)` weg uit `_check_extern_entry` | 1 failed, 11 passed |

De derde en vierde mutatie zijn de andere richting: zonder die helft zou "verklaar alles
extern en toets niets meer" een geldige oplossing lijken, en zou het wegvallen van de
reviewcontrole op de drie BE-RTR-rijen onopgemerkt blijven.

Elke mutatie is teruggezet uit de kopie en daarna met een SHA-256-vergelijking bevestigd
byte-identiek aan het origineel; de suite is na herstel opnieuw groen gemeten (66 passed
samen met `test_validate_feature_docs_review_status.py`, dus geen regressie daar).

GEMETEN NEVENEFFECT OP BESTAANDE RIJEN, expliciet en niet weggelaten. Vier rijen in het echte
register wijzen al buiten hun features-map en passeerden vandaag:
`BE-RTR-037/038/039` (naar `docs/agent-briefs/generated/...`) en BE-AGT-062. De drie
BE-RTR-rijen passeerden om een TOEVALLIGE reden: er staat een kopie van dezelfde agent-brief
onder dezelfde basisnaam in `docs/backend/features/`, dus de basisnaam-route vond hem daar.
De poort toetste dus nooit het pad dat het register daadwerkelijk noemt. Na deze wijziging
gaan die drie van `[OK]` naar `[EXTERN]`: hun DECLARED pad wordt nu gecontroleerd (alle drie
bestaan) en hun reviewbestanden (`review-BE-RTR-037/038/039.md`, alle drie aanwezig en
APPROVED) worden nog steeds getoetst. Wat wegvalt is de Trainingssamenvatting-eis op de
kopie in `features/` -- en die kopie is een final-approver-brief, geen feature-spec.

`BE-AGT-045` verandert NIET van categorie: die rij heeft een verhaal van duizenden tekens in
de padkolom (de naamkolom is doorgelopen) en is dus geen pad-token. Zie
`test_a_prose_cell_with_a_trailing_path_is_not_extern`.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# scripts/ is not a package (no __init__.py), so load it directly by file path.
_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location(
    "validate_feature_docs_extern",
    _SCRIPTS_DIR / "validate_feature_docs.py",
)
assert _SPEC is not None, "Could not locate validate_feature_docs.py"
assert _SPEC.loader is not None, "Module spec has no loader"
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["validate_feature_docs_extern"] = _MOD
_SPEC.loader.exec_module(_MOD)

_SPEC_BODY = """# BE-TST-901 -- proefspec

## Trainingssamenvatting

- Actor: tester
- Voorwaarde: de poort leest dit bestand
- Actie: check_entry aanroepen
"""

_APPROVED_REVIEW = "STATUS: APPROVED\n\nEINDOORDEEL: APPROVED\n"
_REJECTED_REVIEW = "STATUS: CHANGES_REQUESTED\n\nEINDOORDEEL: CHANGES_REQUESTED\n"


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """Geef een callable(rows) -> dict[ID, list[poortfouten]] over een NAGEBOUWD register.

    `rows` is een lijst (id, padwaarde). De helper schrijft een register met die rijen, laat
    `parse_registry()` hem lezen en draait `check_entry()` per rij -- dus inclusief de
    padclassificatie, niet alleen `check_entry` op een handgemaakt dict.
    """
    root = tmp_path
    features = root / "docs" / "backend" / "features"
    reviews = root / "docs" / "backend" / "review"
    adr = root / "docs" / "adr"
    for directory in (features, reviews, adr):
        directory.mkdir(parents=True)
    (adr / "031-addendum.md").write_text("# ADR-addendum\n", encoding="utf-8")
    (features / "BE-TST-901-proef.md").write_text(_SPEC_BODY, encoding="utf-8")

    registry_path = features / "ID-REGISTRY.md"
    conf = dict(_MOD.CONFIG["BE"])
    conf["registry"] = registry_path
    conf["features_dir"] = features
    conf["reviews_dir"] = reviews
    monkeypatch.setattr(_MOD, "ROOT", root)
    monkeypatch.setitem(_MOD.CONFIG, "BE", conf)

    def _run(rows: list[tuple[str, str]]) -> dict[str, list[str]]:
        regels = [
            "## Geregistreerde IDs",
            "",
            "| ID | Naam | Bestand | Sprint | Datum |",
            "| --- | --- | --- | --- | --- |",
        ]
        regels += [f"| {rid} | naam | {pad} | proef | 2026-09-01 |" for rid, pad in rows]
        registry_path.write_text("\n".join(regels) + "\n", encoding="utf-8")
        return {e["id"]: _MOD.check_entry(e) for e in _MOD.parse_registry("BE")}

    mappen = {"root": root, "features": features, "reviews": reviews}
    _run.dirs = mappen  # type: ignore[attr-defined]
    return _run


@pytest.mark.unit
def test_a_row_pointing_outside_features_to_a_missing_file_fails_the_gate(gate) -> None:
    """Mutatierichting 1: een EXTERN pad dat NIET bestaat MOET de poort rood maken.

    Dit is de reden dat de fix geen stille `continue` is. Zonder deze eis kon een
    registerrij naar een willekeurig, niet-bestaand pad buiten `features/` wijzen en toch
    passeren -- en dan bewaakt de poort die rij helemaal niet meer.
    """
    fouten = gate([("BE-TST-902", "docs/adr/bestaat-niet.md")])["BE-TST-902"]
    assert any("MISSING EXTERN FILE" in f for f in fouten), (
        f"Een EXTERN pad naar een niet-bestaand bestand passeerde de poort: {fouten!r}"
    )


@pytest.mark.unit
def test_a_row_pointing_outside_features_to_an_existing_file_passes(gate) -> None:
    """Mutatierichting 2: de vorm van de echte BE-AGT-062-rij MOET passeren.

    Zonder deze helft is "weiger elke rij die buiten features/ wijst" een geldige oplossing,
    en dan staat de poort nog steeds rood op precies het geval dat hij moet accommoderen.
    Er is bewust GEEN reviewbestand en GEEN Trainingssamenvatting: dat zijn de twee eisen die
    voor een ADR-addendum niet gelden.
    """
    assert gate([("BE-TST-903", "docs/adr/031-addendum.md")])["BE-TST-903"] == []


@pytest.mark.unit
def test_a_row_pointing_into_features_is_still_checked_in_full(gate) -> None:
    """Het oude gedrag blijft: een echte feature-spec wordt volledig getoetst.

    Spec bestaat, Trainingssamenvatting staat erin, maar er is GEEN review -- dus de poort
    hoort te falen op de review-eis. Deze test valt om zodra `extern_target` te ruim wordt en
    ook rijen BINNEN `features/` als extern bestempelt.
    """
    fouten = gate([("BE-TST-901", "docs/backend/features/BE-TST-901-proef.md")])["BE-TST-901"]
    assert any("MISSING REVIEW" in f for f in fouten), (
        f"Een gewone feature-spec-rij werd niet meer volledig getoetst: {fouten!r}"
    )


@pytest.mark.unit
def test_a_row_inside_features_without_a_training_summary_still_fails(gate) -> None:
    """Tweede helft van het oude gedrag: de Trainingssamenvatting-eis blijft staan."""
    features = gate.dirs["features"]
    (features / "BE-TST-904-kaal.md").write_text("# kaal, geen kopjes\n", encoding="utf-8")
    (gate.dirs["reviews"] / "review-BE-TST-904.md").write_text(_APPROVED_REVIEW, encoding="utf-8")
    fouten = gate([("BE-TST-904", "docs/backend/features/BE-TST-904-kaal.md")])["BE-TST-904"]
    assert any("Trainingssamenvatting" in f for f in fouten), (
        f"Een spec zonder Trainingssamenvatting passeerde: {fouten!r}"
    )


@pytest.mark.unit
def test_an_extern_row_with_a_rejected_review_still_fails(gate) -> None:
    """Een EXTERN rij hoeft geen review, maar een AFWIJZENDE review mag niet verdwijnen.

    Dit is de ratchet die de reviewcontrole op BE-RTR-037/038/039 overeind houdt nu die rijen
    van `[OK]` naar `[EXTERN]` gaan. Zonder deze eis zou een rij zijn eigen, afwijzende
    review onzichtbaar maken door buiten `features/` te gaan wijzen.
    """
    (gate.dirs["reviews"] / "review-BE-TST-905.md").write_text(_REJECTED_REVIEW, encoding="utf-8")
    fouten = gate([("BE-TST-905", "docs/adr/031-addendum.md")])["BE-TST-905"]
    assert any("NOT APPROVED" in f or "STATUS UNCLEAR" in f for f in fouten), (
        f"Een afwijzende review op een EXTERN rij werd genegeerd: {fouten!r}"
    )


@pytest.mark.unit
def test_an_extern_row_with_an_approved_review_passes(gate) -> None:
    """De andere kant van de ratchet: een goedgekeurde review mag niet blijven hangen."""
    (gate.dirs["reviews"] / "review-BE-TST-906.md").write_text(_APPROVED_REVIEW, encoding="utf-8")
    assert gate([("BE-TST-906", "docs/adr/031-addendum.md")])["BE-TST-906"] == []


@pytest.mark.unit
def test_a_prose_cell_with_a_trailing_path_is_not_extern(gate) -> None:
    """De BE-AGT-045-vorm: proza met een pad aan het eind blijft de basisnaam-route volgen.

    Die rij heeft duizenden tekens in de padkolom omdat de naamkolom is doorgelopen. Zou de
    classificatie op "bevat een /" gaan in plaats van "is EEN pad-token", dan werd die rij
    EXTERN met een niet-bestaand "pad" en zou hij vandaag omvallen -- terwijl hij vandaag
    gewoon zijn specbestand vindt.
    """
    cel = "Lang verhaal met uitleg -- docs/backend/features/BE-TST-901-proef.md"
    assert _MOD.extern_target("BE", cel) is None
    fouten = gate([("BE-TST-907", cel)])["BE-TST-907"]
    assert any("MISSING REVIEW" in f for f in fouten), (
        f"De proza-vorm werd niet meer als gewone spec-rij behandeld: {fouten!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "cel",
    [
        "docs/backend/features/BE-TST-901-proef.md",
        "BE-TST-901-proef.md",
    ],
)
def test_extern_target_returns_none_for_rows_inside_features(cel: str) -> None:
    """Een pad IN de features-map en een kale basisnaam zijn allebei geen EXTERN."""
    assert _MOD.extern_target("BE", cel) is None


@pytest.mark.unit
def test_extern_target_normalizes_backslashes() -> None:
    """Windows-scheidingstekens mogen de classificatie niet omdraaien.

    Zonder normalisatie zou `docs\\backend\\features\\X.md` als EXTERN gelden (geen
    forward-slash-prefixmatch) en daarmee de volledige toetsing van een echte spec omzeilen.
    """
    assert _MOD.extern_target("BE", "docs\\backend\\features\\X.md") is None
    assert _MOD.extern_target("BE", "docs\\adr\\X.md") == "docs/adr/X.md"


#: De rijen in het ECHTE register die buiten hun features-map wijzen, gemeten 2026-09-01.
#: Bewust een expliciet benoemde verzameling met een regel per element: de guard-regel in
#: .claude/rules/quality-gates.md eist dat, omdat "muteer wat hij bewaakt" anders niet
#: afdwingt dat je opschrijft WAT hij bewaakt.
_BRIEF = "docs/agent-briefs/generated/2026-06-22-final-approver-SP-API-011-backlog"
BEKENDE_EXTERNE_RIJEN = {
    "BE-AGT-062": "docs/adr/031-addendum-fase5-autonomy-ladder-scope.md",
    # BE-OPS-001 (2026-09-24): portal-CI spec staat in docs/backend/specs/ i.p.v.
    # features/ -- handmatig geverifieerd: het bestand bestaat en de review
    # (docs/backend/review/review-BE-OPS-portal-ci.md) staat op APPROVED WITH MINOR GAPS.
    "BE-OPS-001": "docs/backend/specs/spec-BE-OPS-portal-ci.md",
    "BE-RTR-037": f"{_BRIEF}-dag1.md",
    "BE-RTR-038": f"{_BRIEF}-dag2.md",
    "BE-RTR-039": f"{_BRIEF}-dag3.md",
}


@pytest.mark.unit
def test_the_real_registry_extern_rows_all_resolve() -> None:
    """Over het ECHTE register: elke EXTERN-rij wijst een bestaand bestand aan.

    Bewust niet over verzonnen invoer. Faalt zodra iemand een registerrij toevoegt die buiten
    `features/` wijst naar iets dat er niet is, en zodra een van deze vier bestanden
    verdwijnt of verplaatst.
    """
    gevonden = {e["id"]: e["extern"] for e in _MOD.parse_registry("BE") if e["extern"] is not None}
    assert gevonden == BEKENDE_EXTERNE_RIJEN, (
        "De verzameling EXTERN-rijen in het register is gewijzigd. Werk "
        f"BEKENDE_EXTERNE_RIJEN bij en controleer elke nieuwe rij handmatig. Gevonden: "
        f"{gevonden!r}"
    )
    ontbreekt = [pad for pad in gevonden.values() if not (_MOD.ROOT / pad).is_file()]
    assert ontbreekt == [], f"EXTERN-rijen wijzen naar niet-bestaande bestanden: {ontbreekt}"


@pytest.mark.unit
def test_the_real_extern_rows_keep_their_review_check() -> None:
    """De drie BE-RTR-rijen hielden een APPROVED review, en die controle blijft gelden.

    Dit legt het gemeten neveneffect vast: `[OK]` -> `[EXTERN]` mag hun reviewcontrole niet
    kosten. Faalt zodra `_check_extern_entry` de review laat vallen, en zodra een van die
    drie reviews van verdict wisselt.
    """
    reviews_dir = _MOD.CONFIG["BE"]["reviews_dir"]
    for rid in ("BE-RTR-037", "BE-RTR-038", "BE-RTR-039"):
        pad = reviews_dir / f"review-{rid}.md"
        assert pad.is_file(), f"{pad} ontbreekt -- dan bewijst deze test niets"
        status, reden = _MOD.classify_review_status(pad.read_text(encoding="utf-8"))
        assert status == _MOD.REVIEW_STATUS_APPROVED, f"{rid}: {reden}"
        entry = {"id": rid, "prefix": "BE"}
        assert _MOD._check_backend_review(entry, required=False) == []

"""BE-HOOK-001 guard: het docs-pad en de volgordecorrectie in de pre-push hook.

Toetst vier structurele eigenschappen. Elk element is in BEIDE richtingen
mutatie-getest (zie MUTATIEBEWIJS-sectie hieronder).

WAAROM STRUCTUUR EN NIET GEDRAG
---------------------------------
De hook draait pas bij een echte git push; een gedragstest vereist een git-
repo met commits, een goedgekeurd SHA, en geen slot-bezetter. Die opstelling
kost meer dan de elementen die we bewaken -- en het risico van een opstelling
die "groen" zegt zonder iets te meten is groter dan het voordeel. De vier
structuurchecks zijn elk zo gekozen dat ze ALLEEN groen zijn als het juiste
gedrag is aangesloten, niet als de tekst toevallig in een comment staat.

MUTATIEBEWIJS (2026-09-27, beide richtingen, alle vier geslaagd)
----------------------------------------------------------------
Voorwaarts -- element verwijderd/verplaatst, test ROOD:
    DEVELOP_REMOTE_SHA="" (nooit capture)       -> ROOD: bereik_uit_remote_sha
    DOCS_ALLEEN=1 vervangen door true           -> ROOD: docs_detectie_aanwezig
    git grep vervangen door echo (leeg)         -> ROOD: glob_tests_afgeleid
    gate naar na CI-fi verplaatst (2 anchors)   -> ROOD: gate_staat_voor_ci

Achterwaarts -- herstelde hook blijft GROEN op alle vier.

Uitgevoerd met scripts/mutation_harness.py, scratchpad/be_hook_001_mutatiebewijs.py.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "scripts" / "hooks" / "pre-push"


def _uitvoerbare_regels(tekst: str) -> list[tuple[int, str]]:
    """Regelnummers + inhoud van uitvoerbare regels (geen commentaar, geen echo).

    Zelfde conventie als test_de_hooks_draaien_gerichte_tests.py zodat de twee
    guards consistent meten.
    """
    regels = []
    for i, regel in enumerate(tekst.splitlines(), start=1):
        gestript = regel.strip()
        if gestript.startswith("#"):
            continue
        if gestript.startswith(("echo ", "info ", "fail ", "ok ")):
            continue
        regels.append((i, regel))
    return regels


def _positie(regels: list[tuple[int, str]], patroon: str) -> int:
    """Regelnummer van de EERSTE uitvoerbare regel die het patroon bevat.

    Geeft -1 als het patroon nergens voorkomt -- dan faalt de aanroeper expliciet.
    """
    for num, tekst in regels:
        if patroon in tekst:
            return num
    return -1


def test_bereik_uit_remote_sha() -> None:
    """DEVELOP_REMOTE_SHA wordt gelezen uit de git stdin-stroom.

    Dit is de variabele die het push-bereik verankert aan de remote-SHA. Zonder
    hem wordt PUSH_BEREIK leeg of onjuist en kiest de hook altijd de volledige
    poort -- ook voor pure docs-pushes.
    """
    tekst = HOOK.read_text(encoding="utf-8")
    uitvoerbaar = "\n".join(r for _, r in _uitvoerbare_regels(tekst))

    assert 'DEVELOP_REMOTE_SHA="$remote_sha"' in uitvoerbaar, (
        "DEVELOP_REMOTE_SHA wordt niet toegewezen vanuit de git stdin-stroom; "
        "het bereik van een develop-push kan dan niet worden berekend en de "
        "docs-poort wordt nooit gekozen (BE-HOOK-001)"
    )


def test_docs_detectie_aanwezig() -> None:
    """DOCS_ALLEEN=1 wordt gezet op basis van de docs-grep.

    De grep telt niet-documentbestanden; is die telling nul dan zijn alle bestanden
    docs. Zonder deze toewijzing kiest de hook altijd de volledige poort.
    """
    tekst = HOOK.read_text(encoding="utf-8")
    uitvoerbaar = "\n".join(r for _, r in _uitvoerbare_regels(tekst))

    assert "DOCS_ALLEEN=1" in uitvoerbaar, (
        "DOCS_ALLEEN=1 staat nergens in uitvoerbare regels van de hook; "
        "het docs-pad wordt dan nooit betreden (BE-HOOK-001)"
    )
    # De detectie moet via grep -cvE draaien, niet via een hardgecodeerde lijst.
    assert "grep -cvE" in uitvoerbaar, (
        "de docs-detectie mist grep -cvE; dan is er geen patroon dat niet-docs "
        "bestanden onderscheidt van docs-bestanden (BE-HOOK-001)"
    )


def test_glob_tests_afgeleid() -> None:
    """GLOB_TESTS wordt op aanroeptijd afgeleid via git grep, niet hardgecodeerd.

    Een nieuwe globtest (een zesde) moet automatisch meegaan in de docs-poort
    zonder dat de hook wordt bijgewerkt. Dat kan alleen als de lijst bij elke
    aanroep opnieuw wordt afgeleid -- niet als hij letterlijk in de hook staat.
    """
    tekst = HOOK.read_text(encoding="utf-8")
    uitvoerbaar = "\n".join(r for _, r in _uitvoerbare_regels(tekst))

    # De afleiding moet VIA git grep zijn, niet een statische lijst.
    assert "git grep" in uitvoerbaar, (
        "GLOB_TESTS is niet afgeleid via git grep; een nieuwe globtest in tests/ "
        "zou dan niet automatisch meegaan in de docs-poort (BE-HOOK-001)"
    )
    # En de zoekterm moet het glob-patroon zijn (rglob of glob op *.md).
    assert r'rglob\("' in uitvoerbaar or r'glob\("' in uitvoerbaar, (
        "de git grep-aanroep bevat het globtest-patroon niet (rglob of glob op *.md); "
        "dan worden andere tests opgepikt die geen docs globben (BE-HOOK-001)"
    )


def test_gate_staat_voor_ci() -> None:
    """De push_gate check staat voor ci-local-fast.sh.

    Volgorde-eis BE-HOOK-001 Fix 1: wie geen goedkeuring heeft, wacht niet 39
    seconden voor niets. De gate-check kost milliseconden; ci-local-fast 39 seconden.
    """
    tekst = HOOK.read_text(encoding="utf-8")
    regels = _uitvoerbare_regels(tekst)

    # De gate-aanroep gebruikt de variabele $PUSH_GATE, niet de letterlijke bestandsnaam;
    # patroon: '"$PUSH_GATE" check' (de variabelenaam in aanhalingstekens + het subcommando).
    gate_regel = _positie(regels, '"$PUSH_GATE" check')
    # De CI-aanroep: bash "$CI_SCRIPT" -- ook via variabele; niet de declaratie CI_SCRIPT=...
    ci_regel = _positie(regels, 'bash "$CI_SCRIPT"')

    assert gate_regel != -1, (
        '"$PUSH_GATE" check is niet meer aanwezig in een uitvoerbare regel van de hook; '
        "de goedkeuringscontrole is dan weggevallen (BE-HOOK-001 Fix 1)"
    )
    assert ci_regel != -1, (
        'bash "$CI_SCRIPT" is niet meer aanwezig in een uitvoerbare regel van de hook'
    )
    assert gate_regel < ci_regel, (
        f'"$PUSH_GATE" check staat op regel {gate_regel} maar bash "$CI_SCRIPT" op '
        f"{ci_regel}; de gate staat ACHTER de 39-seconden CI-stap in plaats van "
        "ervoor -- een push zonder goedkeuring wacht dan onnodig lang (BE-HOOK-001 Fix 1)"
    )

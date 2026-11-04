"""Levende documentatie mag geen infrastructuur beschrijven die niet bestaat (ADR-036 OP-116).

**De bevinding, gemeten 2026-08-29 bij de hermeting van alle open punten.**

De resourcegroep `sanskritisetu-prod` is op 2026-05-11 verwijderd en nooit herbouwd
(`docs/AZURE_TEARDOWN_2026_05_11.md`). Toch beschreven VIER SOC 2-documenten hem als een
draaiende productie-omgeving -- niet twee, zoals de registerregel vermeldde -- met
`az`-commando's die een auditor of een nieuwe beheerder zo kan overtypen. Daarnaast stond
dezelfde omgevingstabel in zes bestanden, wat betekent dat een correctie op vijf plekken
vergeten kan worden.

Het register noteerde "geen guard". Dat klopte voor documentatie: de bestaande
`test_cd_workflows_have_no_hardcoded_infra.py` scant CI/CD-workflows en raakt `docs/` niet.

**Wat deze guard eist.** Elk LEVEND operationeel document dat de productie-resourcegroep bij
naam noemt, moet ergens in datzelfde bestand de tekst `NIET INGERICHT` dragen. Niet per regel --
dat zou elke tabelrij onleesbaar maken -- maar per bestand: wie het document opent, moet de
status kunnen zien zonder een ander bestand te openen.

**Wat bewust BUITEN de scan valt en waarom.** Historische vastleggingen beschrijven wat toen
waar was en horen niet herschreven te worden: `docs/agent-briefs/`, `docs/superpowers/`,
`docs/build-stack-security/`, `docs/reports/`, `docs/adr/` en het teardown-verslag zelf. De
scan raakt alleen documentatie waarnaar iemand vandaag handelt.

**Mutatietest (2026-08-30, beide richtingen):**
- Banner uit `docs/runbooks/deployment-rollback.md` gehaald -> ROOD, met dat bestand in de
  melding.
- Banner teruggezet -> GROEN.
- Scanlijst leeggemaakt -> ROOD op `test_the_scan_finds_the_live_documents` (vacuiteit).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

#: `sanskritisetu-prod` als zelfstandige naam. De negatieve lookahead houdt afgeleide namen
#: buiten de scan (`sanskritisetu-prod-env`, `-logs`, `-db`): dat zijn andere resources, en
#: hun bestaan zegt niets over de resourcegroep.
_PROD_RG = re.compile(r"sanskritisetu-prod(?![\w-])")

#: De tekst die de status van de productie-omgeving eerlijk maakt.
_MARKER = "NIET INGERICHT"

_REPO = Path(__file__).resolve().parents[2]

#: Mappen met levende operationele documentatie: hier handelt iemand vandaag naar.
_LEVENDE_MAPPEN = (
    "docs/compliance",
    "docs/runbooks",
    "docs/guides",
    "docs/deployment",
    "docs/user-guide",
    "docs/infra",
)

#: Losse bestanden die dezelfde rol hebben.
_LEVENDE_BESTANDEN = (
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    "docs/CICD_PIPELINE_VOLLEDIG.md",
    "docs/DEPLOYMENT_GUIDE.md",
)

#: Treffers die geen Azure-resourcegroep zijn, met datum en reden per regel.
#:
#: **Alleen bestanden die in git staan.** De eerste versie noemde hier ook
#: `docs/deployment/MULTI_NODE_DEPLOYMENT_GUIDE.md`, een bestand dat wel in de werkkopie
#: stond maar niet was gecommit -- lokaal groen, in CI rood. De scan gaat sindsdien via
#: `git ls-files`, dus dat kan niet meer.
KNOWN_GEEN_AZURE_GROEP: dict[str, str] = {
    "docs/DEPLOYMENT_GUIDE.md": (
        "2026-08-30: `S3_BUCKET=sanskritisetu-prod` en `docker network create "
        "sanskritisetu-prod` -- een bucketnaam en een Docker-netwerknaam, geen Azure-groep."
    ),
}


def _gevolgde_bestanden() -> set[str]:
    """De bestanden die IN GIT staan, als repo-relatieve posix-paden.

    **Waarom via git en niet via de werkkopie (gemeten 2026-08-30).** De eerste versie liep
    met `rglob` over de schijf. Lokaal stond daar een ongecommit document tussen dat
    `sanskritisetu-prod` noemt; in CI bestaat dat bestand niet. Gevolg: de guard gaf op
    dezelfde commit een ander antwoord op twee machines -- en dat is precies het soort
    verschil waar deze reeks guards voor bestaat. Wat niet in git staat, is geen
    documentatie van dit project.
    """
    uitvoer = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return {deel for deel in uitvoer.stdout.split("\0") if deel}


def _levende_documenten() -> list[Path]:
    gevolgd = _gevolgde_bestanden()
    paden: list[Path] = []
    for map_naam in _LEVENDE_MAPPEN:
        paden.extend(
            _REPO / relatief
            for relatief in sorted(gevolgd)
            if relatief.startswith(f"{map_naam}/")
        )
    for bestand in _LEVENDE_BESTANDEN:
        if bestand in gevolgd:
            paden.append(_REPO / bestand)
    return paden


def test_the_scan_finds_the_live_documents() -> None:
    """Vangnet op een EXPLICIETE verzameling, niet op "de lijst is niet leeg"."""
    gevonden = {p.relative_to(_REPO).as_posix() for p in _levende_documenten()}
    verwacht = {
        "docs/infra/AZURE_OMGEVINGEN.md",
        "docs/runbooks/deployment-rollback.md",
        "docs/compliance/soc2/incident-response-plan.md",
        "CLAUDE.md",
    }
    ontbreekt = sorted(verwacht - gevonden)

    assert not ontbreekt, (
        f"Deze documenten worden niet gescand: {ontbreekt}. Gevonden: {len(gevonden)} "
        "bestanden. Een hernoemde map laat de guard anders stil leeglopen."
    )


def test_live_docs_naming_production_say_it_is_not_provisioned() -> None:
    """Wie de productiegroep noemt, noemt in hetzelfde bestand ook dat hij niet bestaat."""
    overtreders: list[str] = []
    for pad in _levende_documenten():
        relatief = pad.relative_to(_REPO).as_posix()
        if relatief in KNOWN_GEEN_AZURE_GROEP:
            continue
        tekst = pad.read_text(encoding="utf-8", errors="replace")
        if not _PROD_RG.search(tekst):
            continue
        if _MARKER not in tekst:
            aantal = len(_PROD_RG.findall(tekst))
            overtreders.append(f"{relatief} ({aantal}x)")

    assert not overtreders, (
        "Deze levende documenten noemen `sanskritisetu-prod` zonder erbij te zetten dat die "
        "resourcegroep niet bestaat:\n  " + "\n  ".join(overtreders) + "\n\n"
        f"Zet de tekst {_MARKER!r} in het document (een korte banner onder de titel volstaat) "
        "en verwijs naar docs/infra/AZURE_OMGEVINGEN.md. De groep is op 2026-05-11 verwijderd "
        "en nooit herbouwd -- zie docs/AZURE_TEARDOWN_2026_05_11.md (ADR-036 OP-116)."
    )


def test_the_known_exceptions_are_still_needed() -> None:
    """Een uitzondering die niets meer uitzondert hoort weg (staleness)."""
    verlopen: list[str] = []
    for relatief in KNOWN_GEEN_AZURE_GROEP:
        pad = _REPO / relatief
        if not pad.exists():
            verlopen.append(f"{relatief}: bestand bestaat niet meer")
            continue
        if not _PROD_RG.search(pad.read_text(encoding="utf-8", errors="replace")):
            verlopen.append(f"{relatief}: geen treffer meer")

    assert not verlopen, (
        "Deze uitzonderingen in KNOWN_GEEN_AZURE_GROEP zijn niet meer nodig:\n  "
        + "\n  ".join(verlopen)
        + "\n\nHaal ze weg, anders dekt de lijst iets af wat niet meer bestaat."
    )


def test_the_single_source_exists_and_states_the_status() -> None:
    """De enige bron moet bestaan en de status van beide omgevingen noemen."""
    bron = _REPO / "docs/infra/AZURE_OMGEVINGEN.md"

    assert bron.exists(), (
        "docs/infra/AZURE_OMGEVINGEN.md ontbreekt. Dat is de enige plek waar de "
        "Azure-omgevingen worden beschreven; zonder dat bestand verwijzen alle andere "
        "documenten naar niets (ADR-036 OP-116)."
    )
    tekst = bron.read_text(encoding="utf-8")
    for verplicht in (_MARKER, "sanskritisetu-staging", "sanskritisetu-prod"):
        assert verplicht in tekst, (
            f"{verplicht!r} ontbreekt in docs/infra/AZURE_OMGEVINGEN.md. De bron moet beide "
            "omgevingen noemen EN de status van productie, anders is hij geen bron."
        )

"""Geen hardgecodeerde Azure-resourcegroep, en geen secrets in een workflow-`env:` (OP-111).

**Twee bevindingen, allebei gemeten 2026-08-10.**

**1. `cd-production.yml` codeerde de resourcegroep hard** (`PROD_RG: sanskritisetu-prod`), met een
comment die de asymmetrie zelf toegaf: staging gebruikt `secrets.STAGING_RESOURCE_GROUP`. Die
groep BESTAAT niet -- `docs/AZURE_TEARDOWN_2026_05_11.md` legt vast dat beide resourcegroepen en
de container registry op 2026-05-11 zijn verwijderd. `rollback.yml` had een tweede, losse
hardcode. Het secret `PROD_RESOURCE_GROUP` stond al in de beheerhandleiding en werd nergens
gebruikt.

De ADR-regel voor OP-111 zei aanvankelijk "bewust GEEN guard: er is geen repo-artefact om op te
toetsen". Dat klopt voor Redis en NIET voor de resourcegroep -- `cd-production.yml` is een
repo-artefact. Die regel is gecorrigeerd.

**2. De `secrets`-context bestaat niet in een workflow-brede `env:`.** Dit is de val waar ik
zelf bijna in liep: mijn eerste opzet zette `PROD_RG: ${{ secrets.PROD_RESOURCE_GROUP }}` in het
workflow-`env:`. Daar levert dat STIL een lege string op, en `--resource-group ""` wordt pas
achttien stappen verderop zichtbaar -- na drie Docker-builds. Op JOB- en STAP-niveau werkt de
context wel.

Gemeten voor deze guard is geschreven: geen enkele workflow in de repo deed dit. Dat is precies
het moment om het vast te leggen -- niet nadat iemand er een halve deploy op stukloopt.

**Mutatietest (2026-08-10, beide richtingen):**
- `PROD_RG: sanskritisetu-prod` teruggezet -> ROOD op de hardcode-guard.
- `${{ secrets.X }}` in het workflow-brede `env:` gezet -> ROOD op de context-guard.
- LEGITIEM: een secret in een JOB-`env:` -> GROEN.
- LEGITIEM: een niet-geheime waarde in het workflow-`env:` (`ACR`, `KV_PROD`) -> GROEN.
"""

from __future__ import annotations

import re

import yaml

from tests.architecture._ci_workflow import CD_GLOB, WORKFLOW_DIR

#: Resourcegroepnamen die als letterlijke tekst in een workflow niet thuishoren.
_RG_PATROON = re.compile(r"sanskritisetu-(?:prod|staging)\b")

#: Bestandsnamen die meedoen. Ruimer dan `CD_GLOB`: `rollback.yml` deployt ook naar Azure en
#: had zijn eigen hardcode.
_EXTRA_WORKFLOWS = ("rollback.yml",)

#: Plekken waar een letterlijke groepsnaam legitiem is, met datum en reden per regel.
KNOWN_LITERAL_RESOURCE_GROUPS: dict[str, str] = {}


def _workflows() -> list:
    paden = sorted(WORKFLOW_DIR.glob(CD_GLOB))
    for naam in _EXTRA_WORKFLOWS:
        pad = WORKFLOW_DIR / naam
        if pad.exists():
            paden.append(pad)
    return paden


def test_the_scan_finds_the_workflows() -> None:
    """Vangnet op een EXPLICIETE verzameling, niet op "de lijst is niet leeg"."""
    namen = {p.name for p in _workflows()}
    ontbreekt = sorted({"cd-production.yml", "cd-staging.yml", "rollback.yml"} - namen)

    assert not ontbreekt, (
        f"Deze workflows worden niet gescand: {ontbreekt}. Gevonden: {sorted(namen)}. Een "
        "hernoemd bestand valt anders stil buiten de guard."
    )


def test_no_hardcoded_resource_group() -> None:
    """De resourcegroep komt uit een secret, niet uit de broncode."""
    overtreders: list[str] = []
    for pad in _workflows():
        for nummer, regel in enumerate(pad.read_text(encoding="utf-8").splitlines(), start=1):
            zonder_comment = regel.split("#", 1)[0]
            if _RG_PATROON.search(zonder_comment):
                sleutel = f"{pad.name}:{nummer}"
                if sleutel not in KNOWN_LITERAL_RESOURCE_GROUPS:
                    overtreders.append(f"{sleutel}: {regel.strip()}")

    assert not overtreders, (
        "Deze regels coderen een Azure-resourcegroep hard:\n  " + "\n  ".join(overtreders) + "\n\n"
        "Gebruik `${{ secrets.PROD_RESOURCE_GROUP }}` respectievelijk "
        "`${{ secrets.STAGING_RESOURCE_GROUP }}`. Een hardgecodeerde groep is niet te wijzigen "
        "zonder codewijziging, en `sanskritisetu-prod` bestaat vandaag niet eens -- zie "
        "docs/AZURE_TEARDOWN_2026_05_11.md (ADR-036 OP-111)."
    )


def test_no_secrets_context_in_workflow_level_env() -> None:
    """De `secrets`-context bestaat niet op workflow-niveau -- daar wordt het een lege string.

    Dit is geen theoretisch risico. Het is de fout die ik bij het opstellen van OP-111 zelf
    bijna heb gemaakt: `PROD_RG: ${{ secrets.PROD_RESOURCE_GROUP }}` in het workflow-brede
    `env:`. GitHub vult daar niets in, `az ... --resource-group ""` faalt pas achttien stappen
    verderop, en de drie Docker-builds zijn dan al gedraaid.
    """
    overtreders: list[str] = []
    for pad in _workflows():
        geparsed = yaml.safe_load(pad.read_text(encoding="utf-8")) or {}
        for naam, waarde in (geparsed.get("env") or {}).items():
            if "secrets." in str(waarde):
                overtreders.append(f"{pad.name}: env.{naam} = {waarde}")

    assert not overtreders, (
        "Deze workflow-brede `env:`-waarden gebruiken de `secrets`-context:\n  "
        + "\n  ".join(overtreders)
        + "\n\nDaar is die context NIET beschikbaar; de variabele wordt stil een lege string. "
        "Zet hem in het `env:`-blok van de JOB die hem nodig heeft -- daar werkt hij wel "
        "(ADR-036 OP-111)."
    )


def test_known_literal_resource_groups_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET eruit."""
    nog_aanwezig: set[str] = set()
    for pad in _workflows():
        for nummer, regel in enumerate(pad.read_text(encoding="utf-8").splitlines(), start=1):
            if _RG_PATROON.search(regel.split("#", 1)[0]):
                nog_aanwezig.add(f"{pad.name}:{nummer}")

    opgelost = sorted(set(KNOWN_LITERAL_RESOURCE_GROUPS) - nog_aanwezig)
    assert not opgelost, (
        f"Deze regels staan in KNOWN_LITERAL_RESOURCE_GROUPS maar bevatten geen letterlijke "
        f"groepsnaam meer: {opgelost}. Haal ze uit de lijst."
    )

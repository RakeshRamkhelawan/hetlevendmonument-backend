#!/usr/bin/env python3
"""
Controle op de instructielaag: wijst alles nog naar iets dat bestaat en waar is?

Waarom dit bestaat (gemeten 2026-09-27, alles met de hand gevonden):

  - 12 van de 15 skills werden nergens in CLAUDE.md genoemd
  - 10 van de 18 briefsjablonen stonden niet in hun eigen README
  - `quality-reviewer` stond in tien instructiebestanden als verplichte helft van
    Gate 2, terwijl de agentdefinitie in de hele geschiedenis van de repo nooit
    had bestaan. Elke "beiden GO" daarvoor was dus leeg.
  - `.claude/rules/frontend.md` verwijst naar vier regels die "al in CLAUDE.md
    staan" en die nergens in de repo voorkomen
  - `/type-hardening` werd als aanroepbare skill genoemd terwijl er geen SKILL.md is

Het patroon is niet dat er te weinig is. Het is dat wat er is, nergens naar
wijst -- en dat wat er wijst, niet meer klopt.

Gebruik:
    python scripts/check_instructielaag.py            # alle controles
    python scripts/check_instructielaag.py --quiet    # alleen de uitslag

Exitcode 0 = schoon, 1 = er is minstens een defect.

Mutatiebewijs (2026-09-27, beide richtingen, een mutatie per bewaakt element).
Uitgevoerd met een wegwerpbestand `.claude/rules/ZZZ-mutatietest.md` en een
wegwerpmap `.claude/skills/zzz-mutatietest/`, zodat geen bestaand werk is geraakt.

  VOORWAARTS -- elk van de zes controles is rood gekregen:
    1  verwijzing naar `docs/dit-bestaat-echt-niet-xyz.md`   -> betrapt
    2  aanroep `/deze-skill-bestaat-niet`                    -> betrapt
    3  skill zonder vermelding in CLAUDE.md                  -> betrapt
    4  briefsjabloon niet in de README                       -> betrapt (10 bestaande)
    5  agent `verzonnen-reviewer`                            -> betrapt
    6  "`zzz-onvindbare-term` staat al in CLAUDE.md"         -> betrapt
    Telling ging van 16 naar 20 defecten: precies de vier toegevoegde.

  ACHTERWAARTS -- deze legitieme gevallen gaven GEEN defect, anders was de
  telling op 24 uitgekomen in plaats van 20:
    - een kale bestandsnaam in lopende tekst (`auto-test.sh`)
    - een sjabloon-plaatshouder (`...generated/YYYY-MM-DD-iets.md`)
    - een pad dat dieper in de boom staat (`tenants/router.py`)
    - een ingebouwd commando van Claude Code (`/clear`)

  TERUGWEG: na verwijderen van beide wegwerp-artefacten weer 16 defecten, en
  `git status .claude/` toonde geen residu van de test.

Twee fouten die deze controle zelf had en die het mutatiebewijs vond:
  - `pad.lstrip("./")` strookte ALLE leidende punten weg, dus `.claude/SOUL.md`
    werd `claude/SOUL.md` en leek te ontbreken: 57 valse alarmen.
  - De eerste run liep door een pijp naar `head`, waardoor de exitcode 0 leek
    terwijl er 24 defecten waren. Dat is valkuil "tb_line_en_tail_gooien_het
    _bewijs_weg" uit het eigen register.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# De bestanden die samen de instructielaag vormen.
INSTRUCTIELAAG = [
    "CLAUDE.md",
    ".claude/SOUL.md",
    ".claude/WORKING-CONTEXT.md",
]
INSTRUCTIE_GLOBS = [
    ".claude/rules/*.md",
    ".claude/agents/*.md",
    "docs/agent-briefs/*.md",
]

# Paden die als kale bestandsnaam in lopende tekst staan en geen verwijzing zijn.
# Een pad telt alleen als verwijzing wanneer er een "/" in staat.
PAD_PATROON = re.compile(
    r"`([a-zA-Z0-9_./-]*/[a-zA-Z0-9_.-]+\.(?:md|py|sh|json|yml|yaml|ini|ts|tsx))`"
)

# Aanroepen: `/naam` in backticks.
AANROEP_PATROON = re.compile(r"`/([a-z][a-z0-9-]{2,})`")

# Zinnen die beweren dat iets elders staat, met de termen die er dan moeten staan.
STAAT_ELDERS_NL = re.compile(
    r"([^.\n]{5,200}?)\s+sta(?:at|an)\s+al\s+in\s+`?([A-Za-z0-9_./-]+\.md)`?",
)


def instructiebestanden() -> list[Path]:
    """Alle bestanden die samen de instructielaag vormen."""
    gevonden: list[Path] = []
    for naam in INSTRUCTIELAAG:
        p = REPO / naam
        if p.is_file():
            gevonden.append(p)
    for patroon in INSTRUCTIE_GLOBS:
        gevonden.extend(sorted(REPO.glob(patroon)))
    return gevonden


def lees(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def bestaat_in_repo(naam: str) -> str | None:
    """Zoek een kale bestandsnaam via git; geeft het pad terug of None."""
    try:
        uit = subprocess.run(
            ["git", "ls-files", f"**/{naam}"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    eerste = uit.stdout.strip().splitlines()
    return eerste[0] if eerste else None


def bestaat_als_suffix(pad: str) -> bool:
    """Bestaat dit pad ergens dieper in de boom? (`tenants/router.py`)"""
    try:
        uit = subprocess.run(
            ["git", "ls-files", f"*{pad}"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return bool(uit.stdout.strip())


def controle_1_dode_paden() -> list[str]:
    """Elk pad dat de instructielaag noemt, moet bestaan."""
    defecten: list[str] = []
    for bestand in instructiebestanden():
        for pad in sorted(set(PAD_PATROON.findall(lees(bestand)))):
            schoon = pad[2:] if pad.startswith("./") else pad
            if (REPO / schoon).exists():
                continue
            # Een glob of een sjabloon-plaatshouder is geen verwijzing.
            if "*" in pad or "<" in pad or "YYYY" in pad or "NNN" in pad:
                continue
            # Een pad kan relatief binnen de boom staan (`tenants/router.py`).
            if bestaat_als_suffix(schoon):
                continue
            defecten.append(f"{rel(bestand)}: verwijst naar `{pad}` -- bestaat niet")
    return defecten


def werkende_skills() -> set[str]:
    """Skills met een SKILL.md die met frontmatter begint."""
    werkend: set[str] = set()
    for skill_md in sorted(REPO.glob(".claude/skills/*/SKILL.md")):
        regels = lees(skill_md).splitlines()
        if regels and regels[0].strip() == "---":
            werkend.add(skill_md.parent.name)
    return werkend


def werkende_commands() -> set[str]:
    return {p.stem for p in sorted(REPO.glob(".claude/commands/*.md"))}


def controle_2_dode_aanroepen() -> list[str]:
    """Elke `/naam` moet een aanroepbare skill of een commando zijn."""
    beschikbaar = werkende_skills() | werkende_commands()
    # Ingebouwde commando's van Claude Code zelf zijn geen projectartefact.
    ingebouwd = {
        "clear",
        "compact",
        "resume",
        "branch",
        "context",
        "export",
        "rename",
        "model",
        "effort",
        "config",
        "usage",
        "mcp",
        "hooks",
        "agents",
        "tasks",
        "workflows",
        "insights",
        "loop",
        "help",
        "init",
        "fast",
        "add-dir",
        "permissions",
        "rewind",
        "status",
        "deep-research",
        "batch",
        "subtask",
        "fork",
        "cd",
        "login",
        "logout",
        "doctor",
        "memory",
        "review",
        "pr",
    }
    defecten: list[str] = []
    for bestand in instructiebestanden():
        for naam in sorted(set(AANROEP_PATROON.findall(lees(bestand)))):
            if naam in beschikbaar or naam in ingebouwd:
                continue
            defecten.append(
                f"{rel(bestand)}: noemt `/{naam}` -- geen aanroepbare skill of commando"
            )
    return defecten


def controle_3_onzichtbare_skills() -> list[str]:
    """Elke werkende skill moet in CLAUDE.md genoemd worden."""
    claude = lees(REPO / "CLAUDE.md")
    return [
        f"CLAUDE.md noemt `/{naam}` niet -- de skill bestaat wel en wordt dus nooit gebruikt"
        for naam in sorted(werkende_skills())
        if f"/{naam}" not in claude
    ]


def controle_4_onzichtbare_briefs() -> list[str]:
    """Elk briefsjabloon moet in zijn eigen README staan."""
    readme_pad = REPO / "docs/agent-briefs/README.md"
    if not readme_pad.is_file():
        return ["docs/agent-briefs/README.md ontbreekt"]
    readme = lees(readme_pad)
    defecten: list[str] = []
    for brief in sorted(REPO.glob("docs/agent-briefs/*.md")):
        if brief.name == "README.md":
            continue
        if brief.name not in readme:
            defecten.append(
                f"docs/agent-briefs/README.md noemt {brief.name} niet "
                f"({len(lees(brief).splitlines())} regels onzichtbaar)"
            )
    return defecten


def controle_5_ontbrekende_agents() -> list[str]:
    """Een agent die bij naam als rol genoemd wordt, moet bestaan."""
    bestaand = {p.stem for p in sorted(REPO.glob(".claude/agents/*.md"))}
    # Alleen namen in backticks die eruitzien als een agentnaam.
    patroon = re.compile(
        r"`([a-z][a-z0-9]*-(?:reviewer|designer|approver|runner|guide|hunter|analyzer))`"
    )
    defecten: list[str] = []
    for bestand in instructiebestanden():
        for naam in sorted(set(patroon.findall(lees(bestand)))):
            if naam not in bestaand:
                defecten.append(
                    f"{rel(bestand)}: noemt agent `{naam}` -- .claude/agents/{naam}.md bestaat niet"
                )
    return defecten


def controle_6_valse_verwijzing() -> list[str]:
    """Een bewering dat iets 'al in <bestand>' staat, moet waar zijn."""
    defecten: list[str] = []
    for bestand in instructiebestanden():
        # Een bewering kan over meerdere regels lopen; maak er een doorlopende
        # tekst van, anders mist het patroon de termen op de vorige regel.
        inhoud = re.sub(r"\n>?\s*", " ", lees(bestand))
        for zin, doelnaam in STAAT_ELDERS_NL.findall(inhoud):
            doel = REPO / doelnaam if "/" in doelnaam else REPO / doelnaam
            if not doel.is_file():
                gevonden = bestaat_in_repo(doelnaam)
                if not gevonden:
                    defecten.append(
                        f"{rel(bestand)}: zegt dat iets in {doelnaam} staat -- dat bestaat niet"
                    )
                    continue
                doel = REPO / gevonden
            doelinhoud = lees(doel)
            # De termen uit de zin die in backticks of als los woord genoemd worden.
            termen = re.findall(r"`([^`]{3,40})`", zin)
            for term in termen:
                kern = term.strip("`").split("(")[0].strip()
                if kern and kern.lower() not in doelinhoud.lower():
                    defecten.append(
                        f"{rel(bestand)}: zegt dat `{kern}` al in {doelnaam} staat "
                        f"-- staat daar niet"
                    )
    return defecten


CONTROLES = [
    ("Dode paden", controle_1_dode_paden),
    ("Dode aanroepen", controle_2_dode_aanroepen),
    ("Onzichtbare skills", controle_3_onzichtbare_skills),
    ("Onzichtbare briefsjablonen", controle_4_onzichtbare_briefs),
    ("Genoemde agents die niet bestaan", controle_5_ontbrekende_agents),
    ("Valse 'staat al elders'-verwijzingen", controle_6_valse_verwijzing),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="alleen de uitslag tonen")
    args = parser.parse_args()

    totaal = 0
    for naam, functie in CONTROLES:
        defecten = functie()
        totaal += len(defecten)
        if args.quiet:
            continue
        merk = "OK  " if not defecten else "FOUT"
        print(f"[{merk}] {naam}: {len(defecten)}")
        for d in defecten:
            print(f"       {d}")

    bestanden = len(instructiebestanden())
    print()
    if totaal == 0:
        print(f"SCHOON -- {bestanden} instructiebestanden, geen defecten.")
        return 0
    print(f"{totaal} defect(en) in de instructielaag ({bestanden} bestanden gecontroleerd).")
    return 1


if __name__ == "__main__":
    sys.exit(main())

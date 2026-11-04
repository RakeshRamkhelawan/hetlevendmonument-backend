#!/usr/bin/env python3
"""
Controle op een agent-brief: is dit een opdracht waar iemand mee kan werken?

Waarom dit bestaat, gemeten 2026-09-27:

  18 van de 20 recentste briefs in `docs/agent-briefs/generated/` voldeden niet aan
  hun eigen checklist. De eis is minimaal vijf concrete
  `bestand:regel`-verwijzingen; veertien briefs hadden er nul. Niemand heeft dat ooit
  gemeld, want de checklist wordt door de schrijver zelf afgevinkt -- de zwakste vorm
  van borging die er is.

  De brief is stap 1 van de keten. Een fout hier werkt door in alles wat erna komt.
  Gemeten 2026-09-18: een brief zei "vier tests" omdat de docstring van die test dat
  zei; de uitvoerende sessie mat er acht. De brief had de fout overgenomen.

Wat dit WEL toetst: de mechanische eisen, altijd, zonder oordeel.
Wat dit NIET toetst: of de brief de opdracht dekt. Dat blijft het oordeel van de
regie, en de ontvangende sessie mag een brief alsnog weigeren.

Gebruik:
    python scripts/check_brief.py <pad-naar-brief>      # een brief
    python scripts/check_brief.py --since <datum>       # alle briefs vanaf een datum
    python scripts/check_brief.py --blok <pad>          # print het uitslagblok

Exitcode 0 = bruikbaar, 1 = er is minstens een blokkerend defect.

Ontwerpkeuzes die uit onderzoek volgen (2026-09-27, spec-driven development):

  - Een REGELNUMMER verschuift zodra iemand een regel invoegt. Daarom is een
    `bestand:regel` zonder commit-hash een WAARSCHUWING en geen fout: alleen met de
    hash erbij is vast te stellen of het fragment nog klopt. Zie de stempelregel in
    `.claude/skills/sprint-workflow/SKILL.md`.
  - Wat niet te verifieren is, hoort de brief ZELF te markeren als open vraag. Dan is
    het geen vals alarm maar een bewuste keuze. Bron: "instruct the agent to label
    anything it cannot verify as unverified".
  - De 906 historische briefs worden niet geblokkeerd. Een altijd-aan poort geldt voor
    wat er nu gemaakt wordt.

Karpathy-regel 1 is hier geborgd, sinds 2026-09-28 (controle 5):

  De vier regels staan bovenaan `sprint-opstarten.md`, maar alleen regel 4 ("maak vage
  opdrachten verifieerbaar") werd ergens afgedwongen -- door de plaatshouder-, pad- en
  verwijzingcontroles hieronder. Regel 1 ("benoem aannames") stond er als citaat en
  nergens als veld: het woord "aanname" kwam twee keer voor in 460 regels, beide keren
  in de opsomming van de regel zelf. Een plan kwam dus volledig langs deze controle
  zonder dat er een aanname op papier stond.

  Nu eist controle 5 de sectie `## Waar dit plan op rust -- de aannames` met minimaal
  twee ingevulde rijen, en leest daarvoor de TABEL en niet de tekst eromheen -- proza
  dat het woord tien keer noemt telt nul.

  Bewijs in beide richtingen, gemeten op een verder geldige proefbrief:

      sectie ontbreekt volledig          -> GEWEIGERD
      sectie er, tabel nog plaatshouders -> GEWEIGERD (via controle 1)
      sectie er, maar EEN aanname        -> GEWEIGERD
      sectie er, TWEE echte aannames     -> BRUIKBAAR, exitcode 0

  Regel 2 ("Simplicity First") en regel 3 ("niet mengen in een wijziging") zijn hier
  BEWUST niet geborgd: die gaan over de uitvoering en niet over de brief, en zijn pas
  bij de commit te beoordelen. Daar staat nog geen controle op -- gemeten 2026-09-28,
  toen ik regel 3 zelf overtrad met 34 gemengde bestanden in een werkkopie.

Een sprintplan wordt gelezen door een tweede paar ogen (controle 6, 2026-09-28):

  Op een vraag van Rakesh -- waarom start `doc-reviewer` niet na sprint-opstarten? --
  bleek het antwoord: nergens. Een ingevuld sprintplan ging rechtstreeks door naar de
  dag-1-brief en naar Rakesh. Gate 2 lijkt dat te dekken maar geldt voor "features > 50
  regels of > 2 bestanden": dat is code, en een plan is geen code. Het document waar de
  hele sprint op rust werd dus alleen bekeken door wie het schreef.

  Deze controle toetst DAT het gebeurd is, nooit of het oordeel deugt -- dat kan geen
  script. De opdracht voor de reviewer staat uitgeschreven in
  `docs/agent-briefs/sprint-opstarten.md`, inclusief waar hij op let en wat de drie
  toegestane uitslagen betekenen.

  Bewijs in beide richtingen, zeven gevallen, 0 afwijkend:

      geen beoordelingssectie           -> GEWEIGERD
      blok staat alleen in een codeblok -> GEWEIGERD  (anders telt het sjabloonvoorbeeld)
      sectie zonder regel `Uitslag:`    -> GEWEIGERD
      uitslag NIET UITVOERBAAR          -> GEWEIGERD
      uitslag met een verzonnen waarde  -> GEWEIGERD
      uitslag UITVOERBAAR MET GATEN     -> BRUIKBAAR
      uitslag UITVOERBAAR               -> BRUIKBAAR

  Het tweede geval is waarom `_zonder_codeblokken` bestaat: het sjabloon toont het
  uitslagblok als voorbeeld in een ```text-blok, en zonder die stap zou het sjabloon --
  en elke brief die het voorbeeld klakkeloos overneemt -- tellen als "is beoordeeld".

  Dat de persona zelf bestaat, wordt elders geborgd en is nagemeten: haal
  `.claude/agents/doc-reviewer.md` weg en `scripts/check_instructielaag.py` meldt
  "noemt agent `doc-reviewer` -- bestaat niet" op sprint-opstarten.md.

Nulmeting 2026-09-28 over 89 briefs vanaf 2026-09-01: 58 geweigerd. De verdeling laat
zien waarom de commit-hash-stempel bestaat:

    52x  het regelnummer valt buiten het bestand   -> meestal DRIFT, geen schrijffout
    28x  pad bestaat niet                          -> deels verplaatste bestanden
    22x  minder dan vijf bestand:regel-verwijzingen -> WEL fout bij het schrijven
     6x  onvervangen plaatshouder                   -> WEL fout bij het schrijven

Zonder stempel is "de brief had het mis" niet te onderscheiden van "de wereld is verder
gegaan". Met stempel wel: dan meldt dit script "gestempeld op <sha>, sindsdien gewijzigd
-- lees opnieuw" in plaats van blind af te keuren. De meting bewijst dus een regel die al
bestond en die niemand naleefde.

Mutatiebewijs 2026-09-28, beide richtingen, met wegwerpbriefs in de scratchpad:

  VOORWAARTS -- een brief met zes ingebouwde defecten:
    plaatshouder, niet-bestaand pad, regelnummer 999999, te weinig verwijzingen,
    niet-bestaande persona, vage taal -> alle zes betrapt, exitcode 1.

  ACHTERWAARTS -- een schone brief met vijf geldige verwijzingen, een bestaande
    persona, een commit-hash bovenaan en een expliciet gemarkeerde open vraag ->
    exitcode 0, GEEN bevindingen.

  Een tussenstand die het bewijs zelf opleverde: de eerste versie keek maar EEN regel
  terug voor de commit-hash en gaf daardoor vijf valse waarschuwingen op de schone
  brief. Een brief heeft doorgaans EEN leesmoment dat bovenaan staat, niet een hash per
  regel. De blik is verbreed naar het blok boven de verwijzing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PLAATSHOUDER = re.compile(r"\[[A-Z][A-Z _\-0-9/]{2,}\]")
PAD_IN_TEKST = re.compile(r"`([a-zA-Z0-9_./-]*/[a-zA-Z0-9_.-]+\.(?:py|sh|ts|tsx|js|jsx|mjs|cjs|md|json|yml|ini))`")
# `.js`, `.jsx`, `.mjs` en `.json` tellen sinds 2026-10-01 mee.
#
# Ze ontbraken, en dat was geen kleinigheid: een brief OVER een .js-bestand kon per
# constructie niet aan zijn eigen eis van vijf verwijzingen voldoen. Gemeten die dag met
# een brief over `frontend/public/sw.js` -- de service worker die klanten na een uitrol
# de oude versie laat zien. Vijf verwijzingen naar dat bestand telden als NUL, en de
# brief werd geweigerd terwijl hij juist concreter was dan de meeste.
#
# Een poort die een heel bestandstype niet kent, weigert niet de slechte briefs maar de
# briefs over dat type. Dit project is voor de helft TypeScript en JavaScript; de
# frontendbouw, de service worker en de hulpscripts in `frontend/scripts/` zijn .js of
# .mjs. Die oppervlakte was onbeschrijfbaar.
BESTAND_REGEL = re.compile(r"`?([a-zA-Z0-9_./-]+\.(?:py|sh|ts|tsx|js|jsx|mjs|cjs|json)):(\d+)`?")
COMMIT_HASH = re.compile(r"\b([0-9a-f]{8,40})\b")
PERSONA = re.compile(r"[Pp]ersona:?\s*`?([a-z][a-z0-9-]{2,})`?")

# Taal die een meting vervangt door een gevoel.
VAAG = [
    ("waarschijnlijk", "een vermoeden, geen meting"),
    ("vermoedelijk", "een vermoeden, geen meting"),
    ("zou moeten", "een verwachting, geen vastgestelde staat"),
    ("lijkt te", "een indruk, geen meting"),
    ("tbd", "onafgemaakt"),
    ("t.b.d.", "onafgemaakt"),
    ("etc.", "een onvolledige opsomming"),
    ("enzovoort", "een onvolledige opsomming"),
]
# Deze woorden mogen wel, mits de zin ook een commando of een expliciete markering draagt.
MARKERING = re.compile(
    r"niet gemeten|onverifieerbaar|open vraag|NIET VASTGESTELD|te verifieren", re.I
)


@dataclass
class Uitslag:
    blokkerend: list[str] = field(default_factory=list)
    waarschuwing: list[str] = field(default_factory=list)

    @property
    def bruikbaar(self) -> bool:
        return not self.blokkerend


def lees(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def _git(*args: str) -> str:
    try:
        uit = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=20, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return uit.stdout.strip()


def bestand_gewijzigd_sinds(pad: str, hash_: str) -> bool | None:
    """Is dit bestand gewijzigd sinds die commit? None = niet vast te stellen."""
    if not _git("cat-file", "-e", f"{hash_}^{{commit}}"):
        # git geeft niets terug bij succes; check apart of de commit bestaat
        bestaat = subprocess.run(
            ["git", "cat-file", "-e", f"{hash_}^{{commit}}"],
            cwd=REPO,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if bestaat.returncode != 0:
            return None
    log = _git("log", "--oneline", f"{hash_}..HEAD", "--", pad)
    return bool(log)


#: De sectie waarin een sprintplan zijn aannames benoemt (Karpathy-regel 1).
AANNAME_KOP = "## Waar dit plan op rust -- de aannames"

#: De sectie waarin de tweede lezer zijn oordeel achterlaat.
BEOORDELING_KOP = "## Beoordeling"

#: De drie toegestane uitslagen. Alleen de eerste twee laten een plan door.
UITSLAG = re.compile(r"^\s*Uitslag:\s*(.+?)\s*$", re.M)
UITSLAG_DOOR = ("UITVOERBAAR", "UITVOERBAAR MET GATEN")
UITSLAG_STOP = "NIET UITVOERBAAR"


#: Een hek van een omheind blok: drie backticks aan het begin van de regel.
_BLOKHEK = re.compile(r"^ {0,3}```")


def _zonder_codeblokken(tekst: str) -> str:
    """Knip fenced blocks weg.

    Nodig omdat het SJABLOON het uitslagblok als voorbeeld in een ```text-blok toont.
    Zonder deze stap zou een brief die het voorbeeld klakkeloos overneemt -- of het
    sjabloon zelf -- tellen als "is beoordeeld", en dan bewaakt de controle niets.
    """
    return re.sub(r"```.*?```", "", tekst, flags=re.S)


def _regels_zonder_omheind_blok(regels: list[str]) -> list[str]:
    """Vervang de regels van omheinde blokken door lege regels; nummering blijft gelijk.

    Alleen een hek van drie backticks aan het BEGIN van een regel opent of sluit een blok.
    Backticks midden in een zin doen niet mee, anders verdwijnt proza voor de toets
    (`_zonder_codeblokken` knipt wel op elke drie backticks). Een blok zonder sluithek
    blijft staan: liever te veel toetsen dan stil een rest van de brief overslaan.
    """
    uit = list(regels)
    open_op: int | None = None
    for i, regel in enumerate(regels):
        if not _BLOKHEK.match(regel):
            continue
        if open_op is None:
            open_op = i
            continue
        for j in range(open_op, i + 1):
            uit[j] = ""
        open_op = None
    return uit


#: De koppen waaronder een brief opsomt wat er aan het eind moet BESTAAN. Daar noemt een
#: pad iets dat nog gemaakt moet worden; overal elders iets dat je moet kunnen lezen.
_DELIVERABLE_KOPPEN = ("## Verwachte deliverables", "## Deliverables")


def _paden_in_deliverables(tekst: str) -> set[str]:
    """De paden die binnen een deliverables-sectie staan.

    Afgebakend op de markdown-kop tot de volgende `## `-kop. Dat is structuur; een
    zoektocht op een woord als "aanmaken" zou elke zin treffen die het toevallig gebruikt.
    """
    gevonden: set[str] = set()
    regels = tekst.splitlines()
    for i, regel in enumerate(regels):
        if not regel.startswith(_DELIVERABLE_KOPPEN):
            continue
        for volgende in regels[i + 1 :]:
            if volgende.startswith("## "):
                break
            gevonden.update(PAD_IN_TEKST.findall(volgende))
    return gevonden


def _ingevulde_aannames(regels: list[str]) -> int | None:
    """Hoeveel aannames zijn er ECHT ingevuld, of None als de sectie ontbreekt.

    Leest de TABEL en niet de tekst eromheen. Een sectie die het woord "aanname" tien
    keer noemt in proza telt nul; alleen een rij met een gevulde tweede kolom telt.
    Dat is hetzelfde onderscheid dat de guards in tests/architecture/ moeten maken:
    structuur toetsen, niet tekst doorzoeken.

    Een rij telt niet mee als de tweede kolom leeg is, nog een plaatshouder draagt, of
    uit streepjes bestaat (dat is de scheidingsregel van de tabelkop).
    """
    start = next((i for i, r in enumerate(regels) if r.startswith(AANNAME_KOP)), None)
    if start is None:
        return None
    aantal = 0
    for regel in regels[start + 1 :]:
        if regel.startswith("## "):  # volgende sectie: klaar
            break
        if not regel.lstrip().startswith("|"):
            continue
        kolommen = [k.strip() for k in regel.strip().strip("|").split("|")]
        if len(kolommen) < 2:
            continue
        waarde = kolommen[1]
        if not waarde or set(waarde) <= {"-", ":", " "}:
            continue
        if PLAATSHOUDER.search(waarde) or waarde.lower().startswith("waar ik van uitga"):
            continue
        aantal += 1
    return aantal


def controleer(pad: Path) -> Uitslag:
    u = Uitslag()
    if not pad.is_file():
        u.blokkerend.append(f"brief bestaat niet: {pad}")
        return u
    tekst = lees(pad)
    regels = tekst.splitlines()

    # 1. Onvervangen plaatshouders -- een half ingevulde brief is geen opdracht.
    ph = sorted(set(PLAATSHOUDER.findall(tekst)))
    for p in ph:
        u.blokkerend.append(f"onvervangen plaatshouder {p}")

    # 2. Genoemde paden moeten bestaan -- behalve waar de brief om iets NIEUWS vraagt.
    #
    # Toegevoegd 2026-09-28. Gemeten aanleiding: een brief die vroeg om
    # `scripts/toets_rood_voor_de_fix.py` te BOUWEN werd geweigerd omdat dat bestand niet
    # bestond. Dat klopt letterlijk en is precies verkeerd: een opdracht om iets te maken
    # noemt per definitie iets dat er nog niet is. Zo werd elke brief die nieuw werk vraagt
    # onmogelijk, en dat is ongeveer de helft van alle opdrachten.
    #
    # De grens is STRUCTUUR en geen sleutelwoord: alleen binnen de sectie waarin de brief
    # opsomt wat er aan het eind moet BESTAAN. Daarbuiten geldt de eis onverkort, want daar
    # verwijst een pad naar iets dat je moet kunnen lezen.
    te_maken = _paden_in_deliverables(tekst)
    for p in sorted(set(PAD_IN_TEKST.findall(tekst))):
        if "*" in p or "YYYY" in p or "<" in p:
            continue
        if (REPO / p).exists():
            continue
        if _git("ls-files", f"*{p}"):
            continue
        if p in te_maken:
            u.waarschuwing.append(
                f"`{p}` bestaat niet en staat bij de deliverables -- dat mag, maar "
                f"controleer of het een nieuw bestand is en geen typefout"
            )
            continue
        u.blokkerend.append(f"verwijst naar `{p}` -- bestaat niet")

    # 3. bestand:regel-verwijzingen: pad moet bestaan, regel moet binnen het bestand vallen.
    #    Zonder commit-hash in de buurt is het een waarschuwing: het nummer kan verschoven zijn.
    verwijzingen = 0
    for i, regel in enumerate(_regels_zonder_omheind_blok(regels)):
        for bestand, nummer in BESTAND_REGEL.findall(regel):
            verwijzingen += 1
            doel = REPO / bestand
            if not doel.is_file():
                gevonden = _git("ls-files", f"*{bestand}")
                if not gevonden:
                    u.blokkerend.append(f"`{bestand}:{nummer}` -- bestand bestaat niet")
                    continue
                doel = REPO / gevonden.splitlines()[0]
            aantal = len(lees(doel).splitlines())
            if int(nummer) > aantal:
                u.blokkerend.append(
                    f"`{bestand}:{nummer}` -- het bestand heeft maar {aantal} regels"
                )
                continue
            # Draagt deze verwijzing een commit-hash? Zoek eerst op de regel zelf, dan
            # in het blok erboven. Een brief heeft doorgaans EEN leesmoment dat bovenaan
            # staat ("gelezen op commit <sha>"), niet een hash per regel. Gemeten
            # 2026-09-28: een blik van twee regels gaf vijf valse waarschuwingen op een
            # brief die de hash correct een keer bovenaan noemde.
            context = regel or ""
            hashes = COMMIT_HASH.findall(context)
            if not hashes:
                hashes = COMMIT_HASH.findall(" ".join(regels[:i]))
            if not hashes:
                u.waarschuwing.append(
                    f"`{bestand}:{nummer}` heeft geen commit-hash -- "
                    f"het regelnummer is niet te verifieren"
                )
                continue
            gewijzigd = bestand_gewijzigd_sinds(bestand, hashes[0])
            if gewijzigd:
                u.waarschuwing.append(
                    f"`{bestand}:{nummer}` is gestempeld op {hashes[0][:8]}, maar het bestand "
                    f"is sindsdien gewijzigd -- lees het fragment opnieuw"
                )

    # 4. Een sprint-dag of sprintplan zonder concrete verwijzingen is niet uitvoerbaar.
    soort = pad.name
    if ("sprint-dag" in soort or "sprint-opstarten" in soort) and verwijzingen < 5:
        u.blokkerend.append(
            f"maar {verwijzingen} `bestand:regel`-verwijzingen; "
            f"sprint-dag.md stap 5 eist er minimaal 5"
        )

    # 5. Een sprintplan zonder benoemde aannames is Karpathy-regel 1 op papier.
    #
    # Toegevoegd 2026-09-28. Gemeten aanleiding: `sprint-opstarten.md` noemde het woord
    # "aanname" twee keer in 460 regels, en beide keren als CITAAT van de regel ("benoem
    # aannames") -- er was geen veld om ze in te vullen. Een plan kwam dus volledig langs
    # deze controle zonder dat er een aanname op papier stond, terwijl regel 1 bovenaan
    # het sjabloon prijkte.
    #
    # Alleen voor het sprintplan, niet voor een sprint-dag: de aannames horen bij het
    # PLAN, en een dagbrief erft ze. Ze twee keer laten opschrijven levert overschrijven
    # op in plaats van nadenken.
    #
    # De onvervangen plaatshouders `[AANNAME]` vallen al onder controle 1; wat hier
    # bijkomt is het geval waarin iemand de hele sectie WEGLAAT -- dan is er niets te
    # vervangen en meldt controle 1 terecht niets.
    if "sprint-opstarten" in pad.name:
        rijen_ok = _ingevulde_aannames(regels)
        if rijen_ok is None:
            u.blokkerend.append(
                f"geen sectie `{AANNAME_KOP}`; Karpathy-regel 1 eist dat een plan zijn "
                f"aannames benoemt. Neem de sectie over uit "
                f"docs/agent-briefs/sprint-opstarten.md"
            )
        elif rijen_ok < 2:
            u.blokkerend.append(
                f"{rijen_ok} ingevulde aanname(s) in `{AANNAME_KOP}`, minimaal 2 vereist. "
                f"Een aanname is iets waarvan je UITGAAT maar dat je niet hebt gemeten; "
                f"kun je er geen twee bedenken, dan heb je niet genoeg gekeken"
            )

    # 6. Een sprintplan wordt gelezen door iemand die het niet geschreven heeft.
    #
    # Toegevoegd 2026-09-28, op een vraag van Rakesh: waarom wordt `doc-reviewer` niet
    # gestart na sprint-opstarten? Gemeten antwoord: nergens. Een ingevuld sprintplan ging
    # rechtstreeks door naar de dag-1-brief en naar Rakesh. Gate 2 (code-reviewer +
    # quality-reviewer) lijkt dat te dekken maar geldt voor "features > 50 regels of > 2
    # bestanden" -- dat is code, en een plan is geen code. Het document waar de hele sprint
    # op rust werd dus alleen bekeken door de schrijver, en dat is precies wat scheiding
    # van taken verbiedt.
    #
    # Deze controle toetst DAT het gebeurd is, niet of het oordeel deugt. Dat laatste kan
    # geen script; daarom staat de opdracht voor de reviewer uitgeschreven in
    # `docs/agent-briefs/sprint-opstarten.md`.
    if "sprint-opstarten" in pad.name:
        zonder_code = _zonder_codeblokken(tekst)
        if BEOORDELING_KOP not in zonder_code:
            u.blokkerend.append(
                f"geen sectie `{BEOORDELING_KOP}`; een sprintplan wordt gelezen door "
                f"`doc-reviewer` voordat het de keten in gaat. Zie "
                f"docs/agent-briefs/sprint-opstarten.md, 'Laat het plan beoordelen'"
            )
        else:
            gevonden = [w.strip().upper() for w in UITSLAG.findall(zonder_code)]
            if not gevonden:
                u.blokkerend.append(
                    f"`{BEOORDELING_KOP}` zonder regel `Uitslag:`; een beoordeling zonder "
                    f"uitslag is geen beoordeling"
                )
            elif gevonden[0] == UITSLAG_STOP:
                u.blokkerend.append(
                    f"beoordeling zegt {UITSLAG_STOP}; repareer wat de reviewer vond en "
                    f"laat opnieuw lezen voor dit plan de keten in gaat"
                )
            elif gevonden[0] not in UITSLAG_DOOR:
                u.blokkerend.append(
                    f"onbekende uitslag `{gevonden[0]}`; toegestaan zijn "
                    f"{', '.join(UITSLAG_DOOR)} en {UITSLAG_STOP}"
                )

    # 7. Een persona die genoemd wordt, moet bestaan.
    for naam in sorted(set(PERSONA.findall(tekst))):
        if naam in {"per", "van", "die", "voor", "rol"}:
            continue
        if not (REPO / ".claude" / "agents" / f"{naam}.md").is_file():
            u.blokkerend.append(f"noemt persona `{naam}` -- .claude/agents/{naam}.md bestaat niet")

    # 6. Vage taal die een meting vervangt, tenzij de zin zichzelf markeert.
    for i, regel in enumerate(regels, 1):
        laag = regel.lower()
        if MARKERING.search(regel):
            continue
        for woord, waarom in VAAG:
            if woord in laag:
                u.waarschuwing.append(f'regel {i}: "{woord}" -- {waarom}')
                break

    # 7. ASCII-only, zoals overal in dit project.
    niet_ascii = [i for i, r in enumerate(regels, 1) if any(ord(c) > 127 for c in r)]
    if niet_ascii:
        toon = ", ".join(str(n) for n in niet_ascii[:5])
        meer = f" (en {len(niet_ascii) - 5} meer)" if len(niet_ascii) > 5 else ""
        u.waarschuwing.append(f"non-ASCII op regel {toon}{meer}")

    return u


def blok(pad: Path, u: Uitslag) -> str:
    """Het uitslagblok dat in de brief hoort. Geen blok = geen geldige brief."""
    stand = "BRUIKBAAR" if u.bruikbaar else "GEWEIGERD"
    regels = [
        "## Controle",
        "",
        f"`python scripts/check_brief.py {pad.as_posix()}`",
        "",
        f"- Uitslag: **{stand}**",
        f"- Blokkerend: {len(u.blokkerend)}",
        f"- Waarschuwingen: {len(u.waarschuwing)}",
    ]
    for b in u.blokkerend:
        regels.append(f"  - BLOKKEREND: {b}")
    for w in u.waarschuwing:
        regels.append(f"  - let op: {w}")
    regels += [
        "",
        "> Dit blok is machinaal. Het zegt niets over de vraag of deze brief de opdracht",
        "> dekt -- dat oordeel is van de regie. De ontvangende sessie mag een brief",
        "> weigeren, ook als dit blok BRUIKBAAR zegt.",
    ]
    return "\n".join(regels)


def main() -> int:
    parser = argparse.ArgumentParser(description="Controleer een agent-brief.")
    parser.add_argument("brief", nargs="?", help="pad naar de brief")
    parser.add_argument("--since", help="alle briefs met een datum vanaf YYYY-MM-DD")
    parser.add_argument("--blok", action="store_true", help="print het uitslagblok")
    args = parser.parse_args()

    if args.since:
        paden = sorted(
            p
            for p in (REPO / "docs/agent-briefs/generated").glob("*.md")
            if p.name[:10] >= args.since
        )
        if not paden:
            print(f"Geen briefs met een datum vanaf {args.since}.")
            return 0
        stuk = 0
        for p in paden:
            u = controleer(p)
            merk = "ok  " if u.bruikbaar else "FOUT"
            print(f"[{merk}] {p.name}  blokkerend={len(u.blokkerend)} let-op={len(u.waarschuwing)}")
            for b in u.blokkerend:
                print(f"         {b}")
            if not u.bruikbaar:
                stuk += 1
        print()
        print(f"{len(paden)} briefs gecontroleerd, {stuk} geweigerd.")
        return 1 if stuk else 0

    if not args.brief:
        parser.error("geef een brief op, of gebruik --since")
    pad = Path(args.brief)
    if not pad.is_absolute() and not pad.exists():
        pad = REPO / args.brief
    u = controleer(pad)

    if args.blok:
        print(blok(pad, u))
        return 0 if u.bruikbaar else 1

    print(f"Brief: {pad.name}")
    print(f"Uitslag: {'BRUIKBAAR' if u.bruikbaar else 'GEWEIGERD'}")
    print()
    for b in u.blokkerend:
        print(f"  BLOKKEREND  {b}")
    for w in u.waarschuwing:
        print(f"  let op      {w}")
    if u.bruikbaar and not u.waarschuwing:
        print("  geen bevindingen")
    return 0 if u.bruikbaar else 1


if __name__ == "__main__":
    sys.exit(main())

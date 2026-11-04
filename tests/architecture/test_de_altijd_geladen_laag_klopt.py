"""Wat CLAUDE.md "altijd geladen" noemt, laadt ook werkelijk altijd.

**Waarom deze guard bestaat (gemeten 2026-09-28).** CLAUDE.md beweerde dat vier bestanden
altijd meekomen: `SOUL.md`, `WORKING-CONTEXT.md`, `quality-gates.md` en
`backend-patterns.md`. Gemeten aan de context van een echte sessie plus de documentatie op
https://code.claude.com/docs/en/memory klopte daar niets van:

  - `.claude/SOUL.md` -- "6 immutable principles, never negotiated, never overridden" --
    werd door NIETS geladen. Geen `@`-import in CLAUDE.md, geen vermelding in
    `settings.json`, en de SessionStart-hook injecteert alleen de git-stand. De zes
    principes waren ruim een jaar onzichtbaar voor elke sessie die dacht ze te volgen.
  - `.claude/WORKING-CONTEXT.md` evenmin. Op 2026-09-27 werd dat bestand van 1621 naar 218
    regels ingekort met als reden "-24.716 tokens"; die tokens waren nooit in beeld.
  - Er laadden juist DRIE bestanden MEER dan genoemd: `git-safety.md`, `code-quality.md`
    en `testing.md`.

Daarbovenop stond `.claude/rules/git-safety.md` helemaal niet in git terwijl CLAUDE.md en
`docs/agent-werkwijze.md` er allebei naar verwezen. Op deze machine bestond het; voor
iedere kloon was het een dood pad.

**Wat Claude Code werkelijk doet**, uit dezelfde documentatie: elk `.md` in
`.claude/rules/` ZONDER `paths`-kop laadt bij elke sessiestart. Met een `paths`-kop laadt
het pas als er een passend bestand wordt geopend. `paths` is het enige veld dat gelezen
wordt -- "any other field is ignored without an error". Daarom zegt `alwaysApply: false` op
een bestand dat altijd laadt precies het omgekeerde van de waarheid, en daarom verbiedt
`test_geen_genegeerde_kop_die_controle_suggereert` dat veld.

De ene helft van deze guard leest STRUCTUUR (de frontmatter, en `git ls-files`), de andere
helft moet wel tekst lezen, want de claim in CLAUDE.md is proza. Die tekstkant is daarom
afgebakend tot de sectie waar de claim staat -- een naam die toevallig elders in het
bestand voorkomt telt niet mee.

Mutatiebewijs (2026-09-28), EEN REGEL PER RIJ van de bewaakte tabel en in beide
richtingen. Terugweg via een kopie in een tijdelijke map, nooit via `git checkout` -- dat
zou ongecommit werk wissen:

    rij `.claude/SOUL.md` uit de tabel gehaald                   -> ROOD
    rij `.claude/rules/quality-gates.md` uit de tabel gehaald    -> ROOD
    rij `.claude/rules/backend-patterns.md` uit de tabel gehaald -> ROOD
    rij `.claude/rules/git-safety.md` uit de tabel gehaald       -> ROOD
    rij `.claude/rules/code-quality.md` uit de tabel gehaald     -> ROOD
    rij `.claude/rules/testing.md` uit de tabel gehaald          -> ROOD
    `database.md` (heeft `paths`) als altijd-rij toegevoegd      -> ROOD
    de `@`-import in een codeblok gezet                          -> ROOD
    `alwaysApply: false` terug in `testing.md`                    -> ROOD
    `paths`-kop van `database.md` afgehaald                       -> ROOD
    ongetrackt `.claude/rules/zz-tijdelijk.md` toegevoegd         -> ROOD
    datzelfde bestand getrackt EN in de tabel                     -> GROEN
    datzelfde bestand met `paths`-kop, niet in de tabel           -> GROEN
    alles hersteld                                                -> GROEN

De laatste drie zijn de achterwaartse helft: zonder die zou "weiger alles" een geldige
oplossing zijn, en dan blokkeert de guard elke legitieme nieuwe regel.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / ".claude" / "rules"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

#: De sectie van CLAUDE.md waarin de claim staat. Afgebakend op de markdown-kop, zodat een
#: bestandsnaam die ergens anders in het bestand valt niet meetelt als "genoemd".
_SECTIE_KOP = "## Wanneer gebruik je wat"

#: Een `@pad`-import aan het begin van een regel. Claude Code negeert imports binnen
#: code spans en fenced blocks, dus die worden eerst weggeknipt -- anders telt een import
#: die in een voorbeeld staat en nooit laadt, toch mee.
_IMPORT = re.compile(r"^@(\S+)", re.M)

#: De TABEL binnen die sectie die de claim doet, herkend aan zijn kopregel.
#:
#: Eerst stond hier een afbakening op twee proza-markers, en die was te grof: de alinea
#: noemt `database.md` en de andere drie voorwaardelijke regels juist OM te zeggen dat ze
#: anders werken, en een zoektocht op de naam las dat als "wordt altijd geladen". Dat is
#: dezelfde faalvorm als elke holle guard in dit project -- tekst doorzoeken waar structuur
#: hoort. Een tabelrij IS structuur: de eerste kolom is een bewering, de omringende uitleg
#: niet.
_TABEL_KOP = "| Altijd geladen | Waarover |"
_PAD_IN_BACKTICKS = re.compile(r"`([^`]+)`")

#: Koppen die Claude Code NIET leest maar die wel controle suggereren. `paths` is het enige
#: veld dat werkt; de rest wordt stil genegeerd.
_GENEGEERDE_STUURKOPPEN = ("alwaysApply",)


def _frontmatter(pad: Path) -> str:
    """De YAML-kop tussen de eerste twee `---`, of leeg als die er niet is."""
    tekst = pad.read_text(encoding="utf-8")
    if not tekst.startswith("---\n"):
        return ""
    eind = tekst.find("\n---\n", 4)
    return "" if eind == -1 else tekst[4:eind]


def _heeft_paths(pad: Path) -> bool:
    return any(r.startswith("paths:") for r in _frontmatter(pad).splitlines())


def _regelbestanden() -> list[Path]:
    """Alle rules, recursief -- Claude Code doorzoekt de map ook recursief."""
    return sorted(RULES_DIR.rglob("*.md"))


def _altijd_ladende_regels() -> list[Path]:
    return [p for p in _regelbestanden() if not _heeft_paths(p)]


def _zonder_code(tekst: str) -> str:
    """Knip fenced blocks en code spans weg."""
    tekst = re.sub(r"```.*?```", "", tekst, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", tekst)


def _claude_md_sectie() -> str:
    """De sectie waarin CLAUDE.md opsomt wat er altijd laadt."""
    tekst = CLAUDE_MD.read_text(encoding="utf-8")
    start = tekst.find(_SECTIE_KOP)
    assert start != -1, (
        f"De sectie {_SECTIE_KOP!r} staat niet in CLAUDE.md. Daar staat de lijst van wat "
        "er altijd laadt; zonder die sectie meet deze guard niets terwijl hij groen meldt. "
        "Hernoemd? Werk _SECTIE_KOP bij."
    )
    volgende = tekst.find("\n## ", start + len(_SECTIE_KOP))
    return tekst[start : volgende if volgende != -1 else len(tekst)]


def _zonder_punt_slash(pad: str) -> str:
    """`./x` -> `x`, maar `.claude/x` blijft heel.

    `lstrip("./")` doet dit NIET: die strookt elk leidend punt en elke leidende slash weg,
    dus `.claude/SOUL.md` werd `claude/SOUL.md` en de import leek te ontbreken. Precies
    dezelfde fout stond op 2026-09-27 in `scripts/check_instructielaag.py` en gaf daar 57
    valse alarmen.
    """
    return pad[2:] if pad.startswith("./") else pad


def _beloofde_paden() -> set[str]:
    """De paden uit de eerste kolom van de tabel, als repo-relatieve posix-paden."""
    sectie = _claude_md_sectie()
    start = sectie.find(_TABEL_KOP)
    assert start != -1, (
        f"De tabel met kopregel {_TABEL_KOP!r} staat niet in CLAUDE.md. Daar staat de "
        "belofte over wat er altijd laadt; zonder die tabel meet deze guard niets terwijl "
        "hij groen meldt -- dat is een fout en geen overslaan. Hernoemd? Werk _TABEL_KOP bij."
    )
    paden: set[str] = set()
    # De kopregel en de scheidingsregel overslaan; stoppen bij de eerste niet-tabelregel.
    for regel in sectie[start:].splitlines()[2:]:
        if not regel.startswith("|"):
            break
        eerste_kolom = regel.split("|")[1]
        paden.update(_PAD_IN_BACKTICKS.findall(eerste_kolom))
    assert paden, "De tabel heeft geen rijen met een pad in backticks."
    return {_zonder_punt_slash(p.replace("\\", "/")) for p in paden}


def _werkelijk_altijd_geladen() -> set[str]:
    """Wat er volgens het bestandssysteem werkelijk elke sessie meekomt.

    Twee bronnen, allebei structuur en geen tekst: de regelbestanden zonder `paths`-kop, en
    de `@`-imports van CLAUDE.md buiten code.
    """
    regels = {p.relative_to(REPO_ROOT).as_posix() for p in _altijd_ladende_regels()}
    imports = _IMPORT.findall(_zonder_code(CLAUDE_MD.read_text(encoding="utf-8")))
    return regels | {_zonder_punt_slash(i.replace("\\", "/")) for i in imports}


def test_elk_altijd_ladend_bestand_staat_in_de_tabel() -> None:
    """Wie meekomt zonder dat je erom vraagt, hoort in de tabel te staan."""
    ontbreekt = sorted(_werkelijk_altijd_geladen() - _beloofde_paden())
    assert not ontbreekt, (
        f"Deze bestanden laden bij ELKE sessie maar staan niet in de tabel onder "
        f"{_TABEL_KOP!r} in CLAUDE.md: {ontbreekt}. Een sessie draagt ze dan mee zonder te "
        "weten dat ze er zijn, en wie het contextbudget meet telt ze niet mee. Zet ze in de "
        "tabel, of geef ze een `paths`-kop zodat ze alleen laden wanneer het nodig is."
    )


def test_de_tabel_belooft_niets_dat_niet_laadt() -> None:
    """De andere kant: een belofte die niet uitkomt is erger dan geen belofte."""
    teveel = sorted(_beloofde_paden() - _werkelijk_altijd_geladen())
    assert not teveel, (
        f"CLAUDE.md belooft dat deze bestanden altijd laden, maar dat doen ze niet: "
        f"{teveel}. Een bestand laadt alleen automatisch als het in `.claude/rules/` staat "
        "ZONDER `paths`-kop, of als CLAUDE.md het met `@pad` importeert buiten backticks. "
        "Gemeten 2026-09-28: `.claude/SOUL.md` en `.claude/WORKING-CONTEXT.md` stonden hier "
        "allebei in terwijl niets ze laadde -- ruim een jaar lang volgde geen enkele sessie "
        "de zes principes die overal onveranderlijk heetten."
    )


def test_soul_md_wordt_daadwerkelijk_ingelezen() -> None:
    """De zes principes heten onderhandelbaar noch overrulebaar -- dan moeten ze er zijn."""
    soul = REPO_ROOT / ".claude" / "SOUL.md"
    assert soul.is_file(), (
        "`.claude/SOUL.md` bestaat niet. Deze guard meet dan minder dan hij belooft terwijl "
        "hij groen meldt. Verplaatst? Werk deze test bij."
    )
    imports = _IMPORT.findall(_zonder_code(CLAUDE_MD.read_text(encoding="utf-8")))
    genormaliseerd = {_zonder_punt_slash(i.replace("\\", "/")) for i in imports}
    assert ".claude/SOUL.md" in genormaliseerd, (
        "CLAUDE.md importeert `.claude/SOUL.md` niet met `@.claude/SOUL.md`, en dan laadt "
        "dat bestand door NIETS: het is geen CLAUDE.md, het staat niet in `.claude/rules/` "
        "en geen hook injecteert het. Gemeten 2026-09-28: de zes principes stonden ruim een "
        "jaar in geen enkele sessiecontext terwijl overal stond dat ze altijd golden. "
        f"Gevonden imports: {sorted(genormaliseerd) or 'geen'}. Let op: een `@`-pad binnen "
        "backticks of een codeblok importeert NIET -- dat is juist hoe je een pad noemt "
        "zonder hem te laden."
    )


def test_elk_regelbestand_staat_in_git() -> None:
    """Een regel die alleen op deze machine bestaat, is geen regel."""
    op_schijf = {p.relative_to(REPO_ROOT).as_posix() for p in _regelbestanden()}
    assert op_schijf, "Geen enkel regelbestand gevonden -- klopt RULES_DIR nog?"
    uit = subprocess.run(
        ["git", "ls-files", "--", ".claude/rules"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert uit.returncode == 0, f"git ls-files faalde: {uit.stderr.strip()}"
    getrackt = {r.strip() for r in uit.stdout.splitlines() if r.strip()}
    ontbreekt = sorted(op_schijf - getrackt)
    assert not ontbreekt, (
        f"Deze regelbestanden staan niet in git: {ontbreekt}. Ze laden wel in elke sessie "
        "op DEZE machine, dus alles lijkt te werken -- maar voor iedere kloon en elke "
        "worktree bestaan ze niet, en verwijzingen ernaar zijn dode paden. Gemeten "
        "2026-09-28: `git-safety.md` was op die manier onzichtbaar terwijl CLAUDE.md en "
        "docs/agent-werkwijze.md er allebei naar verwezen. `git add` het bestand."
    )


def test_de_instructielaag_voldoet_aan_zijn_eigen_principe_vijf() -> None:
    """Principe 5 verbiedt non-ASCII. Dat gold niet voor de tekst die het principe bevat.

    Gemeten 2026-09-28: 47 tekens buiten ASCII in negen van de negen bestanden van deze
    laag. Waaronder principe 5 zelf, dat luidde "ASCII-ONLY -- No Unicode" met een em-dash
    op de plek van die streepjes. `test_no_non_ascii_in_core_zone.py` bewaakt alleen
    `*.py` in vier mappen onder `src/`, dus de instructielaag zat in geen enkele zone.

    Dit is niet alleen netheid. Dezelfde guard in de kernzone vond tussen 23 regels twee
    echte defecten: een dubbel-gecodeerde em-dash en een UTF-8 BOM. Allebei onzichtbaar in
    een diff, allebei stuk bij gereedschap dat op ASCII rekent -- en deze laag wordt door
    scripts gelezen die precies dat doen.

    Mutatiebewijs (2026-09-28), EEN REGEL PER BESTAND van de zone, want een zone-guard die
    je op een bestand bewijst zegt niets over de andere tien:

        een em-dash terug in CLAUDE.md                          -> ROOD
        een em-dash terug in .claude/SOUL.md                    -> ROOD
        een em-dash terug in .claude/rules/backend-patterns.md  -> ROOD
        een em-dash terug in .claude/rules/code-quality.md      -> ROOD
        een em-dash terug in .claude/rules/database.md          -> ROOD
        een em-dash terug in .claude/rules/error-handling.md    -> ROOD
        een em-dash terug in .claude/rules/frontend.md          -> ROOD
        een em-dash terug in .claude/rules/git-safety.md        -> ROOD
        een em-dash terug in .claude/rules/quality-gates.md     -> ROOD
        een em-dash terug in .claude/rules/security.md          -> ROOD
        een em-dash terug in .claude/rules/testing.md           -> ROOD
        gewone ASCII-streepjes en een ASCII-pijl toegevoegd      -> GROEN
        alles hersteld                                           -> GROEN
    """
    zone = [CLAUDE_MD, REPO_ROOT / ".claude" / "SOUL.md", *_regelbestanden()]
    treffers: list[str] = []
    onleesbaar: list[str] = []
    for pad in zone:
        naam = pad.relative_to(REPO_ROOT).as_posix()
        try:
            tekst = pad.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            # Een bestand dat niet als UTF-8 leest is het ERGSTE geval van deze klasse en
            # mag niet stil worden overgeslagen -- dan meldt de guard groen over minder.
            onleesbaar.append(f"{naam}: {exc}")
            continue
        for nr, regel in enumerate(tekst.splitlines(), 1):
            buiten = sorted({f"U+{ord(c):04X}" for c in regel if ord(c) > 127})
            if buiten:
                treffers.append(f"  {naam}:{nr}  {', '.join(buiten)}")
    assert not onleesbaar, (
        "Deze instructiebestanden zijn geen geldige UTF-8 en zijn dus NIET gecontroleerd:\n"
        + "\n".join(f"  - {f}" for f in onleesbaar)
    )
    assert not treffers, (
        "Tekens buiten ASCII in de instructielaag, terwijl principe 5 in "
        "`.claude/SOUL.md` ze verbiedt:\n"
        + "\n".join(treffers)
        + "\nVervang een em-dash door '--', een pijl door '->' en een letter met accent "
        "door de kale letter. Let op twee stille gevallen: een dubbel-gecodeerde em-dash "
        "leest als 'a-hat-euro-quote', en een UTF-8 BOM staat onzichtbaar voor het eerste "
        "teken van regel 1."
    )


def test_geen_genegeerde_kop_die_controle_suggereert() -> None:
    """`alwaysApply: false` op een bestand dat altijd laadt, is een onware bewering."""
    treffers = [
        f"{p.relative_to(REPO_ROOT).as_posix()} ({veld})"
        for p in _regelbestanden()
        for veld in _GENEGEERDE_STUURKOPPEN
        if any(r.startswith(f"{veld}:") for r in _frontmatter(p).splitlines())
    ]
    assert not treffers, (
        f"Deze regelbestanden hebben een frontmatter-veld dat Claude Code NIET leest: "
        f"{treffers}. De documentatie is expliciet -- `paths` is het enige veld, elk ander "
        "veld wordt genegeerd zonder foutmelding. Gemeten gevolg: vijf bestanden droegen "
        "`alwaysApply` en drie daarvan zeiden `false` terwijl ze elke sessie laadden. Wie "
        "de kop geloofde, dacht dat hij de laadlaag kon sturen. Haal het veld weg; wil je "
        "dat een regel voorwaardelijk laadt, gebruik dan `paths`."
    )

"""Een klant-eindpunt komt er alleen in via een SSRF-gevalideerd schrijfpad.

Besluit Rakesh 2026-09-20: klanten geven hun eigen LLM-eindpunt op. Dat is precies de stap
waarop LiteLLM dit jaar twee keer is uitgebuit -- CVE-2026-59823 (een genest configuratieveld
langs de controle heen) en CVE-2026-84377, waarbij de proxy de opgeslagen sleutels van de
operator meestuurt naar een adres dat de gebruiker kiest.

De controle zit daarom in EEN doorgang: `TenantLLMProviderService.configureer`. Deze bewaker
houdt dat zo, en toetst daarvoor TWEE SCHAKELS -- allebei op structuur en niet op tekst:

1. de verzameling functies die een `TenantLLMProvider` AANMAAKT is exact de toegestane lijst
   (vandaag: alleen de repository, die pure persistentie is);
2. de verzameling functies die dat schrijfpad AANROEPT is exact de toegestane lijst (vandaag:
   alleen de service), en elk van die functies roept ook `validate_url` aan.

Twee schakels en niet een, omdat de validatie niet in de repository MAG staan: de DSM-regel
verbiedt dat `infra` van `auth` afhangt. Zie `TOEGESTANE_BELEIDSPOORTEN` hieronder.

**Waarom de sleutel `bestand::functie` is en niet alleen het bestand.** Een uitzondering op
bestandsniveau maakt de bewaker blind voor elke andere functie in datzelfde bestand. Dat is
gemeten in ADR-036 OP-258: drie mutaties in een naburige functie bleven groen omdat het bestand
al op de lijst stond.

**Waarom hij niet de hele boom inleest.** Alle getrackte bestanden openen heeft in deze repo een
xdist-worker omgelegd. `git grep -l` levert de handvol kandidaten, en alleen die worden
geparseerd.

Mutatietest (2026-09-20, met scripts/mutation_harness.py). Voor de DERDE keer gedraaid, want
bewijs van een vorige vorm geldt niet voor wat er nu staat -- eerst voor de eenschakelige
versie, toen voor de tweeschakelige, en nu na de verbreding die uit Gate 2 kwam:

1. de `validate_url`-aanroep uit `configureer` gehaald -> ROOD.
2. het gevalideerde adres weggegooid en het ORIGINEEL opgeslagen -> ROOD. (Dit is de mutatie
   die de vorige versie van deze bewaker NIET ving: hij toetste of `validate_url` ergens
   voorkwam, niet of de uitkomst ergens heen ging.)
3. een tweede aanroeper van het schrijfpad toegevoegd in de service -> ROOD.
4. een tweede plek die de rij aanmaakt toegevoegd in de repository -> ROOD.
5. een rauwe `INSERT INTO tenant_llm_providers` toegevoegd in de repository -> ROOD. (Ook deze
   was onzichtbaar voor de vorige versie: die kende maar EEN vocabulaire, de modelnaam.)
6. ongewijzigd -> GROEN. `test_de_bewaker_vindt_de_schrijfplek` en
   `test_de_bewaker_vindt_de_beleidspoort` bewijzen dat beide verzamelingen niet leeg zijn; een
   lege verzameling zou de bijbehorende eis vanzelf groen maken.

**Wat deze bewaker NIET ziet, expliciet opgeschreven.** Een `try/except` rond de validatie die
bij een weigering terugvalt op het originele adres en aan dezelfde naam toekent, en een aanroep
onder een `if False:`. Beide blijven groen. Dat is een grens van statische analyse; het staat
hier zodat een volgende lezer hem kent in plaats van hem te ontdekken.

De anti-holle test verdiende zich meteen terug: de eerste versie van deze bewaker vond NUL
schrijvers, omdat `git grep` standaard alleen getrackte bestanden doorzoekt en het model nog
niet gecommit was. Zie `_kandidaten()`.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

_WORTEL = Path(__file__).resolve().parents[2]

#: Het model waarvan een rij een klant-eindpunt draagt.
_MODEL = "TenantLLMProvider"

#: De functie die de SSRF-controle doet.
_VALIDATIE = "validate_url"

#: De naam van het schrijfpad op de repository.
_SCHRIJFPAD = "voeg_toe"

#: De tabel achter het model. Tweede vocabulaire, voor rauwe SQL: een scanner die maar EEN
#: vocabulaire kent geeft geen fout maar een LEGE uitslag (valkuil `triage_kent_maar_een_
#: vocabulaire`).
_TABELNAAM = "tenant_llm_providers"

#: SQLAlchemy-bewerkingen die een rij AANMAKEN of WIJZIGEN. `select` staat er bewust NIET bij:
#: dat is de leesweg, en meenemen zou `alle()` en `actieve()` als schrijver aanwijzen en zo een
#: uitzondering afdwingen die de bewaker juist verzwakt.
_WIJZIGENDE_BEWERKINGEN = frozenset({"insert", "update", "delete"})

#: Woorden waaraan een rauwe SQL-schrijfactie te herkennen is. `create table` en `create policy`
#: staan er niet bij: de migratie moet de tabel kunnen aanmaken zonder als schrijfpad te gelden.
_RAUWE_SCHRIJFWOORDEN = ("insert into", "update ")

#: Wie een rij mag AANMAKEN. Sleutel is `bestand::functie`, nooit alleen het bestand.
TOEGESTANE_SCHRIJVERS = {
    "src/core/repositories/tenant_llm_provider_repository.py::voeg_toe": (
        "pure persistentie; krijgt een al gevalideerd adres en een al versleutelde sleutel"
    ),
}

#: Wie dat schrijfpad mag AANROEPEN. Dit is de laag waar het beleid zit, en elk van deze
#: functies moet de SSRF-controle doen. Twee schakels in plaats van een, omdat de DSM-regel
#: (`test_dsm_009_no_medium_backward.py`) verbiedt dat de repository zelf `src/core/security`
#: importeert: infra mag niet van auth afhangen. Die regel wees iets echts aan -- opslag hoort
#: niet te weten wat een geldig adres is -- en daarom ligt de grens een laag hoger.
TOEGESTANE_BELEIDSPOORTEN = {
    "src/core/services/tenant_llm_provider_service.py::configureer": (
        "de enige doorgang; doet de schakelaar- en SSRF-controle en versleutelt de sleutel"
    ),
}


def _kandidaten(*termen: str) -> list[Path]:
    """Alleen de bestanden die een van `termen` uberhaupt noemen.

    **`--untracked` is hier geen extraatje maar de kern.** `git grep` zoekt standaard ALLEEN in
    getrackte bestanden. Gemeten 2026-09-20: de eerste versie van deze bewaker vond nul
    schrijvers, omdat het model en de repository nog niet gecommit waren. Een bewaker die nieuwe
    code niet ziet, is blind op precies het moment dat hij nodig is -- bij de wijziging die
    binnenkomt. De anti-holle test hieronder betrapte dat, en dat is waarvoor hij er is.
    """
    argumenten = ["git", "grep", "-l", "--untracked", "-i"]
    for term in termen:
        argumenten += ["-e", term]
    uitvoer = subprocess.run(
        [*argumenten, "--", "src/"],
        cwd=_WORTEL,
        capture_output=True,
        text=True,
        check=False,
    )
    return [_WORTEL / regel.strip() for regel in uitvoer.stdout.splitlines() if regel.strip()]


def _functies_met_aanroep(boom: ast.AST, naam: str) -> set[str]:
    """Namen van functies die ergens in hun eigen body `naam(...)` aanroepen.

    Expliciete recursie en GEEN `ast.walk()` vanaf de moduleknoop: `walk` maakt geen verschil
    tussen een geneste functie en zijn ouder, waardoor een aanroep in een binnenfunctie op naam
    van de buitenste zou worden geschreven (valkuil `ast_walk_duikt_functiebodies_in`).
    """
    gevonden: set[str] = set()

    def roept_aan(knoop: ast.AST) -> bool:
        for kind in ast.iter_child_nodes(knoop):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # dat is een eigen functie; die telt voor zichzelf
            if isinstance(kind, ast.Call):
                doel = kind.func
                if isinstance(doel, ast.Name) and doel.id == naam:
                    return True
                if isinstance(doel, ast.Attribute) and doel.attr == naam:
                    return True
            if roept_aan(kind):
                return True
        return False

    def loop(knoop: ast.AST) -> None:
        for kind in ast.iter_child_nodes(knoop):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if roept_aan(kind):
                    gevonden.add(kind.name)
                loop(kind)
            else:
                loop(kind)

    loop(boom)
    return gevonden


def _functies_met_schrijfvorm(boom: ast.AST) -> set[str]:
    """Namen van functies die een rij AANMAKEN OF WIJZIGEN, in welke vorm dan ook.

    **Waarom dit breder is dan de constructor.** Een Gate 2-reviewer draaide de eerste versie
    van deze bewaker op synthetische code en mat dat VIER realistische schrijfvormen onzichtbaar
    bleven: `insert(TenantLLMProvider).values(...)`, `update(...)`, een import onder een alias,
    en `text("INSERT INTO tenant_llm_providers ...")`. Vandaag bestaat er aantoonbaar maar EEN
    schrijfweg, dus de claim klopte; het probleem was de houdbaarheid. Fase 2b voegt vrijwel
    zeker een UPDATE toe (vandaag is een typefout herstellen alleen mogelijk met een nieuwe rij
    op een vrije `volgorde`), en die zou er zonder een enkele rode test onderdoor zijn gegaan.
    Een bewaker die dan zwijgt is erger dan geen bewaker.

    Drie vocabulaires, allemaal op STRUCTUUR en niet op losse tekst:

    1. de constructor `TenantLLMProvider(...)` -- een `ast.Call` met die naam;
    2. het model als ARGUMENT van `insert`/`update`/`delete`. Bewust NIET `select`: dat is de
       leesweg, en die meenemen zou `alle()` en `actieve()` als schrijver aanwijzen en daarmee
       een uitzondering afdwingen die de bewaker zou verzwakken;
    3. een stringliteral met de TABELNAAM plus `insert into` of `update`. De migratie noemt die
       tabelnaam ook, maar doet CREATE/POLICY en geen INSERT -- die valt hier dus buiten, en dat
       is getoetst in `test_de_migratie_telt_niet_als_schrijfpad`.
    """
    gevonden: set[str] = set()

    def is_schrijfvorm(knoop: ast.AST) -> bool:
        if isinstance(knoop, ast.Call):
            doel = knoop.func
            if isinstance(doel, ast.Name) and doel.id == _MODEL:
                return True
            if isinstance(doel, ast.Attribute) and doel.attr == _MODEL:
                return True
            naam_van_doel = (
                doel.id
                if isinstance(doel, ast.Name)
                else doel.attr
                if isinstance(doel, ast.Attribute)
                else ""
            )
            if naam_van_doel in _WIJZIGENDE_BEWERKINGEN:
                for argument in knoop.args:
                    if isinstance(argument, ast.Name) and argument.id == _MODEL:
                        return True
                    if isinstance(argument, ast.Attribute) and argument.attr == _MODEL:
                        return True
        if isinstance(knoop, ast.Constant) and isinstance(knoop.value, str):
            tekst = knoop.value.lower()
            if _TABELNAAM in tekst and any(w in tekst for w in _RAUWE_SCHRIJFWOORDEN):
                return True
        return False

    def bevat_schrijfvorm(knoop: ast.AST) -> bool:
        for kind in ast.iter_child_nodes(knoop):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # dat is een eigen functie; die telt voor zichzelf
            if is_schrijfvorm(kind) or bevat_schrijfvorm(kind):
                return True
        return False

    def loop(knoop: ast.AST) -> None:
        for kind in ast.iter_child_nodes(knoop):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if bevat_schrijfvorm(kind):
                    gevonden.add(kind.name)
                loop(kind)
            else:
                loop(kind)

    loop(boom)
    return gevonden


def _aanroepers(naam: str) -> dict[str, str]:
    """`bestand::functie` van elke plek die `naam(...)` aanroept."""
    resultaat: dict[str, str] = {}
    for pad in _kandidaten(naam):
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        relatief = pad.relative_to(_WORTEL).as_posix()
        for functie in _functies_met_aanroep(boom, naam):
            resultaat[f"{relatief}::{functie}"] = relatief
    return resultaat


def _schrijvers() -> dict[str, str]:
    """`bestand::functie` van elke plek die een `TenantLLMProvider` aanmaakt of wijzigt."""
    resultaat: dict[str, str] = {}
    for pad in _kandidaten(_MODEL, _TABELNAAM):
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        relatief = pad.relative_to(_WORTEL).as_posix()
        for functie in _functies_met_schrijfvorm(boom):
            resultaat[f"{relatief}::{functie}"] = relatief
    return resultaat


def _beleidspoorten() -> dict[str, str]:
    """`bestand::functie` van elke plek die het schrijfpad van de repository aanroept.

    De definitie van `voeg_toe` zelf telt niet mee: een `def` is geen `ast.Call`.
    """
    gevonden = _aanroepers(_SCHRIJFPAD)
    return {
        sleutel: bestand for sleutel, bestand in gevonden.items() if sleutel not in _schrijvers()
    }


def test_de_bewaker_vindt_de_schrijfplek() -> None:
    """Nul schrijvers zou de volgende test trivially groen maken."""
    assert _schrijvers(), "geen enkele plek maakt een TenantLLMProvider aan -- bewaker is leeg"


def test_de_bewaker_vindt_de_beleidspoort() -> None:
    """Idem voor de tweede schakel: nul poorten maakt de validatietest betekenisloos."""
    assert _beleidspoorten(), "niemand roept het schrijfpad aan -- de tweede schakel is leeg"


def test_alleen_de_toegestane_doorgang_maakt_een_klanteindpunt_aan() -> None:
    onbekend = sorted(set(_schrijvers()) - set(TOEGESTANE_SCHRIJVERS))

    assert not onbekend, (
        "Deze plekken maken een TenantLLMProvider aan buiten de gevalideerde doorgang om: "
        f"{onbekend}. Een klant-eindpunt hoort langs de schakelaar EN de SSRF-controle; "
        "een tweede schrijfweg is precies het gat van CVE-2026-59823. Voeg de plek toe aan "
        "TOEGESTANE_SCHRIJVERS met een reden, of laat hem via de repository lopen."
    )


def test_de_migratie_telt_niet_als_schrijfpad() -> None:
    """Het randgeval waarop de verbreding naar rauwe SQL kon stukgaan.

    De migratie noemt `tenant_llm_providers` volop -- CREATE TABLE, indexen, RLS-policies -- maar
    schrijft geen enkele rij. Zou hij wel als schrijver gelden, dan was de enige uitweg hem op de
    uitzonderingslijst zetten, en een uitzondering op een heel bestand maakt de bewaker blind
    voor alles wat er later bij komt (ADR-036 OP-258). Beter meteen niet meetellen.

    Gemeten 2026-09-20: de migratie IS een kandidaatbestand (hij wordt dus echt bekeken) en
    levert nul schrijvers op.
    """
    migraties = [p for p in _kandidaten(_MODEL, _TABELNAAM) if "alembic" in p.as_posix()]

    assert migraties, "de migratie wordt niet eens bekeken -- dan zegt deze test niets"
    for pad in migraties:
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        assert not _functies_met_schrijfvorm(boom), f"{pad.name} geldt ten onrechte als schrijver"


def test_de_bewaker_ziet_ook_insert_update_en_rauwe_sql() -> None:
    """De vier vormen die een Gate 2-reviewer onzichtbaar mat in de eerste versie.

    Dit toetst de DETECTIE zelf op synthetische code, en niet de repo. Zonder deze test zou de
    verbreding pas blijken te werken op het moment dat iemand hem nodig heeft -- en dan is het
    te laat om te ontdekken dat hij niets zag.
    """
    proef = ast.parse(
        "def via_insert(db, url):\n"
        "    db.execute(insert(TenantLLMProvider).values(base_url=url))\n"
        "def via_update(db, url):\n"
        "    db.execute(update(TenantLLMProvider).values(base_url=url))\n"
        "def via_delete(db):\n"
        "    db.execute(delete(TenantLLMProvider))\n"
        "def via_constructor(db, url):\n"
        "    db.add(TenantLLMProvider(base_url=url))\n"
        "def via_rauwe_sql(db, url):\n"
        '    db.execute(text("INSERT INTO tenant_llm_providers (base_url) VALUES (:u)"))\n'
        "def alleen_lezen(db):\n"
        "    return db.execute(select(TenantLLMProvider))\n"
    )

    gevonden = _functies_met_schrijfvorm(proef)

    assert gevonden == {
        "via_insert",
        "via_update",
        "via_delete",
        "via_constructor",
        "via_rauwe_sql",
    }, f"gemist of te veel: {gevonden}"
    assert "alleen_lezen" not in gevonden, "een SELECT is geen schrijfpad"


def test_de_toegestane_schrijvers_bestaan_nog() -> None:
    """Een uitzondering die is opgelost of hernoemd MOET uit de lijst, anders rot hij dicht."""
    verouderd = sorted(set(TOEGESTANE_SCHRIJVERS) - set(_schrijvers()))

    assert not verouderd, f"deze schrijvers bestaan niet meer: {verouderd}"


def test_alleen_de_toegestane_beleidspoort_roept_het_schrijfpad_aan() -> None:
    """De tweede schakel: wie mag de repository laten schrijven."""
    onbekend = sorted(set(_beleidspoorten()) - set(TOEGESTANE_BELEIDSPOORTEN))

    assert not onbekend, (
        f"Deze plekken roepen het schrijfpad aan buiten de beleidslaag om: {onbekend}. "
        "De schakelaar- en SSRF-controle zitten in de service; eromheen schrijven is precies "
        "het gat van CVE-2026-59823."
    )


def test_de_toegestane_beleidspoorten_bestaan_nog() -> None:
    verouderd = sorted(set(TOEGESTANE_BELEIDSPOORTEN) - set(_beleidspoorten()))

    assert not verouderd, f"deze beleidspoorten bestaan niet meer: {verouderd}"


def _naam_uit_validatie(functie: ast.AST) -> str | None:
    """De variabele waaraan het resultaat van `validate_url(...)` wordt toegekend."""
    for knoop in ast.walk(functie):
        if not isinstance(knoop, ast.Assign) or not isinstance(knoop.value, ast.Call):
            continue
        doel = knoop.value.func
        heet_zo = (isinstance(doel, ast.Name) and doel.id == _VALIDATIE) or (
            isinstance(doel, ast.Attribute) and doel.attr == _VALIDATIE
        )
        if heet_zo and len(knoop.targets) == 1 and isinstance(knoop.targets[0], ast.Name):
            return knoop.targets[0].id
    return None


def _naam_die_wordt_weggeschreven(functie: ast.AST) -> str | None:
    """Wat er als `base_url=` aan het schrijfpad wordt meegegeven."""
    for knoop in ast.walk(functie):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        is_schrijfpad = (isinstance(doel, ast.Name) and doel.id == _SCHRIJFPAD) or (
            isinstance(doel, ast.Attribute) and doel.attr == _SCHRIJFPAD
        )
        if not is_schrijfpad:
            continue
        for sleutelwoord in knoop.keywords:
            if sleutelwoord.arg == "base_url" and isinstance(sleutelwoord.value, ast.Name):
                return sleutelwoord.value.id
    return None


def test_het_GEVALIDEERDE_adres_is_ook_het_opgeslagen_adres() -> None:
    """Valideren en dan het ORIGINEEL opslaan is een groene controle die niets doet.

    Dit sluit een gat dat een Gate 2-reviewer aanwees: de vorige versie toetste alleen of
    `validate_url` ERGENS in de functie voorkwam. Een controle waarvan de uitkomst wordt
    weggegooid, is geen controle -- en dat is een realistische refactor, niet een verzonnen
    geval, want de parameter en de gevalideerde waarde heten bijna hetzelfde.

    **Wat deze bewaker nog steeds NIET ziet, eerlijk opgeschreven:** een `try/except` die bij
    een weigering terugvalt op het originele adres en aan dezelfde naam toekent, of een aanroep
    onder een `if False:`. Beide blijven groen. Dat is een grens van statische analyse en geen
    vergissing; wie hier iets aan verandert, hoort dat te weten in plaats van het te ontdekken.
    """
    for sleutel in _beleidspoorten():
        bestand, functienaam = sleutel.split("::", 1)
        boom = ast.parse((_WORTEL / bestand).read_text(encoding="utf-8"))
        for knoop in ast.walk(boom):
            if (
                isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef))
                and knoop.name == functienaam
            ):
                uit_validatie = _naam_uit_validatie(knoop)
                weggeschreven = _naam_die_wordt_weggeschreven(knoop)
                assert uit_validatie is not None, (
                    f"{sleutel}: het resultaat van `{_VALIDATIE}` wordt aan niets toegekend, "
                    "dus het kan onmogelijk het opgeslagen adres zijn"
                )
                assert weggeschreven == uit_validatie, (
                    f"{sleutel}: er wordt `{weggeschreven}` opgeslagen terwijl `{_VALIDATIE}` "
                    f"`{uit_validatie}` opleverde. Een controle waarvan de uitkomst wordt "
                    "weggegooid, beschermt niets."
                )


def test_elke_beleidspoort_valideert_het_adres() -> None:
    """Toegestaan zijn is niet genoeg: de doorgang moet de controle ook echt doen."""
    zonder_controle = []
    for sleutel in _beleidspoorten():
        bestand, functie = sleutel.split("::", 1)
        boom = ast.parse((_WORTEL / bestand).read_text(encoding="utf-8"))
        if functie not in _functies_met_aanroep(boom, _VALIDATIE):
            zonder_controle.append(sleutel)

    assert not zonder_controle, (
        f"Deze schrijfpaden roepen `{_VALIDATIE}` niet aan: {zonder_controle}. Zonder die "
        "controle kan een klant onze server naar een intern adres of de cloud-metadata sturen, "
        "met zijn eigen sleutel als bearer-token erop."
    )

"""Openstaande gaten in de ketenVERIFICATIE, met een gedateerde uitzondering.

Gevonden op 2026-08-09 tijdens BE-AGT-045 slotdag, buiten de scope van die dag (die omvat acht
blokkers). Groene guards met een uitzonderingslijst plus staleness-test, zoals
`.claude/rules/quality-gates.md` voorschrijft -- een opzettelijk RODE test zou hier de merge van
iedereen blokkeren voor iets dat al maanden zo is.

**OP-109: niets rekent de keten ooit na.** `AuditTrailVerificationJob` bestaat, en
`run_audit_verification` staat als dramatiq-actor geregistreerd, maar NIETS zet hem in de
wachtrij: `src/workers/scheduler.py` heeft twaalf `add_job(...)`-regels en geen daarvan is deze.
Verificatie is dus uitsluitend handmatig, via drie admin-endpoints. Manipulatie van een
auditregel wordt daarmee alleen opgemerkt als een mens toevallig kijkt.

**OP-110: de tijdstempel werd VOOR het slot gezet, op VIJF schrijfpaden. Alle vijf zijn opgelost op 2026-10-21 (de lijst hieronder is leeg).** De `AuditLog`
(inclusief `timestamp`) wordt geconstrueerd voordat `pg_advisory_xact_lock` wordt genomen. Twee
gelijktijdige schrijvers in dezelfde tenant kunnen zo een keten opleveren waarin B een EERDERE
tijdstempel heeft dan A maar WEL achter A is geketend, en dan loopt een verificatie die op
tijdstempel sorteert de keten in de verkeerde volgorde af -- een vals "gemanipuleerd"-oordeel,
puur door gelijktijdigheid.

De lijst noemde er lang TWEE. Een onafhankelijke Gate-2-review vond op 2026-08-31 de andere
drie, met de helpers uit dit bestand zelf, in twintig seconden -- omdat er alleen een
staleness-test was en geen DETECTIEtest. Beide helften staan er nu, zoals
`.claude/rules/quality-gates.md` eist.

**Hoe deze guard wordt bewezen, en waarom die vorm is veranderd (2026-08-31).** Eerst door
productiecode te muteren en te kijken of de guard sterft. Dat is aantoonbaar onbetrouwbaar
gebleken: een handgeschreven mutatieharnas produceerde ongeldige Python, pytest gaf daardoor
geen samenvatting, en het harnas las dat als GROEN. Een mutatietest die zijn eigen falen niet
ziet, is erger dan geen mutatietest.

Nu volgen we de vastgelegde praktijk voor een architectuurregel: de REGEL zelf unittesten op
synthetische fragmenten -- gevallen die moeten falen, gevallen die moeten slagen, en de
randgevallen (zie `_SLOT_GEVALLEN` en `_TIJDSTEMPEL_GEVALLEN`). Dat is deterministisch, het kan
niet omvallen op invalide invoer, en elke ontsnappingsvorm die een reviewer vindt wordt hier een
permanente test in plaats van een handeling die iemand moet onthouden. De echte code wordt
daarnaast nog steeds getoetst, maar dan op de vraag waar deze guard over gaat: staat elk
schrijfpad met dit defect in de gedateerde lijst.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEDULER = REPO_ROOT / "src/workers/scheduler.py"

#: De verificatie-actor die wel bestaat maar nergens wordt ingepland, met datum en reden.
KNOWN_UNSCHEDULED_VERIFICATION: dict[str, str] = {
    # Leeg sinds 2026-08-10: `run_audit_verification` is ingepland in scheduler.py (03:00 UTC),
    # samen met `check_hash_chain_integrity` voor de raad-keten (03:10 UTC). Die tweede stond
    # niet in OP-109 en is gevonden bij het uitzoeken van OP-118/119/120.
    #
    # De staleness-test hieronder heeft dit afgedwongen: hij werd rood zodra de job was
    # ingepland en de regel nog in deze lijst stond. Dat is precies waarvoor die test bestaat.
}

#: Schrijfpaden waar de tijdstempel voor het advisory lock wordt gezet, met datum en reden.
#:
#: De sleutel is `pad::functie` en niet meer een kale functienaam (2026-08-31). Er zijn TWEE
#: klassen die `AuditService` heten, elk met een eigen hash-ketenschrijving, en "log_event" zei
#: niet welke van de twee werd bedoeld -- de bestandskeuze zat in een losse moduleconstante
#: erboven. Een lezer kon dus niet zien WAT er bewaakt werd, en dat is precies de vorm waarin
#: een guard stil het verkeerde meet.
KNOWN_TIMESTAMP_BEFORE_LOCK: dict[str, str] = {
    # LEEG sinds 2026-10-21: alle vijf schrijfpaden zetten de tijdstempel NA het slot en voor het
    # hashen (ADR-036 OP-110). Per pad stond hier een gedateerde rij; ze zijn verwijderd toen het
    # pad werd gefixt, omdat de staleness-test hieronder dat afdwingt:
    #   - `src/core/governance/services/audit_service.py::log_event`: eerder op 2026-10-21;
    #   - `src/core/governance/audit.py::log_action`,
    #     `src/core/governance/cookie_consent.py::update_consent`,
    #     `src/core/governance/dsar_service.py::_create_audit_log` en
    #     `src/core/security/security_audit_service.py::log_event`: vervolg van dezelfde dag;
    #   - `src/core/governance/ai_transparency_service.py::log_ai_decision`,
    #     `::request_human_review` en `::set_profiling_opt_out`: tweede vervolg, 2026-10-22. Daar
    #     stond de tijdstempel in de AANROEPER en nam `_populate_hash_chain` het slot (zie de
    #     hulpfunctie-vorm bij `_effectief_slot`).
    # Bewijs: `tests/integration/test_logboekketen_volgorde.py` (afgedwongen volgorde per pad en
    # gemengd, twintig gemengde rondes, bestaande keten). Een NIEUW pad met dit defect hoort hier
    # met datum en reden terug te komen, niet stil te worden toegevoegd.
}

#: Bestanden waarin naar schrijfpaden met een advisory lock wordt gezocht. Expliciet benoemd en
#: niet repo-breed: een scan over alles maakt de test traag en de verzameling onbenoembaar,
#: en quality-gates.md wil juist dat de bewaakte verzameling opgeschreven staat.
AUDIT_SCHRIJFPAD_BESTANDEN = (
    "src/core/governance/audit.py",
    "src/core/governance/services/audit_service.py",
    "src/core/governance/cookie_consent.py",
    "src/core/governance/dsar_service.py",
    "src/core/security/security_audit_service.py",
    "src/core/copilot/council/audit_writer.py",
    "src/core/governance/ai_transparency_service.py",
    # Bundel logboekketens (2026-10-23): de toolauditketen. Een schrijfpad ZONDER slot ziet deze
    # guard niet; dat vangt `test_toolbroker_auditketen_heeft_een_slot.py`.
    "src/core/tool_broker/audit_repository.py",
)


def _geplande_job_ids() -> set[str]:
    """De `id=`-waarden van elke `add_job(...)` in de scheduler, via de AST."""
    boom = ast.parse(SCHEDULER.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        if not (isinstance(doel, ast.Attribute) and doel.attr == "add_job"):
            continue
        for sleutelwoord in knoop.keywords:
            if sleutelwoord.arg == "id" and isinstance(sleutelwoord.value, ast.Constant):
                if isinstance(sleutelwoord.value.value, str):
                    ids.add(sleutelwoord.value.value)
    return ids


#: Uitkomsten van `_tijdstempel_voor_slot`, zodat "niet gevonden" nooit meer op "geen bevinding"
#: lijkt. De oude vorm gaf voor DRIE verschillende situaties hetzelfde `None` terug: functie
#: onvindbaar, tijdstempel onvindbaar, slot onvindbaar. Alleen de eerste werd in de foutmelding
#: genoemd ("of ze zijn hernoemd"), dus een guard die zijn doelfunctie wel vond maar de
#: tijdstempel niet herkende, klaagde over de verkeerde oorzaak.
GEEN_FUNCTIE = "functie niet gevonden"
GEEN_TIJDSTEMPEL = "geen tijdstempel-toekenning gevonden"
GEEN_SLOT = "geen pg_advisory_xact_lock gevonden"


def _tijdstempel_regel(knoop: ast.AST) -> int | None:
    """De regel waar de tijdstempel wordt gezet, in BEIDE voorkomende vormen.

    Twee vormen, en dat is gemeten en niet bedacht (2026-08-31):
    - `AuditLog(timestamp=datetime.now(timezone.utc))` -- keyword, in
      `services/audit_service.py::log_event`.
    - `log_entry.timestamp = datetime.now(timezone.utc)` -- attribuut-toekenning, in
      `governance/audit.py::log_action`.

    De oude vorm kende alleen de eerste. Het tweede schrijfpad gaf daardoor `None` terug, en
    `None` betekende "geen bevinding". Een refactor van de ene vorm naar de andere -- die het
    defect NIET oplost -- zou de guard dus stil hebben laten wegkijken.

    Net als `_slot_regel` slaat dit geneste functiedefinities over: een tijdstempel in een
    closure hoort niet bij DEZE functie.
    """
    regels: list[int] = []
    for binnen in _eigen_knopen(knoop):
        if isinstance(binnen, ast.keyword) and binnen.arg == "timestamp":
            regel = getattr(binnen.value, "lineno", None)
            if regel is not None:
                regels.append(regel)
        elif isinstance(binnen, ast.Assign):
            for doel in binnen.targets:
                if isinstance(doel, ast.Attribute) and doel.attr == "timestamp":
                    regels.append(binnen.lineno)
    return min(regels) if regels else None


#: Aanroepen die SQL daadwerkelijk naar de database sturen. Alleen een `pg_advisory_xact_lock`
#: die als argument aan een van deze gaat, IS een lock. Een logregel die het woord noemt niet,
#: en een docstring al helemaal niet.
SQL_UITVOERDERS = frozenset({"text", "execute", "exec_driver_sql", "scalar", "scalar_one"})


def _slot_regel(knoop: ast.AST) -> int | None:
    """De regel van de eerste `pg_advisory_xact_lock`-AANROEP in deze functie.

    STRUCTUUR en niet tekst, en dat is hier met schade betaald (onafhankelijke Gate 2,
    2026-08-31). De eerste versie verzamelde ELKE `ast.Constant` met die tekenreeks erin. Een
    docstring IS een `ast.Constant`, dus een enkele docstringregel als
    `Chain writes serialize under pg_advisory_xact_lock per tenant.` liet deze guard melden dat
    de bevinding was opgelost -- hij adviseerde dan letterlijk om ADR-036 OP-110 te sluiten
    terwijl `log_entry.timestamp = ...` nog steeds voor de lock stond. Gemeten op ECHTE code
    was hij toen al fout: op `copilot/council/audit_writer.py::persist` gaf hij regel 121
    terug (de docstring) in plaats van de aanroep op 191.

    Nu telt een tekenreeks alleen als hij als argument aan een SQL-uitvoerder gaat
    (`SQL_UITVOERDERS`). Daarmee vervalt ook de tweede voor de hand liggende valse treffer: een
    `logger.info("we nemen pg_advisory_xact_lock")` is wel een `ast.Call`, maar geen uitvoerder.

    Geneste functiedefinities worden overgeslagen: een lock in een closure hoort niet bij DEZE
    functie, en met `min()` zou die de uitspraak kunnen bepalen.
    """
    regels: list[int] = []
    for binnen in _eigen_knopen(knoop):
        if not isinstance(binnen, ast.Call):
            continue
        doel = binnen.func
        naam = doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", None)
        if naam not in SQL_UITVOERDERS:
            continue
        for stuk in ast.walk(binnen):
            if (
                isinstance(stuk, ast.Constant)
                and isinstance(stuk.value, str)
                and "pg_advisory_xact_lock" in stuk.value
            ):
                regels.append(binnen.lineno)
                break
    return min(regels) if regels else None


def _aanroep_regel(knoop: ast.AST, namen: set[str]) -> int | None:
    """De regel van de eerste AANROEP in deze functie van een functie uit `namen`.

    Dit is de hulpfunctie-vorm (2026-10-22): `ai_transparency_service.py` zette de tijdstempel in
    de aanroeper en riep daarna `self._populate_hash_chain(...)` aan, die het slot nam. Slot en
    tijdstempel stonden dus in VERSCHILLENDE functies en `_slot_regel` zag in de aanroeper geen
    slot, waardoor de guard het pad las als geen slot, dus geen defect.

    Alleen een echte `ast.Call` telt, op naam (`self._hulp(...)` en `_hulp(...)`). Een docstring,
    een comment of een tekenreeks die de naam noemt is geen aanroep. Geneste functiedefinities
    worden overgeslagen, net als bij `_slot_regel`.
    """
    regels: list[int] = []
    for binnen in _eigen_knopen(knoop):
        if not isinstance(binnen, ast.Call):
            continue
        doel = binnen.func
        naam = doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", None)
        if naam in namen:
            regels.append(binnen.lineno)
    return min(regels) if regels else None


def _functies(boom: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [k for k in ast.walk(boom) if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _slot_namen(boom: ast.AST) -> set[str]:
    """Namen van functies in DEZE module die het slot nemen, rechtstreeks of via een hulpfunctie.

    Eerst de functies met een eigen slot (`_slot_regel`), dan herhaald de functies die er een van
    aanroepen, tot er niets bijkomt. Op NAAM en per bestand: twee klassen met dezelfde
    methodenaam in een bestand worden samengenomen. Dat kan een aanroeper te streng beoordelen,
    nooit te mild.
    """
    functies = _functies(boom)
    namen = {f.name for f in functies if _slot_regel(f) is not None}
    while True:
        erbij = {
            f.name for f in functies if f.name not in namen and _aanroep_regel(f, namen) is not None
        }
        if not erbij:
            return namen
        namen |= erbij


def _effectief_slot(knoop: ast.AST, namen: set[str]) -> int | None:
    """Het slot van deze functie: het eigen slot, anders de aanroep van een functie die het neemt."""
    eigen = _slot_regel(knoop)
    if eigen is not None:
        return eigen
    return _aanroep_regel(knoop, namen)


def _eigen_knopen(functie: ast.AST) -> list[ast.AST]:
    """Alle knopen van deze functie, ZONDER de bodies van geneste functiedefinities.

    `ast.walk` duikt geneste `def`/`async def` in. Dat is in dit project al twee keer misgegaan
    (een vacuum-guard en een vals positief), en hier zou een lock of tijdstempel in een closure
    de uitspraak over de buitenste functie kunnen bepalen.
    """
    resultaat: list[ast.AST] = []
    stapel: list[ast.AST] = [functie]
    eerste = True
    while stapel:
        knoop = stapel.pop()
        if not eerste and isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        eerste = False
        resultaat.append(knoop)
        stapel.extend(ast.iter_child_nodes(knoop))
    return resultaat


def _tijdstempel_voor_slot(sleutel: str) -> bool | str:
    """Wordt in deze functie de timestamp gezet VOOR het advisory lock?

    `sleutel` is `pad::functie`. Geeft `True`/`False`, of een van de `GEEN_*`-redenen -- nooit
    een kale `None` die als "geen bevinding" leest. Welk BESTAND wordt ingelezen staat nu in de
    sleutel zelf en niet in een moduleconstante erboven.
    """
    pad, _, functienaam = sleutel.partition("::")
    bestand = REPO_ROOT / pad
    if not bestand.exists():
        return f"{GEEN_FUNCTIE} ({pad} bestaat niet)"

    boom = ast.parse(bestand.read_text(encoding="utf-8"))
    namen = _slot_namen(boom)
    for knoop in _functies(boom):
        if knoop.name != functienaam:
            continue

        tijdstempel = _tijdstempel_regel(knoop)
        slot = _effectief_slot(knoop, namen)
        if tijdstempel is None:
            return GEEN_TIJDSTEMPEL
        if slot is None:
            return GEEN_SLOT
        return tijdstempel < slot
    return GEEN_FUNCTIE


def test_the_scan_finds_scheduled_jobs_at_all() -> None:
    """Vangnet: een lege AST-scan zou alles laten slagen."""
    ids = _geplande_job_ids()

    assert len(ids) >= 3, (
        f"Slechts {len(ids)} `add_job(id=...)`-aanroepen gevonden in {SCHEDULER.name}: "
        f"{sorted(ids)}. Is de aanroepvorm veranderd? Dan meet deze guard niets meer."
    )


def test_known_unscheduled_verification_is_not_stale() -> None:
    """Zodra de verificatie WEL wordt ingepland, moet OP-109 uit de lijst."""
    ids = _geplande_job_ids()
    opgelost = sorted(naam for naam in KNOWN_UNSCHEDULED_VERIFICATION if naam in ids)

    assert not opgelost, (
        f"Deze verificatie-jobs staan in KNOWN_UNSCHEDULED_VERIFICATION maar zijn inmiddels wel "
        f"ingepland: {opgelost}. Haal ze uit de lijst en sluit ADR-036 OP-109."
    )


#: Synthetische bronfragmenten voor de detectoren hieronder. Elk fragment is EEN functie.
#:
#: Waarom deze vorm en niet "muteer de echte code en kijk of de guard sterft": dat tweede is de
#: aanpak die ik eerst gebruikte, en die is aantoonbaar onbetrouwbaar. Een handgeschreven
#: mutatieharnas produceerde ongeldige Python, pytest gaf daardoor geen samenvatting, en mijn
#: harnas las dat als GROEN -- een mutatietest die zijn eigen falen niet ziet. De vastgelegde
#: praktijk voor een architectuurregel is de regel ZELF unittesten op gevallen die moeten falen,
#: gevallen die moeten slagen, en de randgevallen. Dat is deterministisch, het kan niet omvallen
#: op invalide invoer, en elke ontsnappingsvorm die een reviewer vindt wordt hier een permanente
#: test in plaats van een handeling die iemand moet onthouden.
_SLOT_GEVALLEN: tuple[tuple[str, str, bool], ...] = (
    (
        "docstring die het lock noemt",
        "async def f(self):\n"
        '    """Chain writes serialize under pg_advisory_xact_lock per tenant."""\n'
        "    return 1\n",
        False,
    ),
    (
        "logregel die het lock noemt",
        "async def f(self):\n"
        '    logger.debug("we nemen straks pg_advisory_xact_lock")\n'
        "    return 1\n",
        False,
    ),
    (
        "comment die het lock noemt",
        "async def f(self):\n    # pg_advisory_xact_lock komt hier\n    return 1\n",
        False,
    ),
    (
        "echte uitvoering via session.execute(text(...))",
        "async def f(self, sessie):\n"
        '    await sessie.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": 1})\n',
        True,
    ),
    (
        "echte uitvoering via exec_driver_sql",
        "async def f(self, sessie):\n"
        '    await sessie.exec_driver_sql("SELECT pg_advisory_xact_lock(1)")\n',
        True,
    ),
    (
        "lock in een geneste functie hoort niet bij de buitenste",
        "async def f(self, sessie):\n"
        "    async def binnen():\n"
        '        await sessie.execute(text("SELECT pg_advisory_xact_lock(1)"))\n'
        "    return binnen\n",
        False,
    ),
)

_TIJDSTEMPEL_GEVALLEN: tuple[tuple[str, str, bool], ...] = (
    (
        "keyword-vorm",
        "def f(self):\n    return AuditLog(timestamp=datetime.now(timezone.utc))\n",
        True,
    ),
    (
        "attribuut-toekenning",
        "def f(self):\n    entry.timestamp = datetime.now(timezone.utc)\n",
        True,
    ),
    (
        "tijdstempel in een geneste functie hoort niet bij de buitenste",
        "def f(self):\n"
        "    def binnen():\n"
        "        entry.timestamp = datetime.now(timezone.utc)\n"
        "    return binnen\n",
        False,
    ),
    ("geen tijdstempel", "def f(self):\n    return 1\n", False),
)


def _eerste_functie(bron: str) -> ast.AST:
    knoop = ast.parse(bron).body[0]
    assert isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef))
    return knoop


@pytest.mark.parametrize(
    ("naam", "bron", "is_lock"), _SLOT_GEVALLEN, ids=[g[0] for g in _SLOT_GEVALLEN]
)
def test_the_lock_detector_reads_structure_not_text(naam: str, bron: str, is_lock: bool) -> None:
    """De lockdetector mag alleen een ECHTE uitvoering zien, geen tekst die het woord bevat.

    De eerste drie gevallen zijn de faalvorm die deze guard ooit had: een docstring is een
    `ast.Constant`, dus een enkele docstringregel liet hem melden dat ADR-036 OP-110 was
    opgelost. Het laatste geval dekt de tweede bekende valkuil: `ast.walk` duikt geneste
    functiedefinities in.
    """
    gemeten = _slot_regel(_eerste_functie(bron)) is not None
    assert gemeten is is_lock, (
        f"{naam}: de lockdetector zegt {'WEL' if gemeten else 'GEEN'} lock, verwacht "
        f"{'WEL' if is_lock else 'GEEN'}. Fragment:\n{bron}"
    )


@pytest.mark.parametrize(
    ("naam", "bron", "heeft_tijdstempel"),
    _TIJDSTEMPEL_GEVALLEN,
    ids=[g[0] for g in _TIJDSTEMPEL_GEVALLEN],
)
def test_the_timestamp_detector_knows_both_forms(
    naam: str, bron: str, heeft_tijdstempel: bool
) -> None:
    """Beide voorkomende vormen tellen, een geneste closure niet.

    De oude detector kende alleen de keyword-vorm. Een refactor naar de attribuut-vorm -- die
    het defect NIET oplost -- liet de guard daardoor stil wegkijken.
    """
    gemeten = _tijdstempel_regel(_eerste_functie(bron)) is not None
    assert gemeten is heeft_tijdstempel, (
        f"{naam}: de tijdstempeldetector zegt {'WEL' if gemeten else 'GEEN'} tijdstempel, "
        f"verwacht {'WEL' if heeft_tijdstempel else 'GEEN'}. Fragment:\n{bron}"
    )


def test_the_lock_detector_reports_the_call_line_not_the_docstring_line() -> None:
    """Regressie op een gemeten fout: de detector gaf de docstringregel terug.

    Op `copilot/council/audit_writer.py::persist` rapporteerde de oude detector regel 121 (een
    docstring die het lock noemt) in plaats van de aanroep op 191, en dat maakte de uitspraak
    over die functie omgekeerd. Dit fragment heeft beide, zodat de regelkeuze zelf wordt
    getoetst en niet alleen het ja/nee.
    """
    bron = (
        "async def f(self, sessie):\n"
        '    """Neemt pg_advisory_xact_lock voor de keten."""\n'
        "    x = 1\n"
        '    await sessie.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": x})\n'
    )
    assert _slot_regel(_eerste_functie(bron)) == 4, (
        "De lockdetector hoort regel 4 (de aanroep) te melden, niet regel 2 (de docstring)."
    )


def _schrijfpaden_in_module(boom: ast.AST, pad: str) -> dict[str, tuple[int | None, int]]:
    """Elke functie van deze module die het slot neemt, rechtstreeks of via een hulpfunctie.

    Geeft `pad::functie -> (tijdstempelregel, slotregel)`. Bij een hulpfunctie-aanroeper is de
    slotregel de regel van de AANROEP. Los van het bestand zodat de synthetische gevallen
    hieronder dezelfde code toetsen als de echte bestanden.
    """
    namen = _slot_namen(boom)
    gevonden: dict[str, tuple[int | None, int]] = {}
    for knoop in _functies(boom):
        slot = _effectief_slot(knoop, namen)
        if slot is None:
            continue
        gevonden[f"{pad}::{knoop.name}"] = (_tijdstempel_regel(knoop), slot)
    return gevonden


def _schrijfpaden_met_slot() -> dict[str, tuple[int | None, int]]:
    """Elke functie in AUDIT_SCHRIJFPAD_BESTANDEN met een echt advisory lock erin, of die een
    hulpfunctie aanroept die het neemt.

    Geeft `pad::functie -> (tijdstempelregel, lockregel)`. De tijdstempelregel mag `None` zijn:
    een functie die het lock neemt maar geen tijdstempel zet, heeft dit defect niet.
    """
    gevonden: dict[str, tuple[int | None, int]] = {}
    for pad in AUDIT_SCHRIJFPAD_BESTANDEN:
        bestand = REPO_ROOT / pad
        if not bestand.exists():
            continue
        boom = ast.parse(bestand.read_text(encoding="utf-8"))
        gevonden.update(_schrijfpaden_in_module(boom, pad))
    return gevonden


def test_the_scan_finds_write_paths_with_a_lock_at_all() -> None:
    """Vangnet: loopt de detectie leeg, dan bewaakt de test hieronder niets.

    Zonder dit vangnet zou een typefout in `SQL_UITVOERDERS` of in
    `AUDIT_SCHRIJFPAD_BESTANDEN` de detectietest stil laten slagen op een lege verzameling.
    """
    gevonden = _schrijfpaden_met_slot()
    assert len(gevonden) >= 6, (
        f"Er zijn maar {len(gevonden)} schrijfpaden met een advisory lock gevonden: "
        f"{sorted(gevonden)}. Op 2026-08-31 waren het zes. Is de detectie stuk of is er echt "
        "code verdwenen? Bij twijfel: eerst meten, niet de drempel verlagen."
    )


def test_the_scan_sees_the_helper_form_in_ai_transparency_service() -> None:
    """Vangnet voor de hulpfunctie-vorm: de drie aanroepers moeten als schrijfpad gezien worden.

    Zonder dit vangnet kan een hernoeming van `_populate_hash_chain` of een kapotte
    `_slot_namen` de drie aanroepers stil uit de verzameling halen, en dan meet de detectietest
    hieronder niets meer voor dit bestand.
    """
    gevonden = _schrijfpaden_met_slot()
    pad = "src/core/governance/ai_transparency_service.py"
    verwacht = {
        f"{pad}::{naam}"
        for naam in (
            "_populate_hash_chain",
            "log_ai_decision",
            "request_human_review",
            "set_profiling_opt_out",
        )
    }
    ontbrekend = sorted(verwacht - set(gevonden))
    assert not ontbrekend, (
        f"Deze schrijfpaden worden niet meer gezien: {ontbrekend}. Is `_populate_hash_chain` "
        "hernoemd, of is `_slot_namen` stuk? Dan meet de guard de hulpfunctie-vorm niet meer."
    )


_HULP = (
    "async def _hulp(self, e):\n"
    '    await self._db.execute(text("SELECT pg_advisory_xact_lock(1)"))\n'
    "    e.timestamp = datetime.now(timezone.utc)\n"
)

#: Synthetische modules voor de hulpfunctie-vorm: (naam, bron, de functies die als defect moeten
#: gelden). Sleutel is `m.py::functie`. Beide richtingen: wat moet falen en wat moet slagen.
_HULP_GEVALLEN: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "aanroeper zet tijdstempel (attribuut) voor de hulpfunctie met het slot",
        _HULP
        + "async def schrijf(self):\n"
        + "    e = AuditLog()\n"
        + "    e.timestamp = datetime.now(timezone.utc)\n"
        + "    await self._hulp(e)\n",
        ("m.py::schrijf",),
    ),
    (
        "aanroeper zet tijdstempel (keyword) voor de hulpfunctie met het slot",
        _HULP
        + "async def schrijf(self):\n"
        + "    e = AuditLog(timestamp=datetime.now(timezone.utc))\n"
        + "    await self._hulp(e)\n",
        ("m.py::schrijf",),
    ),
    (
        "aanroeper roept de hulpfunctie aan met kale naam in plaats van self.",
        _HULP
        + "async def schrijf(self):\n"
        + "    e = AuditLog()\n"
        + "    e.timestamp = datetime.now(timezone.utc)\n"
        + "    await _hulp(self, e)\n",
        ("m.py::schrijf",),
    ),
    (
        "transitief: aanroeper zet tijdstempel voor een tussenfunctie die de hulpfunctie aanroept",
        _HULP
        + "async def midden(self, e):\n"
        + "    await self._hulp(e)\n"
        + "async def schrijf(self):\n"
        + "    e = AuditLog()\n"
        + "    e.timestamp = datetime.now(timezone.utc)\n"
        + "    await self.midden(e)\n",
        ("m.py::schrijf",),
    ),
    (
        "eigen slot, tijdstempel eerst (de oude vorm blijft gezien)",
        "async def f(self, e):\n"
        + "    e.timestamp = datetime.now(timezone.utc)\n"
        + '    await self._db.execute(text("SELECT pg_advisory_xact_lock(1)"))\n',
        ("m.py::f",),
    ),
    (
        "de aanroeper zet de tijdstempel niet, de hulpfunctie wel na het slot (de gefixte vorm)",
        _HULP + "async def schrijf(self):\n    e = AuditLog()\n    await self._hulp(e)\n",
        (),
    ),
    (
        "aanroeper zet de tijdstempel NA de hulpaanroep",
        _HULP
        + "async def schrijf(self):\n"
        + "    e = AuditLog()\n"
        + "    await self._hulp(e)\n"
        + "    e.timestamp = datetime.now(timezone.utc)\n",
        (),
    ),
    (
        "hulpfunctie zonder slot: de aanroeper is geen schrijfpad met dit defect",
        "async def _hulp(self, e):\n    return e\n"
        + "async def schrijf(self):\n"
        + "    e = AuditLog()\n"
        + "    e.timestamp = datetime.now(timezone.utc)\n"
        + "    await self._hulp(e)\n",
        (),
    ),
    (
        "tijdstempel in een geneste functie van de aanroeper hoort niet bij de aanroeper",
        _HULP
        + "async def schrijf(self):\n"
        + "    def binnen(e):\n"
        + "        e.timestamp = datetime.now(timezone.utc)\n"
        + "    await self._hulp(AuditLog())\n",
        (),
    ),
    (
        "de hulpnaam staat alleen in een docstring, comment en tekenreeks",
        _HULP
        + "async def schrijf(self, e):\n"
        + '    """Roept straks _hulp aan."""\n'
        + "    # _hulp komt hier\n"
        + "    e.timestamp = datetime.now(timezone.utc)\n"
        + '    logger.debug("_hulp")\n',
        (),
    ),
)


@pytest.mark.parametrize(
    ("naam", "bron", "verwacht"), _HULP_GEVALLEN, ids=[g[0] for g in _HULP_GEVALLEN]
)
def test_the_helper_form_detector_flags_the_defect_and_only_the_defect(
    naam: str, bron: str, verwacht: tuple[str, ...]
) -> None:
    """Een tijdstempel in de aanroeper voor een hulpfunctie die het slot neemt IS het defect.

    Faalrichting: de eerste vijf gevallen (inclusief de oude eigen-slot-vorm) moeten gevonden
    worden. Slagrichting: de gefixte vorm, een tijdstempel NA de aanroep, een hulpfunctie zonder
    slot, een closure en een kale vermelding van de naam mogen NIET gevonden worden.
    """
    gevonden = sorted(
        sleutel
        for sleutel, (ts, slot) in _schrijfpaden_in_module(ast.parse(bron), "m.py").items()
        if ts is not None and ts < slot
    )
    assert gevonden == sorted(verwacht), f"{naam}: gevonden {gevonden}, verwacht {sorted(verwacht)}"


def test_no_new_timestamp_before_lock() -> None:
    """Elk schrijfpad met dit defect MOET in de gedateerde lijst staan -- ADR-036 OP-110.

    Dit is de DETECTIEhelft, en die ontbrak tot 2026-08-31. Er was alleen een staleness-test,
    en `quality-gates.md` eist beide: zonder detectie blijft een schrijfpad onzichtbaar tot
    iemand er per ongeluk over struikelt. Dat is precies wat er gebeurde -- de lijst noemde
    twee paden, en een onafhankelijke Gate-2-review vond er drie meer met de helpers uit dit
    bestand zelf, in twintig seconden.

    De test faalt dus in twee richtingen: een NIEUW pad met het defect (zonder rij) is rood, en
    een pad waar de volgorde is omgedraaid komt via de staleness-test hieronder naar buiten.
    """
    ongeregistreerd = sorted(
        f"{sleutel} (tijdstempel {ts}, lock {slot})"
        for sleutel, (ts, slot) in _schrijfpaden_met_slot().items()
        if ts is not None and ts < slot and sleutel not in KNOWN_TIMESTAMP_BEFORE_LOCK
    )
    assert not ongeregistreerd, (
        "Deze schrijfpaden zetten de tijdstempel VOOR het advisory lock en staan niet in "
        f"KNOWN_TIMESTAMP_BEFORE_LOCK: {ongeregistreerd}. Zet de tijdstempel na het lock, of "
        "voeg een rij toe met datum en reden en registreer het onder ADR-036 OP-110. Een "
        "schrijfpad dat nergens staat, is een schrijfpad dat niemand meer nakijkt."
    )


def test_known_timestamp_before_lock_is_not_stale() -> None:
    """Zodra de volgorde is omgedraaid, moet OP-110 uit de lijst.

    Itereert over ALLE VIJF schrijfpaden, elk met zijn bestand in de sleutel. Mutatiebewijs
    2026-08-31, een regel per element, op kopieen (zie het rapport van deze workstream):
    de lockregel voor de tijdstempel zetten maakt de betreffende regel ROOD; de functie
    hernoemen of de tijdstempelvorm slopen levert een EIGEN, benoemde reden op in plaats van
    een stille `None`.
    """
    gemeten = {sleutel: _tijdstempel_voor_slot(sleutel) for sleutel in KNOWN_TIMESTAMP_BEFORE_LOCK}

    opgelost = sorted(sleutel for sleutel, fout in gemeten.items() if fout is False)
    assert not opgelost, (
        f"In deze functies staat de tijdstempel inmiddels NA het advisory lock: {opgelost}. "
        "Haal ze uit KNOWN_TIMESTAMP_BEFORE_LOCK en sluit ADR-036 OP-110."
    )

    onanalyseerbaar = sorted(
        f"{sleutel} ({fout})" for sleutel, fout in gemeten.items() if isinstance(fout, str)
    )
    assert not onanalyseerbaar, (
        f"Deze schrijfpaden zijn niet te analyseren: {onanalyseerbaar}. De reden staat erbij: "
        "een verplaatst bestand, een hernoemde functie, een tijdstempel in een derde vorm, of "
        "een verdwenen advisory lock. In al die gevallen meet deze guard niets meer -- repareer "
        "de sleutel of de detectie, en zet er nooit een kale `None` voor terug."
    )

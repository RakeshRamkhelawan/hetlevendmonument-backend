"""De policy-keuze op het council-pad is modeloutput -- deze guard pint de BOVENGRENS daarvan.

**De bevinding (ADR-036 OP-34, hermeten 2026-09-01).** `audit_writer.py:163-168` gebruikt
`proposal.action_type` als opzoeksleutel in `PAYLOAD_POLICY`. Die string komt uit de NLU
(`proposal_builder.py:66`, `action_type=action.action or "noop"`) en de enige beperking erop is een
VORM: `copilot/schemas.py:57-62`, `max_length=64` en `pattern=r"^[a-z][a-z0-9_]*$"` (OP-78). Er is
GEEN allowlist, manifest of denylist die de naam normaliseert of afwijst voordat hij de policy
kiest; `copilot/service.py:433-435` (`KNOWN_ACTIONS`) zit op een ANDER pad
(`handle_proactive_response`, een knopdruk via `api/turn_endpoint.py:151`) en raakt dit pad niet.
`security_officer.py:171-183` toetst de naam wel tegen het `copilot`-profiel, maar levert een
VERDICT op en geen afwijzing: `coordinator.py:199` -> `:389` -> `audit_officer.py:195` loopt
ook bij `BLOCKED` door naar `persist()`.

**Wat deze guard WEL bewaakt, en waarom juist dat.** De vormbeperking van OP-78 sluit nul sleutels
af -- gemeten, zie `test_the_shape_constraint_blocks_no_policy_key`. De echte bovengrens van het
lek is daarom niet de naam maar de VORM van wat leesbaar mag blijven: elke `readable`-vorm in
`PAYLOAD_POLICY` is vandaag een OPSOMMING (`_one_of`) of een GETALBEREIK (`_bounded_int`). Zolang
dat zo is, kan een door het model gekozen `action_type` alleen getallen en opgesomde codes leesbaar
maken en NOOIT vrije tekst. Hoeveel dat is, staat niet als los getal in deze tekst maar wordt
gemeten door `test_the_readable_upper_bound_has_not_grown` en vastgepind in
`PINNED_MAX_READABLE_BITS`.

**De gekozen ernst: LAAG -- en dat is een meting, geen inschatting.** Drie cijfers, alle drie uit
deze repo:
  1. De bovengrens van wat een modelgekozen `action_type` leesbaar maakt is
     `PINNED_MAX_READABLE_BITS` bits, en dat zijn uitsluitend GETALLEN en opgesomde codes.
  2. Dezelfde rij bewaart `action_type` ZELF onbewerkt (`audit_writer.py:259`, kolom
     `String(128)`, `governance/models.py:781`).
  3. Dezelfde rij bewaart `reasoning` onbewerkt (`audit_writer.py:279`, kolom `Text`,
     `governance/models.py:787`), en `CopilotAction.reasoning` (`copilot/schemas.py:66`) heeft
     `min_length=1` en GEEN `max_length` -- onbegrensde, door het model geschreven vrije tekst.
Een verborgen kanaal van tientallen bits aan getallen naast een onbegrensde, verbatim opgeslagen
vrije-tekstkolom in dezelfde rij verandert de risicostand niet. Vandaar LAAG.

**Die ernst is voorwaardelijk, en dat is de hele reden dat deze guard bestaat.** Zou er een
`readable`-vorm bijkomen die een willekeurige string toelaat -- `_bounded_str_len(200)`, een regex
voor "een naam", een UUID-toets -- dan wordt hetzelfde ongevalideerde pad een kanaal voor
persoonsgegevens in KLAARTEKST, in een hash-geketende rij zonder wisroute (OP-36), en dan is LAAG
niet meer houdbaar. Precies die verruiming maakt deze guard rood
(`test_no_readable_shape_admits_a_free_form_string`), zodat de ernst opnieuw beoordeeld MOET worden
in plaats van stil te verlopen.

Dit is bewust een GROENE guard met een gedateerde vastpinning en geen opzettelijk rode test: de
CI-testgate is sinds 2026-07-31 blokkerend, en een LAAG-ernst-observatie mag geen rode test krijgen
ten koste van elke merge (zie `.claude/rules/quality-gates.md`, de uitzonderingsparagraaf).

**Mutatiebewijs (uitgevoerd 2026-09-01, beide richtingen, per test opgeschreven in de docstring).**
"""

from __future__ import annotations

import math
import re
from typing import Callable

import annotated_types
import pytest

from src.core.copilot.schemas import CopilotAction
from src.core.tool_broker.permission_manager import ToolPermissionManager
from src.core.tool_broker.redaction import PAYLOAD_POLICY

#: De vormbeperking op `CopilotAction.action` (`copilot/schemas.py:57-62`, OP-78), hier als
#: LEESBARE DOCUMENTATIE. Deze twee waarden worden NERGENS in een berekening gebruikt: de
#: bereikbaarheid wordt afgeleid uit `_action_shape_constraints()`, dat de constraint-objecten uit
#: het echte Pydantic-veld leest. Ze staan hier zodat een lezer de vorm ziet zonder pydantic te
#: hoeven uitpluizen, en `test_the_documented_constraints_match_the_real_schema` bewaakt dat ze
#: niet uit elkaar lopen.
DOCUMENTED_ACTION_PATTERN = r"^[a-z][a-z0-9_]*$"
DOCUMENTED_ACTION_MAX_LENGTH = 64

#: Het `agent_id` waaronder het council-pad de allowlist bevraagt: `factory.py:141` geeft
#: `_ToolBrokerAdapter` deze default en `security_officer.py:171` roept die adapter aan.
COUNCIL_AGENT_ID = "copilot"

#: De sleutels van `PAYLOAD_POLICY` die door een modelgekozen `action_type` bereikbaar zijn, met
#: per sleutel WAT er leesbaar van blijft. Gemeten 2026-09-01: dat waren ze alle TWAALF. Sinds
#: 2026-09-21 zijn het DERTIEN -- `schedule_training` kwam erbij, en ook die is bereikbaar: geen
#: enkele sleutel wordt door de vormbeperking afgewezen.
#:
#: Hier staat GEEN bewering meer over het `copilot`-profiel. Die stond er wel ("TOEGESTAAN (:41)"
#: / "GEVETOD"), werd door niets getoetst, en een onware toelichting is erger dan geen toelichting.
#: De bewering leeft nu in `COPILOT_MAY_EXECUTE` en wordt gemeten door
#: `test_every_reachable_key_matches_its_profile_claim`.
REACHABLE_POLICY_KEYS: dict[str, str] = {
    "create_task": "leesbaar: priority/status (opsomming)",
    "list_tasks": "leesbaar: skip (bereik), limit (bereik), status (opsomming)",
    "update_task": "leesbaar: priority/status (opsomming)",
    "delete_task": "readable is leeg, dus niets leesbaar",
    "query_hr_database": "leesbaar: offset (bereik), limit (bereik)",
    "analyze_skill_gap": "idem, zelfde vocabulaire en grenzen",
    # Toegevoegd 2026-09-21 met de tool zelf. Leesbaar blijft ALLEEN `status`, en dat is een
    # opsomming uit `EMPLOYEE_TRAINING_STATUSES` (3 waarden = log2(3) = 1,585 bits, dus ver
    # onder de vastgepinde bovengrens). `user_email` en `training_name` zijn met opzet NIET
    # leesbaar: het eerste wijst een persoon aan, het tweede is qua vorm niet te onderscheiden
    # van een persoonsnaam -- zelfde grond als `role` bij de leestools.
    "schedule_training": "leesbaar: status (opsomming)",
    # Toegevoegd 2026-10-24 (crediteuren dag 2) met de tools zelf. Niets is leesbaar (`readable` is leeg): een leverancier,
    # een IBAN, een factuurnummer, een bedrag en de zin met het waarom zijn bedrijfsgegevens of vrije tekst en worden een
    # digest. Het IBAN in het ticket is bovendien gemaskeerd (`payables_registry.maskeer_iban`).
    "record_supplier_invoice": "readable is leeg, dus niets leesbaar",
    "propose_supplier_invoice": "readable is leeg, dus niets leesbaar",
    # Toegevoegd 2026-10-25 (crediteuren dag 3): het betaalvoorstel. Niets leesbaar: leveranciersnamen, gemaskeerde IBAN's, bedragen en
    # de zin met het waarom zijn bedrijfsgegevens en worden een digest; de volledige lijst staat alleen in het ticket.
    "propose_payment_run": "readable is leeg, dus niets leesbaar",
    # Toegevoegd 2026-10-05 met de debiteurentools (dag 2). Leesbaar alleen opsommingen en de
    # paginering; adres, onderwerp en tekst van de brief zijn met opzet digest.
    "list_receivables": "leesbaar: limit/offset (bereik), status (opsomming)",
    "send_payment_reminder": "leesbaar: kind (opsomming)",
    "local__send_email": "readable is leeg",
    "local__llm_generate": "readable is leeg",
    "local__read_file": "readable is leeg",
    "test__echo": "params en readable zijn beide leeg",
    "test__fail": "readable is leeg",
    "test__slow": "leesbaar: delay_seconds (bereik)",
}

#: De bereikbare sleutels die de copilot ook mag UITVOEREN volgens het `copilot`-profiel in
#: `config/tool_permissions.yml:33-56` (namespace `council_action`). Dat onderscheid is de kern
#: van OP-34: bij een toegestane tool is een leesbare `skip`/`limit` per ontwerp verdedigbaar, bij
#: een geweigerde is er geen uitvoering om hem aan te verdedigen -- en `persist()` schrijft die
#: rij toch. Gemeten tegen `ToolPermissionManager.is_tool_allowed`, dus langs dezelfde weg als
#: `security_officer.py:171`.
COPILOT_MAY_EXECUTE: frozenset[str] = frozenset(
    {"create_task", "list_tasks", "update_task", "delete_task"}
)

#: De GEMETEN bovengrens van wat een modelgekozen `action_type` leesbaar in
#: `council_decisions.action_params` kan zetten, in bits, over EEN voorstel (het model kiest per
#: voorstel EEN `action_type`, dus dit is het maximum over de bereikbare sleutels en niet de som).
#:
#: Gemeten 2026-09-01 met:
#:   python -m pytest tests/architecture/test_council_action_type_policy_reachability.py \
#:     -k readable_upper_bound -q
#: Uitkomst: `list_tasks` = log2(100001) + log2(1001) + log2(5) = 28.8988 bits
#: (skip 0..100_000, limit 0..1_000, status uit `TaskStatusLiteral`). Daarna:
#: `query_hr_database`/`analyze_skill_gap` 26.5769, `test__slow` 11.8142, `create_task`/
#: `update_task` 4.3219, de rest 0.
#:
#: Dit getal verving de tekst "~27 bits" die eerder in deze module en in
#: `tests/unit/copilot/test_council_persist_leaks_nothing.py` stond. Die 27 was de waarde van
#: `query_hr_database` en werd ten onrechte ook aan `list_tasks` toegeschreven; niemand kon hem
#: herleiden omdat geen test hem berekende.
PINNED_MAX_READABLE_BITS = 28.8988

#: Tolerantie op de vastpinning hierboven. Klein genoeg dat een extra leesbaar veld (minimaal
#: log2(2) = 1 bit) er altijd doorheen breekt, ruim genoeg voor drijvende-kommaruis.
BITS_TOLERANCE = 0.001

#: Vrije-tekstwaarden die GEEN enkele `readable`-vorm mag accepteren. Gemengd met opzet: een
#: waarde die op een parameternaam lijkt (`PII_THAT_FITS_THE_SHAPE` uit de unit-test), een
#: e-mailadres, een BSN-achtig nummer als STRING, en een lege string.
FREE_FORM_VALUES: tuple[object, ...] = (
    "Jan_Jansen_salaris_82000",
    "jan.jansen@acme.nl",
    "123456782",
    "Finance Analyst",
    "",
    "pending extra tekst",
)

#: Bovengrens waarboven de bereik-meting hieronder opgeeft. Een `readable`-bereik dat verder reikt
#: dan dit is per definitie geen "een handvol bits" meer en hoort een eigen beoordeling te krijgen.
_RANGE_PROBE_CEILING = 2**40


def _action_shape_constraints() -> tuple[str, int]:
    """Patroon en maximumlengte STRUCTUREEL uit `CopilotAction.model_fields["action"]`.

    Dit is de rekenbron voor de bereikbaarheid, niet de literals bovenaan deze module. Pydantic
    v2 legt `max_length=` neer als `annotated_types.MaxLen` en `pattern=` als een intern
    metadata-object met een `pattern`-attribuut; beide worden hier op OBJECT gezocht en hun
    attribuut wordt gelezen. Er wordt niets in een `repr()` gezocht -- dat was de vorige aanpak en
    daar paste "64" ook in "640".
    """
    field = CopilotAction.model_fields["action"]

    max_lengths = [m.max_length for m in field.metadata if isinstance(m, annotated_types.MaxLen)]
    patterns = [
        m.pattern
        for m in field.metadata
        if not isinstance(m, annotated_types.MaxLen)
        and isinstance(getattr(m, "pattern", None), str)
    ]

    assert len(max_lengths) == 1, (
        f"`CopilotAction.action` heeft {len(max_lengths)} MaxLen-constraints in plaats van 1: "
        f"{field.metadata!r}. Deze guard leest de maximumlengte daaruit; zonder precies een "
        "constraint is niet vast te stellen welke policy-sleutels bereikbaar zijn."
    )
    assert len(patterns) == 1, (
        f"`CopilotAction.action` heeft {len(patterns)} patroon-constraints in plaats van 1: "
        f"{field.metadata!r}. Zonder patroon staat de naam volledig vrij en is de verzameling "
        "bereikbare PAYLOAD_POLICY-sleutels niet meer af te leiden."
    )
    return patterns[0], max_lengths[0]


def _reachable_policy_keys() -> set[str]:
    """De `PAYLOAD_POLICY`-sleutels die de ECHTE schemabeperking passeren."""
    pattern_text, max_length = _action_shape_constraints()
    pattern = re.compile(pattern_text)
    return {key for key in PAYLOAD_POLICY if pattern.match(key) and len(key) <= max_length}


def _range_cardinality(shape: Callable[[object], bool]) -> int:
    """Hoeveel gehele getallen accepteert deze bereik-vorm? Gemeten door te PROBEREN.

    Geen closure-inspectie en geen naam van een vrije variabele -- dat is precies de
    classificatie-op-een-naam die `redaction.py:127-133` (OP-51) als fout beschrijft. De vorm is
    monotoon op 0..N, dus exponentieel zoeken plus bisectie geeft de exacte bovengrens.
    """
    assert not shape(-1), (
        "Een bereik-vorm accepteert een negatief getal. Deze meting gaat uit van een bereik dat "
        "bij 0 begint; is dat niet meer zo, breid de meting uit voordat je de bovengrens pint."
    )
    assert shape(0), (
        "Een bereik-vorm accepteert 0 niet. Deze meting gaat uit van een bereik dat bij 0 begint; "
        "is dat niet meer zo, breid de meting uit voordat je de bovengrens pint."
    )

    hoog = 1
    while shape(hoog):
        hoog *= 2
        assert hoog <= _RANGE_PROBE_CEILING, (
            f"Een bereik-vorm accepteert nog waarden boven {_RANGE_PROBE_CEILING}. Dat is geen "
            "'een handvol bits' meer en hoort een eigen beoordeling te krijgen in ADR-036 OP-34."
        )
    laag = hoog // 2
    while laag + 1 < hoog:
        midden = (laag + hoog) // 2
        if shape(midden):
            laag = midden
        else:
            hoog = midden
    return laag + 1


def _enumeration_source(shape: Callable[[object], bool], label: str) -> frozenset[str]:
    """De verzameling waaruit deze opsomming put, uit de CLOSURE van de vorm.

    **Waarom niet proberen.** Een eerste versie mat de omvang door de vorm te bevragen met elke
    waarde uit `TaskStatusLiteral`/`TaskPriorityLiteral`. Dat is een ONDERGRENS en geen meting: een
    vorm die de vijf gedeclareerde statussen accepteert PLUS `"extra_status"` kwam op precies 5
    uit, en de guard bleef GROEN. Gemeten -- dat was mutatie B6, en pas met de closure-meting werd
    die rood.

    **Waarom dit geen classificatie-op-een-naam is.** `redaction.py:127-133` (OP-51) beschrijft
    de fout van een vormsoort herkennen aan de NAAM van een vrije variabele (`maximum`). Hier
    wordt niet naar een naam gekeken: elke cel van de closure wordt op TYPE en op GEDRAG bekeken
    en er moet er precies EEN zijn die een verzameling strings oplevert. Een enumeratie-vorm die
    zijn bron niet zo draagt maakt deze meting ROOD in plaats van stil te laag.
    """
    kandidaten: list[frozenset[str]] = []
    for cel in getattr(shape, "__closure__", None) or ():
        inhoud = cel.cell_contents
        if callable(inhoud):
            try:
                inhoud = inhoud()
            except Exception:  # noqa: BLE001 -- een cel die geen bron is mag niets kosten
                continue
        if (
            isinstance(inhoud, (frozenset, set))
            and inhoud
            and all(isinstance(v, str) for v in inhoud)
        ):
            kandidaten.append(frozenset(inhoud))

    assert len(kandidaten) == 1, (
        f"{label} draagt {len(kandidaten)} herkenbare opsomming-bronnen in zijn closure in plaats "
        "van 1, dus de omvang van de opsomming is niet te meten. `_one_of` "
        "(`redaction.py:157-172`) sluit over de callable die de gedeclareerde verzameling "
        "oplevert; een nieuwe enumeratie-factory moet zijn bron net zo dragen, anders telt deze "
        "meting hem te laag en is `PINNED_MAX_READABLE_BITS` onwaar."
    )
    return kandidaten[0]


def _enumeration_cardinality(shape: Callable[[object], bool], label: str) -> int:
    """Hoeveel waarden accepteert deze opsomming-vorm? De omvang van zijn eigen bron.

    De bron komt uit `_enumeration_source()`; deze functie toetst daarnaast dat de vorm zich ook
    ALS dat lidmaatschap gedraagt. Zonder die twee asserties zou een vorm die zijn bron netjes
    draagt maar in werkelijkheid alles doorlaat op de omvang van die bron worden geteld.
    """
    bron = _enumeration_source(shape, label)

    geweigerd = sorted(v for v in bron if not shape(v))
    assert not geweigerd, (
        f"{label} draagt een bron met {sorted(bron)} maar weigert {geweigerd}. De vorm en zijn "
        "bron lopen uit elkaar; dan meet de omvang van de bron niet wat er leesbaar blijft."
    )

    #: Een waarde die met zekerheid niet in een gedeclareerde opsomming staat. Accepteert de vorm
    #: hem toch, dan is hij geen lidmaatschapstoets meer en zegt de omvang van zijn bron niets.
    kanarie = "kanarie_geen_gedeclareerde_code_0f3a"
    assert kanarie not in bron, "de kanariewaarde is per ongeluk een gedeclareerde code geworden"
    assert not shape(kanarie), (
        f"{label} accepteert {kanarie!r}, een waarde die niet in zijn eigen bron staat. Dit is "
        "geen lidmaatschapstoets meer maar een vormpatroon, en dan is de omvang van de bron geen "
        "bovengrens. Zie ook `test_no_readable_shape_admits_a_free_form_string`."
    )
    return len(bron)


def _readable_bits(tool_name: str) -> float:
    """Hoeveel bits maakt deze policy leesbaar? De som over zijn `readable`-velden."""
    bits = 0.0
    for field, shape in sorted(PAYLOAD_POLICY[tool_name].readable.items()):
        kind = getattr(shape, "shape_kind", None)
        label = f"{tool_name}.{field}"
        if kind == "range":
            bits += math.log2(_range_cardinality(shape))
        elif kind == "enumeration":
            bits += math.log2(_enumeration_cardinality(shape, label))
        else:
            raise AssertionError(
                f"{label} heeft een onbekende `shape_kind` ({kind!r}). Een nieuwe vormsoort moet "
                "hier een meetregel krijgen, anders telt hij niet mee in de vastgepinde "
                "bovengrens van ADR-036 OP-34."
            )
    return bits


def _measured_max_readable_bits() -> tuple[str, float]:
    """De zwaarste bereikbare policy en zijn bits."""
    gemeten = {key: _readable_bits(key) for key in _reachable_policy_keys()}
    zwaarste = max(gemeten, key=lambda k: (gemeten[k], k))
    return zwaarste, gemeten[zwaarste]


@pytest.mark.architecture
def test_the_documented_constraints_match_the_real_schema() -> None:
    """De literals bovenaan zijn documentatie -- deze test bewaakt dat ze waar blijven.

    Dit is een STRUCTUURtoets: `_action_shape_constraints()` leest `MaxLen.max_length` en het
    `pattern`-attribuut van de constraint-objecten. De vorige versie deed
    `assert str(64) in repr(field.metadata) + repr(field.annotation)`.

    Mutaties (uitgevoerd 2026-09-01, in een KOPIE van `copilot/schemas.py`, per element van de
    verzameling {pattern, max_length}):
      - `max_length=64` -> `max_length=640`: de oude tekstzoekactie bleef GROEN ("64" zit in
        "640"), deze test wordt ROOD op de max_length-assertie. Dit is de mutatie uit de
        review-bevinding MEDIUM-1.
      - `max_length=64` -> `max_length=63`: ROOD.
      - `pattern=r"^[a-z][a-z0-9_]*$"` -> `r"^[a-z]+$"`: ROOD.
      - `pattern=` helemaal weggelaten: ROOD op de patroon-assertie in
        `_action_shape_constraints()` (0 in plaats van 1 patroon-constraint).
      - huidige staat -> GROEN.
    """
    gemeten = _action_shape_constraints()
    gedocumenteerd = (DOCUMENTED_ACTION_PATTERN, DOCUMENTED_ACTION_MAX_LENGTH)

    assert gemeten == gedocumenteerd, (
        f"`CopilotAction.action` heeft nu pattern/max_length {gemeten}. De documentatie bovenaan "
        f"deze module zegt {gedocumenteerd}. Werk die bij en meet opnieuw welke "
        "PAYLOAD_POLICY-sleutels erdoor komen -- de bereikbaarheid hieronder rekent met het ECHTE "
        "schema, dus die schuift stil mee als je hier niets doet."
    )


@pytest.mark.architecture
def test_the_shape_constraint_blocks_no_policy_key() -> None:
    """De vastpinning: welke sleutels zijn bereikbaar? Gemeten: alle 12.

    Deze test bestaat om te voorkomen dat iemand concludeert dat OP-78 het probleem heeft
    opgelost. Dat doet hij niet -- geen enkele sleutel wordt door de vorm afgewezen. De
    bereikbaarheid komt uit `_reachable_policy_keys()`, dat het patroon en de maximumlengte uit
    het ECHTE Pydantic-veld leest en niet uit de literals bovenaan.

    Mutaties (uitgevoerd 2026-09-01, beide richtingen):
      - sleutel `"exfiltrate_everything"` aan een kopie van `PAYLOAD_POLICY` toegevoegd -> ROOD,
        met die naam onder "nieuw bereikbaar". Dit is de richting die telt: een nieuwe
        modelkiesbare policy.
      - sleutel `"list_tasks"` uit die kopie verwijderd -> ROOD, onder "niet meer aanwezig".
      - sleutel `"Query_HR"` toegevoegd (hoofdletters, dus het patroon kan hem niet passeren)
        -> GROEN, en dat is correct: onbereikbare sleutels horen de pinning niet te raken. Deze
        mutatie staat er expliciet bij omdat hij de guard scherpstelt op BEREIKBAARHEID en niet
        op "de tabel is gewijzigd".
      - in een kopie van `copilot/schemas.py` `pattern` op `r"^[a-z]+$"` gezet, zodat elke naam
        met een underscore afvalt -> ROOD, met alle TWAALF sleutels onder "niet meer aanwezig".
        Dezelfde mutatie liet de OUDE versie van deze test (commit 5b147b34, die met de
        module-literal rekende) GROEN -- gemeten. Dat is het bewijs voor review-bevinding HIGH:
        de bereikbaarheid komt nu uit het SCHEMA en niet uit de literal bovenaan.
      - huidige staat -> GROEN.
    """
    reachable = _reachable_policy_keys()

    assert reachable == set(REACHABLE_POLICY_KEYS), (
        "De verzameling bereikbare PAYLOAD_POLICY-sleutels is gewijzigd.\n"
        f"  nieuw bereikbaar : {sorted(reachable - set(REACHABLE_POLICY_KEYS))}\n"
        f"  niet meer aanwezig: {sorted(set(REACHABLE_POLICY_KEYS) - reachable)}\n"
        "Elke bereikbare sleutel is een policy die een taalmodel zelf kan kiezen via "
        "`action_type` (ADR-036 OP-34). Voeg de sleutel toe aan `REACHABLE_POLICY_KEYS` MET de "
        "reden, en toets of zijn `readable`-velden vrije tekst toelaten."
    )


@pytest.mark.architecture
def test_the_reachable_key_pinning_is_not_stale() -> None:
    """Een sleutel die uit `PAYLOAD_POLICY` verdwijnt MOET hier ook weg (staleness).

    Zonder deze test blijft een verwijderde tool eeuwig in de lijst staan en suggereert hij een
    oppervlak dat niet meer bestaat -- precies wat er met `local__run_shell` gebeurde
    (verwijderd 2026-08-11, OP-126).

    Mutatie (uitgevoerd 2026-09-01): `"local__run_shell": "..."` aan `REACHABLE_POLICY_KEYS`
    toegevoegd -> ROOD. Huidige staat -> GROEN.
    """
    verdwenen = [key for key in REACHABLE_POLICY_KEYS if key not in PAYLOAD_POLICY]

    assert not verdwenen, (
        f"Deze sleutels staan in `REACHABLE_POLICY_KEYS` maar niet meer in `PAYLOAD_POLICY`: "
        f"{sorted(verdwenen)}. Haal ze hier weg."
    )


@pytest.mark.architecture
def test_every_reachable_key_matches_its_profile_claim() -> None:
    """De TOEGESTAAN/GEVETOD-helft is een BEWERING over `config/tool_permissions.yml` -- meet hem.

    Tot 2026-09-01 stond die bewering als vrije tekst in `REACHABLE_POLICY_KEYS` ("TOEGESTAAN
    (:41)", "GEVETOD -- niet in copilot-profiel") en toetste niets hem. Ze wordt nu per sleutel
    gemeten langs dezelfde weg als productie: `ToolPermissionManager.is_tool_allowed`, aangeroepen
    door `_ToolBrokerAdapter` (`factory.py:150`) namens `security_officer.py:171`.

    Mutaties (uitgevoerd 2026-09-01 op een KOPIE van `config/tool_permissions.yml`, EEN REGEL PER
    ELEMENT van `REACHABLE_POLICY_KEYS`; de 12 runs staan in het rapport):
      - `create_task`, `list_tasks`, `update_task`, `delete_task` elk apart uit `allowed_tools`
        van het `copilot`-profiel gehaald -> ROOD, telkens met die ene sleutel in de melding.
      - `query_hr_database`, `analyze_skill_gap`, `local__send_email`, `local__llm_generate`,
        `local__read_file`, `test__echo`, `test__fail`, `test__slow` elk apart AAN
        `allowed_tools` toegevoegd -> ROOD, telkens met die ene sleutel in de melding.
      - de tweede richting (een legitieme profielwijziging mag NIET blijven hangen):
        `query_hr_database` toegevoegd aan `allowed_tools` EN aan `COPILOT_MAY_EXECUTE` -> GROEN.
        Zonder deze helft zou "eis dat alles GEVETOD is" een geldige oplossing zijn.
      - huidige staat -> GROEN.
    """
    manager = ToolPermissionManager()

    afwijkingen = []
    for key in sorted(REACHABLE_POLICY_KEYS):
        geclaimd = key in COPILOT_MAY_EXECUTE
        gemeten = manager.is_tool_allowed(COUNCIL_AGENT_ID, key)
        if geclaimd != gemeten:
            afwijkingen.append(f"{key}: geclaimd uitvoerbaar={geclaimd}, gemeten={gemeten}")

    assert not afwijkingen, (
        "De bewering over het `copilot`-profiel klopt niet meer met "
        "`config/tool_permissions.yml`:\n  "
        + "\n  ".join(afwijkingen)
        + "\n\nWerk `COPILOT_MAY_EXECUTE` bij. Let op WELKE kant op het schuift: een sleutel die "
        "van GEVETOD naar TOEGESTAAN gaat, geeft de copilot uitvoerrechten op een tool waarvan de "
        "leesbare payload nooit voor dat profiel is beoordeeld (ADR-036 OP-34)."
    )


@pytest.mark.architecture
def test_the_readable_upper_bound_has_not_grown() -> None:
    """De bovengrens in bits wordt BEREKEND uit `PAYLOAD_POLICY`, niet geschat.

    Hier stond eerder geen test maar een getal ("~27 bits") in drie docstrings. Dat getal was de
    waarde van `query_hr_database` en werd ook aan `list_tasks` toegeschreven, dat er een
    status-opsomming bij heeft. Niemand kon het herleiden omdat niets het uitrekende.

    De meting: per bereikbare sleutel de som van log2 van de omvang van elk leesbaar bereik en
    elke opsomming; de bovengrens is het MAXIMUM daarover, want het model kiest per voorstel EEN
    `action_type`.

    Mutaties (uitgevoerd 2026-09-01, in-memory op een kopie van `PAYLOAD_POLICY`, EEN REGEL PER
    ELEMENT van de verzameling vormsoorten {range, enumeration}):
      - range: `list_tasks.skip` van `_bounded_int(100_000)` naar `_bounded_int(1_000_000)`
        -> ROOD, gemeten 32.2207 bits.
      - enumeration: `list_tasks.status` van `_one_of(_task_statuses)` naar een `_one_of` op een
        bron met vijf extra codes -> ROOD, gemeten 29.8988 bits.
      - enumeration, tweede vorm: een vorm die zijn bron wel draagt maar ELKE string accepteert
        -> ROOD op de kanarie-assertie in `_enumeration_cardinality`.
      - enumeration, derde vorm: een vorm die zijn bron draagt maar `"pending"` weigert -> ROOD;
        vorm en bron lopen uit elkaar, dus de omvang van de bron meet niets.
      - enumeration, vierde vorm: `"status"` vervangen door een lambda die de vijf statussen
        PLUS `"extra_status"` accepteert en geen bron draagt -> ROOD ("0 herkenbare
        opsomming-bronnen"). Dit was mutatie B6 en die bleef GROEN toen de meting nog over de
        gedeclareerde waarden PROBEERDE in plaats van de bron te lezen.
      - een leesbaar veld `owner` toegevoegd met `shape_kind = "range"` en grens 1 -> ROOD,
        gemeten 29.8988 bits: een extra veld van 1 bit breekt door `BITS_TOLERANCE` heen.
      - huidige staat -> GROEN.

    De andere richting (de bovengrens KRIMPT) hoort ook rood te worden, anders blijft een te hoge
    pinning staan; dat doet `test_the_pinned_readable_upper_bound_is_not_stale`.
    """
    zwaarste, gemeten = _measured_max_readable_bits()

    assert gemeten <= PINNED_MAX_READABLE_BITS + BITS_TOLERANCE, (
        f"De bovengrens van OP-34 is GEGROEID: `{zwaarste}` maakt nu {gemeten:.4f} bits leesbaar, "
        f"vastgepind stond {PINNED_MAX_READABLE_BITS}. Een modelgekozen `action_type` kan dus "
        "meer door het model gekozen data leesbaar in `council_decisions.action_params` zetten "
        "-- een "
        "hash-geketende rij zonder wisroute (OP-36). Is dit bedoeld, dan hoort er een expliciete "
        "beoordeling bij in ADR-036 OP-34 EN een nieuwe, gedateerde waarde in "
        "`PINNED_MAX_READABLE_BITS`."
    )


@pytest.mark.architecture
def test_the_pinned_readable_upper_bound_is_not_stale() -> None:
    """Een gekrompen bovengrens MOET ook rood zijn -- anders rot de pinning dicht.

    Blijft `PINNED_MAX_READABLE_BITS` te hoog staan nadat een grens is aangescherpt, dan
    suggereert hij een oppervlak dat niet meer bestaat en heeft de guard hierboven stilzwijgend
    ruimte om te groeien tot dat oude getal.

    Mutatie (uitgevoerd 2026-09-01, in-memory op een kopie van `PAYLOAD_POLICY`):
      - `list_tasks.skip` van `_bounded_int(100_000)` naar `_bounded_int(1_000)` -> ROOD; de
        zwaarste bereikbare policy is dan `query_hr_database` met 26.5769 bits tegen een pinning
        van 28.8988.
      - huidige staat -> GROEN.
    """
    zwaarste, gemeten = _measured_max_readable_bits()

    assert gemeten >= PINNED_MAX_READABLE_BITS - BITS_TOLERANCE, (
        f"De bovengrens van OP-34 is GEKROMPEN: `{zwaarste}` maakt nog {gemeten:.4f} bits "
        f"leesbaar, vastgepind staat {PINNED_MAX_READABLE_BITS}. Dat is goed nieuws, maar de "
        "pinning moet mee omlaag -- anders bewaakt de guard hierboven een grens die al is "
        "opgeschoven en kan het lek stil terugkruipen naar de oude waarde."
    )


@pytest.mark.architecture
def test_no_readable_shape_admits_a_free_form_string() -> None:
    """DE guard. Dit is wat de ernst van OP-34 op LAAG houdt.

    Elke `readable`-vorm is vandaag een opsomming of een getalbereik, dus een modelgekozen
    `action_type` kan nooit vrije TEKST leesbaar maken. Komt er een vorm bij die dat wel doet, dan
    wordt hetzelfde ongevalideerde pad een kanaal voor persoonsgegevens in klaartekst en is de
    ernst LAAG niet meer houdbaar -- die keuze moet dan een eigen beoordeling krijgen.

    Mutaties (uitgevoerd 2026-09-01, verruiming, in-memory op een kopie van `PAYLOAD_POLICY`):
      - `list_tasks` een leesbaar veld `note` gegeven met `lambda v: isinstance(v, str)`
        -> ROOD, met veldnaam en waarde in de melding.
      - realistischer: een leesbaar veld `owner` met een regex `^[A-Za-z ]{1,40}$` voor "een
        naam" -> ROOD, betrapt op `"Finance Analyst"`. Deze variant staat erbij omdat de eerste
        te grof is om iets te bewijzen: niemand voegt `isinstance(v, str)` toe, maar een
        naam-regex is precies het soort verruiming dat plausibel lijkt.
      - huidige staat -> GROEN.

    Andersom (de tweede richting, die "weiger alles" uitsluit): een vorm die NIETS accepteert
    houdt DEZE guard groen -- gemeten, mutatie M8b. Die richting wordt daarom afgedekt door
    `test_every_readable_shape_still_accepts_a_legitimate_value` hieronder, en zonder die test is
    de leesbaarheid die AI Act art. 12(2) nodig heeft stil te slopen zonder dat iets rood wordt.
    """
    overtredingen: list[str] = []

    for tool_name, policy in sorted(PAYLOAD_POLICY.items()):
        for field, shape in sorted(policy.readable.items()):
            for value in FREE_FORM_VALUES:
                if shape(value):
                    overtredingen.append(f"{tool_name}.{field} accepteert {value!r}")

    assert not overtredingen, (
        "Een leesbare vorm in `PAYLOAD_POLICY` accepteert vrije tekst:\n  "
        + "\n  ".join(overtredingen)
        + "\n\nDaarmee kan een taalmodel via een zelfgekozen `action_type` "
        "(`audit_writer.py:163-168`, ongevalideerd -- ADR-036 OP-34) een persoonsgegeven in "
        "KLAARTEKST in `council_decisions.action_params` zetten: een JSONB-kolom in een "
        "hash-geketende tabel zonder wisroute (OP-36). Tot nu toe was elke leesbare vorm een "
        "opsomming of een getalbereik en bleef het lek beperkt tot de bits die "
        "`test_the_readable_upper_bound_has_not_grown` meet. Is deze verruiming bedoeld, dan "
        "hoort daar een expliciete herbeoordeling van de ernst bij in ADR-036."
    )


@pytest.mark.architecture
def test_every_readable_shape_still_accepts_a_legitimate_value() -> None:
    """De tweede richting: "weiger alles" is geen geldige oplossing.

    Zonder deze test is de guard hierboven ook groen te krijgen door elke vorm `False` te laten
    teruggeven, en dan is niet meer vast te stellen WAT er gevraagd werd -- de toetsbaarheid die
    AI Act art. 12(2) van de logging verlangt (zie de moduledocstring van `redaction.py`).

    Mutaties (uitgevoerd 2026-09-01, in-memory op een kopie van `PAYLOAD_POLICY`):
      - elke leesbare vorm van `list_tasks` vervangen door `lambda v: False` -> ROOD, met
        `list_tasks.limit (range)` en `list_tasks.skip (range)` in de melding. Diezelfde mutatie
        laat `test_no_readable_shape_admits_a_free_form_string` GROEN -- daarom bestaat deze test.
      - een vorm met een onbekende `shape_kind` (`"brand_new_kind"`) toegevoegd -> ROOD op de
        assertie in de lus. Een nieuwe vormsoort zonder voorbeeldwaarde zou anders ongemerkt
        buiten deze toets vallen (dezelfde fout als OP-51, waar een nieuwe vormsoort door een
        classificatie op een NAAM niet werd gezien).
      - huidige staat -> GROEN.
    """
    from typing import get_args

    from src.domains.tasks.schemas import TaskPriorityLiteral, TaskStatusLiteral

    #: Per vormsoort een waarde die er WEL door moet. `shape_kind` wordt gezet door de
    #: vorm-factories in `redaction.py:136` en `:154` en is al bewaakt door
    #: `test_tool_policy_matches_the_tools.py:457-477`.
    kandidaten: dict[str, tuple[object, ...]] = {
        "range": (0, 1),
        "enumeration": get_args(TaskStatusLiteral)
        + get_args(TaskPriorityLiteral)
        # Debiteurentools (2026-10-05): een geldige status en een geldige soort brief.
        + ("open", "herinnering"),
    }

    doden: list[str] = []

    for tool_name, policy in sorted(PAYLOAD_POLICY.items()):
        for field, shape in sorted(policy.readable.items()):
            kind = getattr(shape, "shape_kind", None)
            assert kind in kandidaten, (
                f"{tool_name}.{field} heeft een onbekende `shape_kind` ({kind!r}). Een nieuwe "
                "vormsoort moet hier een legitieme voorbeeldwaarde krijgen, anders toetst deze "
                "guard hem niet en kan hij ongemerkt niets meer accepteren."
            )
            if not any(shape(value) for value in kandidaten[kind]):
                doden.append(f"{tool_name}.{field} ({kind})")

    assert not doden, (
        "Deze leesbare vormen accepteren geen enkele legitieme waarde meer: "
        f"{doden}. De redactie is dan feitelijk 'digest alles' geworden en het auditspoor is "
        "waardeloos -- dat is geen fix van OP-34 maar het uitzetten van de leesbaarheid."
    )

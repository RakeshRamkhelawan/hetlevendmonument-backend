"""Architecture test: geen tool-payload gaat rauw naar een bewarende sink (ADR-036 OP-27).

Een tool-payload is bij agent-gedreven uitvoering de `json.loads` van een `TOOL_CALL`-directive
en dus modeloutput. Die dict gaat naar de event bus, de leeropslag, de ADR-019 auditketen en de
proces-globale uitvoeringsgeschiedenis -- alle vier bewarend, de derde onuitwisbaar. Deze guard
eist dat elke plek die zo'n sink voedt de geredigeerde variant meekrijgt.

**Een naam als contract.** De enige waarde die een sink mag ontvangen heet `publish_payload`.
Dat is geen stijlregel maar de handhavingshaak: de guard kan niet zien of een dict geredigeerd
IS, alleen of hij uit de enige plek komt waar redactie gebeurt. Daarom is de naam het contract,
en heet de parameter van `_publish_tool_event` ook zo.

**Positief formuleren, niet negatief.** Een eerdere opzet zocht naar de spelling
`payload=payload`. Dat vangt precies een geval: een alias (`payload=hr_payload`), een kopie
(`dict(payload)`) of een positioneel argument glipt er allemaal door.

**Drie vormen, want twee waren niet genoeg (ronde 2).** De vorige versie keek alleen naar
keyword-argumenten met een bekende naam. Een gemeten probe met twee overtredingen in het
bewaakte pad -- `repo.log_execution(**{"tool_input": payload})` en
`store["x"] = {"payload": payload}` -- liet alle vijf tests groen: `**`-unpacking heeft
`keyword.arg is None` en werd overgeslagen, en een dict-assignment is geen aanroep. Beide zijn
nu overtredingen, en dat is met synthetische bronnen in BEIDE richtingen getoetst: de guard
betrapt de overtreding, en verwerpt de correcte vorm niet.

**De VIJFDE sink: het raadsbesluit (ADR-036 OP-48, 2026-08-31).** `SCAN_ROOTS` dekte alleen
`tool_broker`, dus `council_decisions.action_params` -- dezelfde modeloutput, JSONB NOT NULL, in
een gehashte keten -- lag volledig buiten deze guard. Dat pad is vandaag correct
(`audit_writer.py::persist` redigeert), maar een regressie daar was onzichtbaar. Toegevoegd:
`src/core/copilot/council` aan `SCAN_ROOTS`, `action_params` aan `GUARDED_DICT_KEYS` en
`GUARDED_KEYWORDS`, `CouncilDecisionRow` aan `SINKS`. Mutatiebewijs: een regel per toegevoegd
element, met de meting van VOOR de uitbreiding ernaast.

Drie dingen bleken daarbij nodig om de guard eerlijk te houden:

1. **Een tweede veilige naam, MET een PAKKET-BREDE herkomstcontrole.** Het raadspad noemt zijn
   geredigeerde dict `published_params`. Alleen de naam toelaten zou de handhavingshaak slap
   maken, dus `test_every_safe_name_really_comes_from_the_redactor` eist dat elke toekenning aan
   een naam uit `SAFE_NAMES` uit een `redact_for_publication(...)`-aanroep komt.

   Die controle dekte eerst maar EEN bestand, en dat was het gat (onafhankelijke Gate 2,
   2026-08-31): `SAFE_NAMES` geldt overal onder `SCAN_ROOTS`, maar de herkomst werd alleen in
   `audit_writer.py` nagegaan. Een reviewer maakte een TWEEDE raadsschrijfpad met
   `published_params = proposal.action_params` en `CouncilDecisionRow(action_params=...)`, en de
   hele suite bleef groen -- 11 passed. Dat is woordelijk het scenario waarvoor OP-48 bestaat.
   Nu loopt de controle over elk bewaakt bestand, en is opnieuw gemeten: hetzelfde tweede pad
   geeft ROOD, een tweede pad dat wel redigeert blijft GROEN.

   Een toekenning die geen runtime-waarde kan dragen telt niet mee. `publish_payload: dict = {}`
   staat in `tool_broker/service.py:378` en `api/v1/tool_broker/execution_router.py:69` als
   initialisatie voordat de redactor zijn werk doet; die als overtreding rekenen is een valse
   positieve, en een guard met valse positieven wordt uitgezet in plaats van gevolgd.
2. **Vrijstellingen per SCOPE in plaats van per BESTAND.** `audit_writer.py` bevat beide soorten:
   een valse positief in de pure `compute_canonical_json` en de ECHTE sink in `persist`. Een
   bestandsbrede uitzondering had de sink die OP-48 wil bewaken meteen weer blind gemaakt --
   gemeten, zie de mutatietabel.
3. **Een dict-waarde van uitsluitend constanten is geen payload.** Dat kost twee valse
   positieven in `members/compliance_officer.py` (een vaste `ai_disclosure`-instructiestring) en
   maakt de uitzondering voor `schemas.py` overbodig -- die is vervallen, afgedwongen door de
   staleness-test zelf.

AST en geen grep: een aanroep die over meerdere regels is geformatteerd ontsnapt aan een
tekstuele zoekactie. Paden vanaf `__file__` en niet CWD-relatief.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Breder dan alleen service.py: `log_execution` is een publieke methode, dus een toekomstige
# aanroeper elders moet ook gedekt zijn. De API-laag hoort erbij sinds daar de vierde sink zit.
SCAN_ROOTS = (
    REPO_ROOT / "src/core/tool_broker",
    REPO_ROOT / "src/core/api/v1/tool_broker",
    # ADR-036 OP-48, toegevoegd 2026-08-31. Het raadsbesluit-schrijfpad is de VIJFDE bewarende
    # sink: `council_decisions.action_params` (JSONB, NOT NULL) krijgt dezelfde door een
    # taalmodel geschreven dict die op het toolpad als `payload` langskomt, en de rij gaat in
    # een gehashte keten. Dat pad is vandaag correct -- `audit_writer.py::persist` redigeert --
    # maar het lag volledig buiten deze guard, dus een regressie daar was onzichtbaar.
    REPO_ROOT / "src/core/copilot/council",
)
EXTRA_SCAN_FILES = (REPO_ROOT / "src/core/api/v1/tool_broker_shared.py",)

REDACTION = REPO_ROOT / "src/core/tool_broker/redaction.py"
HITL_WRITE_PATH = REPO_ROOT / "src/core/tool_broker/router.py"
COUNCIL_WRITE_PATH = REPO_ROOT / "src/core/copilot/council/audit_writer.py"

#: De namen waaronder een geredigeerde waarde een sink mag bereiken.
#:
#: TWEE namen sinds 2026-08-31 (OP-48), en dat is een afweging en geen verwatering. Het
#: raadspad noemt zijn geredigeerde dict `published_params` -- de uitkomst van dezelfde
#: `redact_for_publication()`. De naam is hier de handhavingshaak, dus een tweede naam
#: toelaten zou hem slap maken als er niets tegenover stond: daarom eist
#: `test_the_council_safe_name_really_comes_from_the_redactor` dat `published_params` in
#: `audit_writer.py` daadwerkelijk uit een `redact_for_publication`-aanroep wordt toegekend.
#: Zonder die tweede eis was `published_params = proposal.action_params` groen gebleven -- de
#: exacte vorm die deze guard hoort te vangen (gemeten, zie die test).
SAFE_NAMES = frozenset({"publish_payload", "published_params"})

#: Methodes die de payload in een bewarende opslag zetten.
#: Bewust ZONDER `create`, en dat is gemeten en niet gegokt (2026-08-04, ronde 6).
#:
#: De WRITE naar `hitl_tickets.payload` was onzichtbaar voor deze guard -- `hitl_repository.py:176`
#: doet `self.create(payload=payload)` en `create` stond niet in deze lijst, terwijl de gedateerde
#: uitzondering op `hitl_store.py` alleen de READ-projectie dekte. Dat is de VIJFDE keer in deze
#: reeks dat een naamlijst een token te kort was, nu in de sink-enumeratie zelf (ADR-036 OP-47).
#:
#: `create` toevoegen loste dat niet goed op. Gemeten: 3 treffers op keyword-argumenten (de twee
#: HITL-paden plus de niet-gemounte `router.py:557`), maar de guard kijkt OOK naar positionele
#: argumenten en vlagde daarmee `business_registry.py:133` -- `service.create(task_in)`, de tool die
#: zijn werk doet met een gevalideerd Pydantic-model. Dat is geen sink en geen uitzondering; het als
#: uitzondering registreren zou de lijst vervuilen met iets wat gewoon correct is, en een guard met
#: valse positieven wordt uitgezet in plaats van vervuld.
#:
#: Het HITL-schrijfpad heeft daarom een EIGEN guard met een gedateerde uitzondering en een
#: staleness-test: `tests/architecture/test_hitl_ticket_write_is_registered.py`.
#:
#: `CouncilDecisionRow` erbij sinds 2026-08-31 (OP-48). Dat is een MODELCONSTRUCTOR en geen
#: methode, en juist daarom hoort hij hier: de rij wordt met `session.add()` weggeschreven, dus
#: de constructie IS het schrijfmoment. `audit_writer.py:259` is de enige aanroep.
SINKS = frozenset({"_publish_tool_event", "log_execution", "CouncilDecisionRow"})

#: Keyword-argumenten van die methodes die de payload dragen.
#: `action_params` erbij sinds 2026-08-31 (OP-48): dat is de naam waaronder de modeloutput het
#: raadspad binnenkomt (`types.py`, `Proposal.action_params`) en de kolomnaam in
#: `council_decisions`.
GUARDED_KEYWORDS = frozenset({"payload", "tool_input", "publish_payload", "action_params"})

#: Sleutels in een dict-literal die een payload dragen. VIER spellingen, want dit is de
#: vierde keer in deze reeks dat een naamlijst een token te kort was: `mcp_client.py` zette
#: de rauwe payload onder `arguments` in een exceptie-context en bleef daardoor onzichtbaar.
#: `params` is bewust NIET opgenomen -- die naam komt alleen voor in OpenAPI-voorbeelden en
#: leverde uitsluitend valse positieven op. Een guard die rood staat om de verkeerde reden
#: wordt uitgezet, niet vervuld. `tool_execution_history[id] = {...}` is
#: een assignment en geen aanroep; zonder deze regel bleef de vierde sink onzichtbaar.
#: `action_params` erbij sinds 2026-08-31 (OP-48), zelfde reden als bij GUARDED_KEYWORDS.
GUARDED_DICT_KEYS = frozenset({"payload", "arguments", "tool_input", "action_params"})

#: Bestanden met een rauwe payload in een dict die NIET naar een bewarende sink gaat.
#: Gedateerd, met reden per regel; de staleness-test hieronder houdt hem eerlijk.
#:
#: LEEG sinds ronde 3, en die leegte is verdiend en niet vergeten. `clients.py` stond hier met
#: als reden "de exceptie-context is de foutpad-familie, die wordt in OP-29 gedicht". Dat bleek
#: een onderschatting: `ToolBrokerException` zet zijn context in `detail`, Starlette rendert dat
#: in `str(exception)`, en `execution_router.py` schreef dat in een API-uitleesbare regel. De
#: payload is daarom bij de BRON uit die context gehaald in plaats van hier geparkeerd.
#: De staleness-test hieronder heeft die uitzondering zelf omgeduwd zodra dat gebeurde.
#: Sleutel is `pad::gekwalificeerde scope` en niet meer alleen `pad` (2026-08-31, OP-48). Een
#: bestandsbrede uitzondering was te grof: `audit_writer.py` bevat een valse positief EN de
#: echte sink, en per bestand overslaan had die sink meteen weer blind gemaakt.
KNOWN_RAW_PAYLOAD_SITES: dict[str, str] = {
    "src/core/tool_broker/hitl_store.py::_ticket_to_dict": (
        "2026-08-03, BEWUSTE UITZONDERING (geen openstaand punt) -- het HITL-ticket toont de "
        "echte waarden aan de mens die de actie goedkeurt. Redigeren zou het toezicht uit AI Act "
        "art. 14 een formaliteit maken. Zie ook OP-31: dat de GOEDKEURDER dit mag zien "
        "rechtvaardigt niet dat /tools/hitl/audit het tenantbreed en permanent uitlevert."
    ),
    # VERVALLEN 2026-08-31: `src/core/tool_broker/schemas.py::ToolHITLRequest` stond hier sinds
    # 2026-08-03 als valse positief (`json_schema_extra` OpenAPI-voorbeelden). Die uitzondering
    # is niet meer nodig: `_carries_runtime_data()` ziet nu dat de voorbeeldwaarde een dict van
    # uitsluitend CONSTANTEN is en dus geen runtime-payload kan dragen. De staleness-test
    # hieronder heeft dat zelf afgedwongen -- hij werd rood op precies deze regel zodra de
    # structurele check erin zat. Dat is waarvoor die test bestaat.
    "src/core/copilot/council/audit_writer.py::CouncilAuditWriter.compute_canonical_json": (
        "2026-08-31, VALSE POSITIEF (OP-48) -- deze functie is PUUR: ze bouwt een dict, geeft "
        "`json.dumps(...)` terug en bewaart niets. De enige aanroeper is `persist()` op "
        "`audit_writer.py:246-252`, en die geeft `proposal=redacted_proposal` mee -- de "
        "`replace()`-kopie met `action_params=published_params` uit `:184-186`. De waarde is hier "
        "dus al geredigeerd; de statische check kan dat niet zien omdat de parameter `proposal` "
        "heet. Rechtstreeks nagemeten op het aanroep-keyword, niet aangenomen. Redigeren MAG "
        "hier ook niet: drie verifiers (`chain_verifier.py:92`, `report_generator.py:72-100`, "
        "`forensics.py`) rekenen de hash na uit de opgeslagen rij, en een tweede redactie geeft "
        "een andere hash -- dan meldt elke historische rij zich als gemanipuleerd."
    ),
    "src/core/tool_broker/audit_utils.py::compute_audit_hash": (
        "2026-08-26, VALSE POSITIEF (OP-28) -- `compute_audit_hash`'s `data`-dict is geen sink, "
        "de functie retourneert alleen een sha256-digest en bewaart de dict zelf nergens. De "
        "enige aanroeper, `audit_repository.py::log_execution`, ontvangt zijn `tool_input`-"
        "parameter van `service.py:573`: `tool_input=publish_payload` -- rechtstreeks "
        "nagetraceerd, niet aangenomen. De waarde is dus al geredigeerd voordat hij hier "
        "aankomt; de statische check kan dat alleen niet zien over een functiegrens heen, "
        "omdat de parameternaam hier `tool_input` heet en niet `publish_payload`."
    ),
}


def _relative(path: Path) -> str:
    """Repo-relatief pad met schuine strepen, zodat de uitzonderingslijst eenduidig is."""
    return path.relative_to(REPO_ROOT).as_posix()


def _sink_call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return str(getattr(func, "id", ""))


def _is_the_redacted_value(node: ast.expr) -> bool:
    """Is dit exact een geredigeerde payload?"""
    return isinstance(node, ast.Name) and node.id in SAFE_NAMES


#: Knooptypes die naar een waarde van BUITEN de brontekst verwijzen.
_RUNTIME_REFERENCES = (ast.Name, ast.Attribute, ast.Call, ast.Subscript, ast.Starred)


def _carries_runtime_data(node: ast.expr) -> bool:
    """Kan deze expressie een runtime-payload dragen, of is hij volledig uit literalen opgebouwd?

    Een dict-literal met uitsluitend constanten erin is AUTEURSTEKST en geen modeloutput; die
    kan per definitie geen persoonsgegeven lekken. Zonder dit onderscheid keurde de uitbreiding
    naar `src/core/copilot/council` twee correcte plekken af:
    `members/compliance_officer.py:135` en `:242` zetten
    `evidence={"modifications": {"action_params": {"ai_disclosure": "..."}}}` -- een vaste
    instructie-string, geen payload. Dat zijn precies de valse positieven waardoor een guard
    wordt uitgezet in plaats van vervuld, en registreren als uitzondering zou de lijst vervuilen
    met iets wat gewoon correct is.
    """
    return any(isinstance(inner, _RUNTIME_REFERENCES) for inner in ast.walk(node))


def _scoped_nodes(node: ast.AST, stack: tuple[str, ...]) -> Iterator[tuple[ast.AST, str]]:
    """Elke knoop met de GEKWALIFICEERDE naam van de functie of klasse waarin hij leeft.

    Bestond niet voor 2026-08-31, en dat was het echte probleem met de uitzonderingslijst: die
    sloeg een heel BESTAND over. `audit_writer.py` heeft beide soorten in zich -- een valse
    positief in `compute_canonical_json` en de ECHTE sink in `persist` -- dus een
    bestandsbrede uitzondering had de sink die OP-48 wil bewaken meteen weer blind gemaakt.
    """
    label = ".".join(stack) if stack else "<module>"
    yield node, label
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _scoped_nodes(child, stack + (child.name,))
        else:
            yield from _scoped_nodes(child, stack)


def offenders_in_source(where: str, source: str, exempt: frozenset[str] = frozenset()) -> list[str]:
    """Alle overtredingen in een bronbestand.

    Neemt de brontekst en niet een pad, zodat de guard zelf op synthetische bronnen
    mutatie-getest kan worden -- in beide richtingen.

    `exempt` bevat gekwalificeerde scope-namen (`Klasse.methode`) die worden overgeslagen; zie
    `KNOWN_RAW_PAYLOAD_SITES`.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    offenders: list[str] = []
    safe = " of ".join(sorted(SAFE_NAMES))

    for node, scope in _scoped_nodes(tree, ()):
        if scope in exempt:
            continue

        if isinstance(node, ast.Call) and _sink_call_name(node) in SINKS:
            label = f"{where}:{node.lineno} {_sink_call_name(node)}(...)"
            if node.args:
                offenders.append(f"{label} geeft positionele argumenten door")
            for keyword in node.keywords:
                if keyword.arg is None:
                    offenders.append(
                        f"{label} gebruikt **-unpacking, dus welke waarde de sink krijgt is "
                        "niet meer statisch vast te stellen"
                    )
                elif keyword.arg in GUARDED_KEYWORDS and not _is_the_redacted_value(keyword.value):
                    offenders.append(f"{label} {keyword.arg}= is niet {safe}")

        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in GUARDED_DICT_KEYS
                    and not _is_the_redacted_value(value)
                    and _carries_runtime_data(value)
                ):
                    offenders.append(
                        f'{where}:{node.lineno} dict-sleutel "{key.value}" krijgt niet {safe}'
                    )

    return offenders


def _guarded_sources() -> Iterator[tuple[Path, str]]:
    """Elk bewaakt bronbestand met zijn inhoud."""
    paths: list[Path] = []
    for root in SCAN_ROOTS:
        if root.exists():
            paths.extend(sorted(root.rglob("*.py")))
    paths.extend(path for path in EXTRA_SCAN_FILES if path.exists())

    for path in paths:
        try:
            yield path, path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue


def _sink_calls_per_name() -> dict[str, int]:
    """Hoeveel aanroepen er per naam uit `SINKS` gevonden worden.

    PER NAAM en niet als totaal, en dat verschil is gemeten (onafhankelijke Gate 2,
    2026-08-31). Het vangnet was `totaal >= 8` terwijl er 10 aanroepen zijn, en de
    net-toegevoegde raadssink draagt er precies EEN bij. `CouncilDecisionRow` hernoemen liet
    die sink dus stil uit het gezichtsveld verdwijnen -- 11 passed, terwijl de guard vanaf dat
    moment niets meer over het raadspad zei. Een onvindbaar doel gaf dezelfde uitkomst als een
    schoon resultaat, en dat is de faalvorm die dit bestand juist moet uitsluiten.
    """
    per_naam: dict[str, int] = {naam: 0 for naam in SINKS}
    for _, source in _guarded_sources():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                naam = _sink_call_name(node)
                if naam in per_naam:
                    per_naam[naam] += 1
    return per_naam


def _exempt_scopes(relative_path: str) -> frozenset[str]:
    """De vrijgestelde scopes BINNEN dit bestand."""
    prefix = f"{relative_path}::"
    return frozenset(
        key[len(prefix) :] for key in KNOWN_RAW_PAYLOAD_SITES if key.startswith(prefix)
    )


def test_every_sink_receives_the_redacted_payload() -> None:
    """Publicatie, auditregel, uitvoeringsgeschiedenis en raadsbesluit krijgen de redactie."""
    offenders: list[str] = []

    for path, source in _guarded_sources():
        relative = _relative(path)
        offenders.extend(offenders_in_source(relative, source, _exempt_scopes(relative)))

    assert not offenders, (
        "Deze plekken voeden een bewarende sink zonder de geredigeerde payload:\n"
        + "\n".join(f"  - {o}" for o in offenders)
        + "\n\nGebruik de uitkomst van redact_for_publication "
        f"({' of '.join(sorted(SAFE_NAMES))}). De payload is "
        "modeloutput en kan persoonsgegevens bevatten in willekeurige sleutels; de event bus, "
        "de leeropslag, de ADR-019 auditketen en de uitvoeringsgeschiedenis bewaren alle vier."
    )


def test_every_sink_name_is_actually_found() -> None:
    """Vangnet PER SINK: elke naam in `SINKS` moet minstens een aanroep hebben.

    Een totaaldrempel volstond niet. Met `totaal >= 8` bij 10 aanroepen kon de raadssink -- die
    er precies EEN bijdraagt -- verdwijnen door `CouncilDecisionRow` te hernoemen, zonder dat
    iets rood werd (gemeten Gate 2, 2026-08-31). Per naam eisen sluit dat: een sink die niet
    meer gevonden wordt, is een sink die deze guard niet meer bewaakt, en dat hoort een
    zichtbare beslissing te zijn.
    """
    per_naam = _sink_calls_per_name()
    verdwenen = sorted(naam for naam, aantal in per_naam.items() if aantal == 0)

    assert not verdwenen, (
        f"Deze sinks uit SINKS worden nergens onder SCAN_ROOTS aangeroepen: {verdwenen} "
        f"(gevonden per naam: {per_naam}). Verplaatst of hernoemd? Werk SCAN_ROOTS of SINKS bij "
        "-- laat het niet stil staan, want vanaf nu bewaakt deze guard dat pad niet meer."
    )


def test_the_guard_catches_a_double_star_unpack() -> None:
    """`**`-unpacking verbergt de waarde en was aantoonbaar onzichtbaar voor de vorige versie."""
    offenders = offenders_in_source("probe.py", "repo.log_execution(**{'tool_input': payload})\n")

    assert offenders, (
        "Een sink die via **-unpacking wordt gevoed passeert. Gemeten op 2026-08-03: met deze "
        "regel in het bewaakte pad bleef de vorige guard volledig groen."
    )


def test_the_guard_catches_a_dict_literal_sink() -> None:
    """Een dict-assignment is geen aanroep; de vierde sink werkt precies zo."""
    offenders = offenders_in_source(
        "probe.py", "store['x'] = {'payload': request.payload, 'result': None}\n"
    )

    assert offenders, (
        "Een payload die via een dict-literal in een bewarende opslag belandt passeert. Zo bleef "
        "`tool_execution_history` in de eerste ronde ongeteld."
    )


def test_the_guard_catches_a_positional_argument() -> None:
    """Positioneel doorgeven omzeilt elke keyword-controle."""
    offenders = offenders_in_source("probe.py", "repo.log_execution(agent, tool, payload)\n")

    assert offenders, "Een positioneel doorgegeven payload passeert."


def test_the_guard_does_not_reject_the_correct_form() -> None:
    """Andere richting van de mutatietest: geen valse positieven.

    Zonder deze test kan de guard groen blijven door alles te verwerpen -- dan is hij niet
    strenger maar alleen luidruchtiger, en wordt hij bij het eerste ongemak uitgezet.
    """
    correct = (
        "repo.log_execution(agent_id=a, tool_input=publish_payload)\n"
        "self._publish_tool_event(publish_payload=publish_payload, tool_name=t)\n"
        "store['x'] = {'payload': publish_payload}\n"
    )

    assert not offenders_in_source("probe.py", correct), (
        "De guard verwerpt de correcte vorm. Dan meet hij niet of de payload geredigeerd is "
        "maar of iemand hem uberhaupt gebruikt."
    )


def test_known_raw_payload_sites_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht.

    Per SCOPE en niet per bestand: een vrijgestelde scope die zelf geen overtreding meer bevat
    is stale, ook als een ANDERE scope in hetzelfde bestand er nog een heeft.
    """
    still_offending: set[str] = set()
    for path, source in _guarded_sources():
        relative = _relative(path)
        alle = _exempt_scopes(relative)
        met_alles = len(offenders_in_source(relative, source, alle))
        for scope in alle:
            # Het VERSCHIL is toerekenbaar aan deze scope; zo telt een overtreding in een
            # andere, niet-vrijgestelde scope niet mee als bestaansgrond voor deze uitzondering.
            zonder_deze = len(offenders_in_source(relative, source, alle - {scope}))
            if zonder_deze > met_alles:
                still_offending.add(f"{relative}::{scope}")

    stale = sorted(set(KNOWN_RAW_PAYLOAD_SITES) - still_offending)

    assert not stale, (
        f"Deze uitzonderingen gelden niet meer: {stale}. Er staat geen rauwe payload meer in. "
        "Haal ze uit KNOWN_RAW_PAYLOAD_SITES zodat de guard die scope weer bewaakt."
    )


def test_human_oversight_write_path_is_deliberately_not_redacted() -> None:
    """Het HITL-ticket blijft de echte waarden tonen (AI Act art. 14).

    Gericht op het echte SCHRIJFPAD (`router.py`, `repo.create(payload=...)`) en niet op
    `hitl_store.create_ticket`: die heeft geen enkele aanroeper. Een eerdere versie van deze
    test controleerde dat verkeerde bestand en zou groen zijn gebleven terwijl het schrijfpad
    wel geredigeerd raakte.
    """
    source = HITL_WRITE_PATH.read_text(encoding="utf-8")

    assert "redact_for_publication" not in source, (
        "Het HITL-schrijfpad redigeert nu ook. Dan keurt een mens een actie goed zonder de "
        "waarden te zien, en is het toezicht uit AI Act art. 14 een formaliteit. Is dit "
        "bewust, dan hoort er een ADR-aanpassing bij en niet alleen een codewijziging."
    )


def _assignments_of(source: str, name: str) -> list[ast.expr]:
    """Elke expressie die aan `name` wordt toegekend."""
    tree = ast.parse(source)
    values: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    values.append(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name and node.value:
                values.append(node.value)
    return values


def test_every_safe_name_really_comes_from_the_redactor() -> None:
    """Een naam uit `SAFE_NAMES` is alleen veilig als hij UIT `redact_for_publication` komt.

    De hoofdguard leest een NAAM, dus zonder deze tegenprestatie zou
    `published_params = proposal.action_params` -- rauwe modeloutput onder een veilige naam --
    volledig groen blijven. Dat is de terugkerende faalvorm in dit project: TEKST doorzoeken
    waar STRUCTUUR getoetst moet worden.

    DEZE TEST DEKTE EERST EEN ENKEL BESTAND, EN DAT WAS HET GAT (onafhankelijke Gate 2,
    2026-08-31). `SAFE_NAMES` geldt overal onder `SCAN_ROOTS`, maar de herkomst werd alleen in
    `audit_writer.py` nagegaan. Een reviewer heeft een TWEEDE raadsschrijfpad gemaakt --
    `leaky_writer.py` met `published_params = proposal.action_params` en
    `CouncilDecisionRow(action_params=published_params)` -- en de hele suite bleef GROEN, 11
    passed. Dat is woordelijk het scenario waarvoor ADR-036 OP-48 is aangemaakt: "een volgende
    sprint die in `src/core/copilot/council/` een tweede schrijfpad toevoegt met
    `proposal.action_params` verbatim wordt door geen enkele architecture-test betrapt."

    De controle loopt nu over ELK bewaakt bestand en over ELKE naam in `SAFE_NAMES`. Daarmee is
    de vrijbrief niet langer breder dan zijn tegenprestatie.
    """
    gevonden_per_naam: dict[str, int] = {naam: 0 for naam in SAFE_NAMES}
    overtredingen: list[str] = []

    for path, source in _guarded_sources():
        if not any(naam in source for naam in SAFE_NAMES):
            continue
        for naam in SAFE_NAMES:
            for value in _assignments_of(source, naam):
                # Een toekenning die geen runtime-waarde kan dragen is een INITIALISATIE, geen
                # payload: `publish_payload: dict[str, object] = {}` staat in
                # `tool_broker/service.py:378` en `api/v1/tool_broker/execution_router.py:69`
                # voordat de redactor zijn werk doet. Die eisen dat ook die uit
                # `redact_for_publication` komt, is een valse positieve -- en een guard met
                # valse positieven wordt uitgezet in plaats van gevolgd. Zelfde afweging en
                # zelfde helper als bij `_carries_runtime_data` hierboven.
                if not _carries_runtime_data(value):
                    continue
                gevonden_per_naam[naam] += 1
                callee = ""
                if isinstance(value, ast.Call):
                    callee = (
                        value.func.attr
                        if isinstance(value.func, ast.Attribute)
                        else str(getattr(value.func, "id", ""))
                    )
                if callee != "redact_for_publication":
                    overtredingen.append(f"{_relative(path)}:{value.lineno} ({naam})")

    assert not overtredingen, (
        f"Deze toekenningen geven een veilige naam aan iets dat NIET uit "
        f"`redact_for_publication(...)` komt: {sorted(overtredingen)}. Zo'n naam mag elke sink "
        "voeden, dus een ongeredigeerde payload komt daarmee in "
        "`council_decisions.action_params` -- JSONB, NOT NULL, in een gehashte keten. Laat de "
        "waarde door de redactor gaan, of gebruik een naam die niet in SAFE_NAMES staat."
    )

    ongebruikt = sorted(naam for naam, aantal in gevonden_per_naam.items() if aantal == 0)
    assert not ongebruikt, (
        f"Deze namen staan in SAFE_NAMES maar worden nergens onder SCAN_ROOTS toegekend: "
        f"{ongebruikt}. Een vrijbrief zonder gebruiker bewaakt niets en hoort uit SAFE_NAMES -- "
        "anders staat er een naam klaar die een volgende auteur ongemerkt kan gebruiken."
    )


def test_pseudonymisation_never_uses_secret_key() -> None:
    """`SECRET_KEY` heeft een gepubliceerde default en is waardeloos als sleutel.

    Alleen deze assertie op broncodeniveau. De fail-closed-eigenschap wordt afgedwongen door de
    GEDRAGSTEST `test_production_without_a_key_fails_closed`. Een eerdere versie eiste hier ook
    "er staat ergens een raise", en die kon `if False: raise` niet van een levend pad
    onderscheiden -- aantoonbaar vacuum.
    """
    tree = ast.parse(REDACTION.read_text(encoding="utf-8"))
    referenced = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Attribute, ast.Name))
    }

    assert "SECRET_KEY" not in referenced, (
        "redaction.py gebruikt SECRET_KEY in code. Die heeft een gepubliceerde default; als "
        "pseudonimiseringssleutel is hij waardeloos."
    )


def test_every_executable_tool_has_a_reviewed_allowlist() -> None:
    """Een nieuwe tool moet een BEOORDEELDE allowlist krijgen, niet stil degraderen.

    Zonder deze eis krijgt een nieuwe tool "alles digesten": privacy-veilig, maar de auditregel
    wordt onbruikbaar zonder dat iemand het merkt. Een lege `frozenset()` is een geldig
    antwoord -- als het een expliciet antwoord is.
    """
    from src.core.tool_broker.business_registry import BusinessToolRegistry
    from src.core.tool_broker.hr_registry import HRToolRegistry
    from src.core.tool_broker.redaction import PAYLOAD_POLICY

    executable = BusinessToolRegistry.known_tool_names() | HRToolRegistry.known_tool_names()
    missing = sorted(executable - set(PAYLOAD_POLICY))

    assert not missing, (
        f"Deze uitvoerbare tools hebben geen regel in PAYLOAD_POLICY: {missing}. "
        "Voeg er een toe -- een lege frozenset() is een geldig antwoord, zolang het een "
        "beoordeeld antwoord is."
    )

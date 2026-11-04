"""Een agent-besturingsknop mag geen succes retourneren als hij niets doet (ADR-036 OP-178).

Deze guard hoort bij registerrij **OP-178** in
`docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md`. Dat nummer staat hier
expliciet omdat `tests/architecture/test_adr036_register_is_parseable.py` een SLUITING alleen
als bewezen aanvaardt wanneer het bewijs aantoonbaar over die bevinding gaat: een testbestand
telt pas als het OP-nummer erin voorkomt. Zonder deze regel zou een willekeurig testbestand als
bewijs kunnen dienen -- dat gat is op 2026-08-14 gemeten bij OP-84.

**De bevinding, gemeten 2026-08-31.** `pause`, `resume` en `restart` retourneerden
`{"status": "success", ...}` terwijl hun hele body bestond uit een logregel en twee appends aan een
in-memory lijst. Geen agent, geen wachtrij, geen circuit breaker werd geraakt. De behandeling van
die bevinding staat in `tests/unit/api/test_pause_agent_pauses_or_fails_loud.py`; DIT bestand
bewaakt dat de vorm niet terugkomt.

**De invariant, structureel en niet tekstueel.** Voor elke hieronder EXPLICIET genoemde handler:
geeft hij IETS terug zonder te weigeren, dan moet zijn body minstens een aanroep bevatten die iets
kan bewerkstelligen. Aanroepen die per definitie niets aan de wereld veranderen (`logger.*`,
`list.append`, `datetime.now`, `.isoformat`, het bouwen van een `JSONResponse`, `asyncio.sleep`)
tellen daarbij niet mee.

**Eerste versie van deze guard was te smal, en dat is GEMETEN, niet vermoed (Gate 2, 2026-08-31).**
Hij keek of de handler een LETTERLIJKE succeswaarde retourneerde -- `{"status": "success"}`,
`{"status": "ok"}` of `{"success": True}` -- en negeerde al het andere. Vier ontsnappingsvormen
bleven daardoor groen, elk apart nagemeten door twee onafhankelijke reviewers:
`return {"status": "paused", "message": "Agent paused"}`, `return {"result": "paused"}`,
`return JSONResponse({"status": "success"})` en de omweg via een variabele
(`payload = {...}` gevolgd door `return payload`). De guard bewaakte dus de drie waarden van de
HISTORISCHE body in plaats van de invariant. Dat is dezelfde faalvorm als de aanscherping van
2026-08-14 (vier mutaties, alle vier op `docs_url`): mutatiebewijs per GEVAL in plaats van per
VORM. De toets is nu omgedraaid -- niet "welke waarde geef je terug" maar "heb je iets gedaan".

Merk op dat de guard NIET eist dat de handler 501 geeft. Dat zou de tweede mutatierichting kapot
maken: zodra iemand een echt hold-mechanisme bouwt en de knop laat werken, moet deze test groen
BLIJVEN. "Weiger alles" is hier geen geldige oplossing.

**Wat deze guard NIET dekt, expliciet.** Retourneert een handler een zelfgebouwd
responsmodel (`return AgentControlResponse(status="paused")`), dan telt die constructor als
effect en blijft de guard groen -- gemeten. Een lijst van alle mogelijke modelklassen is niet
opsombaar, dus dat gat is hier niet te dichten zonder de tweede mutatierichting te breken. Het
wordt gedekt door `tests/unit/api/test_pause_agent_pauses_or_fails_loud.py`, dat voor alle zes
handlers hard op een 501 asserteert; die tests waren pre-fix aantoonbaar rood (9 failed / 9 passed
op het unit-bestand). Dit staat hier opgeschreven zodat een volgende lezer de grens ziet zonder
hem opnieuw te moeten uitvinden.

**Waarom de handlers met naam in een verzameling staan en niet via een patroon worden gezocht.**
`quality-gates.md` (aanscherping 2026-08-14): een guard itereert over een expliciet benoemde
verzameling en het mutatiebewijs heeft een regel per element. Een naam-patroon zou bovendien stil
leeg kunnen lopen na een rename -- daarom toetst `test_every_named_control_handler_exists` dat elke
genoemde handler ook echt gevonden wordt.

**Uitgevoerde mutaties (allemaal met een KOPIE als terugweg, nooit `git checkout --`).**

*Eerste reeks: EEN REGEL PER ELEMENT van de benoemde verzameling.* Elk van de zes handlers is
apart vervangen door een body die succes meldt zonder iets te doen (logregel plus
`return {"status": "success"}`). Gemeten 2026-08-31 met het harnas dat per handler muteert,
draait en herstelt:

| # | Element | Verwacht | Gemeten |
| --- | --- | --- | --- |
| 1 | `agents_router.py::pause_agent` | ROOD | ROOD |
| 2 | `agents_router.py::resume_agent` | ROOD | ROOD |
| 3 | `agents_router.py::restart_agent` | ROOD | ROOD |
| 4 | `management_endpoints.py::pause_agent` | ROOD | ROOD |
| 5 | `management_endpoints.py::resume_agent` | ROOD | ROOD |
| 6 | `management_endpoints.py::restart_agent` | ROOD | ROOD |

*Tweede reeks: EEN REGEL PER VORM.* Dit is de reeks die in de eerste versie ontbrak en waardoor
vier ontsnappingen groen bleven. Alle mutaties op `agents_router.pause_agent`:

| # | Vorm | Verwacht | Gemeten |
| --- | --- | --- | --- |
| 7 | oude body (logregel + append + `status="success"`) | ROOD | ROOD |
| 8 | andere WAARDE: `{"status": "paused", "message": "Agent paused"}` | ROOD | ROOD |
| 9 | andere SLEUTEL: `{"result": "paused"}` | ROOD | ROOD |
| 10 | ingepakt: `return JSONResponse({"status": "success"})` | ROOD | ROOD |
| 11 | omweg: `payload = {...}` gevolgd door `return payload` | ROOD | ROOD |
| 12 | placeholder: `await asyncio.sleep(0)` plus success | ROOD | ROOD |
| 13 | LEGITIEM: `await _hold_store.set_hold(...)` plus success | GROEN | GROEN |
| 14 | BEKEND GAT: `return AgentControlResponse(status="paused")` | GROEN | GROEN |
| 15 | `pause_agent` hernoemd (guard leegtrekken) | ROOD | ROOD (bestaans-test) |
| 16 | huidige, ongemuteerde staat | GROEN | GROEN |

Mutatie 13 is de belangrijkste helft: zonder die controle zou deze guard een werkende
pauzeerknop verbieden, en dan is "weiger alles" een geldige oplossing. Mutatie 12 is toegevoegd
omdat dit project die placeholder al eens echt heeft gehad (AUDIT-009). Mutatie 14 is het gat dat
hierboven expliciet is opgeschreven -- gemeten GROEN, bewust niet gedicht, gedekt door de
unit-test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: De besturingsknoppen die deze guard dekt, per bestand. Zes elementen, zes mutatieregels in de
#: tabel hierboven. Komt er een vierde knop (stop, kill, drain), dan hoort hij hier bij.
CONTROL_ENDPOINTS: dict[str, tuple[str, ...]] = {
    "src/core/api/v1/management/agents_router.py": (
        "pause_agent",
        "resume_agent",
        "restart_agent",
    ),
    "src/core/api/management_endpoints.py": (
        "pause_agent",
        "resume_agent",
        "restart_agent",
    ),
}

#: Aanroepen die niets aan de wereld veranderen. Een handler die ALLEEN deze aanroept en toch
#: succes meldt, liegt. De lijst is opzettelijk kort: bij twijfel geldt een aanroep als effect,
#: zodat de guard eerder een echte implementatie doorlaat dan een lege knop.
INERT_CALL_NAMES = frozenset(
    {
        # logging
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        # in-memory boekhouding en tijd/format-hulp
        "append",
        "isoformat",
        "now",
        "utcnow",
        "format",
        "strftime",
        # zuivere builtins
        "str",
        "int",
        "len",
        "list",
        "dict",
        "sorted",
        # Het INPAKKEN van een antwoord verandert niets aan de wereld. Zonder deze namen was
        # `return JSONResponse({"status": "success"})` een "effect" en bleef de guard groen --
        # gemeten bij Gate 2, 2026-08-31.
        "JSONResponse",
        "ORJSONResponse",
        "UJSONResponse",
        "PlainTextResponse",
        "HTMLResponse",
        "Response",
        # Wachten is geen werk. Dit project heeft die placeholder al eens gehad: AUDIT-009,
        # `_execute_step` deed `await asyncio.sleep(0.01)` en meldde altijd succes.
        "sleep",
    }
)

#: Aanroepen die zelf een fout opgooien in plaats van een antwoord op te leveren.
#:
#: Deze namen tellen NIET als effect: `refuse_agent_control()` gooit intern op, dus het is de
#: weigering en niet het werk. Ze staan hier apart van `INERT_CALL_NAMES` omdat de reden anders
#: is -- inert betekent "doet niets", weigerend betekent "levert geen antwoord op".
#:
#: Tot Gate 2 (2026-08-31) gaf een van deze namen, of een `ast.Raise` waar dan ook in de body,
#: de hele handler VRIJSTELLING van de controle. Dat was de fout: `ast.walk` ziet ook een `raise`
#: in een tak die niets met het antwoordpad te maken heeft. Gemeten door een onafhankelijke
#: reviewer: `if agent_id == "nooit": refuse_agent_control(...)` gevolgd door de oude succes-body
#: liet de guard op 12 passed staan. De vrijstelling is weg; deze namen tellen nu alleen niet mee
#: als EFFECT.
REFUSING_CALL_NAMES = frozenset({"refuse_agent_control"})

#: Exception-klassen waarvan het CONSTRUEREN geen effect op de wereld is. Naast deze namen geldt
#: ook de conventie `*Error` / `*Exception` -- zie `_is_exception_constructor`.
EXCEPTION_CONSTRUCTORS = frozenset({"HTTPException", "PermissionError", "ValueError", "TypeError"})


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    return None


def _body_nodes(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> list[ast.AST]:
    """Alleen de BODY, niet de decorators en niet de parameter-defaults.

    Dit onderscheid is essentieel en is de bekende valkuil bij `ast.walk`: `@router.post(...)` is
    een Call, en `Depends(require_scopes(...))` in de defaults ook. Zou de guard die meenemen, dan
    vindt hij bij ELKE endpoint een "effect" en bewaakt hij niets meer.
    """
    nodes: list[ast.AST] = []
    for stmt in fn.body:
        nodes.extend(ast.walk(stmt))
    return nodes


def _call_name(node: ast.Call) -> str | None:
    """De naam waaronder een aanroep herkenbaar is, of None bij een uitdrukking."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _nodes_inside_raises(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> set[int]:
    """De id's van alle knopen die BINNEN een `raise`-statement leven.

    Nodig omdat een exception construeren geen effect op de wereld is: `raise HTTPException(400)`
    bevat een `ast.Call`, en die mag niet als "er gebeurt iets" tellen.
    """
    binnen: set[int] = set()
    for node in _body_nodes(fn):
        if isinstance(node, ast.Raise):
            binnen.update(id(inner) for inner in ast.walk(node))
    return binnen


def _returns_a_value(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """True als de handler ergens een waarde teruggeeft, in welke vorm dan ook.

    Bewust vormblind: een dict-literal, een `JSONResponse`, een variabele of een modelinstantie
    zijn voor de aanroeper alle vier "de knop meldt iets". De vorige versie keek alleen naar een
    `ast.Dict` met een bekende succeswaarde, en dat maakte vier ontsnappingsvormen groen.
    """
    return any(isinstance(node, ast.Return) and node.value is not None for node in _body_nodes(fn))


def _is_exception_constructor(name: str) -> bool:
    """Herkent het construeren van een exception, wat geen effect op de wereld is.

    Naast de expliciete namen ook alles wat op `Error` of `Exception` eindigt. Dat is een
    conventie en geen bewijs, maar hier is de faalrichting veilig: iets ten onrechte als
    exception zien maakt de guard STRENGER, niet slapper.
    """
    return name in EXCEPTION_CONSTRUCTORS or name.endswith(("Error", "Exception"))


def _effect_calls(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> list[str]:
    """Namen van aanroepen die iets aan de wereld kunnen veranderen.

    Drie soorten vallen af, en de laatste twee zijn na Gate 2 toegevoegd omdat de guard zonder
    hen met EEN validatie-`raise` het zwijgen was op te leggen (gemeten door een onafhankelijke
    reviewer: `if not agent_id: raise HTTPException(400)` plus de oude succes-body gaf 12
    passed):

    1. Inerte aanroepen: logging, in-memory appends, tijd/format, een antwoord inpakken, sleep.
    2. Alles BINNEN een `raise`-statement. Een exception construeren en opgooien verandert niets
       aan agenten, wachtrijen of brekers -- het is de weigering zelf.
    3. Exception-CONSTRUCTORS waar ze ook staan. `HTTPException(400)` als losse expressie is
       geen effect, en `_effect_calls` rekende hem eerst wel mee: daarmee bleef de mutatie zelfs
       groen als de `raise`-uitweg was gedicht.
    """
    binnen_raise = _nodes_inside_raises(fn)
    found: list[str] = []
    for node in _body_nodes(fn):
        if not isinstance(node, ast.Call) or id(node) in binnen_raise:
            continue
        name = _call_name(node)
        if name is None or name in INERT_CALL_NAMES or _is_exception_constructor(name):
            continue
        # Een weigerende aanroep is de weigering zelf, geen werk. Zonder deze regel bleef de
        # vorm "weiger in EEN tak, meld succes in de andere" ongezien: `refuse_agent_control`
        # gold dan als effect en dekte daarmee de leugen in het andere pad.
        if name in REFUSING_CALL_NAMES:
            continue
        found.append(name)
    return found


#: Synthetische handler-bodies voor de regel zelf: (naam, bron, is_overtreding).
#:
#: Waarom deze vorm er is (2026-08-31). Deze guard werd bewezen door productiecode te muteren.
#: Dat is traag, het moet handmatig herhaald worden, en mijn eigen mutatieharnas produceerde
#: ongeldige Python en las de ontbrekende pytest-samenvatting als GROEN. De vastgelegde praktijk
#: voor een architectuurregel is de REGEL unittesten op gevallen die moeten falen, gevallen die
#: moeten slagen, en de randgevallen. Elke ontsnappingsvorm die een reviewer vindt staat hier
#: daarna permanent, in plaats van in een handeling die iemand moet onthouden.
_REGEL_GEVALLEN: tuple[tuple[str, str, bool], ...] = (
    (
        "oude body: logregel, append, succes",
        "async def h(agent_id, current_user):\n"
        '    logger.info("Pausing %s", agent_id)\n'
        '    log_entries.append({"agent": agent_id})\n'
        '    return {"status": "success"}\n',
        True,
    ),
    (
        "andere waarde dan success",
        'async def h(agent_id):\n    return {"status": "paused", "message": "Agent paused"}\n',
        True,
    ),
    (
        "andere sleutel",
        'async def h(agent_id):\n    return {"result": "paused"}\n',
        True,
    ),
    (
        "ingepakt in JSONResponse",
        'async def h(agent_id):\n    return JSONResponse({"status": "success"})\n',
        True,
    ),
    (
        "omweg via een variabele",
        'async def h(agent_id):\n    payload = {"status": "success"}\n    return payload\n',
        True,
    ),
    (
        "placeholder: await asyncio.sleep(0)",
        'async def h(agent_id):\n    await asyncio.sleep(0)\n    return {"status": "success"}\n',
        True,
    ),
    # De twee vormen die de onafhankelijke Gate-2-review GROEN mat op de vorige versie.
    (
        "validatie-raise naast een succes-return",
        "async def h(agent_id):\n"
        "    if not agent_id:\n"
        "        raise HTTPException(400)\n"
        '    logger.info("x")\n'
        '    return {"status": "success"}\n',
        True,
    ),
    (
        "weigering in EEN tak, succes in de andere",
        "async def h(agent_id):\n"
        '    if agent_id == "nooit":\n'
        "        refuse_agent_control(agent_id)\n"
        '    return {"status": "success"}\n',
        True,
    ),
    (
        "LEGITIEM: echt werk plus succes",
        "async def h(agent_id):\n"
        "    await _hold_store.set_hold(agent_id)\n"
        '    return {"status": "success"}\n',
        False,
    ),
    (
        "LEGITIEM: alleen weigeren, geen antwoord",
        "async def h(agent_id, current_user):\n"
        '    logger.info("x")\n'
        '    refuse_agent_control("pause", agent_id, str(current_user.id))\n',
        False,
    ),
    (
        "LEGITIEM: alleen een eigen raise, geen antwoord",
        "async def h(agent_id):\n    raise HTTPException(501)\n",
        False,
    ),
    # BEKEND GAT, hier vastgepind zodat een wijziging zichtbaar is en niet stil.
    (
        "BEKEND GAT: eigen responsmodel telt als effect",
        'async def h(agent_id):\n    return AgentControlResponse(status="paused")\n',
        False,
    ),
)


def _eerste_functie(bron: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    knoop = ast.parse(bron).body[0]
    assert isinstance(knoop, (ast.AsyncFunctionDef, ast.FunctionDef))
    return knoop


@pytest.mark.parametrize(
    ("naam", "bron", "is_overtreding"),
    _REGEL_GEVALLEN,
    ids=[g[0] for g in _REGEL_GEVALLEN],
)
def test_the_rule_itself_catches_every_known_form(
    naam: str, bron: str, is_overtreding: bool
) -> None:
    """De regel moet elke bekende leugenvorm zien, en geen legitieme implementatie weigeren.

    Een handler is een overtreding als hij een waarde teruggeeft terwijl er niets gebeurt. De
    twee `raise`-gevallen hierboven zijn de kern: zonder de reparatie van 2026-08-31 zette een
    enkele validatie-`raise` de hele controle uit, want `ast.walk` ziet die ook in een tak die
    niets met het antwoordpad te maken heeft.
    """
    fn = _eerste_functie(bron)
    overtreding = _returns_a_value(fn) and not _effect_calls(fn)
    assert overtreding is is_overtreding, (
        f"{naam}: de regel zegt {'WEL' if overtreding else 'GEEN'} overtreding, verwacht "
        f"{'WEL' if is_overtreding else 'GEEN'}. Effect-aanroepen gevonden: {_effect_calls(fn)}. "
        f"Fragment:\n{bron}"
    )


_CASES = [(path, handler) for path, handlers in CONTROL_ENDPOINTS.items() for handler in handlers]


@pytest.mark.parametrize(("module_path", "handler_name"), _CASES)
def test_every_named_control_handler_exists(module_path: str, handler_name: str) -> None:
    """Vangnet tegen een leeggelopen guard: een rename mag hem niet vacuum maken (mutatie 7)."""
    path = Path(module_path)
    assert path.exists(), f"{module_path} bestaat niet meer -- werk CONTROL_ENDPOINTS bij."
    assert _find_function(_parse(path), handler_name) is not None, (
        f"{module_path} heeft geen handler {handler_name!r} meer. Is hij hernoemd of verplaatst, "
        "werk CONTROL_ENDPOINTS bij; anders bewaakt deze guard niets."
    )


@pytest.mark.parametrize(("module_path", "handler_name"), _CASES)
def test_control_handler_does_not_confirm_success_without_doing_anything(
    module_path: str, handler_name: str
) -> None:
    """Iets terugmelden mag, maar alleen als er ook iets gebeurt.

    Er is GEEN vrijstelling voor een handler die ergens een `raise` heeft. Die was er wel, en dat
    was het gat: `ast.walk` ziet ook een `raise` in een validatietak, dus een enkele
    guard-clause zette de hele controle uit. Wie helemaal geen waarde teruggeeft, valt hieronder
    vanzelf buiten de assertie -- een weigering die niets retourneert kan niet over succes liegen.
    """
    fn = _find_function(_parse(Path(module_path)), handler_name)
    if fn is None:
        pytest.skip("handler bestaat niet -- zie test_every_named_control_handler_exists")

    if not _returns_a_value(fn):
        return  # geeft niets terug, bevestigt dus ook niets

    effects = _effect_calls(fn)
    assert effects, (
        f"{module_path}::{handler_name} geeft een antwoord terug terwijl zijn body alleen inerte "
        "aanroepen doet (logging, in-memory appends, tijd/format, een antwoord inpakken, sleep). "
        "Dat is een toezichtsknop die altijd slaagt en nooit werkt -- ongeacht WELKE waarde erin "
        "staat, want ook 'paused' of 'ok' leest een beheerder als: het is gelukt. Laat hem ofwel "
        "echt iets doen, ofwel expliciet weigeren via "
        "`src.core.api.agent_control_unavailable.refuse_agent_control` (ADR-036 golf 1 WS1)."
    )

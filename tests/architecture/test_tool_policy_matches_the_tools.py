"""Architecture test: `PAYLOAD_POLICY` klopt met de tools die hij beschrijft (ADR-036 OP-27).

`redaction.PAYLOAD_POLICY` bepaalt per tool welke payload-sleutelnamen bij het vocabulaire van
die tool horen. Een naam die er niet in staat wordt zelf een pseudonym -- dus een ONTBREKENDE
naam maakt het log onbruikbaar, en een FANTOOMNAAM verklaart een sleutel leesbaar die de tool
nooit leest.

**Waarom dit bestand er is.** De bestaande guard
(`test_tool_payloads_are_pseudonymised.py::test_every_executable_tool_has_a_reviewed_allowlist`)
controleert of er een REGEL is, nooit of de regel WAAR is. Daardoor liep de tabel op zes punten
achter op de werkelijkheid zonder dat een test klaagde:

| Tabel zei | Werkelijkheid | Vindplaats |
| --- | --- | --- |
| `list_tasks: offset` | leest `skip` | `business_registry.py:178` |
| `test__slow: seconds` | leest `delay_seconds` | `test_tools.py:29` |
| `test__echo: message` | leest geen benoemde sleutel | `test_tools.py:16` |
| `local__llm_generate: model` | leest alleen `prompt` | `local_registry.py:230` |
| `create_task`: 5 velden | `TaskCreate` heeft 10 | `domains/tasks/schemas.py:15-31` |
| `update_task`: 5 velden | `TaskUpdate` heeft 10 + ticketref | `schemas.py:34-50` |

Drie daarvan zaten in `local__`/`test__`-tools, en die kwamen in de oude guard niet voor omdat
`LocalToolRegistry` geen `known_tool_names()` had. Die is nu toegevoegd.

**Twee bronnen van waarheid, en dat is opzet.** Waar de tool een echte declaratie heeft
(`TaskCreate`/`TaskUpdate`, en de constanten in `hr_registry`) vergelijken we daarmee. Waar die
niet bestaat -- 10 van de 12 tools lezen simpelweg `params.get("x")` -- scannen we de AST van de
implementerende methode. Dat is geen omweg: het is de enige machineleesbare vorm die de
werkelijkheid heeft, en een test die daarop vergelijkt betrapt drift zonder dat we schema's
moeten verzinnen die niet bestaan.

De tabel zelf blijft literalen bevatten en importeert de declaraties niet op runtime. Dat is een
bewuste keuze: `redaction.py` wordt op elk toolpad geimporteerd en hoort geen importafhankelijkheid
op een domeinmodule te krijgen voor iets wat een test even goed afdwingt.

**De scan is KLASSE-GESCOPED (ADR-036 OP-41, 2026-08-31).** Tot die datum zocht
`_read_keys_in_method` met `ast.walk(tree)` de eerste functie met de gezochte naam in het HELE
bestand, met een `break` erachter -- dus ongeacht klasse, en bij een onvindbare naam stil `set()`.
Dat was latent (elk van de veertien namen komt exact een keer voor), maar een tweede klasse met
dezelfde methodenaam liet de driftdetectie op het verkeerde lichaam draaien zonder een woord.
`_IMPLEMENTATIONS` draagt daarom nu GEKWALIFICEERDE namen, de resolutie gebruikt expliciete
recursie in plaats van `ast.walk()`, en zowel een onvindbare als een ambigue naam ketst luid af.
Bewijs, en dit is met opzet in twee soorten gescheiden (bijgewerkt na de onafhankelijke Gate 2
van 2026-08-31, die terecht opmerkte dat het door elkaar liep):

  - MUTATIEbewijs op de LOGICA van de resolver, op SYNTHETISCHE bronnen:
    `test_the_scanner_scopes_by_class` en `test_an_ambiguous_name_is_loud`. Die raken geen
    enkel element van `_IMPLEMENTATIONS` -- dat is de bedoeling, want ze toetsen het gedrag van
    de resolver en niet de inhoud van de lijst.
  - RESOLUTIEbewijs per element van `_IMPLEMENTATIONS`:
    `test_every_implementation_entry_names_its_class` zoekt elk (pad, gekwalificeerde
    naam)-paar daadwerkelijk op en faalt op een vermelding die niet meer bestaat. Dat is geen
    mutatie maar een bestaanscontrole, en die twee zijn niet hetzelfde.

Waarom dat onderscheid hier expliciet staat: de eerdere tekst beloofde "een mutatieregel per
(pad, naam)-paar, alle zestien" en verwees naar de twee synthetische tests. Die leveren dat
niet, en een lezer die de aanscherping van 2026-08-14 in vijf seconden wil controleren, komt
dan bedrogen uit. De lijst telt 16 (pad, naam)-paren over 14 unieke methodenamen; waar hieronder
"veertien" staat, gaat het over de namen.
"""

import ast
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Waar de implementatie van elke tool staat: pad -> de methodenamen die payload-sleutels lezen.
#: Per tool de METHODE, zodat de scan niet het hele bestand meeneemt.
#: Meerdere methodes per tool, want een tool leest zijn payload niet altijd op een plek:
#: `query_hr_database` haalt `role` in `execute_hr_tool` en de paginering in `_role_occupancy`,
#: en de business-tools halen `task_id` via de helper `_extract_task_id`. De sleutels van alle
#: genoemde methodes worden vereenigd.
_LOCAL = "src/core/tool_broker/local_registry.py"
_TEST = "src/core/tool_broker/test_tools.py"
_BUSINESS = "src/core/tool_broker/business_registry.py"
_HR = "src/core/tool_broker/hr_registry.py"
_RECEIVABLES = "src/core/tool_broker/receivables_registry.py"

#: De methodenaam is GEKWALIFICEERD (`Klasse.methode`, of kaal voor een moduleniveau-functie).
#: Dat is geen cosmetica -- zie `_resolve_qualified()`: tot 2026-08-31 zocht de scanner de eerste
#: functie met de gezochte naam in het HELE bestand, ongeacht klasse (ADR-036 OP-41).
_IMPLEMENTATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "local__read_file": ((_LOCAL, "LocalToolRegistry._tool_read_file"),),
    "local__send_email": ((_LOCAL, "LocalToolRegistry._tool_send_email"),),
    "local__llm_generate": ((_LOCAL, "LocalToolRegistry._tool_llm_generate"),),
    "test__echo": ((_TEST, "test_echo"),),
    "test__fail": ((_TEST, "test_fail"),),
    "test__slow": ((_TEST, "test_slow"),),
    "create_task": ((_BUSINESS, "BusinessToolRegistry._handle_create_task"),),
    "list_tasks": ((_BUSINESS, "BusinessToolRegistry._handle_list_tasks"),),
    "update_task": (
        (_BUSINESS, "BusinessToolRegistry._handle_update_task"),
        (_BUSINESS, "BusinessToolRegistry._extract_task_id"),
    ),
    "delete_task": (
        (_BUSINESS, "BusinessToolRegistry._handle_delete_task"),
        (_BUSINESS, "BusinessToolRegistry._extract_task_id"),
    ),
    "query_hr_database": (
        (_HR, "HRToolRegistry.execute_hr_tool"),
        (_HR, "HRToolRegistry._role_occupancy"),
    ),
    "analyze_skill_gap": (
        (_HR, "HRToolRegistry.execute_hr_tool"),
        (_HR, "HRToolRegistry._skill_gap"),
    ),
    # BEWUST zonder `execute_hr_tool`, anders dan de twee leestools hierboven. Die methode
    # leest `role`, `department` en `employee_id` -- de zoekvelden van een LEESTOOL. De
    # schrijftool wordt daarom in `execute_hr_tool` afgehandeld VOOR die controles, zodat die
    # drie namen niet bij zijn vocabulaire horen. Zou hij er wel langs gaan, dan moest
    # `PAYLOAD_POLICY["schedule_training"]` drie velden noemen die de tool niet kent.
    "schedule_training": ((_HR, "HRToolRegistry._schedule_training"),),
    "list_receivables": ((_RECEIVABLES, "ReceivablesToolRegistry._list"),),
    "send_payment_reminder": ((_RECEIVABLES, "ReceivablesToolRegistry._send"),),
}

#: Tools waarvan een deel van het vocabulaire in een CONSTANTE staat in plaats van in een
#: `payload.get()`. `hr_registry._UNSUPPORTED_FILTERS` (`:72-81`) somt de namen op die de tool
#: expliciet WEIGERT; die horen bij het vocabulaire -- de tool kent ze, en een geweigerde naam
#: hoort leesbaar in het log te staan zodat je ziet wat er is gevraagd.
#: De waarde is een volledig gekwalificeerd pad; `_constant_vocabulary()` resolvet het echt.
#: Tot 2026-08-15 was dit literaal DECORATIEF: de helper eronder hardcodeerde
#: `if tool_name != "query_hr_database"`. Toen `analyze_skill_gap` erbij kwam -- dezelfde
#: weigerlijst, andere naam -- meldde de fantoomtest daardoor twee namen die de tool wel
#: degelijk kent. Dat is de vijfde keer in deze reeks dat een handmatige naamlijst een token
#: te kort bleek, en nu draagt de lijst zelf de logica.
_VOCABULARY_FROM_CONSTANTS: dict[str, str] = {
    "query_hr_database": "src.core.tool_broker.hr_registry._UNSUPPORTED_FILTERS",
    # Dezelfde weigerlijst geldt voor beide HR-tools: `execute_hr_tool` loopt hem af voordat
    # hij naar de ene of de andere implementatie dispatcht.
    "analyze_skill_gap": "src.core.tool_broker.hr_registry._UNSUPPORTED_FILTERS",
}

#: Tools die hun payload NIET zelf uitlezen maar doorgeven aan een Pydantic-model. Hun
#: vocabulaire is dat model. `_handle_create_task` doet `TaskCreate(**data)`
#: (`business_registry.py:124`) en leest geen enkele sleutel met `.get()`, dus een AST-scan
#: alleen zou hier LEEG teruggeven -- en dan meldt de fantoomtest elke parameter.
_SCHEMA_BACKED: dict[str, str] = {
    "create_task": "TaskCreate",
    "update_task": "TaskUpdate",
}


#: De namen waaronder de payload in een tool-implementatie binnenkomt. Alleen lezingen OP een
#: van deze namen tellen; anders pakt de scan ook een LLM-respons, een configdict of een
#: MIME-header.
_PAYLOAD_NAMES = frozenset({"payload", "params"})

#: Helpers waarvan het TWEEDE argument de payload-sleutel is: `helper(payload, "naam", ...)`.
#: `_extract_task_id` hoort er NIET in: daar is het tweede argument de toolnaam voor de
#: foutmelding (`_extract_task_id(payload, "delete_task")`), en die helper leest `task_id`
#: intern -- zijn body staat daarom in `_IMPLEMENTATIONS` en wordt gewoon meegescand.
_PAYLOAD_HELPERS = frozenset({"_read_bounded_int", "_extract_int"})


def _constant_vocabulary(tool_name: str) -> set[str]:
    """De namen die een tool kent via een CONSTANTE in plaats van via `payload.get()`.

    Resolvet het pad uit `_VOCABULARY_FROM_CONSTANTS` daadwerkelijk, zodat een tool toevoegen
    aan dat literaal genoeg is en niemand deze functie hoeft aan te raken.
    """
    source = _VOCABULARY_FROM_CONSTANTS.get(tool_name)
    if source is None:
        return set()

    module_path, _, constant_name = source.rpartition(".")
    module = importlib.import_module(module_path)
    constant = getattr(module, constant_name)
    return set(constant)


#: Sleutels die de BROKER injecteert of als controleveld gebruikt, dus niet in de tool-methode
#: te vinden. Gedateerd, met reden per regel.
_BROKER_INJECTED: dict[str, str] = {
    "tenant_id": "2026-08-03 -- service.py:159-166 injecteert dit uit de executiecontext",
    "user_id": "2026-08-03 -- idem",
    "_hitl_ticket_ref": (
        "2026-08-03 -- HITL-controleveld; service.py:211 leest het, business_registry.py:228 popt "
        "het voor de HIGH-risk tools"
    ),
}


#: Statements waarvan de body bij DEZELFDE scope hoort. Een methode kan achter een
#: `if TYPE_CHECKING:` of in een `try:` staan en is dan nog steeds een methode van die klasse.
#: `ast.walk()` is hier expliciet NIET bruikbaar: die duikt ook functiebodies in, en dan is een
#: geneste hulpfunctie ineens een "methode" van de omsluitende klasse (gemeten valkuil in dit
#: project: een AST-guard die "alleen moduleniveau" beweerde pakte via `ast.walk()` op een
#: `if`-blok toch functiebodies mee).
_TRANSPARENT_BLOCKS = (
    ast.If,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.For,
    ast.AsyncFor,
    ast.While,
)


def _scope_members(node: ast.AST) -> list[ast.stmt]:
    """De statements die DIRECT in deze scope leven.

    Daalt af in blokken die geen eigen naamruimte openen (`if`/`try`/`with`/loops) en stopt BIJ
    -- niet IN -- elke `def`/`class`: die worden zelf teruggegeven, hun body niet. Zo kan een
    naam nooit uit een geneste functie of een binnenklasse worden opgepikt.
    """
    members: list[ast.stmt] = []
    body = getattr(node, "body", [])
    stack: list[ast.stmt] = list(body)
    while stack:
        statement = stack.pop(0)
        members.append(statement)
        if isinstance(statement, _TRANSPARENT_BLOCKS):
            for attribute in ("body", "orelse", "finalbody"):
                stack.extend(getattr(statement, attribute, []) or [])
            for handler in getattr(statement, "handlers", []) or []:
                stack.extend(handler.body)
    return members


def _resolve_qualified(tree: ast.Module, qualified_name: str) -> ast.AST | None:
    """Zoek `Klasse.methode` (of een kale moduleniveau-naam) met KLASSE-SCOPING.

    De oude vorm liep `ast.walk(tree)` over de hele module en nam de EERSTE functie met de
    gezochte naam, ongeacht in welke klasse hij stond, met een `break` erachter (ADR-036 OP-41).
    Dat was vandaag latent -- de veertien methodenamen komen elk exact een keer voor -- maar een
    tweede klasse met dezelfde methodenaam liet de scanner stil het VERKEERDE lichaam meten, en
    dan draait de driftdetectie op een methode die niets met die tool te maken heeft.

    Een naam die BINNEN een scope meer dan een keer voorkomt is ambigu en ketst luid af. Dat is
    niet theoretisch: `ast.walk()` is breedte-eerst, dus de oude vorm koos de ONDIEPSTE treffer
    en niet de tekstueel eerste. Voor de drie moduleniveau-tools in `test_tools.py` gaf dat bij
    toeval het juiste antwoord, en "bij toeval juist" is precies wat een guard niet mag zijn.
    """
    scope: ast.AST = tree
    segments = qualified_name.split(".")
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        wanted: tuple[type[ast.AST], ...] = (
            (ast.FunctionDef, ast.AsyncFunctionDef) if is_last else (ast.ClassDef,)
        )
        matches = [
            member
            for member in _scope_members(scope)
            if isinstance(member, wanted) and getattr(member, "name", None) == segment
        ]
        assert len(matches) <= 1, (
            f"`{segment}` komt {len(matches)}x voor in dezelfde scope bij het opzoeken van "
            f"`{qualified_name}`. Welke van de twee de driftdetectie hoort te meten is dan niet "
            "vast te stellen; op runtime wint de laatste definitie. Hernoem er een, of maak de "
            "vermelding in _IMPLEMENTATIONS eenduidig."
        )
        if not matches:
            return None
        scope = matches[0]
    return scope


def _read_keys_in_method(relative_path: str, method_name: str) -> set[str]:
    """De payload-sleutels die deze methode letterlijk uitleest.

    `method_name` is GEKWALIFICEERD (`Klasse.methode`, of kaal voor een moduleniveau-functie) en
    wordt met klasse-scoping opgezocht; zie `_resolve_qualified()`.

    Gevonden vormen: `x.get("naam")`, `x.get("naam", default)`, `x["naam"]` en
    `_read_bounded_int(payload, "naam", ...)` / `_extract_int(payload, "naam", ...)`.

    Een onvindbaar doel is een FOUT en geen lege uitkomst. De oude vorm gaf hier stil `set()`
    terug, en dan meldt de fantoomtest elke parameter van die tool als niet-gelezen -- een
    verwarrende foutmelding over de verkeerde eigenschap.
    """
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return _read_keys_in_source(source, method_name, relative_path)


def _read_keys_in_source(source: str, method_name: str, where: str) -> set[str]:
    """Als `_read_keys_in_method`, maar op brontekst -- zodat de resolver mutatie-getest kan
    worden op synthetische bronnen, in BEIDE richtingen."""
    tree = ast.parse(source)

    target = _resolve_qualified(tree, method_name)
    assert target is not None, (
        f"`{method_name}` is niet te vinden in {where}. _IMPLEMENTATIONS verwijst naar "
        "een gekwalificeerde naam (`Klasse.methode`, of kaal op moduleniveau) die daar niet "
        "bestaat -- hernoemd, verplaatst, of de klassenaam ontbreekt. Zolang dit niet klopt "
        "meet de driftdetectie voor deze tool niets."
    )

    keys: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Call):
            func = node.func
            # `payload.get("x")` -- de ONTVANGER moet de payload zijn. Zonder die eis pakt de
            # scan ook `response.get("content")`, `self.whitelist.get(...)` en `msg["To"]`, en
            # dan meldt hij drie fantoomparameters die niets met de payload te maken hebben.
            # Gemeten: dat gebeurde bij de eerste versie op precies die drie.
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and isinstance(func.value, ast.Name)
                and func.value.id in _PAYLOAD_NAMES
                and node.args
            ):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    keys.add(first.value)
                continue

            # `self._read_bounded_int(payload, "x", ...)` / `self._extract_int(payload, "x", ...)`
            helper = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if helper in _PAYLOAD_HELPERS and len(node.args) >= 2:
                receiver, key = node.args[0], node.args[1]
                if (
                    isinstance(receiver, ast.Name)
                    and receiver.id in _PAYLOAD_NAMES
                    and isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                ):
                    keys.add(key.value)

        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in _PAYLOAD_NAMES
        ):
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                keys.add(index.value)

    return keys


def _measured_keys(tool_name: str) -> set[str]:
    """Alle payload-sleutels die deze tool aantoonbaar leest, uit alle betrokken methodes."""
    keys: set[str] = set(_constant_vocabulary(tool_name))
    if tool_name in _SCHEMA_BACKED:
        keys |= _schema_fields(_SCHEMA_BACKED[tool_name])
    for path, method in _IMPLEMENTATIONS[tool_name]:
        keys |= _read_keys_in_method(path, method)
    return keys


def _schema_fields(model_name: str) -> set[str]:
    from src.domains.tasks import schemas

    model = getattr(schemas, model_name)
    return set(model.model_fields)


def _policy() -> dict[str, object]:
    from src.core.tool_broker.redaction import PAYLOAD_POLICY

    return dict(PAYLOAD_POLICY)


def _params(tool_name: str) -> set[str]:
    from src.core.tool_broker.redaction import PAYLOAD_POLICY

    return set(PAYLOAD_POLICY[tool_name].params)


def test_every_executable_tool_including_local_ones_has_a_policy() -> None:
    """Alle twaalf tools, niet vijf.

    De oude guard uniete alleen Business en HR. `LocalToolRegistry.known_tool_names()` bestond
    niet, dus zeven tools -- inclusief `local__run_shell` en `local__send_email`, de twee
    gevaarlijkste -- hadden geen enkele dekking.
    """
    from src.core.tool_broker.business_registry import BusinessToolRegistry
    from src.core.tool_broker.hr_registry import HRToolRegistry
    from src.core.tool_broker.local_registry import LocalToolRegistry
    from src.core.tool_broker.receivables_registry import ReceivablesToolRegistry

    executable = (
        set(BusinessToolRegistry.known_tool_names())
        | set(HRToolRegistry.known_tool_names())
        | set(ReceivablesToolRegistry.known_tool_names())
        | set(LocalToolRegistry.known_tool_names())
    )
    missing = sorted(executable - set(_policy()))

    assert not missing, (
        f"Deze uitvoerbare tools hebben geen regel in PAYLOAD_POLICY: {missing}. Zonder regel "
        "wordt elke sleutelnaam een pseudonym en is de auditregel onbruikbaar."
    )


def _executable_tool_names() -> set[str]:
    """Alle uitvoerbare tools, uit de drie registries."""
    from src.core.tool_broker.business_registry import BusinessToolRegistry
    from src.core.tool_broker.hr_registry import HRToolRegistry
    from src.core.tool_broker.local_registry import LocalToolRegistry
    from src.core.tool_broker.receivables_registry import ReceivablesToolRegistry

    return (
        set(BusinessToolRegistry.known_tool_names())
        | set(HRToolRegistry.known_tool_names())
        | set(ReceivablesToolRegistry.known_tool_names())
        | set(LocalToolRegistry.known_tool_names())
    )


def test_the_drift_detector_covers_every_executable_tool() -> None:
    """`_IMPLEMENTATIONS` is de dekkingsverzameling van dit hele bestand, en die moet compleet zijn.

    Toegevoegd 2026-08-04 (ronde 5). Beide driftrichtingen
    (`test_no_policy_declares_a_parameter_the_tool_never_reads` en
    `test_no_tool_reads_a_parameter_the_policy_does_not_know`) itereren over `_IMPLEMENTATIONS`, en
    dat is een handmatig literaal. Er was geen test die controleerde of dat literaal alle
    uitvoerbare tools dekt.

    Bewezen met een mutatie: een nieuwe tool `local__http_post` die `url` en `headers` leest, met
    een policy-regel die `body` declareert (fantoomnaam), `headers` mist en een onzinnige grens op
    `url` zet -- 18 tests groen. Dezelfde drift op een tool die WEL in `_IMPLEMENTATIONS` staat
    (`list_tasks: skip` -> `offset`) doodt beide richtingen direct. De guard werkt dus; zijn
    dekkingsverzameling was de steekproef.

    Dat is de les uit par. 6.5 van de overdracht -- "een vangnet per bewaakt item, niet per
    voorbeeld" -- een laag hoger dan waar hij oorspronkelijk over ging, en de vierde keer in deze
    reeks dat een handmatige naamlijst een token te kort bleek.
    """
    uncovered = sorted(_executable_tool_names() - set(_IMPLEMENTATIONS))

    assert not uncovered, (
        f"Deze uitvoerbare tools staan niet in _IMPLEMENTATIONS: {uncovered}. Beide "
        "driftrichtingen in dit bestand itereren over dat literaal, dus voor deze tools wordt "
        "GEEN drift tussen PAYLOAD_POLICY en de code gedetecteerd -- een fantoomparameter of een "
        "gemiste sleutelnaam blijft daar onzichtbaar. Voeg de tool toe met de methode(n) die zijn "
        "payload lezen."
    )


def test_the_drift_detector_has_no_phantom_tools() -> None:
    """En de andere richting: een tool in `_IMPLEMENTATIONS` die niet meer bestaat.

    Zonder deze eis rot het literaal dicht: een verwijderde tool blijft staan, de scan zoekt naar
    een methode die er niet is, en het vangnet
    (`test_the_scanner_finds_keys_for_every_tool_that_has_them`) begint te klagen over iets anders
    dan het echte probleem.
    """
    phantom = sorted(set(_IMPLEMENTATIONS) - _executable_tool_names())

    assert not phantom, (
        f"Deze tools staan in _IMPLEMENTATIONS maar zijn niet uitvoerbaar: {phantom}. Haal ze "
        "eruit, anders bewaakt de drift-detector een tool die niet bestaat."
    )


def test_local_tool_names_dispatch_and_every_method_is_named() -> None:
    """`_TOOL_NAMES` in BEIDE richtingen tegen de methodenaamruimte.

    Richting 1: elke naam moet dispatchen -- anders staat er een tool in de lijst die niet
    bestaat, en dat is precies waarom `tool_risk_levels.yml` vier fantoom-`local__`-regels heeft.
    Richting 2: elke `_tool_*`-methode moet door een naam gedekt zijn -- anders bestaat er een
    uitvoerbare tool zonder beoordeling.
    """
    from src.core.tool_broker.local_registry import LocalToolRegistry
    from src.core.tool_broker.receivables_registry import ReceivablesToolRegistry

    registry = LocalToolRegistry()
    names = set(LocalToolRegistry.known_tool_names())

    def _method_for(tool_name: str) -> str:
        stripped = (
            tool_name.replace("local__", "", 1) if tool_name.startswith("local__") else tool_name
        )
        return f"_tool_{stripped.replace('__', '_')}"

    undispatchable = sorted(name for name in names if not hasattr(registry, _method_for(name)))
    assert not undispatchable, (
        f"Deze namen in _TOOL_NAMES dispatchen niet naar een methode: {undispatchable}."
    )

    methods = {name for name in dir(registry) if name.startswith("_tool_")}
    covered = {_method_for(name) for name in names}
    unnamed = sorted(methods - covered)
    assert not unnamed, (
        f"Deze _tool_*-methodes staan niet in _TOOL_NAMES: {unnamed}. Er bestaat dan een "
        "uitvoerbare tool zonder regel in PAYLOAD_POLICY, want de guard hierboven kan hem niet "
        "zien."
    )


def test_no_policy_declares_a_parameter_the_tool_never_reads() -> None:
    """Fantoomnamen: de tabel verklaart een sleutel bij het vocabulaire die de code niet leest."""
    offenders: list[str] = []

    for tool_name, methods in sorted(_IMPLEMENTATIONS.items()):
        actual = _measured_keys(tool_name) | set(_BROKER_INJECTED)
        phantom = sorted(_params(tool_name) - actual)
        if phantom:
            where = ", ".join(f"{path}::{method}" for path, method in methods)
            offenders.append(f"{tool_name}: {phantom} (gemeten in {where})")

    assert not offenders, (
        "Deze tools hebben een parameternaam in PAYLOAD_POLICY die de implementatie nooit "
        "uitleest:\n" + "\n".join(f"  - {o}" for o in offenders) + "\n\nEen fantoomnaam verklaart "
        "een sleutel leesbaar die niet bestaat; de ECHTE sleutel wordt dan gedigest. Zo stond "
        "`offset` in de tabel terwijl business_registry `skip` leest."
    )


def test_no_tool_reads_a_parameter_the_policy_does_not_know() -> None:
    """Ontbrekende namen: de tool leest een sleutel die de tabel niet kent."""
    offenders: list[str] = []

    for tool_name, methods in sorted(_IMPLEMENTATIONS.items()):
        actual = _measured_keys(tool_name) - set(_BROKER_INJECTED)
        unknown = sorted(actual - _params(tool_name))
        if unknown:
            where = ", ".join(f"{path}::{method}" for path, method in methods)
            offenders.append(f"{tool_name}: {unknown} (gemeten in {where})")

    assert not offenders, (
        "Deze tools lezen een payload-sleutel die niet in PAYLOAD_POLICY staat:\n"
        + "\n".join(f"  - {o}" for o in offenders)
        + "\n\nDie sleutelnaam wordt dan zelf een pseudonym, en de auditregel laat niet meer zien "
        "welke vorm de aanroep had. Voeg de naam toe, met een beoordeling of de WAARDE leesbaar "
        "mag blijven."
    )


def test_the_task_tools_match_their_pydantic_declaration() -> None:
    """`create_task`/`update_task` valideren via TaskCreate/TaskUpdate -- dat is het vocabulaire.

    `business_registry.py:124` en `:230` doen `TaskCreate(**data)` / `TaskUpdate(**data)`, dus elk
    veld van die modellen is een geldige parameter en niets anders is dat. De tabel liep hier
    respectievelijk 5 en 6 velden achter.
    """
    for tool_name, model_name in (("create_task", "TaskCreate"), ("update_task", "TaskUpdate")):
        expected = _schema_fields(model_name)
        actual = _params(tool_name) - set(_BROKER_INJECTED) - {"task_id"}

        assert actual == expected, (
            f"`{tool_name}` wijkt af van `{model_name}`.\n"
            f"  ontbreekt in de tabel : {sorted(expected - actual)}\n"
            f"  staat er te veel in  : {sorted(actual - expected)}\n"
            "De Pydantic-declaratie is de bron van waarheid; de tabel hoort hem te volgen."
        )


def test_the_hr_bounds_match_the_registry_constants() -> None:
    """De grenzen in de tabel komen van de tool, niet van een zelfgekozen rond getal.

    `_bounded_int(1_000)` / `_bounded_int(100_000)` moeten `MAX_LIMIT` / `MAX_OFFSET` zijn. Wijken
    ze uiteen, dan wordt een waarde leesbaar vastgelegd die de tool daarna alsnog weigert -- of
    juist gedigest terwijl hij geldig is.
    """
    from src.core.tool_broker.hr_registry import MAX_LIMIT, MAX_OFFSET
    from src.core.tool_broker.redaction import PAYLOAD_POLICY

    readable = PAYLOAD_POLICY["query_hr_database"].readable

    assert readable["limit"](MAX_LIMIT) is True
    assert readable["limit"](MAX_LIMIT + 1) is False, (
        f"De bovengrens voor `limit` is niet MAX_LIMIT ({MAX_LIMIT}) uit hr_registry."
    )
    assert readable["offset"](MAX_OFFSET) is True
    assert readable["offset"](MAX_OFFSET + 1) is False, (
        f"De bovengrens voor `offset` is niet MAX_OFFSET ({MAX_OFFSET}) uit hr_registry."
    )


#: Elke `_bounded_int`-grens in de tabel, met de constante waar hij vandaan moet komen.
#: (tool, sleutel) -> (module, constantennaam). Gedateerd 2026-08-04.
#:
#: Deze lijst bestaat omdat `test_the_hr_bounds_match_the_registry_constants` hierboven
#: hardgecodeerd is op `query_hr_database`. Een NIEUWE tool met een ruimere grens dan hij zelf
#: accepteert werd door niets betrapt -- precies de fout die de docstring van `_bounded_int`
#: beschrijft, en de reden dat de dekking hier expliciet is in plaats van per voorbeeld.
_BOUND_SOURCES: dict[tuple[str, str], tuple[str, str]] = {
    ("query_hr_database", "limit"): ("src.core.tool_broker.hr_registry", "MAX_LIMIT"),
    ("query_hr_database", "offset"): ("src.core.tool_broker.hr_registry", "MAX_OFFSET"),
    # `analyze_skill_gap` gebruikt dezelfde `_read_bounded_int` en dus dezelfde constanten.
    ("analyze_skill_gap", "limit"): ("src.core.tool_broker.hr_registry", "MAX_LIMIT"),
    ("analyze_skill_gap", "offset"): ("src.core.tool_broker.hr_registry", "MAX_OFFSET"),
    # `list_tasks` leest `skip`/`limit` rechtstreeks uit de payload (business_registry.py:178) en
    # heeft geen eigen constanten; de grenzen zijn bewust dezelfde als voor het HR-pad.
    ("list_tasks", "limit"): ("src.core.tool_broker.hr_registry", "MAX_LIMIT"),
    ("list_tasks", "skip"): ("src.core.tool_broker.hr_registry", "MAX_OFFSET"),
    # Debiteurentools (2026-10-05): de grenzen van `receivables_registry._list`.
    ("list_receivables", "limit"): ("src.core.tool_broker.receivables_registry", "MAX_LIMIT"),
    ("list_receivables", "offset"): ("src.core.tool_broker.receivables_registry", "MAX_OFFSET"),
    # De vertraging van de testtool; zie de reden bij PAYLOAD_POLICY.
    ("test__slow", "delay_seconds"): ("", "3600"),
}


def _bounded_int_keys() -> set[tuple[str, str]]:
    """Elke (tool, sleutel) waarvan de leesbare waarde een GRENS is en geen opsomming.

    Uit de BRON: een `_bounded_int`-checker heeft `maximum` in zijn closure, een `_one_of`-checker
    niet. Zo betrapt deze verzameling ook een nieuwe grens die iemand toevoegt.
    """
    from src.core.tool_broker.redaction import PAYLOAD_POLICY

    found: set[tuple[str, str]] = set()
    untagged: list[str] = []
    for tool_name, policy in PAYLOAD_POLICY.items():
        for key, shape in policy.readable.items():
            kind = getattr(shape, "shape_kind", None)
            if kind is None:
                untagged.append(f"{tool_name}.{key}")
                continue
            if kind == "range":
                found.add((tool_name, key))

    # Een vorm ZONDER label is een fout en geen geval om over te slaan (ADR-036 OP-51).
    #
    # Deze functie leidde de classificatie eerder af uit de aanwezigheid van de vrije variabele
    # `maximum` in de closure -- dus uit een NAAM. Een nieuwe vormsoort (`_bounded_str_len(maxlen)`,
    # `_int_range(lo, hi)`) heeft die naam niet, viel daardoor buiten `found`, en
    # `test_every_bound_in_the_policy_has_a_registered_source` bleef groen. Dan staat er een
    # leesbaar veld in `PAYLOAD_POLICY` zonder geregistreerde herkomst, en dat is exact het gat
    # waarvoor OP-34 bestaat.
    #
    # Stil overslaan zou diezelfde fout herhalen, dus hier faalt het luid: wie een vorm toevoegt,
    # labelt hem.
    assert not untagged, (
        f"Deze leesbare vormen hebben geen `shape_kind`: {sorted(untagged)}. Zet in de "
        "vorm-factory in `redaction.py` een `check.shape_kind = ...` -- 'range' als de waarde "
        "binnen een GRENS leesbaar blijft (die heeft een geregistreerde herkomst nodig), "
        "'enumeration' als hij lid moet zijn van een opgesomde verzameling. Zonder label kan deze "
        "guard een grens zonder herkomst niet zien."
    )
    return found


def test_every_bound_in_the_policy_has_a_registered_source() -> None:
    """Een grens zonder herkomst is een zelfgekozen rond getal.

    Toegevoegd 2026-08-04 (ronde 5). Faalscenario dat dit voorkomt: een sprint voegt
    `list_employees` toe met `readable={"limit": _bounded_int(1_000_000)}` terwijl de tool
    `MAX_LIMIT=100` hanteert. De policy-guard eist een regel, krijgt die, en zwijgt -- en het model
    heeft dan een leesbaar 20-bits veld in de onuitwisbare auditketen.
    """
    unregistered = sorted(_bounded_int_keys() - set(_BOUND_SOURCES))

    assert not unregistered, (
        f"Deze grenzen hebben geen geregistreerde herkomst: {unregistered}. Zet er de constante "
        "bij waar de grens van de TOOL vandaan komt, of leg met een reden vast waarom het getal "
        "hier gekozen is. Een ruimere grens dan de tool accepteert maakt een waarde leesbaar die "
        "de tool daarna alsnog weigert -- en dat is bandbreedte die het model vrij kiest (OP-34)."
    )


def test_the_bound_registry_is_not_stale() -> None:
    """Een geregistreerde grens die uit de tabel is verdwenen, hoort uit de lijst."""
    stale = sorted(set(_BOUND_SOURCES) - _bounded_int_keys())

    assert not stale, (
        f"Deze vermeldingen hebben geen grens meer in PAYLOAD_POLICY: {stale}. Haal ze uit "
        "_BOUND_SOURCES."
    )


def test_the_scanner_finds_keys_for_every_tool_that_has_them() -> None:
    """Mutatietest, richting 1: een guard die niets vindt, bewijst niets.

    Dit vangnet dekt ELKE tool en niet een voorbeeld. Dat is geen overdaad: de eerste versie van
    dit bestand had een vangnet op alleen `_tool_send_email`, en daardoor bleef onopgemerkt dat
    twee methodenamen in `_IMPLEMENTATIONS` niet bestonden -- de scan gaf leeg terug en meldde
    vervolgens elke parameter van die twee tools als fantoom. Een verkeerde methodenaam moet hier
    stuklopen, niet in een verwarrende foutmelding elders.

    `test__echo` is de enige uitzondering: die echoot de hele payload en leest geen benoemde
    sleutel (`test_tools.py:16`), dus zijn vocabulaire is met opzet leeg.
    """
    empty = sorted(
        tool_name
        for tool_name in _IMPLEMENTATIONS
        if tool_name != "test__echo" and not _measured_keys(tool_name)
    )

    assert not empty, (
        f"De scanner vond geen enkele payload-sleutel voor: {empty}. Waarschijnlijk bestaat een "
        "methodenaam in _IMPLEMENTATIONS niet (meer). Zolang de scan leeg terugkomt zijn de "
        "fantoom- en ontbrekende-naam-tests vacuum voor die tool."
    )


def test_the_scanner_does_not_invent_keys() -> None:
    """Mutatietest, richting 2: geen valse positieven op een methode zonder payload-lezingen."""
    keys = _read_keys_in_method(
        "src/core/tool_broker/local_registry.py", "LocalToolRegistry._load_whitelist"
    )

    assert "allowed_commands" not in _params("local__read_file"), (
        "Deze test gaat ervan uit dat `allowed_commands` geen tool-parameter is."
    )
    # `== set()` en niet `<= {...}` (aangescherpt 2026-08-04, ronde 5). `_load_whitelist` doet geen
    # enkele `.get()` op een payload-naam en retourneert dict-literals, dus de juiste verwachting is
    # LEEG. Met de oude `<=`-vorm zouden twee valse positieven ongehinderd passeren, en dan bewijst
    # deze mutatietest niets over de eigenschap die hij beweert te toetsen.
    assert keys == set(), (
        f"De scanner haalt sleutels uit een methode die geen payload leest: {sorted(keys)}. "
        "`_load_whitelist` leest geen payload, dus elke gevonden sleutel is een valse positief -- "
        "en een scanner met valse positieven meldt drift die er niet is, waarna de guard wordt "
        "uitgezet in plaats van vervuld."
    )


#: Een module met TWEE klassen die dezelfde methodenaam hebben, en een moduleniveau-functie met
#: die naam erbij. Elk lichaam leest een andere sleutel, zodat de gemeten sleutel VERTELT welk
#: lichaam de resolver heeft gepakt. Dat is de kern: de vorige versie kon niet mis gaan zonder
#: dat je het merkte, want hij gaf een plausibele maar verkeerde verzameling terug.
_COLLIDING_SOURCE = '''
def _handle(payload):
    """Moduleniveau-naamgenoot."""
    return payload.get("van_moduleniveau")


class Decoy:
    def _handle(self, payload):
        """Eerste klasse in het bestand -- deze pakte de oude scanner."""
        return payload.get("van_decoy")


class Real:
    def _handle(self, payload):
        """Deze hoort gemeten te worden."""
        return payload.get("van_real")
'''


def test_the_scanner_scopes_by_class() -> None:
    """Mutatietest OP-41: bij een naambotsing meet de scanner het JUISTE lichaam.

    Mutatie (2026-08-31, op een synthetische bron zodat de productiecode onaangeraakt blijft):
    drie functies met de naam `_handle` in een module -- op moduleniveau, in `Decoy` en in
    `Real` -- die elk een andere payload-sleutel lezen.

    Vastgesteld met de OUDE vorm (`for node in ast.walk(tree): ... break`) op exact deze bron:
    die gaf `{"van_moduleniveau"}` voor ELK van de drie doelen, want hij nam de eerste treffer in
    de module ongeacht scope. De sleutel is dus een getuige: krijg je `van_real` terug, dan is
    `Real._handle` gemeten en niets anders.

    Vandaag is dit latent -- de veertien namen in `_IMPLEMENTATIONS` komen elk exact een keer
    voor -- en juist daarom staat de eis hier en niet in een productiebestand: een tweede klasse
    met een `_handle_list_tasks` is een gewone refactor, en die mag deze driftdetectie niet stil
    op het verkeerde lichaam laten draaien.
    """
    assert _read_keys_in_source(_COLLIDING_SOURCE, "Real._handle", "probe.py") == {"van_real"}
    assert _read_keys_in_source(_COLLIDING_SOURCE, "Decoy._handle", "probe.py") == {"van_decoy"}
    assert _read_keys_in_source(_COLLIDING_SOURCE, "_handle", "probe.py") == {"van_moduleniveau"}


def test_the_scanner_does_not_reach_into_a_nested_function() -> None:
    """Andere richting: een geneste functie is GEEN methode van de omsluitende klasse.

    Mutatie: `Outer.method` bevat een geneste `def _inner`. `Outer._inner` mag niet resolven --
    doet hij dat wel, dan opent `_scope_members` functiebodies en kan elke hulpfunctie als
    methode worden aangewezen. Dat is de gemeten valkuil in dit project: `ast.walk()` op een
    `if`/`try`-blok duikt toch functiebodies in.
    """
    source = (
        "class Outer:\n"
        "    def method(self, payload):\n"
        "        def _inner(payload):\n"
        "            return payload.get('genest')\n"
        "        return _inner(payload)\n"
    )

    tree = ast.parse(source)
    assert _resolve_qualified(tree, "Outer.method") is not None
    assert _resolve_qualified(tree, "Outer._inner") is None, (
        "Een geneste functie resolvet als methode van de omsluitende klasse. Dan kan de "
        "driftdetectie het lichaam van een hulpfunctie meten in plaats van de tool-methode."
    )
    assert _resolve_qualified(tree, "_inner") is None, (
        "Een geneste functie resolvet als moduleniveau-functie."
    )


def test_the_scanner_still_finds_a_method_behind_a_transparent_block() -> None:
    """Andere richting: klasse-scoping mag een LEGITIEM geval niet weigeren.

    Zonder deze helft is "resolve nooit iets" een geldige oplossing: elke tool zou dan afketsen
    op de luide assertie in `_read_keys_in_source`, en dat leest als een kapotte guard in plaats
    van een strengere. Mutatie: dezelfde methode achter `if True:` in de klassebody en achter
    `try:` op moduleniveau -- beide horen gewoon gevonden te worden.
    """
    source = (
        "import typing\n"
        "try:\n"
        "    class Wrapped:\n"
        "        if typing.TYPE_CHECKING:\n"
        "            pass\n"
        "        if True:\n"
        "            def method(self, payload):\n"
        "                return payload.get('achter_een_blok')\n"
        "except ImportError:\n"
        "    pass\n"
    )

    assert _read_keys_in_source(source, "Wrapped.method", "probe.py") == {"achter_een_blok"}


def test_an_unresolvable_target_is_loud() -> None:
    """Een onvindbaar doel is een fout, geen lege verzameling.

    De oude vorm gaf stil `set()` terug bij een verkeerde methodenaam. De fantoomtest meldde
    dan elke parameter van die tool als "wordt nooit gelezen" -- een foutmelding over de
    verkeerde eigenschap, en dat kostte in een eerdere ronde al tijd aan twee namen die niet
    bestonden.
    """
    with pytest.raises(AssertionError, match="niet te vinden"):
        _read_keys_in_source(_COLLIDING_SOURCE, "Real._bestaat_niet", "probe.py")

    with pytest.raises(AssertionError, match="niet te vinden"):
        _read_keys_in_source(_COLLIDING_SOURCE, "GeenKlasse._handle", "probe.py")


def test_an_ambiguous_name_is_loud() -> None:
    """Twee definities met dezelfde naam in dezelfde scope: afketsen, niet gokken.

    Mutatie: een tweede moduleniveau-`test_echo` voor de echte. Op runtime wint de LAATSTE
    definitie, dus "de eerste pakken" is aantoonbaar het verkeerde antwoord -- en dat was wat de
    oude vorm deed. Bij de drie moduleniveau-tools kwam de oude vorm bij TOEVAL goed uit, omdat
    `ast.walk()` breedte-eerst is en de ondiepste treffer koos; met een naamgenoot op dezelfde
    diepte gaf hij stil `{"MUTANT"}` terug. Gemeten per element op 2026-08-31, alle zestien
    (pad, naam)-paren.
    """
    source = (
        'def dubbel(payload):\n    return payload.get("eerste")\n\n\n'
        'def dubbel(payload):\n    return payload.get("tweede")\n'
    )

    with pytest.raises(AssertionError, match="in dezelfde scope"):
        _read_keys_in_source(source, "dubbel", "probe.py")


def test_every_implementation_entry_names_its_class() -> None:
    """Elke vermelding in `_IMPLEMENTATIONS` resolvet, en resolvet EENDUIDIG.

    Dit is het vangnet per bewaakt element in plaats van per voorbeeld: de veertien
    (pad, gekwalificeerde naam)-paren worden hier alle veertien opgezocht. Een vermelding die
    per ongeluk kaal blijft terwijl de functie in een klasse leeft, valt hier om -- en niet pas
    in een verwarrende fantoommelding.
    """
    onvindbaar: list[str] = []
    for tool_name, methods in sorted(_IMPLEMENTATIONS.items()):
        for path, qualified in methods:
            tree = ast.parse((REPO_ROOT / path).read_text(encoding="utf-8"))
            if _resolve_qualified(tree, qualified) is None:
                onvindbaar.append(f"{tool_name}: {path}::{qualified}")

    assert not onvindbaar, (
        f"Deze vermeldingen in _IMPLEMENTATIONS resolveren niet: {onvindbaar}. Gebruik de "
        "gekwalificeerde naam (`Klasse.methode`) van de methode die de payload leest."
    )

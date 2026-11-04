"""Architecture test: het resultaat-pad naar de bewarende sinks is geregistreerd (ADR-036 OP-29).

OP-27 dekt de PAYLOAD. Het RESULTAAT niet: `result`, `tool_output` en `error_detail` gaan
ongefilterd naar dezelfde bewarende sinks. Bij `local__read_file` is `result` bestandsinhoud, bij
`local__llm_generate` modeltekst, en `error_detail=str(exc)` echoot routinematig de waarde die de
fout veroorzaakte -- dus vaak precies de invoerwaarde die OP-27 juist pseudonimiseert.

**Waarom deze guard bestaat.** De NOOIT-lijst in `.claude/rules/quality-gates.md` verbiedt een
bevinding naar de backlog te sturen zonder architecture-test in dezelfde commit. OP-29 werd in
ronde 1 in de ADR opgeschreven en had er geen -- terwijl de bevinding ernaast (OP-28) er wel een
kreeg. Precies het patroon waar die regel voor is geschreven.

Groene guard met een gedateerde uitzonderingslijst plus staleness-test in plaats van een rode
test: de CI-testgate is blokkerend, en OP-29 wordt niet in deze dag gedicht. Wat deze guard WEL
afdwingt: er komt geen NIEUWE plek bij die een resultaat rauw naar een bewarende sink stuurt
zonder dat iemand deze lijst moet uitbreiden en de reden opschrijven.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_ROOTS = (
    REPO_ROOT / "src/core/tool_broker",
    REPO_ROOT / "src/core/api/v1/tool_broker",
)

#: Sinks die bewaren (zie test_tool_payloads_are_pseudonymised.py voor de payload-kant).
SINKS = frozenset({"_publish_tool_event", "log_execution"})

#: Argumenten en dict-sleutels die het resultaat of de foutmelding dragen.
#:
#: `error` staat er sinds ronde 3 bij, en dat was een echt gat: de opgeslagen regel in
#: `execution_router.py` gebruikt de sleutel `error`, niet `error_detail`, dus de guard was blind
#: voor een lek dat via `str(exception)` de rauwe payload in een API-uitleesbare regel zette.
#: Derde keer in deze reeks dat een sink werd gemist omdat een naamlijst een token te kort was --
#: vandaar dat hier nu BEIDE spellingen staan.
RESULT_FIELDS = frozenset({"result", "tool_output", "error_detail", "error"})

#: Namen die aangeven dat de waarde door een filter is geweest. Nog nergens in gebruik; dit is
#: de vorm die de OP-29-fix moet aannemen, zodat deze guard hem dan automatisch accepteert.
SAFE_NAMES = frozenset({"publish_result", "publish_error"})

#: Bekende, gedateerde plekken waar een resultaat ongefilterd naar een bewarende sink gaat.
#: Sleutel: `<bestandsnaam>:<veld>`. Regelnummers bewust niet, die schuiven bij elke edit.
#:
#: Leeg sinds OP-29 is opgelost (2026-08-26): alle zes plekken geven nu `publish_result`/
#: `publish_error` door (redaction.py::digest_result/value_digest), berekend op de plek waar
#: het resultaat/de foutmelding voor het eerst beschikbaar is -- zelfde patroon als
#: `publish_payload` (OP-27).
KNOWN_UNFILTERED_RESULTS: dict[str, str] = {}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return str(getattr(func, "id", ""))


def _is_filtered(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id in SAFE_NAMES


def _is_a_stored_execution_record(node: ast.Dict) -> bool:
    """Is deze dict-literal een opgeslagen uitvoeringsregel?

    Gemeten criterium: hij draagt ook een `payload`-sleutel. Zonder die eis vangt de guard elke
    dict met een `"result"`-sleutel, en dat gaf twee valse positieven -- `mcp_client.py` geeft
    een toolresultaat terug aan de AANROEPER (geen opslag) en `schemas.py` is een
    OpenAPI-voorbeeld. Een guard die daarop rood staat wordt uitgezet, niet vervuld.
    """
    return any(isinstance(key, ast.Constant) and key.value == "payload" for key in node.keys if key)


def unfiltered_result_fields(source: str) -> set[str]:
    """Welke resultaatvelden gaan hier ongefilterd naar een bewarende sink?"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in SINKS:
            for keyword in node.keywords:
                if keyword.arg in RESULT_FIELDS and not _is_filtered(keyword.value):
                    found.add(str(keyword.arg))

        elif isinstance(node, ast.Dict) and _is_a_stored_execution_record(node):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in RESULT_FIELDS
                    and not _is_filtered(value)
                ):
                    found.add(str(key.value))

    return found


def _sources() -> tuple[list[tuple[str, str]], list[str]]:
    """(naam+inhoud per bewaakt bestand, leesfouten of ontbrekende scanwortels).

    Twee vaste mappen zonder eigen vangnet: een hernoemde scanwortel liet het bewaakte
    oppervlak stil naar nul krimpen, en een leesfout werd stil weggegooid.
    """
    resultaten: list[tuple[str, str]] = []
    fouten: list[str] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            fouten.append(f"{root.relative_to(REPO_ROOT).as_posix()}: scanwortel bestaat niet")
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                resultaten.append((path.name, path.read_text(encoding="utf-8-sig")))
            except (OSError, UnicodeDecodeError) as exc:
                fouten.append(f"{path.name}: {exc}")
    return resultaten, fouten


def _current_violations() -> tuple[set[str], list[str]]:
    """(overtredingen, fouten -- inclusief parse-fouten van echte bestanden)."""
    sources, fouten = _sources()
    violations: set[str] = set()
    for name, source in sources:
        try:
            ast.parse(source)
        except SyntaxError as exc:
            fouten.append(f"{name}: {exc}")
            continue
        for field in unfiltered_result_fields(source):
            violations.add(f"{name}:{field}")
    return violations, fouten


def test_the_scan_actually_scans_files() -> None:
    """Vangnet: een verplaatste scanwortel of een onleesbaar/onparseerbaar bestand mag
    deze guard niet blind maken."""
    sources, fouten = _sources()
    assert len(sources) >= 20, (
        f"Slechts {len(sources)} bestanden gescand onder {SCAN_ROOTS} -- dat lijkt een "
        "(bijna) lege scan. Deze guard controleert dan vrijwel niets."
    )
    _, parsefouten = _current_violations()
    alle_fouten = sorted(set(fouten) | set(parsefouten))
    assert not alle_fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden, of de scanwortel ontbreekt, en "
        "zijn NIET gecontroleerd op een ongefilterd resultaat:\n"
        + "\n".join(f"  - {f}" for f in alle_fouten)
    )


def test_no_new_unfiltered_result_reaches_a_persisting_sink() -> None:
    """Nieuwe plekken zijn geblokkeerd; de bekende staan gedateerd geregistreerd."""
    huidig, _fouten = _current_violations()
    new = sorted(huidig - set(KNOWN_UNFILTERED_RESULTS))

    assert not new, (
        "Hier gaat een tool-resultaat of foutmelding ongefilterd naar een bewarende sink:\n"
        + "\n".join(f"  - {item}" for item in new)
        + "\n\nEen resultaat kan bestandsinhoud, modeltekst of een echo van de invoerwaarde "
        "zijn. Filter het (naam `publish_result` / `publish_error`), of zet het met datum en "
        "reden in KNOWN_UNFILTERED_RESULTS -- dan is het een bewuste, vindbare beslissing."
    )


def test_known_unfiltered_results_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    huidig, _fouten = _current_violations()
    stale = sorted(set(KNOWN_UNFILTERED_RESULTS) - huidig)

    assert not stale, (
        f"Deze uitzonderingen gelden niet meer: {stale}. Het resultaat gaat daar niet langer "
        "ongefilterd naar een bewarende sink. Haal ze uit KNOWN_UNFILTERED_RESULTS zodat de "
        "guard die plek weer bewaakt."
    )


def test_the_guard_catches_an_unfiltered_result() -> None:
    """Mutatietest, richting 1: de guard betrapt een rauw resultaat."""
    found = unfiltered_result_fields("self._publish_tool_event(result=raw_output)\n")

    assert found == {"result"}, "Een rauw resultaat naar een bewarende sink passeert."


def test_the_guard_catches_an_unfiltered_result_in_a_stored_record() -> None:
    """Ook de dict-vorm: zo bewaart de uitvoeringsgeschiedenis zijn regel."""
    found = unfiltered_result_fields(
        "store[key] = {'payload': publish_payload, 'result': raw_output}\n"
    )

    assert found == {"result"}, "Een rauw resultaat in een opgeslagen uitvoeringsregel passeert."


def test_the_guard_ignores_a_result_that_is_returned_not_stored() -> None:
    """Een resultaat teruggeven aan de aanroeper is geen opslag.

    `mcp_client.py` doet `return {"result": text}` en `schemas.py` heeft een OpenAPI-voorbeeld
    met die sleutel. Beide werden door een eerdere, bredere versie van deze guard als
    overtreding gemeld -- twee gemeten valse positieven.
    """
    found = unfiltered_result_fields("return {'result': text_value}\n")

    assert not found, (
        "De guard meldt een resultaat dat aan de aanroeper wordt teruggegeven. Dat is geen "
        "bewarende sink; zo'n guard staat rood om de verkeerde reden en wordt uitgezet."
    )


def test_the_guard_accepts_a_filtered_result() -> None:
    """Mutatietest, richting 2: geen valse positieven.

    Zonder deze test blijft de guard groen door alles te verwerpen, en dan meet hij niet of het
    resultaat gefilterd is maar of iemand het veld uberhaupt gebruikt.
    """
    found = unfiltered_result_fields("self._publish_tool_event(result=publish_result)\n")

    assert not found, (
        "De guard verwerpt de gefilterde vorm. Dan kan de OP-29-fix hem nooit groen krijgen en "
        "wordt de guard bij het dichten van de bevinding weggehaald in plaats van vervuld."
    )

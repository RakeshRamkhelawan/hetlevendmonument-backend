"""Architecture test: het HITL-auditarchief is admin-only en zonder klaartekst (ADR-036 OP-31).

`GET /api/v1/tools/hitl/audit` had als enige dependency `get_current_user` -- geen scope, geen
adminrol -- en leverde voor ELK ticket in de tenant, in elke status en onbeperkt in tijd het
ONBEWERKTE `tool_input` uit, plus het e-mailadres van de aanvrager. Voor de tools die een ticket
krijgen (HIGH-risk: `local__run_shell`, `local__send_email`) is dat de klaartekst van de aanroep.

Dat maakte de pseudonimisering van OP-27 omzeilbaar langs de voordeur: wat in de ADR-019
auditketen een digest is, stond hier in het klare voor iedere ingelogde collega.

**De grens die deze guard vastlegt.** AI Act art. 14 rechtvaardigt dat de GOEDKEURDER ziet wat
hij goedkeurt, op het moment van goedkeuren -- dat is `/hitl/pending`, en daar blijven de waarden
staan. Het rechtvaardigt geen permanent, tenantbreed klaartekstarchief. Die twee endpoints moeten
dus verschillend zijn, en dat verschil hoort onder een test te staan zodat niemand ze later "voor
de consistentie" gelijktrekt -- in welke richting dan ook.

Geen gedateerde uitzonderingslijst: dit is GEFIXED, niet uitgesteld. Een lege lijst zou hier dus
misleidend zijn.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
#: De vier HITL-endpoints zijn op 2026-08-05 uit `tool_broker/router.py` gehaald en in een
#: EIGEN router gezet (ADR-036 OP-37). Reden: dat bestand bevat 11 routes waaronder een
#: tokenendpoint dat het wachtwoord niet tegen de database controleert, en het moest
#: geserveerd worden. Alleen de vier hier mounten houdt de aangeboden oppervlakte gelijk aan
#: de bedoelde. Deze guard volgt de code; hij bewaakt dezelfde eigenschap op de nieuwe plek.
ROUTER = REPO_ROOT / "src/core/api/v1/tool_broker/hitl_router.py"

#: De functie die het permanente archief teruggeeft, en de functie die het
#: goedkeuringsoppervlak is. Beide met opzet in deze test, want de eigenschap is dat ze
#: VERSCHILLEN.
AUDIT_ENDPOINT = "list_hitl_audit"
APPROVAL_ENDPOINT = "list_pending_hitl_requests"


def _function(name: str) -> ast.AST:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(
        f"`{name}` bestaat niet meer in {ROUTER.name}. Hernoemd of verplaatst? Werk deze guard "
        "bij -- anders bewaakt hij niets."
    )


def _calls_admin_check(name: str) -> bool:
    """Staat er een AANROEP van de adminrol-check in deze functie?

    **Wat dit niet toetst, en dat is gemeten en niet vermoed:** of het RESULTAAT van die aanroep
    iets afdwingt. Nagegaan 2026-08-04 (ronde 5) door de `raise` te vervangen door een kale
    `is_tenant_admin(current_user)`-aanroep: deze check bleef groen, terwijl de gedragstest
    `test_a_normal_tenant_user_is_refused` terecht omviel. De AST-vorm bewaakt dus dat de check
    AANWEZIG is en het gedragstestpaar dat hij WERKT -- samen genoeg, apart niet. De docstring
    beloofde eerder het tweede en leverde het eerste.
    """
    for node in ast.walk(_function(name)):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if called in {"is_tenant_admin", "_is_tenant_admin"}:
                return True
    return False


def _excludes_tool_input(name: str) -> bool:
    """Filtert deze functie haar projectie, en zo ja: op een uitsluiting of een toelaatlijst?

    Herkent beide vormen, want ze zijn allebei in omloop geweest:

    - `!= "tool_input"` -- de oude uitsluiting;
    - `in _AUDIT_FIELDS` -- de toelaatlijst die die uitsluiting sinds ADR-036 OP-67 vervangt.

    Dat de uitsluitingsvorm hier nog wordt herkend is geen tolerantie: de omgekeerde test
    hieronder (`/hitl/pending` MOET de waarden tonen) gebruikt dezelfde functie, en die moet
    blijven betrappen dat iemand daar alsnog een filter aanzet, in welke vorm dan ook.

    Zelfde beperking als `_calls_admin_check`: dit is een VORMtoets op de aanwezigheid van een
    filter, geen bewijs dat de geretourneerde projectie klopt. Dat laatste dekken de gedragstest
    en `test_the_audit_allowlist_contains_no_model_written_field` hieronder.
    """
    for node in ast.walk(_function(name)):
        if (
            isinstance(node, ast.Compare)
            and any(isinstance(op, ast.NotEq) for op in node.ops)
            and any(
                isinstance(comparator, ast.Constant) and comparator.value == "tool_input"
                for comparator in node.comparators
            )
        ):
            return True
        if (
            isinstance(node, ast.Compare)
            and any(isinstance(op, ast.In) for op in node.ops)
            and any(
                isinstance(comparator, ast.Name) and comparator.id == "_AUDIT_FIELDS"
                for comparator in node.comparators
            )
        ):
            return True
    return False


#: Velden in de ticket-dict die door een TAALMODEL zijn geschreven, en dus nooit in een permanent
#: archief horen. `hitl_store._to_dict` leest ze uit `payload`, en die payload is op het live pad
#: `dict(proposal.action_params)` plus `_reason` (= `decision.explanation_for_user`).
_MODEL_WRITTEN_FIELDS = frozenset({"tool_input", "reason", "agent_id", "task_id"})


def test_the_audit_allowlist_contains_no_model_written_field() -> None:
    """De toelaatlijst zelf, niet de vorm van de code eromheen (ADR-036 OP-67).

    De vorige guard toetste uitsluitend op `tool_input`. Een blinde review mat wat er dan nog
    doorheen kwam: `reason` is modelproza dat de HIGH-risk handeling beschrijft en in de praktijk
    de parameters navertelt. Het endpoint beloofde te tonen DAT er iets is gevraagd en niet WAT,
    en die belofte klopte niet. Deze test kijkt naar de inhoud van de lijst, zodat een nieuw
    modelveld niet stil kan meeliften.
    """
    from src.core.api.v1.tool_broker.hitl_router import _AUDIT_FIELDS

    leaking = sorted(_MODEL_WRITTEN_FIELDS & set(_AUDIT_FIELDS))

    assert not leaking, (
        f"Deze velden zijn door een taalmodel geschreven en staan TOCH in de toelaatlijst van "
        f"/hitl/audit: {leaking}. Het archief hoort te tonen DAT er iets is gevraagd, niet WAT."
    )


def test_the_audit_allowlist_still_carries_the_oversight_identities() -> None:
    """De andere kant: leegmaken is geen oplossing.

    Zonder wie het vroeg en wie het goedkeurde is een art.-14-toezichtsarchief waardeloos. Deze
    test zorgt dat "alles eruit" niet als fix telt.
    """
    from src.core.api.v1.tool_broker.hitl_router import _AUDIT_FIELDS

    for field in ("ticket_ref", "status", "requested_by", "approved_by", "created_at"):
        assert field in _AUDIT_FIELDS, (
            f"`{field}` ontbreekt in de toelaatlijst van /hitl/audit. Een toezichtsarchief zonder "
            "identiteiten en tijdstippen toont niets bruikbaars."
        )


def test_the_hitl_audit_archive_requires_an_admin_role() -> None:
    """Een permanent archief van goedkeuringsverzoeken is geen gewoon leesrecht."""
    assert _calls_admin_check(AUDIT_ENDPOINT), (
        f"`{AUDIT_ENDPOINT}` roept geen adminrol-check aan. Dan kan elke ingelogde gebruiker van "
        "de tenant het volledige HITL-archief lezen, inclusief wie wat heeft aangevraagd. "
        "Gebruik `is_tenant_admin` uit `src/core/auth/dependencies.py` -- niet een eigen kopie: "
        "die check bestond al twee keer identiek en is daarom geconsolideerd."
    )


def test_the_hitl_audit_archive_does_not_project_tool_input() -> None:
    """Het archief laat zien DAT er iets is gevraagd, niet WAT."""
    assert _excludes_tool_input(AUDIT_ENDPOINT), (
        f"`{AUDIT_ENDPOINT}` sluit `tool_input` niet uit de projectie. Dan staat de klaartekst "
        "van de tool-aanroep permanent in een API-antwoord, terwijl dezelfde gegevens in de "
        "ADR-019 auditketen gepseudonimiseerd zijn (OP-27). De pseudonimisering is dan "
        "omzeilbaar langs de voordeur."
    )


def test_the_approval_surface_still_shows_the_real_values() -> None:
    """De andere richting: `/hitl/pending` MOET de waarden blijven tonen (AI Act art. 14).

    Zonder deze test is "sluit tool_input overal uit" een geldige oplossing, en dan keurt een mens
    een actie goed zonder te zien wat hij goedkeurt -- dan is het toezicht een formaliteit. Dit is
    de reden dat de uitzondering op de redactie bestaat, en die reden hoort even hard vast te
    staan als de beperking hierboven.
    """
    assert not _excludes_tool_input(APPROVAL_ENDPOINT), (
        f"`{APPROVAL_ENDPOINT}` sluit `tool_input` nu ook uit. Dat is het GOEDKEURINGS-oppervlak: "
        "wie een actie goedkeurt moet zien wat hij goedkeurt (AI Act art. 14). Is dit bewust, "
        "dan hoort er een ADR-aanpassing bij en niet alleen een codewijziging."
    )


def test_the_guard_can_tell_the_two_endpoints_apart() -> None:
    """Vangnet: als de AST-analyse stilvalt, zeggen de tests hierboven niets.

    Beide functies moeten gevonden worden EN de twee eigenschappen moeten daadwerkelijk
    verschillen. Zou `_excludes_tool_input` altijd True of altijd False geven, dan zou een van de
    drie tests hierboven vacuum zijn zonder dat het opvalt.
    """
    assert _excludes_tool_input(AUDIT_ENDPOINT) != _excludes_tool_input(APPROVAL_ENDPOINT), (
        "De analyse geeft voor beide endpoints dezelfde uitkomst. Dan meet ze niet het verschil "
        "dat deze guard bewaakt, en zijn de tests hierboven niet betekenisvol."
    )


def _ticket_dict_keys() -> set[str]:
    """De sleutels die `hitl_store._ticket_to_dict` DAADWERKELIJK oplevert.

    Gemeten door de functie aan te roepen, niet door de bron te lezen: sinds ADR-036 OP-68 is hij
    puur (geen database-toegang), dus dat kan gewoon.
    """
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from src.core.tool_broker.hitl_store import _ticket_to_dict

    nu = datetime.now(timezone.utc)
    ticket = SimpleNamespace(
        ticket_ref="TOOL-X",
        tenant_id=1,
        status="pending",
        tool_name="create_task",
        payload={},
        risk_level="HIGH",
        created_at=nu,
        expires_at=nu,
        resolved_at=None,
        resolved_by=None,
        resolution_note=None,
    )
    return set(_ticket_to_dict(ticket, None))


def test_every_allowed_field_actually_exists_in_the_response() -> None:
    """Een toelaatlijst moet over ECHTE velden gaan (ADR-036 OP-82).

    **Hoe dit gevonden is.** De blinde securityreview mat dat `_AUDIT_FIELDS` de namen
    `created_at`, `resolved_at` en `risk_level` bevatte terwijl `_ticket_to_dict` die nooit
    oplevert. Gevolg: het toezichtsarchief had geen aanmaaktijdstip en geen risiconiveau, terwijl de
    guard ernaast vrolijk `"created_at" in _AUDIT_FIELDS` bevestigde. De guard toetste de LIJST en
    niet het ANTWOORD -- precies het onderscheid waar deze hele reeks over gaat.

    Deze test sluit die klasse fout: een naam in de lijst die de dict niet kent, valt om.
    """
    from src.core.api.v1.tool_broker.hitl_router import _AUDIT_FIELDS

    bestaat_niet = sorted(set(_AUDIT_FIELDS) - _ticket_dict_keys())

    assert not bestaat_niet, (
        f"Deze velden staan in de toelaatlijst van /hitl/audit maar worden nooit opgeleverd: "
        f"{bestaat_niet}. De lijst suggereert dan informatie die het antwoord niet bevat -- en een "
        "guard die de lijst toetst in plaats van het antwoord bevestigt dat."
    )


def test_the_broadcast_allowlist_also_only_names_real_fields() -> None:
    """Zelfde eis voor de websocket-projectie."""
    from src.core.tool_broker.hitl_notifier import _BROADCASTABLE

    bestaat_niet = sorted(set[str](_BROADCASTABLE) - _ticket_dict_keys())

    assert not bestaat_niet, (
        f"Deze velden staan in _BROADCASTABLE maar worden nooit opgeleverd: {bestaat_niet}."
    )


def test_the_audit_archive_carries_a_timestamp_and_a_risk_level() -> None:
    """Wat een toezichtsarchief minimaal moet kunnen zeggen.

    Zonder aanmaaktijdstip kan een auditor niet vaststellen WANNEER er iets is gevraagd, en zonder
    risiconiveau niet waarom er een mens aan te pas moest komen. Beide stonden wel in de lijst en
    ontbraken in het antwoord.
    """
    from src.core.api.v1.tool_broker.hitl_router import _AUDIT_FIELDS

    geleverd = _ticket_dict_keys()
    for veld in ("created_at", "risk_level", "resolution_note"):
        assert veld in _AUDIT_FIELDS and veld in geleverd, (
            f"`{veld}` ontbreekt in de toelaatlijst of in het antwoord van /hitl/audit. "
            f"In lijst: {veld in _AUDIT_FIELDS}; geleverd: {veld in geleverd}."
        )

"""Architecture test: de audit-hash dekt wat de auditregel als invoer bewaart (OP-28).

`compute_audit_hash` (`tool_broker/audit_utils.py`) dekt tenant, agent, tool, timestamp, status,
output-hash en previous-hash. Vijf kolommen van `ToolAuditLog` bewaren door de aanroeper
aangeleverde gegevens en staan er NIET in. Die kolommen staan dus in een keten die manipulatie
hoort te detecteren, zonder zelf gedekt te zijn: ze zijn te wijzigen zonder dat
`verify_chain_integrity()` breekt.

Dat weegt zwaarder sinds OP-27: juist `tool_input` draagt nu het gepseudonimiseerde spoor van de
invoer, en dat spoor is waarmee art. 12(2) toezicht en risico-identificatie mogelijk maakt.
Bewijs dat niet manipulatiebeschermd is, is zwakker bewijs.

**Let op de onderbouwing.** Een eerdere versie van dit bestand schreef dat `tool_input` het bewijs
draagt dat de AI-verordening zou EISEN. Die claim is in ronde 3 weerlegd -- invoer-logging is alleen
verplicht voor Annex III punt 1(a) (biometrische identificatie) en dit systeem valt onder punt 4 --
en stond hier nog in TWEE assertiemeldingen. Dat is de gevaarlijkste plek voor een onjuiste
wetsclaim: wie deze test ziet falen leest de melding als argument, en concludeert dan dat de invoer
leesbaar moet blijven. Precies de afweging die vier reviewrondes de verkeerde kant op is gegaan.
Zie ADR-036 OP-27 en `tests/architecture/test_refuted_ai_act_claim_stays_refuted.py`.

**Correctie ronde 2.** De eerste versie noemde alleen `tool_input` en verstopte de andere vier
in `_NOT_INPUT` -- de lijst "geen aangeleverde invoer". Daardoor leek OP-28 een kolom te
beslaan terwijl het er vijf zijn. `_NOT_INPUT` bevatte bovendien twee namen die geen kolom van
dit model zijn (`created_at`, `metadata`), en de staleness-test keek daar niet naar. Een
uitzonderingslijst die zijn eigen verval niet detecteert is precies wat de
uitzonderingsparagraaf in `.claude/rules/quality-gates.md` wil voorkomen, dus staat er nu ook
een staleness-test op `_NOT_INPUT`.

Groene guard met een gedateerde uitzondering in plaats van een rode test, conform die
uitzonderingsparagraaf: de CI-testgate is blokkerend, dus een opzettelijk rode test zou elke
merge van iedereen stilleggen voor een bevinding die naar Fase D gaat. Nieuwe gevallen worden
wel geblokkeerd, en de staleness-tests zorgen dat een uitzondering niet stil blijft staan nadat
hij is opgelost.
"""

import inspect

#: Kolommen op `ToolAuditLog` die door de aanroeper aangeleverde gegevens bewaren en dus in de
#: hash horen. Pad -> reden, gedateerd. Leeg sinds OP-28 is opgelost (2026-08-26):
#: `compute_audit_hash` neemt nu ook `tool_input`/`task_id`/`error_detail`/`hitl_ticket_ref`/
#: `hitl_approved_by` op, via de enige aanroeper (`audit_repository.py::log_execution`).
KNOWN_UNHASHED_INPUT: dict[str, str] = {}

#: Kolommen die bewust niet in de hash zitten omdat ze geen aangeleverde invoer zijn.
#: Reden per regel, want zonder reden is dit een plek om bevindingen in te laten verdwijnen --
#: wat in ronde 1 ook gebeurde.
_NOT_INPUT: dict[str, str] = {
    "id": "surrogaatsleutel van de database, niet aangeleverd",
    "audit_hash": "de hash zelf; kan zichzelf niet dekken",
    "output_hash": "afgeleide van tool_output en zit als parameter WEL in de hash",
    "tool_output": "gedekt via output_hash, dat in de hash zit",
    "duration_seconds": "door de broker gemeten, niet aangeleverd",
    "risk_level": "deterministisch afgeleid van tool_name, dat in de hash zit",
}


def _hashed_parameters() -> set[str]:
    from src.core.tool_broker.audit_utils import compute_audit_hash

    return set(inspect.signature(compute_audit_hash).parameters)


def _all_column_names() -> set[str]:
    from src.core.governance.models import ToolAuditLog

    return {str(column.name) for column in ToolAuditLog.__table__.columns}


def _input_columns() -> set[str]:
    return _all_column_names() - set(_NOT_INPUT)


def test_every_persisted_input_column_is_hashed() -> None:
    """Een nieuwe invoerkolom moet in de hash worden opgenomen."""
    unhashed = sorted(_input_columns() - _hashed_parameters() - set(KNOWN_UNHASHED_INPUT))

    assert not unhashed, (
        "Deze kolommen van ToolAuditLog bewaren aangeleverde gegevens maar zitten niet in "
        f"compute_audit_hash: {unhashed}. Een auditketen die zijn eigen invoer niet dekt, "
        "detecteert wijziging van die invoer niet -- en sinds OP-27 draagt die invoer het "
        "gepseudonimiseerde spoor waarmee art. 12(2) toezicht mogelijk maakt.\n\nNeem de kolom op "
        "in de hash, of zet hem met datum en reden in KNOWN_UNHASHED_INPUT.\n\nLET OP: dit is GEEN "
        "argument om de invoer leesbaar te houden. Dat de wet leesbare invoer zou eisen is een "
        "weerlegde claim (ADR-036 OP-27, ronde 3) -- invoer-logging is alleen verplicht voor "
        "biometrische identificatie, en dit systeem valt daar niet onder."
    )


def test_known_unhashed_list_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    hashed = _hashed_parameters()
    columns = _all_column_names()

    stale = sorted(name for name in KNOWN_UNHASHED_INPUT if name in hashed or name not in columns)

    assert not stale, (
        f"Deze uitzonderingen gelden niet meer: {stale}. Ze zitten inmiddels in de hash of de "
        "kolom bestaat niet meer. Haal ze uit KNOWN_UNHASHED_INPUT."
    )


def test_not_input_list_is_not_stale() -> None:
    """Ook de 'geen invoer'-lijst mag geen verlopen namen bevatten.

    Zonder deze test kan een naam die geen kolom (meer) is blijven staan, en dan verbergt de
    lijst niets zichtbaars maar wel de mogelijkheid om er iets in te laten verdwijnen. In ronde
    1 stonden `created_at` en `metadata` erin; geen van beide is een kolom van dit model, en
    vijf echte invoerkolommen stonden ertussen.
    """
    columns = _all_column_names()
    stale = sorted(name for name in _NOT_INPUT if name not in columns)

    assert not stale, (
        f"Deze namen in _NOT_INPUT zijn geen kolom van ToolAuditLog: {stale}. Verwijder ze -- "
        "een uitzondering voor een niet-bestaande kolom dekt niets en maskeert wel."
    )


#: De vijf kolommen die tot 2026-08-26 in KNOWN_UNHASHED_INPUT stonden. Zwart-doos-bewijs
#: hieronder, want de twee tests hierboven meten alleen of `compute_audit_hash` een parameter
#: MET DIE NAAM heeft -- niet of die parameter ook echt in het gehashte payload terechtkomt.
#: Dat gat is geen theorie: het verwijderen van `task_id` uit de `data`-dict binnen de functie
#: (parameter laten staan, alleen de regel in de dict weghalen) liet beide tests hierboven
#: GROEN, want de signature veranderde niet. Vandaar deze test op het ANTWOORD van de functie,
#: niet op zijn vorm.
_VOORHEEN_ONGEDEKTE_KOLOMMEN = (
    "tool_input",
    "task_id",
    "error_detail",
    "hitl_ticket_ref",
    "hitl_approved_by",
)


def _basis_argumenten() -> dict[str, object]:
    from datetime import datetime, timezone

    return {
        "tenant_id": 1,
        "agent_id": "agent-1",
        "tool_name": "local__read_file",
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "status": "success",
        "output_hash": "deadbeef",
        "previous_hash": "genesis",
        "tool_input": {"path": "a"},
        "task_id": "task-1",
        "error_detail": None,
        "hitl_ticket_ref": None,
        "hitl_approved_by": None,
    }


def test_changing_a_previously_unhashed_column_changes_the_hash() -> None:
    """Zwart-doos-tegenbewijs voor de signature-check hierboven: de VORM is niet genoeg.

    Voor elk van de vijf kolommen die tot 2026-08-26 buiten de hash vielen: een andere waarde
    voor die kolom, alle andere argumenten gelijk, moet een andere hash opleveren. Blijft de
    hash gelijk, dan wordt die waarde -- ondanks een gelijknamige parameter op de functie --
    in werkelijkheid niet gehasht.
    """
    from src.core.tool_broker.audit_utils import compute_audit_hash

    basis = _basis_argumenten()
    referentie = compute_audit_hash(**basis)  # type: ignore[arg-type]

    ongewijzigd: list[str] = []
    for kolom in _VOORHEEN_ONGEDEKTE_KOLOMMEN:
        gewijzigd = dict(basis)
        huidige = gewijzigd[kolom]
        gewijzigd[kolom] = {"anders": True} if isinstance(huidige, dict) else "een-andere-waarde"
        andere_hash = compute_audit_hash(**gewijzigd)  # type: ignore[arg-type]
        if andere_hash == referentie:
            ongewijzigd.append(kolom)

    assert not ongewijzigd, (
        f"Deze kolommen veranderen de hash niet, ondanks een gelijknamige parameter op "
        f"compute_audit_hash: {ongewijzigd}. De parameter bestaat dus wel, maar wordt niet "
        "(meer) opgenomen in het gehashte payload -- controleer de `data`-dict in de "
        "functie zelf, niet alleen de signature."
    )

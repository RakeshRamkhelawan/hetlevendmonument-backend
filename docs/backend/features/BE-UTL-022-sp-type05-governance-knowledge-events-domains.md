# BE-UTL-022 — SP-TYPE-05 Governance/Knowledge/Events/Domains Type Hardening

**ID:** BE-UTL-022
**Sprint:** SP-TYPE-05 Dag 6-9
**Type:** Utility (type refactoring)
**Status:** CLOSED
**Bestanden:** src/core/governance/, src/core/knowledge/, src/core/events/, src/domains/

## Samenvatting

Type hardening in governance layer, knowledge services, event pub/sub, and domain services.

## Wijzigingen

SP-TYPE-02 Group B: 11 source files updated, 32 AST regression tests written and passing (0.61s).

Changes by file:

- **compliance_guardian.py**: removed empty `if TYPE_CHECKING:` block and its unused `TYPE_CHECKING` import
- **rate_limiter.py**: removed unused `Optional` import
- **cookie_consent.py**: removed unused `Optional` import; narrowed local `ts: Any` to `ts: datetime | None` (getattr on ORM datetime columns)
- **sharding.py**: narrowed `_analyze_event` return from `Any | None` to `dict[str, Any] | None`; narrowed `_handle_violations` param from `list[Any]` to `list[dict[str, Any]]`
- **knowledge_service.py**: removed unused `Optional` import
- **sop_executor.py**: removed unused `Dict`, `List`, `Optional` imports
- **pubsub_manager.py**: removed unused `Dict`, `List`, `Optional` imports
- **observability.py**: removed unused `List`, `Optional` imports
- **experiments.py**: removed unused `Any` import entirely; narrowed all four endpoint return types from `Any` to `ExperimentResponse`, `list[ExperimentResponse]`, `ExperimentResponse`, and `dict[str, str]` respectively
- **chat_service.py**: removed unused `Dict`, `List`, `Optional` imports; narrowed `serialized_tool_calls: Any` to `list[dict[str, Any]] | None`
- **experimentation_service.py**: removed unused `Optional` import

Skipped (per rules): all `*args: Any`, `**kwargs: Any`, generic decorator signatures, unknown external service types (signal_bus, tool_broker, ab_framework results), `get_stats() -> dict[str, Any]` (mixed-type values: bool/int/list[str]), `pubsub: Any` (redis asyncio pubsub — external type, no stub).

## Trainingssamenvatting

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | SP-TYPE-05 workflow agent |
| Voorwaarde | 11 source files in governance/knowledge/events/domains with unused legacy imports and `Any`-typed locals/returns |
| Actie | HIGH-confidence Any replacements via parallel analysis; unused import removal; local variable narrowing |
| Systeemreactie | ruff import checks pass; AST regression tests verify narrowed types persist |
| Succesrespons | 32 AST regression tests green in 0.61s, 0 ruff errors, 0 mypy regressions |
| Foutrespons | Skipped files documented with rationale (external types, heterogeneous dicts, *args/**kwargs) |
| Uitzonderingen | `*args: Any`, `**kwargs: Any`, governance rule dicts (`dict[str, Any]` legitimately heterogeneous), redis asyncio pubsub (no stub available) |

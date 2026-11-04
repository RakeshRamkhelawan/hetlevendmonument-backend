# BE-SVC-012 -- HITL Store DB-backed (SP-WE-04)

**ID:** BE-SVC-012
**Sprint:** SP-WE-04
**Datum:** 2026-06-01
**ADR:** ADR-015 (WE-018)

---

## Samenvatting

Twee onafhankelijke HITL stores bestonden naast elkaar (WE-018):
- `hitl_store.py`: in-memory dict `_hitl_tickets`, gelezen door `execute_tool()`
- `hitl_repository.py`: ORM-backed DB repository, aangesproken door REST API

Operator-goedkeuringen via de REST API bereikten `execute_tool()` nooit.
De HITL-gate was effectief gebroken. Fix: `HITLStore` volledig herschreven als DB-backed
wrapper over `HITLTicketRepository`.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/tool_broker/hitl_store.py` | `_hitl_tickets` in-memory dict verwijderd; `HITLStore.__init__(repository: HITLTicketRepository)`; `create_ticket()` -> `repository.create()`; `get_approval_status()` -> `repository.get()` |
| `src/core/tool_broker/service.py` | `execute_tool()` bouwt `HITLStore(repo)` on-demand via `db_session`; lest approval status uit DB |

## Architectuurbeslissingen

1. **HITLStore als thin wrapper**: `HITLStore` delegeert volledig naar `HITLTicketRepository`; geen eigen state.
2. **On-demand instantiatie in execute_tool**: `ToolBrokerService` bouwt `HITLStore` on-demand via `self.db_session` (lazy, per request).
3. **Tenant-scoped reads**: `get_approval_status(ticket_id, tenant_id=tenant_id)` — operator van tenant A kan ticket van tenant B niet zien.

## Trainingssamenvatting

### Flow 1: Operator keurt HITL-ticket goed; tool wordt uitgevoerd

- **Actor:** Operator (via HITL review UI) + ToolBrokerService (systeem)
- **Voorwaarde:** HITL ticket aangemaakt door ToolBrokerService; ticket staat op "pending"
- **Actie:** Operator POST /api/v1/hitl/{id}/approve via REST API
- **Systeemreactie:** `HITLTicketRepository.update(status="approved")` in DB; `ToolBrokerService.execute_tool()` roept `HITLStore.get_approval_status()` aan -> leest status uit DB
- **Succesrespons:** `status="approved"` -> tool wordt uitgevoerd
- **Foutrespons:** status != "approved" of ticket niet gevonden -> `ToolExecutionException` (tool geblokkeerd)
- **Uitzonderingen:** ticket van andere tenant (tenant_id mismatch) -> `None` -> tool geblokkeerd

### Flow 2: Operator wijst HITL-ticket af

- **Actor:** Operator
- **Voorwaarde:** HITL ticket op "pending"
- **Actie:** POST /api/v1/hitl/{id}/reject
- **Systeemreactie:** `status="rejected"` in DB
- **Succesrespons:** `execute_tool()` ziet rejected -> `ToolExecutionException`
- **Foutrespons:** ticket niet gevonden -> 404
- **Uitzonderingen:** n/a

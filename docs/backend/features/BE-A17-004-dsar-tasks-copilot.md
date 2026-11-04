# BE-A17-004 -- DSAR dekt agentic_tasks + copilot conversation-memory (GDPR art. 17)

- Feature ID: BE-A17-004
- Status: Implemented
- Sprint: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 7
- Branch: `iter/dag7-gdpr`
- Reviewer: code-reviewer + security-reviewer (Gate 2) -- zie `docs/backend/review/review-BE-A17-004.md`
- Datum: 2026-07-13
- ADR: ADR-003/004/005 (tenant-isolatie + RLS), ADR-019 (audit)

## Doel

DSAR-export (art. 20) en -erasure (art. 17) dekten `agentic_tasks` en het copilot-conversatiegeheugen
niet. Beide worden nu meegenomen, per-user en tenant-gescoped.

## Werk (`src/core/governance/dsar_service.py` + `src/core/copilot/conversation_memory.py`)

- **Sessie-index** (beslissing Rakesh): `ConversationMemory.add(..., user_id=)` indexeert het session_id
  in een Redis-set `copilot:user_sessions:{tenant_id}:{user_id}` (TTL 1u). Nieuwe methoden
  `get_user_sessions` en `clear_user_sessions` (tenant-gescoped, nooit cross-tenant; hergebruikt `_key`).
  `chat_websocket.py` geeft `user_id` mee bij het opslaan.
- **Export**: secties `agentic_tasks` (`Task.tenant_id==tenant AND Task.created_by==user`) en
  `copilot_conversations` (live sessies via de index; TTL-beperking gedocumenteerd).
- **Delete** (hard + soft): `agentic_tasks` fysiek verwijderd (geen `is_active`, net als CVA), binnen
  `begin_nested`; copilot-sessies gewist via `clear_user_sessions` binnen `best_effort` (een Redis-storing
  laat de DSAR-delete niet falen; gelogd met `exc_info`).

## Tenant-isolatie

Alle queries filteren op `tenant_id` + de maker (`created_by`); de Redis-index en -clear zijn per
`{tenant_id}:{user_id}` -- nooit tenant-breed of cross-tenant.

## Acceptatiecriteria

- Export bevat de taken en copilot-sessies van de user (eigen tenant).
- Hard/soft-delete verwijdert de taken van de user; taken van een andere tenant blijven staan.
- Copilot-sessies van de user worden gewist; Redis-storing -> delete slaagt alsnog (best_effort).

## Risico (gedocumenteerd)

Sessies van vóór deze wijziging hebben geen index -> onbereikbaar tot hun 1u-TTL verloopt. Acceptabel.

## Trainingssamenvatting

### Flow 1: Recht op verwijdering incl. taken + copilot

- Actor: gebruiker (of admin) die een DSAR-delete aanvraagt.
- Voorwaarde: geldige user binnen de tenant; autorisatie akkoord.
- Actie: `delete_user_data(user_id, tenant_id, hard_delete=...)`.
- Systeemreactie: `agentic_tasks` van de user worden verwijderd (tenant-gescoped) en de copilot-Redis-
  sessies via de user->sessie-index gewist; overige DSAR-stappen ongewijzigd.
- Succesrespons: `DSARDeletionResult` met `records_affected` incl. `agentic_tasks` + `copilot_sessions`.
- Foutrespons: Redis-storing -> copilot-clear geeft 0 terug, delete slaagt alsnog (best_effort, gelogd).
- Uitzonderingen: nooit cross-tenant of tenant-breed wissen bij een enkele-user-DSAR.

## Definition of Done

- [x] Export + hard/soft-delete dekken tasks + copilot; sessie-index geimplementeerd
- [x] 5 helper-unit-tests + 5 conversation_memory index-tests groen
- [x] Gate 2 (code + security) opgelost; Gate 3 groen; review APPROVED; ID-REGISTRY bijgewerkt

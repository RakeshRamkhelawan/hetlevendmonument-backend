# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-005
- Feature naam: HITL cleanup_expired tenant filter (B-018 fix)
- Status: APPROVED
- Auteur: Claude Sonnet 4.6
- Reviewer: code-reviewer + quality-reviewer subagents (Laag A/C)
- Datum: 2026-05-30
- Gerelateerde user story / ticket: MASTER-AUDIT-COMPLEET.md B-018
- Gerelateerde router / module: src/core/tool_broker/hitl_repository.py + src/workers/actors.py
- Gerelateerde frontend endpoints: geen (intern)
- Gerelateerde database tabellen: hitl_tickets
- Versie: 1.0

---

## Doel en scope

### Doel

HITLTicketRepository.cleanup_expired() markeerde verlopen HITL-tickets van ALLE tenants
tegelijk, zonder tenant_id filter. Cross-tenant data-modificatie in strijd met ADR-005.
Fix: tenant_id parameter toevoegen + WHERE filter + TenantFilterBypass in actor.

### In scope

- cleanup_expired(self, tenant_id: int) signature fix + WHERE filter
- cleanup_expired_hitl_tickets Dramatiq actor: TenantFilterBypass + per-tenant loop
- Bestaande unit tests bijgewerkt

### Out of scope

- Verwijdering van expired ticket payloads (PII-retentie, valt onder run_retention_cleanup)
- Schema-wijziging

---

## Build summary

- Gewijzigd: src/core/tool_broker/hitl_repository.py (signature + WHERE filter)
- Gewijzigd: src/workers/actors.py (TenantFilterBypass + per-tenant loop)
- Gewijzigd: tests/unit/test_hitl_repository.py (twee tests bijgewerkt met tenant_id=1)
- Beinvloede flows: HITL ticket lifecycle (expiry path)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-005a | HITLTicketRepository.cleanup_expired | Repository method fix | src/core/tool_broker/hitl_repository.py | Wijziging | HITL ticket expiry |
| BE-SEC-005b | cleanup_expired_hitl_tickets actor | Dramatiq actor fix | src/workers/actors.py | Wijziging | HITL ticket expiry |

---

## API-flows

### Flow: HITL ticket expiry (scheduled, hourly)

- Trigger: APScheduler hourly at :15 -> cleanup_expired_hitl_tickets.send()
- Service-stappen:
  1. TenantFilterBypass() context openen
  2. SELECT DISTINCT tenant_id WHERE status=pending AND expires_at < now
  3. Loop over tenant_ids: cleanup_expired(tid) per tenant
  4. UPDATE hitl_tickets SET status=expired WHERE tenant_id=tid AND status=pending AND expires_at < now
  5. session.commit()
- Successtatus: dict(expired_tickets_marked=N)
- Foutpaden: exception -> Dramatiq herprobeert

---

## Detaildocumentatie per artefact

---

## [BE-SEC-005a] HITLTicketRepository.cleanup_expired(tenant_id)

### 1. Type
- Repository method (security fix)

### 2. Locatie
- Bestandspad: src/core/tool_broker/hitl_repository.py
- Klasse / functie: HITLTicketRepository.cleanup_expired

### 3. Gerelateerde flow
- HITL ticket expiry flow

### 4. Doel
Markeer verlopen HITL-tickets als expired voor een specifieke tenant.

### 5. Functionele beschrijving
Tickets die de SLA (4 uur) hebben overschreden en nog pending zijn worden op expired gezet.

### 6. Technische beschrijving
UPDATE hitl_tickets SET status=expired, resolved_at=now WHERE tenant_id=:tid AND status=pending AND expires_at < :now. Returns result.rowcount.

### 7. Zichtbaarheids- en toegangsregels
- Intern gebruik (actor/scheduler)
- Tenant-isolatie: WHERE tenant_id verplicht (ADR-005)

### 8. Request-specificatie
- Handtekening: async def cleanup_expired(self, tenant_id: int) -> int

### 9. Response-specificatie
- int: aantal bijgewerkte tickets

### 10. Validaties en constraints
- tenant_id moet positief integer zijn
- Alleen status=pending tickets worden bijgewerkt

### 11. Business rules
- SLA = 4 uur (_SLA_HOURS = 4)
- Ticket payload (PII) wordt niet verwijderd

### 12. Afhankelijkheden
- HITLTicket ORM model, sqlalchemy.update, async session

### 13. Foutafhandeling
- Database fouten propageren naar caller

### 14. Transacties en dataintegiteit
- Geen commit in de methode -- caller committeert

### 15. Telemetry / logging / tracing
- logger.info bij count > 0 met count + tenant_id in extra

### 16. Caching
- Niet gecached

### 17. Acceptatiecriteria
- tenant_id: int in signatuur
- WHERE tenant_id aanwezig in UPDATE statement
- cleanup_expired(tenant_id=1) past alleen tenant 1 tickets aan
- count 0 = geen log entry

### 18. Integratoruitleg
- Aanroepen vanuit actor met TenantFilterBypass actief
- Commit is verantwoordelijkheid van caller

### 19. Trainingssamenvatting

- Actor: Dramatiq actor (scheduler)
- Voorwaarde: worker process, TenantFilterBypass actief in calling context
- Actie: count = await repo.cleanup_expired(tenant_id)
- Systeemverwerking: UPDATE hitl_tickets WHERE tenant_id + status + expires_at
- Succesrespons: int (aantal bijgewerkte rijen)
- Foutrespons: exception propagateert
- Uitzonderingen: count=0 bij geen verlopen tickets (geen fout)

---

## [BE-SEC-005b] cleanup_expired_hitl_tickets actor

### 1. Type
- Dramatiq actor (scheduled maintenance)

### 2. Locatie
- Bestandspad: src/workers/actors.py
- Klasse / functie: cleanup_expired_hitl_tickets

### 3. Gerelateerde flow
- HITL ticket expiry flow

### 4. Doel
Uurlijkse job: verlopen HITL-tickets als expired markeren, per tenant gesoleerd.

### 5. Functionele beschrijving
Ontdekt welke tenants verlopen tickets hebben, loopt per tenant, roept cleanup_expired aan.

### 6. Technische beschrijving
TenantFilterBypass -> SELECT DISTINCT tenant_id -> loop cleanup_expired(tid) -> commit.

### 7. Zichtbaarheids- en toegangsregels
- Dramatiq queue: cleanup, max_retries: MAX_RETRIES, time_limit: 60s

### 8. Request-specificatie
- Dramatiq message zonder parameters

### 9. Response-specificatie
- dict(expired_tickets_marked=N)

### 10. Validaties en constraints
- TenantFilterBypass MOET aanwezig zijn

### 11. Business rules
- Cleanup lag: max 1 uur
- Idempotent: meerdere runs = geen extra updates

### 12. Afhankelijkheden
- TenantFilterBypass, HITLTicketRepository, get_db_session

### 13. Foutafhandeling
- except Exception: logger.exception + raise (Dramatiq herprobeert)

### 14. Transacties en dataintegiteit
- session.commit() na alle per-tenant updates

### 15. Telemetry / logging / tracing
- logger.info("hitl_cleanup.expired_tickets_marked: %d", count)

### 16. Caching
- Niet gecached

### 17. Acceptatiecriteria
- TenantFilterBypass aanwezig in actor body
- cleanup_expired() altijd aangeroepen met tenant_id argument
- Return dict met expired_tickets_marked sleutel

### 18. Integratoruitleg
- Handmatig: cleanup_expired_hitl_tickets.send() (geen args)
- Scheduler: geconfigureerd in src/workers/scheduler.py

### 19. Trainingssamenvatting

- Actor: APScheduler (hourly at :15) of handmatig
- Voorwaarde: Dramatiq worker actief, DB bereikbaar
- Actie: cleanup_expired_hitl_tickets.send()
- Systeemverwerking: TenantFilterBypass -> SELECT DISTINCT -> per-tenant loop -> commit
- Succesrespons: dict(expired_tickets_marked=N)
- Foutrespons: exception gere-raised, Dramatiq herprobeert
- Uitzonderingen: lege tenant list = count=0, geen error

---

## Integratorhandleiding

Handmatig triggeren: `from src.workers.actors import cleanup_expired_hitl_tickets; cleanup_expired_hitl_tickets.send()`

---

## Open aannames

- Retention cleanup voor expired ticket payloads (PII) valt buiten scope van deze sprint

## Open vragen

Geen

## Risico's

- Cleanup lag max 1 uur voor tickets die expireren na de discovery query

---

## QA-checks

- [x] cleanup_expired(tenant_id) WHERE filter aanwezig
- [x] TenantFilterBypass aanwezig in actor
- [x] test_hitl_repository.py bijgewerkt
- [x] SP-S02 meta-tests: 7/7 PASS

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig per artefact
- [x] Review: zie docs/backend/review/review-BE-SEC-005.md

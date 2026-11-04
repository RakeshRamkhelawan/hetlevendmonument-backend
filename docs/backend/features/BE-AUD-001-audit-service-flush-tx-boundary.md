# BE-AUD-001 -- AuditService.log_event() transactie-grens fix

**Sprint:** SP-AUDIT-003 Dag 1
**Datum:** 2026-06-30
**Status:** APPROVED

---

## Samenvatting

`AuditService.log_event()` deed na het schrijven van de audit entry `await db.commit()`.
Die commit sloot de VOLLEDIGE outer transaction van de caller -- niet alleen de audit savepoint.
Elk aanroepend endpoint had daarmee onverwacht al zijn openstaande wijzigingen gecommittet
voeordat de caller dat zelf kon doen. Dit is een ADR-019 schending (audit moet non-blocking zijn
en mag de primaire transactie niet sturen).

**Fix:** `await db.commit()` vervangen door `await db.flush()`.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/governance/services/audit_service.py` | `commit()` -> `flush()` + docstring update |
| `tests/unit/test_audit_service_unit.py` | 2 nieuwe tests + 6 stale assertions bijgewerkt |

---

## Technische toelichting

### Savepoint-semantiek

`async with db.begin_nested()` maakt een SAVEPOINT in PostgreSQL. Bij het verlaten van de
context manager wordt het savepoint gereleased (de writes worden naar de outer transaction
buffer gestuurd). `flush()` daarna zorgt dat de writes naar de DB-server worden gestuurd
zonder de outer transaction te sluiten.

`commit()` zou de outer transaction sluiten -- inclusief alle andere openstaande writes van
de caller die nog niet klaar waren. Dit was het bug.

### Durabiliteitssemantiek na fix

`log_event()` retourneert `True` als de schrijfactie naar de savepoint is geslaagd.
Durabilitiet hangt af van de caller die de outer transaction commit. In de praktijk doet
`get_db` (src/core/database/database.py:489) automatisch `await session.commit()` na elke
succesvolle request -- dus alle endpoints zijn veilig.

### Zelf-bewaking

De bestaande `try/except` in `log_event()` (RuntimeError + SQLAlchemyError + Exception)
vangt ook `flush()`-fouten op. Callers van `log_event()` hoeven NIET in `best_effort`
gewrapped te worden -- `log_event()` zelf-bewaakt al.

---

## Tests

| Test | Type | Wat het test |
|------|------|--------------|
| `test_log_event_does_not_commit_outer_transaction` | unit | `commit()` wordt NIET aangeroepen |
| `test_log_event_calls_flush_after_savepoint` | unit | `flush()` wordt precies 1x aangeroepen |
| `test_log_event_handles_database_error` | unit | `flush()` die SQLAlchemyError gooit -> False |
| `test_log_event_success` | unit | success-pad: flush 1x, commit 0x |
| `test_log_security_event_with_db` | unit | wrapper roept ook flush aan, niet commit |

---

## Buiten scope (pre-existing, aparte backlog)

| ID | Bevinding | Actie |
|----|-----------|-------|
| TODO(SP-AUDIT-004) | `log_security_event()` logt raw `details` dict in log_message (PII-risico) | Aparte backlog |
| TODO(SP-AUDIT-004) | `log_event()` accepteert `tenant_id=None`, audit entry wordt stil verworpen als DB NOT NULL | Aparte backlog |
| TODO(SP-AUDIT-004) | `src/domains/verticals/` aanroepen zonder session-parameter -> audit stil overgeslagen | DI-aanpassing nodig |


## Trainingssamenvatting

- Actor: Een endpoint, service of worker die een audit log wil schrijven en al een `AsyncSession` (`db`) heeft.
- Voorwaarde: De caller beschikt over een actieve async SQLAlchemy sessie; de `AuditService.log_event()` methode is geimporteerd uit `src.core.governance.services.audit_service`.
- Actie (request): Roep `await AuditService.log_event(db=db, event_type=..., severity=..., source_ip=..., endpoint=..., description=..., optioneel user_id/tenant_id/action/resource/metadata)` aan.
- Systeemverwerking: Indien `metadata` aanwezig is, wordt gecontroleerd of deze JSON-serialiseerbaar is (zo niet, reset naar `{}` met warning). Vervolgens wordt een savepoint geopend via `async with db.begin_nested()`, een `AuditLog`-record aangemaakt, en indien `tenant_id` niet `None` wordt best-effort de hash-chain gevuld met `pg_advisory_xact_lock` en `HashChainVerifier`. Tot slot wordt `await db.flush()` aangeroepen.
- Succesrespons: De functie retourneert `True`; de audit entry zit in de transaction buffer en wordt pas durable wanneer de caller zelf `commit()` doet.
- Foutrespons: Bij `RuntimeError`, `SQLAlchemyError` of onverwachte exception wordt `False` teruggegeven en een warning/error gelogd; de outer transaction van de caller blijft ongemoeid.
- Uitzonderingen: `tenant_id=None` slaat hash-chain populatie over; niet-serialiseerbare metadata wordt vervangen door `{}`; de functie voert zelf geen `commit()` uit.

# BE-SEC-018: best_effort wrapping voor security audit DB writes

**Sprint:** SP-DSM-001
**Datum:** 2026-06-13
**Status:** IMPLEMENTED

---

## Probleemstelling

`SecurityAuditService.log_event()` en `_create_alert()` schreven direct naar de database
met bare `db.add() + await db.commit()` zonder `best_effort` context manager. Dit schendt
backend-patterns.md §3: "Audit log daarna in best_effort."

Bijkomende bevindingen (Gate 2):
- `self._last_hash` werd buiten de DB-commit bijgewerkt — bij een mislukte commit zou de
  SHA-256 hash chain permanently inconsistent worden zonder observable error.
- Na een mislukte audit-log commit kon `_check_detection_rules()` nog steeds worden
  aangeroepen met een `event_id` van een rij die nooit geschreven is, wat zou resulteren
  in alerts met een dangling `triggering_event_id`.
- `except SQLAlchemyError` blocks waren dead code na de wrapping.
- `logger.error()` aanroepen misten `exc_info=True` (backend-patterns.md §10).

---

## Oplossing

### `log_event()` — sentinel pattern + best_effort

```python
_committed = False
async with best_effort("security audit log", db_session=db):
    db.add(audit_entry)
    await db.commit()
    # Hash chain advances only after a confirmed commit
    self._last_hash = audit_entry.event_metadata.get("log_hash")
    _committed = True

if _committed:
    # Cache + detection rules only for committed events
    await self._check_detection_rules(...)
    return event_id
return None
```

### `_create_alert()` — sentinel pattern + best_effort

```python
_committed = False
async with best_effort("security alert creation", db_session=db):
    db.add(alert)
    await db.commit()
    _committed = True

if _committed:
    logger.warning("SECURITY ALERT ...")
    for callback in self.alert_callbacks: ...
```

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/security/security_audit_service.py` | best_effort import + sentinel pattern in log_event() + _create_alert() |
| `tests/architecture/test_security_audit_best_effort.py` | 3 nieuwe architecture tests (waren ROOD voor de fix) |

---

## Invarianten bewaakt door architecture tests

- `test_log_event_uses_best_effort`: AST-check dat log_event() een best_effort AsyncWith gebruikt
- `test_log_event_last_hash_inside_best_effort`: AST-check dat _last_hash BINNEN de best_effort body staat
- `test_create_alert_uses_best_effort`: AST-check dat _create_alert() een best_effort AsyncWith gebruikt

---

## Gerelateerde bevindingen

- SP-DSM-001 Taak 3 (best_effort) — zie ook Taak 4 (DSM reclassificatie)
- ADR-019: audit logging + SHA-256 hash chain
- backend-patterns.md §3 + §10

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.

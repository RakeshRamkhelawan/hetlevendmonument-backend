# Review BE-DSM-031 -- AuditService ThreatLevel-ontkoppeling

**Sprint:** SP-DSM-015 Dag 2
**Datum:** 2026-06-25
**Status:** APPROVED

---

## Samenvatting

Twee onafhankelijke reviewers (code-reviewer + quality-reviewer) beoordeelden de geplande
wijziging. Beide gaven initieel CHANGES_REQUESTED vanwege identieke blockers. Na het
verwerken van de blockers is de status APPROVED.

---

## Bevindingen

### RC-001 / QR-001 (BLOCKER -- opgelost)

**Bevinding:** `getattr(severity, "name", severity)` slaat uppercase op (`"HIGH"`).
`ThreatLevel` is `str, Enum` met lowercase waarden. DB verwacht lowercase.

**Actie:** Gewijzigd naar `str(getattr(severity, "value", severity)).lower()`.

**Status:** OPGELOST -- `threat_level='low'` bevestigd in INSERT-log.

---

### RC-002 / QR-002 (BLOCKER -- opgelost)

**Bevinding:** `derived_level.upper()` geeft uppercase string door aan `log_event`
terwijl `.name` op de ontvangende kant `AttributeError` gaf voor plain strings.

**Actie:** `severity = derived_level` (al lowercase), geen `.upper()`.
`getattr`-fallback in Change 2 handelt plain strings correct af.

**Status:** OPGELOST.

---

### QR-003 (MINOR -- pre-existing, backlog)

**Bevinding:** f-string `log_message` in `log_security_event` regels 152-162.

**Status:** Pre-existing. TODO in code aanwezig, backlog SP-AUDIT-004.

---

### RC-004 / QR-006 (MINOR -- pre-existing, buiten scope)

**Bevinding:** `db.add(entry)` + `await db.commit()` zonder `best_effort` in
`AuditService.log_event`. Per CLAUDE.md patroon 3 zou dit `best_effort` moeten zijn.

**Status:** Pre-existing (bestond voor deze sprint). Backlog SP-AUDIT-003.

---

### RC-006 (MINOR -- informational)

**Bevinding:** `ThreatLevel.INFO` is nooit bereikbaar via `log_security_event`.
Consistent met het oude gedrag (MEDIUM fallback voor onbekende levels).

**Status:** Geen actie vereist.

---

## DoD-checklist

- [x] Rode test was ROOD voor de fix
- [x] Test GROEN na de fix
- [x] Arch-suite: 248 passed, 0 failed (was 247)
- [x] Gerichte unit-tests: 251 passed, 0 failed
- [x] Pyright: geen nieuwe errors in gewijzigde bestanden
- [x] Alle BLOCKER-bevindingen opgelost voor commit
- [x] MINOR-bevindingen gedocumenteerd als pre-existing backlog

---

**Eindoordeel: APPROVED**

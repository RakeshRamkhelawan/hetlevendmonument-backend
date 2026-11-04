# Review — BE-EP-010: ALS Ping via SignalBus

**Reviewer:** Sprint-uitvoeringsagent SP-E06
**Datum:** 2026-05-29
**Verdict:** APPROVED WITH MINOR GAPS

---

## Laag A reviews

### A1 — Code review (code-reviewer subagent)

**Verdict:** NEEDS REVISION → herzien → APPROVED

Bevindingen:
- **HIGH (opgelost):** Duplicate import `SignalBus` (al aanwezig in bestaande import). **Fix:** samengevoegd tot `from ... import Signal, SignalBus, SignalTier`.
- **HIGH (opgelost):** Geen foutafhandeling rond `emit()` — inconsistent met alle andere endpoints in hetzelfde bestand (die alle `asyncio.wait_for` + 504 gebruiken). **Fix toegepast:** `asyncio.wait_for(..., timeout=ALS_ORCHESTRATOR_TIMEOUT_SECONDS)` + `except TimeoutError → 504` + `except Exception → logger.error + 503`.
- **MEDIUM (geaccepteerd):** Ping-signaal kan silent worden dropped bij cooldown (SignalBus-mechanisme). Endpoint retourneert 200 ook bij dropped signal. Gedocumenteerd als "by design" in Trainingssamenvatting Uitzonderingen.
- **INFO:** `get_orchestrator()` heeft geen concurrency-guard voor simultane eerste-aanroepen. Pre-existing; buitenscope SP-E06.

### A2 — Quality review (general-purpose subagent)

**Verdict:** APPROVED

Bevindingen: Alle 10 checks geslaagd. `%s`-formatting, ASCII-only, `datetime.now(timezone.utc)`, geen hardcoded URL, geen `any`-types, geen `from __future__ import annotations`.

---

## Checklist

- [x] tenant_id uit JWT (Depends)
- [x] Geen hardcoded URLs/secrets
- [x] ASCII-only logging
- [x] `datetime.now(timezone.utc)` correct
- [x] Error handling (504/503) consistent met peer-endpoints
- [x] Duplicate import verwijderd
- [x] Standard response format {"success": true, "data": ...}
- [x] Tests rood voor implementatie, groen erna
- [x] Trainingssamenvatting aanwezig

---

**Eindvonnis: APPROVED WITH MINOR GAPS** — cooldown silent-drop is geaccepteerd en gedocumenteerd; geen CRITICAL of HIGH open issues.

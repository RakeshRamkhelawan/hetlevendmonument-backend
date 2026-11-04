# Review BE-TSK-003 — CVA Tasks User-ID Fix

**Datum:** 2026-05-30
**Sprint:** SP-W02
**Reviewer:** Laag A (code-reviewer + quality-reviewer subagents)
**Verdict:** APPROVED WITH MINOR GAPS

---

## Bevindingen

### GESLOTEN (gefixed voor merge)

| ID | Ernst | Beschrijving | Fix |
|----|-------|-------------|-----|
| QR-1 | HIGH | `int(user_id)` unsafe bij niet-numerieke string | Wrapped in `try/except (ValueError, TypeError)` |
| QR-2 | HIGH | 5 f-string loggers in cva_tasks.py | Vervangen door `%s` stijl |
| QR-3 | MEDIUM | `raise e` verliest originele traceback | Vervangen door bare `raise` |
| QR-6 | HIGH | f-string logger.info in workflow_tasks.py | Vervangen door `%s` stijl |
| CR-4 | CRITICAL | Telegram caller stuurde geen `user_id` | `"user_id": sender.get("id")` toegevoegd |
| CR-1-ext | HIGH | WhatsApp `user_id="unknown"` crashte `int()` cast | Vervangen door `user_id = None` |

### OPEN (bewust uitgesteld)

| ID | Ernst | Beschrijving | Reden uitstel |
|----|-------|-------------|---------------|
| CR-3 | MEDIUM | `async def process_cva_message` actor zonder AsyncIO middleware | Pre-existing; vereist bredere broker-configuratie audit. Los op in SP-W01 of aparte sprint. |
| TODO-WA | LOW | WhatsApp user_id lookup via phone -> DB nog niet geimplementeerd | Scope SP-W02 is B-013/B-015 fix; DB lookup vereist User model + query. TODO comment toegevoegd. |

---

## Eindoordeel

De P0-bugs B-013 en B-015 zijn volledig gesloten. Alle HIGH/CRITICAL bevindingen uit de Laag A
review zijn gefixed. De twee open items zijn bewust uitgesteld en gedocumenteerd.

**Verdict: APPROVED WITH MINOR GAPS**

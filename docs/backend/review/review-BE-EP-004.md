# Review: BE-EP-004 Documents Upload Endpoint

**Reviewer:** code-reviewer + general-purpose subagent
**Datum:** 2026-05-28
**Status:** APPROVED WITH MINOR GAPS

---

## Bevindingen

### CRITICAL: 0

### HIGH: 0

### MEDIUM: 2

1. **Memory pressure:** `await file.read(max_size + 1)` laadt de volledige file in memory. Voor 50MB is dit acceptabel voor Dag 1, maar verdient streaming in een toekomstige sprint.
2. **Content type validatie:** MIME type whitelist is aanwezig, maar magic-byte sniffing (python-magic) ontbreekt. Dit is een bekende beperking voor Dag 1.

### LOW: 1

- `os.getenv` wordt gebruikt voor `STORAGE_BACKEND` om test overrides te ondersteunen. Dit is een uitzondering op de centrale config regel, goed gedocumenteerd in code.

---

## Samenvatting

Endpoint is architecturaal correct: DB-record-voor-file, tenant binding check, file security (path traversal + size + MIME whitelist), SHA-256 checksum, async I/O via `aiofiles`, `best_effort` audit. Alle 10 tests groen.

**Verdict: APPROVED WITH MINOR GAPS**

# BE-UTL-019 — Sp Type04 Database

**ID:** BE-UTL-019
**Sprint:** SP-TYPE-04 Dag 2-4 Group B
**Type:** Utility (type refactoring)
**Status:** CLOSED — commit `5bdf93cf`
**Bestanden:** src/core/database/query_optimizer.py, src/core/database/unit_of_work.py, src/core/database/query_analyzer.py, src/core/database/database.py, src/core/database/retry_logic.py

---

## Samenvatting

Type hardening in database layer: ORM sessions, query tools, retry logic.

---

## Wijzigingen

AsyncSession for unit_of_work, async_sessionmaker[AsyncSession], TracebackType for __aexit__, Engine for query_optimizer, list[dict[str,Any]] for suggestions. All legacy typing imports cleaned.

---

## Trainingssamenvatting

**Flow: Type-annotatie refactoring**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety sprint agent (SP-TYPE-04 workflow) |
| Voorwaarde | Bestanden bevatten `Any` annotaties zonder TODO of met TODO als baseline |
| Actie | HIGH-confidence type replacements via gestructureerde analyse |
| Systeemverwerking | Parallel analyse -> apply -> TDD tests -> ruff -> commit |
| Succesrespons | TDD tests groen, ruff 0 errors |
| Foutrespons | Revert bij ruff failure; skip bij niet-gevonden old_text |
| Uitzonderingen | *args:Any, **kwargs:Any, generic decorators, externe SDK types bewust als Any gelaten |

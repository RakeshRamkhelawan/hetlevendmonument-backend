# BE-UTL-025 — Pyright Type-errors Fix (10 errors in 3 bestanden)

**ID:** BE-UTL-025
**Sprint:** Post-SP-TYPE type-safety cleanup
**Type:** Utility (bug fix)
**Status:** CLOSED — commit `9b0a2dc7`
**Bestanden:**
- `src/core/agents/mixins/learning_mixin.py` (8 errors)
- `src/domains/agentic/api/experiments.py` (1 error)
- `src/workers/workflow_worker.py` (1 error)

---

## Samenvatting

10 pyright type-errors opgelost die zichtbaar werden door de SP-TYPE type-narrowings.
Geen logica-wijzigingen — alleen type-annotaties en type-suppression commentaar.

---

## Wijzigingen per bestand

### `learning_mixin.py` (8 errors → 0)

**Root cause:** `if TYPE_CHECKING:` blok conflicteerde met `try/except ImportError` stubs.
Pyright zag de stub-klassen als de "declared types" en de echte klassen als incompatibele
overschrijvingen.

**Fixes:**
- TYPE_CHECKING blok verwijderd (redundant naast try/except)
- `ObservationService` stub toegevoegd aan except-blok
- `type: ignore[assignment]` op try-imports (stub ≠ echte klasse)
- `type: ignore[reportInvalidTypeForm]` + `type: ignore[return-value]` op observation_service property
- `callable(service.load_from_db)` → `callable(getattr(service, "load_from_db", None))` (hasattr narrows niet)
- `cast(Any, service/cross_service).method()` voor methods op stubs

### `experiments.py` (1 error → 0)

**Root cause:** `repo.list_experiments()` geeft `Sequence[PromptExperiment]` (ORM) terug,
maar annotatie zegt `list[ExperimentResponse]` (Pydantic). FastAPI serialiseert via
`response_model=list[ExperimentResponse]` — de annotatie is functioneel correct maar
typeconflict met SQLAlchemy Sequence.

**Fix:** `# type: ignore[return-value]` met comment dat de ORM→Pydantic conversie via
FastAPI's response_model plaatsvindt.

### `workflow_worker.py` (1 error → 0)

**Root cause:** In testing-mode else-branch: `get_redis_broker = None` was niet
toewijsbaar aan het eerder geïnfereerde type `() -> Any`.

**Fix:** `# type: ignore[assignment]` op de None-toewijzing.

---

## Trainingssamenvatting

**Flow: Pyright type-error fix na type-narrowing**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety engineer |
| Voorwaarde | SP-TYPE sprints leggen type-errors bloot via type-narrowing |
| Actie | Per error: root cause analyseren, minimale fix toepassen |
| Systeemverwerking | `python -m pyright <file>` → 0 errors; ruff → 0 errors |
| Succesrespons | 0 pyright errors op alle 3 bestanden |
| Foutrespons | N.v.t. |
| Uitzonderingen | `type: ignore[assignment]` op try/except stub-imports is het enige alternatief voor TYPE_CHECKING dubbeling bij optionele dependencies |

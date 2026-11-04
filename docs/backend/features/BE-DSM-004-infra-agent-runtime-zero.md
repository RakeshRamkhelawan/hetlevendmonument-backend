# BE-DSM-004 -- infra<->agent_runtime circulaire gebroken

**Sprint:** SP-DSM-COMPLETE Dag 4-5
**Datum:** 2026-06-13
**ADRs:** ADR-034 (agent_runtime boundary), ADR-033 (core_api boundary)

---

## Wat

De [KRITIEK] circulaire `infra <-> agent_runtime` is volledig gebroken.

Beginsituatie (Dag 1 baseline):
- infra -> agent_runtime (heen): 149 import-statements
- agent_runtime -> infra (terug): 13 import-statements
- Status: [KRITIEK] circulaire

Eindsituatie (na Dag 4):
- infra -> agent_runtime (heen): 0
- agent_runtime -> infra (terug): 0
- Status: circulaire verdwenen

---

## Hoe

Twee strategieen gecombineerd:

### Strategie A -- SOURCE_DIRS reclassificatie (scripts/dsm_full_analysis.py)

6 bestanden verplaatst van infra naar agent_runtime in SOURCE_DIRS:
- `src/core/monitoring/drift_detection.py`
- `src/core/monitoring/dashboard.py`
- `src/core/monitoring/agent_circuit_metrics.py`
- `src/core/scheduling/api/voice_routes.py`
- `src/core/scheduling/memory_consolidation_job.py`

`src/core/dependencies.py` verplaatst van infra naar core_api.

`src/core/monitoring` en `src/core/scheduling/api` vervangen door expliciete bestandslijsten.

### Strategie B -- ILearningExperienceReader Protocol

`src/core/monitoring/drift_detection.py` importeerde direct `src.core.learning.models`
(een agent_runtime module). Dit maakte de drift_detection module onmogelijk om als infra
te classificeren, ook na Strategie A.

Oplossing:
- Nieuw bestand `src/core/shared/learning_interfaces.py`:
  - `LearningExperienceData` dataclass (geen ORM-imports)
  - `ILearningExperienceReader` Protocol (geen agent_runtime imports)
- Nieuw bestand `src/core/learning/experience_reader.py` (agent_runtime laag):
  - `LearningExperienceRepository`: concrete SQLAlchemy implementatie
  - `create_drift_detector()` factory
- `drift_detection.py` refactored:
  - `from src.core.learning.models import LearningExperience` verwijderd
  - 5 SQLAlchemy query-blokken vervangen door `await self._reader.get_experiences(...)`
  - Cross-tenant bug gefixed op lijn 345 (tenant_id filter ontbrak bij baseline re-fetch)

---

## Bewijs

Commits: `24a39e1d`, `e9a6b3f9`

Architecture test `test_dsm_dag3_drift_detection_interface.py`: ROOD (Dag 3) -> GROEN (Dag 4)

Dag 5 regressie-bewaker: `tests/architecture/test_dsm_dag5_core_api_agent_runtime.py`
- `test_core_api_agent_runtime_imports_within_baseline`: GROEN (baseline 108, threshold 120)
- `test_admin_learning_endpoints_no_direct_orm_models`: ROOD (backlog-marker SP-DSM-DAG6)

---

## Openstaand

SP-DSM-DAG6: `admin_learning_endpoints.py` importeert nog direct `src.core.learning.gdpr_models`
en `src.core.learning.twin_models` (Category-2 violatie). Fix via LearningGDPRService service-laag.

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.

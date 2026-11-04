# BE-SVC-060..067: Compliance Sub-Routers Service Injection (ADR-033 S4)

## Overzicht

Alle 8 compliance sub-routers omgezet van directe `get_db`/`AsyncSession`/`select`-imports
naar service-injectie via factory-functies in `dependencies.py` (ADR-033).

## Sprint

AUDIT-SINGLE-TENANT-DB01 S4

## Datum

2026-07-01

## Gewijzigde bestanden

| ID | Router | Factory |
|----|--------|---------|
| BE-SVC-060 | `score_router.py` | `get_score_service` |
| BE-SVC-061 | `gdpr_summary_router.py` | `get_aggregation_service` |
| BE-SVC-062 | `ai_act_summary_router.py` | `get_aggregation_service` |
| BE-SVC-063 | `gdpr_dsar_router.py` | `get_aggregation_service` |
| BE-SVC-064 | `ai_act_decisions_router.py` | `get_aggregation_service` |
| BE-SVC-065 | `integrity_status_router.py` | `get_hash_chain_verifier` |
| BE-SVC-066 | `integrity_verify_router.py` | `get_hash_chain_verifier` |
| BE-SVC-067 | `pdf_router.py` | `get_score_service` + `get_aggregation_service` |

## Wijzigingen per router

### Patroon (alle routers)

Verwijderd:
- `from sqlalchemy.ext.asyncio import AsyncSession`
- `from src.core.database.database import get_db`
- `from sqlalchemy import select` (waar aanwezig)

Toegevoegd:
- `Depends(get_<service>_factory)` als handler-parameter
- Directe service-aanroep zonder inline-instantiatie

### Nieuwe factory-functies in `dependencies.py`

```python
async def get_score_service(db: AsyncSession = Depends(get_db)) -> ComplianceScoreCalculator:
    return ComplianceScoreCalculator(db_session=db)

async def get_aggregation_service(db: AsyncSession = Depends(get_db)) -> ComplianceAggregationService:
    return ComplianceAggregationService(db_session=db)

async def get_hash_chain_verifier(db: AsyncSession = Depends(get_db)) -> HashChainVerifier:
    return HashChainVerifier(db_session=db)
```

### Nieuwe methoden in `ComplianceAggregationService`

- `get_dsar_requests(tenant_id, since)` -- vervangt inline `db.execute(select(DSARRequest)...)`
- `get_ai_decisions(tenant_id, since)` -- vervangt inline `db.execute(select(AIDecision)...)`

### Kritieke correcties (BLOCKER-fixes)

- `pdf_router.py`: `db.commit()` in `best_effort` vervangen door `agg_svc.db_session.flush()`
- `integrity_verify_router.py`: timezone-guard toegevoegd voor Query-params die naive datetime opleveren

## Architecture test

`tests/architecture/test_compliance_subrouters_no_direct_db.py` -- GROEN

AST-scan bevestigt: geen FORBIDDEN symbolen (`get_db`, `AsyncSession`, `select`, `func`, `update`, `delete`) meer in de 8 router-bestanden.

## Test resultaten

- `tests/unit/test_compliance_router.py`: 99 passed, 0 failed
- `tests/architecture/test_compliance_subrouters_no_direct_db.py`: 1 passed
- `python -m pyright`: 0 errors (baseline gehandhaafd)

## Review status

APPROVED

## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met geldige JWT en opgeloste tenant.
- Voorwaarde: `src/core/api/v1/compliance/dependencies.py` exporteert `get_score_service`, `get_aggregation_service` en `get_hash_chain_verifier`; sub-routers importeren deze factories.
- Actie (request): Verstuur `GET /api/v1/compliance/score` met geldige `Authorization` header.
- Systeemverwerking: `score_router.get_compliance_score` injecteert `calculator = Depends(get_score_service)`; de factory maakt `ComplianceScoreCalculator(db_session=db)`; vervolgens wordt `await calculator.calculate_overall_score(tenant_id=current_user.tenant_id)` aangeroepen en het resultaat in een `ComplianceScoreResponse` gewrapped.
- Succesrespons: HTTP 200 met `ComplianceScoreResponse` velden `overall_score`, `gdpr_score`, `ai_act_score`, `audit_score`, `calculated_at` en `tenant_id`.
- Foutrespons: HTTP 401 indien niet geauthenticeerd; HTTP 500 `Failed to calculate compliance score: ...` bij interne fout.
- Uitzonderingen: `score_router.py` bevat geen directe imports van `get_db`, `AsyncSession` of `select`; history endpoint `GET /score/history` werkt analoog via `get_score_service`.

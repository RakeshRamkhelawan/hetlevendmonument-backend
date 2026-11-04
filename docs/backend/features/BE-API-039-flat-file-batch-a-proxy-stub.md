# BE-API-039 -- ADR-033 Batch A Flat File Proxy Stubs

Sprint: SP-API-010 Dag 2
Datum: 2026-06-11
Categorie: architecture / refactor (ADR-033 Contract 1)
Status: APPROVED

---

## Samenvatting

6 van de 9 `src/core/api/*_endpoints.py` flat files schonden ADR-033 Contract 1 via directe
imports uit verboden domeinen (`src.core.database`, `src.core.governance`, `src.core.agents`,
`src.core.workflow`). Alle 6 zijn omgezet naar proxy stubs met RFC 8594/9745
deprecation headers. De 3 structurele blockers zijn gedocumenteerd als xfail(strict=True)
architecture tests voor SP-API-011.

---

## Deliverables

### Nieuwe bestanden

| Bestand | Doel |
|---------|------|
| `tests/architecture/test_flat_file_batch_a_clean.py` | 1 PASS-test: 6 clean files hebben 0 violations |
| `tests/architecture/test_flat_file_batch_a_gaps.py` | 3 XFAIL: agent/admin_learning/assistant gaps (SP-API-011) |
| `tests/architecture/test_flat_file_migration_gaps.py` | 5 XFAIL: routes zonder v1/ equivalent (SP-API-011) |
| `src/core/api/v1/company/dependencies.py` | Facade: re-export GlobalPack + PackFeedback (ADR-033) |

### Gewijzigde bestanden (proxy stubs)

| Bestand | Violations verwijderd | Aanpak |
|---------|----------------------|--------|
| `tool_endpoints.py` | 1 (lazy agents import) | Orphan-comment bijgewerkt; zoeklogic stubbed |
| `orchestrator_endpoints.py` | 5 (database + governance + workflow x3) | /multi-agent volledig gestubbed |
| `workflow_refinement_endpoints.py` | 3 (workflow.schemas + agents x2) | Schemas inline; /chat + /refine gestubbed |
| `template_endpoints.py` | 2 (database + workflow lazy) | database -> api.dependencies; /deploy gestubbed |
| `agentic_flow_endpoints.py` | 1 (database) | database -> api.dependencies |
| `pack_feedback_endpoints.py` | 2 (database + governance) | Facade v1/company/dependencies.py; alle routes werkend |

### Bijgewerkte tests

| Bestand | Wijziging |
|---------|-----------|
| `tests/unit/test_orchestrator_endpoints.py` | 4 tests bijgewerkt naar stub-gedrag (OversightGate verwijderd) |

---

## Stub-patroon (alle 6 bestanden)

```python
# orphan:exempt reason: SP-API-010 proxy stub -- TODO(SP-API-011): migreer naar v1/<domein>/
_DEPRECATION_SUNSET = "Thu, 01 Jan 2028 00:00:00 GMT"

@router.post("/endpoint", deprecated=True)
async def handler(response: Response, ...) -> ...:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    # TODO(SP-API-011): <verboden import> verwijderd -- ADR-033 Contract 1
    return {"status": "deprecated", "message": "Use v1/... (SP-API-011)"}
```

---

## Gaps gedocumenteerd (SP-API-011)

### Structurele blockers (xfail -- geen stub mogelijk)

| Bestand | Reden |
|---------|-------|
| `agent_endpoints.py` | Circulaire dep met v1/agents/; v1/ importeert dit bestand |
| `admin_learning_endpoints.py` | GDPR/LLM-budget routes hebben geen v1/ service |
| `assistant_endpoints.py` | POST /ask heeft geen v1/ equivalent |

### Routes zonder v1/ equivalent (proxy stub behoudt route)

| Route | Bestand |
|-------|---------|
| GET /integrations/catalog | tool_endpoints.py |
| GET /integrations/search | tool_endpoints.py |
| WS /ws/builder | agentic_flow_endpoints.py |
| POST /{id}/deploy | template_endpoints.py |
| GET /search/ | template_endpoints.py |

---

## Pre-existing bevinding (buiten scope)

`src/core/scheduling/smart/predictor.py` bevat uncommitted type-wijzigingen die 9 pyright
errors veroorzaken. Bewezen niet-scope via `git stash` test (pyright = 0 zonder die wijzigingen).
Vereist aparte fix-sprint voor SP-API-011 of eerder.

---

## Trainingssamenvatting

### Flow 1: API client roept deprecated flat-file endpoint aan (happy path)

| Stap | Inhoud |
| --- | --- |
| **Actor** | Externe API client (frontend, integratie, of tool) |
| **Voorwaarde** | Client is geauthenticeerd (JWT geldig); endpoint bestaat nog in flat-file router |
| **Actie** | Client stuurt HTTP-request naar bijv. `POST /api/v1/orchestrator/multi-agent` |
| **Systeemreactie** | FastAPI routeert naar proxy stub; stub zet `Deprecation: true` en `Sunset: Thu, 01 Jan 2028 00:00:00 GMT` headers; retourneert 200 met `{"status": "deprecated", "message": "Use v1/orchestration/ (SP-API-011)"}` |
| **Succesrespons** | HTTP 200 -- body bevat migratie-hint naar v1/ equivalent; RFC 8594 headers aanwezig |
| **Foutrespons** | HTTP 401 indien JWT ontbreekt of verlopen (auth-gate via Depends geborgd) |
| **Uitzonderingen** | `pack_feedback_endpoints.py`: 7 routes functioneel behouden (geen stub-response); RFC headers niet gezet (routes nog actief, geen v1/ equivalent beschikbaar) |

### Flow 2: API client roept deprecated endpoint aan zonder te migreren (unhappy path)

| Stap | Inhoud |
|------|--------|
| **Actor** | Externe API client die de Sunset-datum negeert |
| **Voorwaarde** | Client blijft flat-file endpoint aanroepen na 2028-01-01 |
| **Actie** | Request naar `POST /api/v1/workflows/refine/chat` |
| **Systeemreactie** | Stub retourneert lege suggesties + deprecation-bericht; werkelijke LLM-logica niet meer aanwezig |
| **Succesrespons** | HTTP 200 -- functioneel gedegradeerd; client ontvangt geen echte AI-analyse |
| **Foutrespons** | HTTP 401 bij ontbrekend JWT |
| **Uitzonderingen** | Na SP-API-011 wordt de route vervangen door v1/ equivalent; flat-file stub kan dan verwijderd worden |

---

## Testresultaten

```
tests/architecture/test_flat_file_batch_a_clean.py::test_batch_a_clean_files_have_zero_forbidden_imports  PASSED
tests/architecture/test_flat_file_batch_a_gaps.py  3 XFAILED (strict=True, blijven rood tot SP-API-011)
tests/architecture/test_flat_file_migration_gaps.py  5 XFAILED (strict=True)
tests/unit/test_orchestrator_endpoints.py  4 PASSED (stub-gedrag tests)
tests/unit/test_template_endpoints.py  PASSED (geen regressies)
tests/unit/test_sp_a02_pack_feedback_db.py  PASSED (geen regressies)
tests/unit/api/  112 PASSED
tests/architecture/  76 passed, 12 xfailed (0 regressions)
pyright src/  0 errors (mijn wijzigingen; predictor.py pre-existing buiten scope)
```

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.

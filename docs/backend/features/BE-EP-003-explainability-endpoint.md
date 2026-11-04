# Backend Feature Spec — BE-EP-003: Mission Step Explainability Endpoint

## Algemene Informatie

* **Feature-ID:** BE-EP-003
* **Naam:** Mission Step Explainability Endpoint
* **Bestandspad:** `src/core/api/mission_endpoints.py`
* **Sprint:** SP-C02 Dag 1
* **Datum:** 2026-05-28
* **Autonomie Ladder Niveau:** L2 Co-Pilot

---

## Doel & Context

Dit endpoint implementeert het ophalen van echte AI-transparantie/AI Act-gegevens voor een specifieke stap van een missie, ter vervanging van nep-mock-data. Het is verplicht voor compliance met EU AI Act Art. 13. Het endpoint queryt de `council_decisions` tabel en past strikte tenant-isolatie toe.

---

## Datamodel & Bron

* **Tabel:** `council_decisions` (ORM-model: `CouncilDecisionRow`)
* **Relatie:** De `step_id` komt overeen met `proposal_id` in de database.
* **Sortering:** Meest recente beslissing gesorteerd op `timestamp DESC`.

---

## API Contract

### Request
* **Methode:** `GET`
* **Pad:** `/api/v1/missions/{mission_id}/steps/{step_id}/explainability`
* **Beveiliging:** JWT met `agents:read` OAuth2 scope (en cookie session support).
* **Tenant Resolving:** Altijd via JWT Context (`get_tenant`), nooit via client payload.

### Succesrespons (HTTP 200)
```json
{
  "success": true,
  "data": {
    "available": true,
    "step_id": "1f2a21b4-1f50-47c8-bdc1-f86a2beb728b",
    "agent_type": "workflow",
    "decision_rationale": "Decision made based on cluster 1 analysis.",
    "verdict": "APPROVED",
    "deliberation_ms": 450,
    "human_reviewed": false,
    "risk_level": null
  }
}
```

### Geen data (HTTP 200)
Als er geen deliberatie is opgenomen in de database voor deze `step_id`:
```json
{
  "success": true,
  "data": {
    "available": false,
    "reason": "No council deliberation recorded for this step."
  }
}
```

---

## Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Ingelogde gebruiker of frontend hook die AI Act transparantie opvraagt |
| Voorwaarde | Geldige JWT, tenant_id in token aanwezig, mission_id en step_id zijn strings |
| Actie | GET /api/v1/missions/{mission_id}/steps/{step_id}/explainability |
| Systeemreactie | Query op council_decisions tabel gefilterd op tenant_id en step_id |
| Succesrespons | HTTP 200 + {"success": true, "data": {"available": true/false, ...}} |
| Foutrespons | HTTP 401 bij geen auth; HTTP 500 + {"success": false, "error": {...}} bij DB-fout |
| Uitzonderingen | Geen council decision aanwezig: {"available": false} zonder fout; step_id niet gekoppeld aan proposal_id: behandeld als geen data |

---

## Verificatie & Tests

* **Testbestand:** `tests/unit/test_sp_c02_explainability.py`
* **Testcases:**
  - `test_explainability_endpoint_exists`
  - `test_explainability_invalid_uuid_returns_available_false`
  - `test_explainability_never_returns_mock_data`
  - `test_unauthenticated_request_returns_401`
  - `test_tenant_isolation_prevents_cross_tenant_access`

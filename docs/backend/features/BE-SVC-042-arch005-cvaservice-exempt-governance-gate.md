# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-042
- Feature naam: CVAService ADR-022 exempt + GovernanceGate HTTPException correctie (ARCH-005)
- Status: APPROVED
- Auteur: Claude (SP-CVA-P1 Dag 1)
- Reviewer: quality-reviewer
- Datum: 2026-06-21
- Gerelateerde user story / ticket: SP-CVA-P1 Dag 1 -- ARCH-005 + pre-existing governance_gate fix
- Gerelateerde router / module: `src/core/services/cva_service.py`, `src/core/copilot/council/governance_gate.py`
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.0

---

## Doel en scope

### Doel

Twee correcties in de CVA/Council governance-stack:

1. **ARCH-005**: Architecture test `test_cva_learning_mixin_decision.py` was intentioneel ROOD omdat
   CVAService het ADR-022 LearningMixin-patroon niet implementeerde. CVAService is een service-laag,
   geen agent -- ADR-022 exempt is de juiste beslissing. Een comment markeert dit expliciet zodat
   de test GROEN wordt.

2. **governance_gate fix**: `require_council_approval()` gooide `GovernanceVetoError` (subklasse van
   `SanskritiError`, NIET van `HTTPException`) terwijl de docstring, alle callers en alle tests
   `HTTPException(403)` verwachtten. Dit veroorzaakte 4 falende unit tests.

### In scope

- Comment `# ADR-022 exempt: ...` boven `class CVAService:` in `cva_service.py`
- Vervang `GovernanceVetoError` door `HTTPException(403, detail={...})` in `governance_gate.py`
- Architectuurtest GROEN na comment
- 4 pre-existing unit tests GROEN na governance_gate fix

### Out of scope

- Werkelijke ADR-022 LearningMixin implementatie voor CVAService (niet gewenst: service-laag)
- GovernanceVetoError als exception-type (bestaande callers ongewijzigd)

---

## Build summary

- Nieuw gebouwd: n.v.t.
- Gewijzigd:
  - `src/core/services/cva_service.py`: comment regel boven klasse
  - `src/core/copilot/council/governance_gate.py`: raise HTTPException(403) i.p.v. GovernanceVetoError
- Verwijderd: `from src.core.exceptions import GovernanceVetoError` import uit governance_gate.py
- Beinvloede bestaande flows: alle routes die `require_council_approval()` aanroepen ontvangen nu correct HTTPException(403)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SVC-042a | CVAService ADR-022 exempt comment | Service architectuurmarker | `src/core/services/cva_service.py` | Wijziging | Architecture test |
| BE-SVC-042b | governance_gate HTTPException correctie | Service governance | `src/core/copilot/council/governance_gate.py` | Wijziging | Council approval flow |

---

## API-flows

### Flow: Council approval (gecorrigeerd)

- Naam: Governance gate -- niet-APPROVED verdicts
- Trigger: `require_council_approval()` aangeroepen vanuit een AI-route
- Voorwaarden: AgentCouncil geretourneerd heeft BLOCKED/MODIFIED/HITL_REQUIRED/DEFERRED
- Request-pad: route -> require_council_approval() -> council.deliberate() -> verdict != APPROVED
- Service-stappen:
  1. Council retourneert CouncilDecision met non-APPROVED verdict
  2. `raise HTTPException(403, detail={code, message, decision_id, verdict})`
- DB-operaties: geen extra
- Successtatus: geen (403 wordt altijd gegooid bij non-APPROVED)
- Foutpaden: `403 Forbidden` met `{"code": "GOVERNANCE_BLOCKED", "decision_id": "...", "verdict": "..."}`
- Eindtoestand: geen DB-write; beslissing al door CouncilAuditWriter gelog (AuditOfficer)

---

## Detaildocumentatie per artefact

---

## [BE-SVC-042a] CVAService ADR-022 exempt comment

### 1. Type

- Service architectuurmarker (comment)

### 2. Locatie

- Bestandspad: `src/core/services/cva_service.py`
- Klasse: `class CVAService`

### 3. Gerelateerde flow

- Architecture test `tests/architecture/test_cva_learning_mixin_decision.py`

### 4. Doel

- ADR-022 schrijft voor dat agents `LearningMixin` moeten implementeren. CVAService is een
  service-laag (geen agent); leren verloopt via council agents in de call-keten. De comment
  markeert dit als een expliciete beslissing -- niet als een gemiste implementatie.

### 5. Functionele beschrijving

- Geen gedragswijziging. De comment maakt de architectuurbeslissing zichtbaar voor tools,
  reviewers en de architecture test.

### 6. Technische beschrijving

- `# ADR-022 exempt: service-laag, geen agent. Learning via council agents in call chain.`
  direct boven `class CVAService:`
- Architecture test zoekt op `"# ADR-022 exempt:"` in de broncode van `cva_service.py`

### 7. Zichtbaarheids- en toegangsregels

- n.v.t. (geen runtime-gedrag)

### 17. Acceptatiecriteria

- `tests/architecture/test_cva_learning_mixin_decision.py` GROEN na toevoeging comment
- Geen pyright-fouten

---

## [BE-SVC-042b] governance_gate HTTPException correctie

### 1. Type

- Service-functie correctie (exception type)

### 2. Locatie

- Bestandspad: `src/core/copilot/council/governance_gate.py`
- Functie: `require_council_approval()`

### 3. Gerelateerde flow

- Alle AI-routes: copilot/turn, cva/chat, focus builder, ALS, agentic

### 4. Doel

- Docstring, callers en tests verwachtten HTTPException(403) bij non-APPROVED verdicts.
  De implementatie gooide GovernanceVetoError (subklasse SanskritiError, niet HTTPException).
  FastAPI converteert SanskritiError niet automatisch naar HTTP 403; de response-code was
  onbepaald. Correctie: raise HTTPException(403) met gestructureerd detail-object.

### 5. Functionele beschrijving

- Bij BLOCKED/MODIFIED/HITL_REQUIRED/DEFERRED: `HTTPException(403)` met:
  - `code`: "GOVERNANCE_BLOCKED"
  - `message`: uitleg voor gebruiker (of fallback "Governance policy violation")
  - `decision_id`: str(decision.decision_id)
  - `verdict`: decision.verdict.value

### 6. Technische beschrijving

- Verwijderd: `from src.core.exceptions import GovernanceVetoError`
- Vervangen: `raise GovernanceVetoError(...)` door `raise HTTPException(status_code=403, detail={...})`
- HTTPException is door FastAPI standaard vertaald naar JSON response

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne service-aanroep)
- Tenant-isolatie: decision.tenant_id zit in het audit-record (via CouncilAuditWriter)

### 8. Request-specificatie

- n.v.t. (interne aanroep, geen HTTP route)

### 9. Response-specificatie

- 403 Forbidden:
  ```json
  {
    "detail": {
      "code": "GOVERNANCE_BLOCKED",
      "message": "<explanation_for_user>",
      "decision_id": "<uuid>",
      "verdict": "BLOCKED|MODIFIED|HITL_REQUIRED|DEFERRED"
    }
  }
  ```

### 13. Foutafhandeling

- 403: Council retourneert non-APPROVED verdict
- 500: Council crash -> HTTPException(500, code="COUNCIL_UNAVAILABLE") [ongewijzigd]

### 17. Acceptatiecriteria

- `test_require_council_approval_raises_403_on_non_approve[BLOCKED]` GROEN
- `test_require_council_approval_raises_403_on_non_approve[MODIFIED]` GROEN
- `test_require_council_approval_raises_403_on_non_approve[HITL_REQUIRED]` GROEN
- `test_require_council_approval_raises_403_on_non_approve[DEFERRED]` GROEN
- `exc_info.value.status_code == 403`
- `exc_info.value.detail["code"] == "GOVERNANCE_BLOCKED"`
- `"decision_id" in exc_info.value.detail`

### 18. Integratoruitleg

- Bij governance-blokkering ontvangt de caller HTTP 403 met `detail.code == "GOVERNANCE_BLOCKED"`
- `detail.decision_id` is traceerbaar in het audit-log
- `detail.verdict` geeft de specifieke reden (BLOCKED, HITL_REQUIRED, etc.)

### 19. Trainingssamenvatting

- Actor: AI-route (copilot, CVA, agentic)
- Voorwaarde: AgentCouncil keurt het voorstel niet goed
- Actie: `require_council_approval()` aangeroepen met voorstel
- Systeemverwerking: Council retourneert non-APPROVED verdict -> governance_gate gooit HTTPException(403)
- Succesrespons: n.v.t. (APPROVED pad ongewijzigd)
- Foutrespons: 403 met `code=GOVERNANCE_BLOCKED`, `decision_id`, `verdict`
- Uitzonderingen: Council crash -> 500 COUNCIL_UNAVAILABLE

---

## Integratorhandleiding

- Wanneer governance blokkeert: HTTP 403 met `detail.code == "GOVERNANCE_BLOCKED"`
- Gebruik `detail.decision_id` voor support-escalatie of HITL-flow
- Gebruik `detail.verdict` voor client-side branching (bijv. toon "Goedkeuring vereist" bij HITL_REQUIRED)

---

## Open aannames

- GovernanceVetoError blijft bestaan in exceptions module voor mogelijke directe throws buiten governance_gate

## Open vragen

- n.v.t.

## Risico's

- Geen; correctie brengt implementatie in lijn met docstring en tests

---

## QA-checks

- [x] Architecture test test_cva_learning_mixin_decision.py GROEN
- [x] 4 parametrized governance gate tests GROEN
- [x] 491 targeted tests pass (geen regressies)
- [x] pyright: 0 errors (baseline behouden)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED

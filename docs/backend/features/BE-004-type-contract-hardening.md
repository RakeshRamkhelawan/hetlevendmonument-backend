# Backend Feature Specification

## Metadata

- **Feature ID:** BE-004
- **Feature naam:** Type Contract Hardening — Mypy Compliance Fixes
- **Status:** Geïmplementeerd
- **Auteur:** Kimi Code CLI
- **Reviewer:** (self-review via reviewer prompt)
- **Datum:** 2026-05-28
- **Gerelateerde user story / ticket:** Pre-existing mypy errors in copilot service layer
- **Gerelateerde router / module:** Copilot Council, Governance GDPR, Copilot Dependencies
- **Gerelateerde frontend endpoints:** Geen
- **Gerelateerde database tabellen:** `council_decisions` (indirect via audit_writer)
- **Versie:** 1.0

---

## Doel en scope

### Doel

Drie pre-existing mypy typefouten in de copilot service-laag structureel oplossen door ontbrekende protocol-members en class-methoden toe te voegen. Dit maakt de code future-proof voor verdere type-hardening en voorkomt dat nieuwe wijzigingen op dezelfde lijnen falen.

### In scope

1. `IAuditWriter.bind_execution_result` — ontbrekende `status` parameter toevoegen aan Protocol.
2. `GDPREnforcer.detect_pii()` — ontbrekende method toevoegen aan concrete class.
3. `CouncilAuditWriter.log_user_response()` — ontbrekende method toevoegen aan concrete class.
4. Unit tests voor `detect_pii()` (13 nieuwe testcases).
5. Regressieverificatie: 47/47 bestaande tests blijven groen.

### Out of scope

- Nieuwe API-endpoints of routers.
- Database schema-wijzigingen (migraties).
- Gedragswijzigingen in runtime logica.
- Frontend-wijzigingen.

---

## Build summary

- **Nieuw gebouwd:**
  - `GDPREnforcer.detect_pii()` met regex-heuristieken voor email, telefoon, SSN, creditcard.
  - `CouncilAuditWriter.log_user_response()` met structured logging.
  - 13 unit tests in `TestDetectPii`.
- **Gewijzigd:**
  - `src/core/copilot/protocols.py` — `status: str = "success"` toegevoegd aan `IAuditWriter.bind_execution_result`.
  - `src/core/governance/gdpr_enforcer.py` — `detect_pii()` toegevoegd.
  - `src/core/copilot/council/audit_writer.py` — `log_user_response()` toegevoegd.
  - `tests/unit/governance/test_gdpr_enforcer.py` — `TestDetectPii` class toegevoegd.
- **Verwijderd:** Geen.
- **Beïnvloede bestaande flows:**
  - Council factory (`build_council`) — `PrivacyOfficer` instantiatie wordt nu type-correct.
  - Copilot dependency builder (`_build_copilot_service`) — `CouncilAuditWriter` wordt nu correct geaccepteerd als `IAuditWriter`.
  - Copilot service (`_execute_decision`) — `bind_execution_result` call is nu type-correct.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SCH-001 | IAuditWriter.bind_execution_result | Protocol | `src/core/copilot/protocols.py` | Wijziging | Copilot execution audit trail |
| BE-UTL-001 | GDPREnforcer.detect_pii | Utility | `src/core/governance/gdpr_enforcer.py` | Wijziging | PrivacyOfficer deliberatie |
| BE-SVC-001 | CouncilAuditWriter.log_user_response | Service | `src/core/copilot/council/audit_writer.py` | Wijziging | Council audit logging |

---

## API-flows

Geen nieuwe API-flows. Dit is een type-hardening change op bestaande interne flows.

---

## Detaildocumentatie per artefact

---

## [BE-SCH-001] IAuditWriter.bind_execution_result

### 1. Type

Protocol (structural subtyping).

### 2. Locatie

- **Bestandspad:** `src/core/copilot/protocols.py`
- **Klasse / functie:** `IAuditWriter.bind_execution_result`

### 3. Gerelateerde flow

Copilot execution audit trail — na succesvolle of gefaalde tool-execution wordt het resultaat gebonden aan de council decision.

### 4. Doel

Het Protocol definieert het contract voor audit writers die execution results kunnen vastleggen. De `status` parameter was impliciet aanwezig in alle implementaties maar ontbrak in het Protocol, waardoor mypy een typefout rapporteerde bij calls die `status` doorgaven.

### 5. Functionele beschrijving

`bind_execution_result` koppelt het resultaat van een geautoriseerde actie aan een bestaande council decision record. De `status` parameter geeft aan of de executie succesvol was (default `"success"`) of is mislukt (bijv. `"failed"`).

### 6. Technische beschrijving

- **Signature voor fix:**
  ```python
  async def bind_execution_result(
      self,
      *,
      decision_id: UUID,
      tenant_id: int,
      result_data: dict[str, Any],
      status: str = "success",
  ) -> None: ...
  ```
- **Impact:** Alle bestaande implementaties (`_FailClosedAudit`, `CouncilAuditWriter`) hadden deze parameter al, dus de fix is backward-compatible.
- **Geen runtime impact** — het Protocol wordt alleen door mypy gecontroleerd.

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** N.v.t. (intern protocol).
- **Vereiste rol / scope:** N.v.t.
- **Tenant-isolatie:** `tenant_id` is een verplichte parameter in de signature.
- **Feature flag:** Geen.

### 8. Request-specificatie

N.v.t. — intern protocol, geen HTTP endpoint.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `decision_id` moet een geldige `UUID` zijn.
- `tenant_id` is verplicht (type `int`).
- `result_data` is een `dict[str, Any]`.
- `status` is een `str` met default `"success"`.

### 11. Business rules

- De audit writer MOET het execution result kunnen koppelen aan een bestaande council decision.
- Bij ontbrekende audit writer configuratie MOET een `RuntimeError` worden gegooid (fail-closed gedrag via `_FailClosedAudit`).

### 12. Afhankelijkheden

- `uuid.UUID`
- `typing.Any`

### 13. Foutafhandeling

- N.v.t. op protocol-niveau. Concrete implementaties hanteren eigen foutafhandeling (bijv. `AuditWriteError` in `CouncilAuditWriter`).

### 14. Transacties en dataïntegriteit

N.v.t. op protocol-niveau.

### 15. Telemetry / logging / tracing

N.v.t. op protocol-niveau.

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [x] `IAuditWriter.bind_execution_result` accepteert `status: str = "success"`.
- [x] Alle bestaande implementaties van `IAuditWriter` zijn compatible met het gewijzigde protocol.
- [x] Mypy rapporteert geen typefout meer op de call site in `service.py:285`.

### 18. Integratoruitleg

N.v.t. — intern protocol, niet zichtbaar voor API-consumenten.

### 19. Trainingssamenvatting

- **Actor:** CopilotService bij het binden van execution results.
- **Voorwaarde:** Een council decision bestaat en tool execution is afgerond.
- **Actie (request):** Roep `audit_writer.bind_execution_result(..., status="failed")` aan.
- **Systeemverwerking:** Audit writer persistert resultaat-hash en status.
- **Succesrespons:** Geen return value (`None`).
- **Foutrespons:** `RuntimeError` als audit writer niet is geconfigureerd.
- **Uitzonderingen:** Database fouten bij schrijven worden gelogd en doorgesluisd.

---

## [BE-UTL-001] GDPREnforcer.detect_pii

### 1. Type

Utility method (class method op `GDPREnforcer`).

### 2. Locatie

- **Bestandspad:** `src/core/governance/gdpr_enforcer.py`
- **Klasse / functie:** `GDPREnforcer.detect_pii`

### 3. Gerelateerde flow

PrivacyOfficer deliberatie — stap 2 (PII detection in action_params).

### 4. Doel

Detecteer gevoelige persoonsgegevens (PII) in een data payload zodat de `PrivacyOfficer` kan beslissen of een actie extra goedkeuring vereist (bijv. bulk export).

### 5. Functionele beschrijving

`detect_pii` doorloopt een geneste datastructuur (dicts, lists, strings) en zoekt met regex naar bekende PII-patronen: emailadressen, telefoonnummers (US-formaat), SSNs (US-formaat `123-45-6789`), en creditcardnummers. De method retourneert een lijst met gevonden PII-type namen zonder duplicaten.

### 6. Technische beschrijving

- **Signature:**
  ```python
  def detect_pii(self, data: dict[str, Any]) -> list[str]
  ```
- **Implementatie:** Recursieve flattening van nested dicts/lists naar strings, gevolgd door regex matching.
- **Patronen:**
  - Email: `[\w.-]+@[\w.-]+\.[a-zA-Z]{2,}`
  - Telefoon: `\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b`
  - SSN: `\b\d{3}-\d{2}-\d{4}\b`
  - Creditcard: `\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b`
- **Return value:** Lege lijst (`[]`) als geen PII wordt gevonden; anders lijst met unieke type s

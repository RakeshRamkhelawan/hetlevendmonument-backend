# Backend Feature Specification

## Metadata

- Feature ID: BE-AUD-004
- Feature naam: log_security_event() PII-sanering in system logs
- Status: APPROVED
- Auteur: AI-agent (SP-AUDIT-004)
- Reviewer: BE-review-agent
- Datum: 2026-06-30
- Gerelateerde user story / ticket: SP-AUDIT-004
- Gerelateerde router / module: src/core/governance/services/audit_service.py
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: audit_logs (indirecte schrijfoperatie via AuditService.log_event)
- Versie: 1.0

---

## Doel en scope

### Doel

Voorkomt dat Persoonsidentificeerbare Informatie (PII) uit de `details`-dict van
`log_security_event()` in system logs terechtkomt. Dit is een ADR-019-vereiste en
noodzakelijk voor SOC 2 / GDPR-compliance.

### In scope

- Wijziging van `log_message` f-string: `details={details}` -> `details_keys={details_keys}`
- Wijziging van `description` fallback: `f"{event_type}: {details}"` -> `f"{event_type}: keys={list(details)}"`
- Alleen sleutelnamen worden gelogd; waarden worden nooit naar system log geschreven

### Out of scope

- Wijzigingen aan de DB-schrijfoperatie (details-dict gaat NIET-gesaneerd naar DB via event_metadata)
- Wijzigingen aan `log_event()` of andere audit-methoden

---

## Build summary

- Nieuw gebouwd: n.v.t.
- Gewijzigd: `src/core/governance/services/audit_service.py` (2 plaatsen: log_message + description fallback)
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: alle aanroepen van `log_security_event()` met een details-dict

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AUD-004 | log_security_event PII-sanering | BE-UTL | src/core/governance/services/audit_service.py | Wijziging | Security event logging |

---

## API-flows

### Flow: log_security_event met PII-gevoelige details

- Naam: Security event logging
- Trigger: aanroep van `log_security_event(event_type="...", details={"email": "...", "token": "..."})`
- Voorwaarden: details-dict bevat PII of gevoelige waarden
- Request-pad: caller -> log_security_event -> log_message constructie -> system log
- Service-stappen:
  1. `details_keys = list(details) if details else []`
  2. log_message bevat `details_keys=[...]` (sleutels, geen waarden)
  3. description fallback: `f"{event_type}: keys={list(details)}"` (sleutels, geen waarden)
  4. DB-write via AuditService.log_event (event_metadata bevat volledige dict -- alleen DB, niet log)
- DB-operaties: INSERT in audit_logs via AuditService.log_event (waarden gaan naar DB, niet naar system log)
- Successtatus + response: None (void function)
- Foutpaden: als db=None, wordt DB-schrijfoperatie overgeslagen
- Eindtoestand: system log bevat sleutelnamen; DB bevat volledige event_metadata

---

## Detaildocumentatie per artefact

## [BE-AUD-004] log_security_event() PII-sanering

### 1. Type

- Utility-functie

### 2. Locatie

- Bestandspad: src/core/governance/services/audit_service.py
- Klasse / functie: log_security_event() (module-level functie)

### 3. Gerelateerde flow

- Security event logging flows (CROSS_TENANT_ATTEMPT, QUOTA_EXCEEDED, INVALID_JWT, etc.)

### 4. Doel

- Voorkomt dat PII-waarden (email, tokens, credentials) in system logs verschijnen
- Voldoet aan ADR-019 PII-separatieprincipe en SOC 2 logging-controls

### 5. Functionele beschrijving

- Voor sanering: `log_message` bevatte `f"... details={details}"` -- volledige dict inclusief PII-waarden
- Na sanering: `log_message` bevat `f"... details_keys={details_keys}"` -- alleen de sleutelnamen
- De `description` fallback in AuditService.log_event() is eveneens gesaneerd van `f"{event_type}: {details}"` naar `f"{event_type}: keys={list(details)}"`
- Operationeel team ziet welke datavelden aanwezig waren zonder de waarden te zien

### 6. Technische beschrijving

- Wijziging 1 (log_message, regels 133-138 na fix):
  ```python
  details_keys = list(details) if details else []
  log_message = (
      f"SECURITY EVENT [{derived_level.upper()}]: {event_type} | "
      f"user_id={user_id} | tenant_id={tenant_id} | "
      f"path={request_path} | method={request_method} | "
      f"ip={ip_address} | details_keys={details_keys}"
  )
  ```
- Wijziging 2 (description fallback, regel 159-160 na fix):
  ```python
  description=description or (f"{event_type}: keys={list(details)}" if details else event_type),
  ```
- De `event_metadata` parameter voor AuditService.log_event() blijft ongewijzigd:
  `metadata={"request_method": request_method, **(details or {})}` -- volledige dict gaat naar DB

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne aanroep)
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: n.v.t. (logging utility)
- Feature flag: n.v.t.

### 8. Request-specificatie

- Methode: Python function call (intern)
- Route: n.v.t.
- Relevante parameters: `details: dict[str, Any] | None`

### 9. Response-specificatie

- Successtatus: None (void)
- Response schema: n.v.t.
- Foutstatussen: n.v.t.

### 10. Validaties en constraints

- Als details=None: details_keys=[] (lege lijst)
- Als details={}: details_keys=[] (lege lijst)
- Als details={"k": "v"}: details_keys=["k"] (alleen sleutels)

### 11. Business rules

- PII-waarden mogen NOOIT in system logs verschijnen (ADR-019)
- DB mag volledige details bevatten voor forensisch gebruik (toegangsbeheer apart)
- Sleutelnamen zijn voldoende voor operationele monitoring en alerting

### 12. Afhankelijkheden

- `src/core/shared/security_events.py`: SecurityEvent constanten
- `src/core/governance/services/audit_service.py:AuditService.log_event()`: DB-schrijfoperatie

### 13. Foutafhandeling

- Alle: n.v.t. (guard is non-throwing; system log write mislukt nooit in Python logger)

### 14. Transacties en dataintegritiet

- Wijziging heeft geen invloed op DB-transactie; alleen system log output is gewijzigd

### 15. Telemetry / logging / tracing

- Voor: `details={"email": "victim@example.com"}` -> volledig zichtbaar in system log
- Na: `details_keys=["email"]` -> alleen sleutelnaam zichtbaar in system log

### 16. Caching

- n.v.t.

### 17. Acceptatiecriteria

- PII-waarden (bijv. email-adressen, tokens) verschijnen NIET in system log berichten
- Sleutelnamen uit de details-dict verschijnen WEL in system log berichten
- description fallback bevat GEEN raw details-waarden
- DB event_metadata bevat nog steeds de volledige dict (ongewijzigd)

### 18. Integratoruitleg

- Callers van log_security_event() hoeven niets te wijzigen
- System logs zijn nu compliant voor log-aggregatiesystemen (Splunk, CloudWatch, etc.)
- Voor forensisch gebruik: volledige details staan in de audit_logs tabel in de DB

### 19. Trainingssamenvatting

- Actor: interne service (auth middleware, HITL gate, etc.)
- Voorwaarde: security event met gevoelige details (email, tokens, IP-ranges)
- Actie: `await log_security_event(event_type="CROSS_TENANT_ATTEMPT", details={"email": "user@x.com"})`
- Systeemverwerking: sleutels worden geextraheerd; system log ontvangt sleutelnamen; DB ontvangt volledige dict
- Succesrespons: None (void)
- Foutrespons: n.v.t.
- Uitzonderingen: als details=None, verschijnt "details_keys=[]" in log (geen fout)

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Geen API-wijziging; puur interne sanering
- Log-monitoring dashboards moeten `details_keys=[...]` verwachten in plaats van `details={...}`
- Alert-regels die matchen op details-inhoud moeten worden bijgewerkt naar details_keys

---

## Open aannames

- DB-opslag van volledige details is acceptabel mits toegangsbeheer op DB-niveau correct is (SOC 2 controle apart)

## Open vragen

- n.v.t.

## Risico's

- Laag: operationele alerting op details-inhoud werkt niet meer; teams moeten DB-queries gebruiken voor waarden

---

## QA-checks

- [x] Happy path: details met PII niet in system log
- [x] Edge case: details=None -> geen fout, lege lijst
- [x] Edge case: details={} -> lege lijst
- [x] DB-write bevat nog steeds volledige dict (ongewijzigd)
- [x] description fallback gesaneerd
- [x] Logging en tracing gecontroleerd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Foutstatussen beschreven
- [x] Functionele en technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Open aannames benoemd
- [x] QA-checks uitgevoerd
- [x] Review: APPROVED

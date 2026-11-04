# Backend Feature Specification

## Metadata

- Feature ID: BE-AUD-003
- Feature naam: AuditService.log_action() tenant_id=None guard
- Status: APPROVED
- Auteur: AI-agent (SP-AUDIT-004)
- Reviewer: BE-review-agent
- Datum: 2026-06-30
- Gerelateerde user story / ticket: SP-AUDIT-004
- Gerelateerde router / module: src/core/governance/audit.py
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: audit_logs
- Versie: 1.0

---

## Doel en scope

### Doel

Voorkomt dat `AuditService.log_action()` een audit-entry schrijft zonder geldige tenant_id.
Zonder deze guard kon een None-waarde een untraceable row creeren in de audit_logs tabel,
of in bepaalde DB-configuraties een runtime NOT NULL-fout veroorzaken, afhankelijk van de
nullable-instelling op ORM vs. DB-niveau.

### In scope

- Signatuurwijziging: `tenant_id: int` -> `tenant_id: int | None`
- Early-return guard met `logger.warning` als `tenant_id is None`
- Nuleffect op DB bij None-waarde (geen session.add aanroep)

### Out of scope

- Wijzigingen aan callers (gedekt door BE-AUD-005)
- Wijzigingen aan de hash-chain logica
- Wijzigingen aan andere auditservice-methoden

---

## Build summary

- Nieuw gebouwd: n.v.t.
- Gewijzigd: `src/core/governance/audit.py` (signatuur + guard)
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: elke flow die `log_action()` aanroept met een potentieel None tenant_id

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AUD-003 | log_action() tenant_id None guard | BE-UTL | src/core/governance/audit.py | Wijziging | Alle audit-flows |

---

## API-flows

### Flow: log_action() None-pad

- Naam: log_action None-pad
- Trigger: aanroep van `AuditService.log_action(tenant_id=None, ...)`
- Voorwaarden: tenant_id is None (bijv. system-context zonder actieve tenant)
- Request-pad: caller -> log_action() -> guard -> return None
- Service-stappen:
  1. `tenant_id_int = int(tenant_id) if tenant_id is not None else None` --> None
  2. Guard: `if tenant_id_int is None: logger.warning(...); return None`
  3. Geen verdere verwerking, geen DB-actie
- DB-operaties: geen
- Successtatus + response: None (geen AuditLog object aangemaakt)
- Foutpaden: n.v.t. (guard is early-return, geen exception)
- Eindtoestand: audit_logs tabel ongewijzigd; WARNING in application log

---

## Detaildocumentatie per artefact

## [BE-AUD-003] AuditService.log_action() tenant_id=None guard

### 1. Type

- Utility-functie (guard in service-methode)

### 2. Locatie

- Bestandspad: src/core/governance/audit.py
- Klasse / functie: AuditService.log_action()

### 3. Gerelateerde flow

- Alle router-flows die audit-logging uitvoeren

### 4. Doel

- Voorkomt untraceable audit-entries door None tenant_id vroegtijdig af te wijzen

### 5. Functionele beschrijving

- Als een aanroeper `tenant_id=None` meegeeft, logt de methode een WARNING en retourneert `None`
- Er wordt geen AuditLog object aangemaakt of aan de session toegevoegd
- De caller-flow wordt niet onderbroken (geen exception)

### 6. Technische beschrijving

- Signatuur na wijziging: `async def log_action(tenant_id: int | None, ...) -> AuditLog | None`
- Guard staat direct na `tenant_id_int` berekening, voor de hash-chain logica
- `logger.warning("Audit log skipped: tenant_id is None for action=%s resource=%s", action, resource)`
- Return type is `AuditLog | None` (was `AuditLog`)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne service-aanroep)
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: afgedwongen door guard (geen entry zonder tenant)
- Feature flag: n.v.t.

### 8. Request-specificatie

- Methode: Python method call (intern)
- Route: n.v.t.
- Path parameters: n.v.t.
- Query parameters: n.v.t.
- Request body (schema): n.v.t.
- Verplichte headers: n.v.t.

### 9. Response-specificatie

- Successtatus: None (als tenant_id=None); AuditLog (als tenant_id geldig)
- Response schema: AuditLog | None
- Foutstatussen: n.v.t.

### 10. Validaties en constraints

- `tenant_id is None` -> early return None, geen DB-write
- `tenant_id is not None` -> int()-cast, normale flow

### 11. Business rules

- Audit entries zonder tenant zijn niet traceerbaar en mogen niet worden opgeslagen (ADR-005, ADR-019)
- Een WARNING in de application log is vereist zodat operationeel team het kan monitoren

### 12. Afhankelijkheden

- `src/core/governance/models.py`: AuditLog model
- `src/core/governance/hash_chain.py`: HashChainVerifier (niet geraakt door guard)

### 13. Foutafhandeling

- 400: n.v.t.
- 401: n.v.t.
- 403: n.v.t.
- 404: n.v.t.
- 409: n.v.t.
- 422: n.v.t.
- 429: n.v.t.
- 500: n.v.t. (guard vangt None af zonder exception)
- 503: n.v.t.

### 14. Transacties en dataintegritiet

- Bij None-pad: geen session.add(), geen commit, geen hash-chain mutatie
- Outer transactie van de caller blijft onaangetast

### 15. Telemetry / logging / tracing

- `logger.warning("Audit log skipped: tenant_id is None for action=%s resource=%s", action, resource)`
- Logt altijd (zowel in productie als test-omgeving)

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- Als `tenant_id=None` meegegeven wordt: retourneert None
- Als `tenant_id=None` meegegeven wordt: `session.add()` wordt NIET aangeroepen
- Als `tenant_id=None` meegegeven wordt: WARNING verschijnt in application log met "tenant_id" of "None"
- Als `tenant_id` een geldig integer is: normale flow wordt uitgevoerd

### 18. Integratoruitleg

- De guard is intern en transparant voor callers
- Callers die `tenant_id=None` meegeven ontvangen `None` terug (geen exception)
- De best_effort wrapper rondom de aanroep absorbeert dit None-resultaat zonder fout

### 19. Trainingssamenvatting

- Actor: interne service (router of middleware)
- Voorwaarde: audit-aanroep waarbij tenant_id None is (bijv. system-context)
- Actie (request): `await audit_service.log_action(tenant_id=None, action="...", resource="...")`
- Systeemverwerking: guard detecteert None, logt WARNING, retourneert None zonder DB-write
- Succesrespons: None (geen AuditLog object)
- Foutrespons: n.v.t. (geen exception)
- Uitzonderingen: als session=None EN tenant_id geldig: existing guard voor "no session provided" slaat eveneens audit over

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Interne guard; geen impact op API-consumers
- Callers mogen tenant_id=None doorgeven zonder crashrisico
- Operationeel team moet WARNING-berichten monitoren op "Audit log skipped: tenant_id is None"

---

## Open aannames

- AuditLog.tenant_id is nullable=True op ORM-niveau (geverifieerd in models.py); de guard is dus preventief, niet ter voorkoming van een DB-fout

## Open vragen

- n.v.t.

## Risico's

- Laag: guard verhoogt de kans op "missing audit trail" zichtbaarheid via WARNING

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (tenant_id=None)
- [x] Dataintegritiet en transacties getest
- [x] Performance / load getest (n.v.t.)
- [x] Caching getest (n.v.t.)
- [x] Logging en tracing gecontroleerd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED

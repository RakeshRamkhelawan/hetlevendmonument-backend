# BE-DSM-041: SP-DSM-019 Dag 1 -- tenancy->governance backward deps gesloten

## Status

APPROVED

## Sprint

SP-DSM-019 Dag 1

## Datum

2026-06-26

## Samenvatting

DSM-ARCH-001 gesloten: tenancy->governance backward coupling van 3 naar 0 gebracht.
Aanpak: SecurityEvent class + lichtgewicht log_security_event verplaatst naar
`src/core/shared/security_events.py`. Dead code verwijderd uit audit_middleware.py.
Geen MODULE_MAP wijziging — code-level fix zonder governance I regressie.

## Deliverables

### 1. Nieuw bestand: src/core/shared/security_events.py

Bevat `SecurityEvent` class (pure string-constanten) en `log_security_event` async
functie voor ASGI-middleware callers (logger-only, geen DB-sessie).

Reden voor aparte shared versie: quota_middleware en tenant_middleware roepen
`log_security_event` ZONDER `db=` parameter -- de DB-audit-tak in de governance versie
is voor deze callers altijd een no-op. De shared versie elimineert de onnodige
governance-import zonder functionele regressie.

### 2. Gewijzigd: src/core/governance/services/audit_service.py

`SecurityEvent` class-definitie vervangen door:
```python
from src.core.shared.security_events import SecurityEvent
```

`log_security_event` blijft in governance (met volledige AuditService.log_event DB-path)
voor callers die een `db=` sessie meegeven (auth_service, admin dependencies, scheduling).

### 3. Gewijzigd: src/core/middleware/quota_middleware.py

Import gewijzigd van governance naar shared:
```python
# Was: from src.core.governance.services.audit_service import SecurityEvent, log_security_event
from src.core.shared.security_events import SecurityEvent, log_security_event
```

### 4. Gewijzigd: src/core/middleware/tenant_middleware.py

Identiek patroon als quota_middleware.py.

### 5. Gewijzigd: src/core/middleware/audit_middleware.py

Dead code verwijderd: `log_learning_audit_event` functie (regels 373-400) had geen
externe callers (alle callers gebruiken al `src.core.shared.learning_audit`).
De lazy import `from src.core.governance.audit import audit_service` verviel hiermee.

### 6. Gewijzigd: tests/architecture/test_dsm_medium_pairs_tracking.py

`test_TODO_SP_DSM_017_tenancy_governance_backward_is_zero` hernoemd naar
`test_SP_DSM_019_tenancy_governance_backward_is_zero` met bijgewerkte docstring.
De test was rood (pre-existing failure) en is nu GROEN.

## DSM Metrics

| Metriek | Voor | Na | Target |
|---------|------|-----|--------|
| tenancy->governance edges | 3 | **0** | 0 |
| governance I | 0.373 (Ce=38, Ca=64) | 0.367 (Ce=36, Ca=62) | < 0.40 |
| tenancy->agent_runtime | 0 | 0 | 0 (al opgelost) |

Governance I NIET gestegen door de fix: de shared versie van SecurityEvent + log_security_event
vervangt governance-imports in tenancy; governance Ca daalt met 2 (quota + tenant middleware),
Ce daalt ook omdat governance.services.audit_service nu SecurityEvent importeert uit shared
in plaats van het zelf te definiëren (shared-edge was al aanwezig).

## Arch Tests

| Test | Voor | Na |
|------|------|----|
| `test_SP_DSM_019_tenancy_governance_backward_is_zero` (hernoemd van TODO_SP_DSM_017) | FAIL (pre-existing) | **PASS** |
| `test_dsm_011_governance_instability_below_0_40` | PASS | PASS |
| `test_dsm017_tenancy_agent_runtime_edge_is_zero` | PASS | PASS |
| Arch suite totaal | 265 passed, 2 failed | **266 passed, 2 failed** |

De 2 resterende failures zijn pre-existing van uncommitted wijzigingen aan
`src/core/agents/base_agent.py` (SP-DLP-003 Dag 2 context, niet veroorzaakt door SP-DSM-019).

## Pyright

0 errors (baseline 0, gehandhaafd).

## Unit tests

36 gerichte tests GROEN (tests/unit/middleware/ + tests/unit/test_audit_service_unit.py).

## Trainingssamenvatting

### shared.security_events module

**Actor:** ASGI middleware (quota_middleware, tenant_middleware)
**Voorwaarde:** HTTP request binnenkomt; middleware moet een security event loggen (quota overschreden, ongeldige tenant, etc.)
**Actie:** Middleware importeert `SecurityEvent` en `log_security_event` uit `src.core.shared.security_events`; roept `await log_security_event(event_type=SecurityEvent.QUOTA_EXCEEDED, ...)` aan zonder `db=` parameter
**Systeemverwerking:** `log_security_event` zoekt severity op in `_SEVERITY_MAP`, kiest het juiste log-level (error/warning/info), logt via Python `logger` met `%s`-stijl formatting; geen database-schrijfoperatie
**Succesrespons:** Security event verschijnt in systeemloggen op het juiste niveau; request-verwerking gaat ononderbroken verder
**Foutrespons:** Geen uitzonderingen — `log_security_event` heeft geen `raise`; logfouten worden door Python logging-framework afgehandeld
**Uitzonderingen:** Callers die DB-audit nodig hebben (auth_service, admin dependencies, scheduling) importeren NIET uit shared maar uit `governance.services.audit_service` en geven `db=session` mee

### governance.services.audit_service (gewijzigd)

**Actor:** Auth, admin, scheduling modules
**Voorwaarde:** Security event met database-audit vereist (bijv. na login, JWT-validatie)
**Actie:** Caller importeert `log_security_event` uit governance; roept aan met `db=session`
**Systeemverwerking:** Governance-versie logt naar logger EN schrijft via `AuditService.log_event(db=db, ...)` naar de `audit_logs` tabel
**Succesrespons:** Audit record aangemaakt in database; event in systemlogs
**Foutrespons:** Database-fout wordt gelogd via `logger.error(..., exc_info=True)`; geen re-raise (best-effort patroon)
**Uitzonderingen:** `SecurityEvent` class is nu geimporteerd uit shared — backward compatibel voor alle bestaande callers

## Gewijzigde bestanden

- `src/core/shared/security_events.py` (nieuw)
- `src/core/governance/services/audit_service.py`
- `src/core/middleware/quota_middleware.py`
- `src/core/middleware/tenant_middleware.py`
- `src/core/middleware/audit_middleware.py`
- `tests/architecture/test_dsm_medium_pairs_tracking.py`
- `tests/unit/test_shared_security_events.py` (nieuw, FA-003 fix)

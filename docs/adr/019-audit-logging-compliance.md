# ADR 019: Audit Logging - GDPR/SOC2 Compliance

## Status

Accepted — Geimplementeerd (SHA-256 hash chain actief, 2026-05-26)

## Context

SanskritiSetu moet voldoen aan:

- **GDPR**: PII access logging, data subject requests, retention policies
- **SOC2**: Authentication logging, access controls, change management
- **Enterprise**: append-only audit trail (per ONTWERP, niet afgedwongen door de database -- zie "Wat tamper-evident hier WEL en NIET betekent"), compliance reporting

We hebben een enterprise-grade audit systeem nodig.

## Decision

We implementeren een **Audit Logger** met:

1. **Unified Audit Events**: Alle acties (user, agent, system) loggen naar één stream
2. **Data Classification**: Elk event heeft classificatie (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED)
3. **Compliance Reports**: Automatische generatie van:
   - GDPR reports (PII accesses, data exports, deletions)
   - SOC2 reports (auth events, policy violations, session management)
4. **Integrity**: SHA-256 hash chain voor tamper detection -- met de grenzen uit
   "Wat tamper-evident hier WEL en NIET betekent"
5. **Retention**: Automatische purging na retention period per classificatie

### Audit Event Types

```python
# Data access (GDPR)
DATA_ACCESS, PII_ACCESS, DATA_MODIFICATION, DATA_DELETION, DATA_EXPORT

# Security (SOC2)
AUTHENTICATION_SUCCESS, AUTHENTICATION_FAILURE, AUTHORIZATION_DENIED
SESSION_STARTED, SESSION_ENDED, POLICY_VIOLATION

# Contract lifecycle
CONTRACT_PROPOSED, AGREED, EXECUTED, VETOED, OVERRIDDEN
```

### Report Generation

- **GDPR Report**: Total accesses, PII accesses, by purpose, response times
- **SOC2 Report**: Auth stats, violations, session metrics, uptime
- **Compliance Score**: 0-100 score met recommendations

## Implementatie (2026-05-26)

### Audit event typen actief in productie

| Event type | Categorie | Retention |
| ---------- | --------- | --------- |
| `AUTHENTICATION_SUCCESS` | Security | 365 dagen |
| `AUTHENTICATION_FAILURE` | Security | 365 dagen |
| `AUTHORIZATION_DENIED` | Security | 365 dagen |
| `DATA_ACCESS` | GDPR | 365 dagen |
| `PII_ACCESS` | GDPR | 365 dagen |
| `DATA_EXPORT` | GDPR | 365 dagen |
| `TOOL_EXECUTION` | Agent safety | 365 dagen |
| `POLICY_VIOLATION` | Compliance | 365 dagen |
| `RETRIEVAL_PERFORMED` | Context Engine | 13 maanden |
| `RETRIEVAL_FAILED` | Context Engine | 13 maanden |
| `CROSS_TENANT_LEAKAGE_DETECTED` | Security | 7 jaar |
| `CONTEXT_TRUNCATED` | Context Engine | 90 dagen |

### Hash chain integriteit

Elke audit log entry heeft een `previous_hash` verwijzing naar de vorige entry per tenant.
`clock_timestamp()` wordt gebruikt voor timestamp (niet `NOW()`) om hash chain correctheid te garanderen bij concurrent writes.
Bewuste keuze: geen Event Sourcing (ADR-018 is post-MVP) — hash chain is voldoende voor SOC 2.

### Wat tamper-evident hier WEL en NIET betekent

> Toegevoegd 2026-08-11 na een uitputtende meting (ADR-036 OP-118 t/m OP-121). Dit ADR gebruikte
> "tamper-evident" zonder dreigingsmodel: er stond nergens tegen WELKE aanvaller de keten
> beschermt en waar de sleutel staat. Afgeleide documenten namen die term over en maakten hem
> onderweg sterker ("tamper-proof", "onweerlegbaar", "voorkomt silent tampering door aanvallers
> met DB-toegang"). Die formuleringen zijn niet houdbaar, en dat is hier nu expliciet.

**Wat de keten WEL detecteert:**

| Situatie | Sinds | Hoe |
| --- | --- | --- |
| Wijziging van `tenant_id`, `action`, `resource` of `timestamp` in een rij midden in de keten | altijd | de opvolger valt om op de schakel |
| Verwijderen van rijen, inclusief de hele staart | 2026-08-10 | het anker per tenant (`audit_chain_anchors`) vergelijkt de rijtelling met de vorige meting |
| Herschrijven van geschiedenis met gelijkblijvend aantal rijen | 2026-08-10 | het anker vergelijkt ook de ketenkop |
| Nieuwe rijen zonder hash (hash-strippen) | 2026-08-10 | het watermerk in het anker; het BESTAANDE aantal is een bekend gat (OP-108) |
| Dat er uberhaupt niet meer gecontroleerd wordt | 2026-08-10 | de verificatie draait dagelijks en er is een `absent()`-alert |

**Wat de keten NIET detecteert, en dat is de kern:**

1. **Een aanvaller met schrijfrechten op de database kan de hele keten herberekenen.** De hash is
   ongesleuteld SHA-256 over kolommen die in dezelfde rij staan. Gemeten: `is_valid=True` na een
   volledige hercompute. In elke configuratie in deze repo draait de applicatie bovendien als
   `postgres` met `GRANT ALL`, en er is nergens een `REVOKE` op `audit_logs`. **Dit is ADR-036
   OP-120 en wordt op dit moment opgelost met een HMAC.**
2. **Zeven kolommen vallen buiten de hash.** `_compute_hash` dekt vijf velden. `user_id`,
   `event_metadata`, `description`, `event_type`, `threat_level`, `client_ip` en `endpoint` zijn
   te wijzigen zonder ketenbreuk. Voor het HITL-pad is dat sinds 2026-08-09 afgevangen met een
   digest in `resource` (`hitl_evidence.py`); voor andere schrijvers niet (OP-121).
3. **Het anker staat in dezelfde database als het bewijs.** Het vangt een kapotte opruimjob, een
   ongeluk, en een aanvaller die het anker niet kent -- niet iemand die het meebijwerkt. Zolang
   het anker niet is ondertekend, is dit een consistentiecontrole en geen onafhankelijk bewijs.
4. **Wie de applicatie compromitteert, heeft alles.** Sleutel en databaseverbinding zitten in
   hetzelfde procesgeheugen. Een HMAC verplaatst de drempel naar "kan de tabel schrijven EN een
   omgevingsvariabele lezen" -- dat is een echte verbetering tegen een gestolen database of
   backup, en geen verdediging tegen codeuitvoering in de applicatie.
5. **Er is geen kopie buiten deze database.** Zie de correctie bij "Bewaar-locatie bewijs": de
   gestreamde kopie naar Log Analytics bestaat niet. Zonder externe, append-only bestemming is
   er geen bewijs dat een beheerder met volledige toegang niet kan aanraken (OP-119).

**Conclusie voor een auditor.** De keten maakt wijziging en verwijdering *aantoonbaar* voor een
aanvaller zonder databaseschrijfrechten, en sinds 2026-08-10 wordt daar dagelijks op
gecontroleerd en gealarmeerd. De term "tamper-proof" is nergens van toepassing, en "onweerlegbaar"
evenmin: daarvoor is een externe, onafhankelijk beheerde bestemming nodig.

### Report generatie

- SOC 2 rapport beschikbaar via `/api/v1/copilot/audit/report` (authenticated)
- Compliance score 0-100 met aanbevelingen
- GDPR rapport via DSAR-export endpoint

### Retrieval audit trail (toegevoegd 2026-05-27)

Elke Copilot turn die gebruik maakt van de Context Engine (ADR-027 §11) produceert een retrievalevidence record:

```json
{
  "event": "RETRIEVAL_PERFORMED",
  "decision_id": "...",
  "tenant_id": "42",
  "user_id": "123",
  "sources": [
    {"type": "platform_knowledge", "chunks": 5, "sources_hash": "sha256:abc..."},
    {"type": "live_registry", "endpoints": 12, "agents": 3, "tools": 8},
    {"type": "twin_memory", "profile_version": "1.2.0", "memories": 4}
  ],
  "tenant_scope_check": "passed",
  "truncation_applied": false,
  "retrieval_ms": 145
}
```

**Cross-tenant leakage detectie**:
- Als `tenant_scope_check` faalt (een retrieved chunk heeft een ander `tenant_id`), wordt `CROSS_TENANT_LEAKAGE_DETECTED` geëmit
- Dit is een **severity CRITICAL** audit event met 7-jaar retentie
- Triggert onmiddellijk `POLICY_VIOLATION` en alert `SearchCrossTenantLeakage` (ADR-014)

### Bewaar-locatie bewijs

> **Gecorrigeerd 2026-08-11 (ADR-036 OP-120).** Hier stonden drie beweringen die niet door de
> code werden gedragen. Ze zijn niet weggehaald maar doorgehaald met de meting erbij, zodat
> zichtbaar blijft dat de claim is bijgesteld en waarom.

- Database: PostgreSQL. ~~tenant-gesoleerd via RLS (ADR-005)~~ -- **onjuist.** `audit_logs` is
  EXPLICIET uitgesloten van RLS en van de ORM-tenantfilter. Vastgelegd op drie plaatsen:
  `src/alembic/versions/20260522_add_rls_core_tables.py:7-8` ("*audit_logs is intentionally
  excluded*"), `d4e5f6a7b8c9_create_audit_logs_table.py:22-25`, en
  `src/core/database/tenant_query_filter.py:190-192` (de enige hardgecodeerde uitzondering op de
  automatische filter). ADR-005 regel 113 zegt zelf het omgekeerde van wat hier stond.
  Tenant-isolatie op deze tabel bestaat uitsluitend als handgeschreven `WHERE tenant_id = ...`
  in de aanroepende services.
- ~~Azure Log Analytics: gestreamde kopie voor long-term retention en KQL queries~~ --
  **niet geimplementeerd.** De workspace bestaat in `infra/modules/log-analytics.bicep`, maar
  niets stuurt er auditregels heen: geen `diagnosticSettings`, geen OpenTelemetry-logexport, geen
  `azure-monitor`-pakket in enige requirements-file. De workspace-id is alleen een Bicep-output.
- Retentie: 365 dagen is geconfigureerd op de Log Analytics-workspace, maar er komt daar niets
  binnen (zie hierboven). Voor de database geldt de retentie uit `retention_cleanup.py`.

## Consequences

### Positive

- Out-of-the-box GDPR/SOC2 compliance
- Automatische report generation voor auditors
- Real-time compliance monitoring
- Complete audit trail voor forensics

### Negative

- Significant storage requirements (alle events gelogd)
- Performance impact van crypto hashing per event
- Complexe retention logic

### Mitigations

- Async logging (non-blocking)
- Hot/warm/cold tier storage
- Configurable retention per event type
- Sampling voor high-frequency events (optioneel)

## AI Act Governance Mapping (ADR-031)

Dit ADR levert aantoonbaar bewijs voor de volgende AI Act vereisten:

| Vereiste | Artikel | Hoe dit ADR voldoet |
|----------|---------|---------------------|
| Automatic logging of every AI decision | EU AI Act art. 12 | Council → AuditOfficer → hash chain is the mandatory step 5 of the canonical governance pipeline; no AI action executes without audit write |
| Logs retained minimum 6 months | EU AI Act art. 26(6) | 13-month retention for all Council decisions and officer reasoning chains (exceeds minimum) |
| Tamper-evident logs | EU AI Act art. 12, ISO 42001 | SHA-256 hash chain with `previous_hash` linkage per tenant. **Zie "Wat tamper-evident hier WEL en NIET betekent" hieronder** -- de dekking is smaller dan de term suggereert (gecorrigeerd 2026-08-11) |
| Event log with actor, model, outcome | ISO 42001 A.6.2.8 | `CouncilDecision` schema includes full decision context: tenant_id, user_id, model_id, model_version, verdict, officer_verdicts, deliberation_ms |
| Right to explanation | GDPR art. 13-15 | `explanation_for_user` field per decision; audit viewer UI at `/api/v1/copilot/audit/{decision_id}` |

## SOC 2 Mapping

Dit ADR levert aantoonbaar bewijs voor de volgende SOC 2 Security Criteria:

| Criterium | Subcriteria | Hoe dit ADR voldoet |
| --------- | ----------- | ------------------- |
| CC4.1 | Monitoring activities | Alle audit events worden real-time vastgelegd; compliance score is meetbaar en rapporteerbaar via `/api/v1/copilot/audit/report` |
| CC4.2 | Evaluates and communicates deficiencies | Automatische SOC 2 rapport generatie toont auth-statistieken, policy violations en session metrics; compliance score 0-100 met concrete aanbevelingen |
| CC7.2 | Monitoring tools implemented | SHA-256 hash chain maakt tamper detection mogelijk; `AUTHENTICATION_FAILURE` events zijn detecteerbaar en doorzoekbaar via KQL in Log Analytics |
| CC7.3 | Security incidents identified and communicated | `POLICY_VIOLATION` en `AUTHORIZATION_DENIED` events zijn searchable via KQL in Azure Log Analytics; DSAR export via dedicated endpoint |
| CC7.4 | Security events assessed | Forensisch onderzoek mogelijk via hash chain traversal (`previous_hash` naar `hash`); `output_hash` in tool_audit_logs bewaart bewijs zonder gevoelige output op te slaan |

### Bekende implementatiegat (P0-5) — vastgesteld 2026-05-28

**Probleem:** Het `ExportJob` model en de bijbehorende tabel (`export_jobs`) bestaan niet.
`GET /api/v1/gdpr/export/download/{id}` crasht met `NoSuchTableError`. GDPR Art. 20
(recht op data-portabiliteit) is daarmee volledig geblokkeerd voor alle gebruikers.

**Vereiste fix (P0):**

1. Maak `src/core/models/gdpr_models.py` aan:

```python
class ExportJob(Base):
    __tablename__ = "export_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.clock_timestamp())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

2. Alembic-migratie aanmaken (`add_export_jobs_table`) met correcte `downgrade()`.
3. `POST /api/v1/gdpr/export` — start async Dramatiq actor, retourneert `{"job_id": ...}`.
4. `GET /api/v1/gdpr/export/download/{job_id}` — retourneert bestand als `status == "completed"`,
   HTTP 202 als `status == "pending"`, HTTP 404 als job niet bestaat.

**Tijdsinschatting:** 3-4u. Volledig fix-plan: `docs/frontend/pages/22-platform-p0-blockers-scope.md`.

---

## Implementatie-bevinding -- L3 Wiring Audit 2026-06-01

### CG-008 [HIGH] AuditLoggingMiddleware is een orphan -- nooit toegevoegd aan de ASGI-stack

**Situatie:** ADR-019 beschrijft request-level audit logging als onderdeel van de compliance-pipeline.
**Werkelijkheid:** `AuditLoggingMiddleware` is gedefinieerd in
`src/core/middleware/audit_middleware.py` maar is NOOIT geimporteerd of toegevoegd in
`src/core/api/setup/middleware_config.py`. Er bestaat geen request-level audit trail in de ASGI-stack:
geen logging van wie welk endpoint aanriep, wanneer, van welk IP, met welke response-code.
**Bewijs:** grep op `AuditLoggingMiddleware` in `middleware_config.py`: geen resultaat.
`src/core/middleware/audit_middleware.py` bestaat maar staat los van de middleware-stack.
**Impact:**

- SOC 2 CC7.2 (monitor system components) is niet gedekt voor API request-level events
- Security-incidenten kunnen niet worden gereconstrueerd uit logs
- AI Act Artikel 12 (automatische logging voor high-risk AI) is niet aantoonbaar voor alle routes
- `AuditLoggerMiddleware` (security pattern detection: SQLi, XSS, path traversal) is ook orphan

**Fix:** Importeer `AuditLoggingMiddleware` in `middleware_config.py` en voeg het toe aan de
middleware-stack tussen `TenantMiddleware` en `SecurityMiddleware`. Activeer `log_to_db=True`
in productie voor DB-backed audit trails per ADR-019.
**Sprint:** SP-WE-14 (te plannen, P1 compliance)

---

### Open gaps richting volledige SOC 2 Type I readiness

- Geen geautomatiseerde alerting op abnormale authenticatie-patronen (bijv. meer dan 5 `AUTHENTICATION_FAILURE` per minuut per IP); drempel en kanaal zijn nog niet geconfigureerd
- Geen formeel incident response plan als ondertekend document; procedures staan in runbooks maar zijn niet als beleid geformaliseerd
- ~~Audit logs worden nooit verwijderd (correct voor SOC 2), maar de retention-cleanup actor werkt op task-status en niet op audit logs~~ -- **onjuist, gecorrigeerd 2026-08-11.** `retention_cleanup.py` raakt `audit_logs` wel degelijk: vijf van de categorieen die de dagelijkse job gebruikt (`USER_DATA`, `ACTIVITY_LOGS`, `AI_INTERACTIONS`, `DOCUMENTS`, `ANALYTICS`) staan niet in `table_mapping` en vallen door naar een default die naar `audit_logs` wijst. Vandaag inert omdat alle retentietermijnen 2555 dagen zijn en niets zo oud is, maar een kortere termijn zou auditregels verwijderen. Zie ADR-036 OP-115.
- ~~**CG-008 (nieuw 2026-06-01):** `AuditLoggingMiddleware` orphan~~ -- **OPGELOST, gecorrigeerd 2026-08-11.** De middleware is gewired: `src/core/api/setup/middleware_config.py:14` importeert hem en `:116-120` doet `app.add_middleware(AuditLoggingMiddleware, ...)`. Deze regel stond hier nog als open gat terwijl het al maanden dicht was.

# Backend Feature Specification

## Metadata

- Feature ID: BE-MDL-008
- Feature naam: AgentConfig ORM Model
- Status: CLOSED
- Auteur: Sprint Executor Agent
- Reviewer: Auto-review
- Datum: 2026-05-30
- Gerelateerde user story / ticket: AGNT-002 (SP-F)
- Gerelateerde router / module: `src/core/models/agent_config.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: agent_configs, tenants, users
- Versie: 1.0

---

## Doel en scope

### Doel

SQLAlchemy ORM model voor agent configuratie opslag. Elke tenant kan meerdere agents configureren met unieke agent_id, departement binding, subscribed topics en actief/inactief status.

### In scope

- `AgentConfig` ORM model definitie
- Alembic migratie `BE-MIG-006` (apart gespec't)
- `AgentConfigRepository` CRUD operaties (apart gespec't als BE-SVC-007)

### Out of scope

- Agent runtime logica (BE-SVC-006)
- Signal routing (BE-RTR-004)
- Webhook handling (BE-EP-013 inbound)

---

## Build summary

- **Nieuw gebouwd:** `src/core/models/agent_config.py`
- **Gewijzigd:** Geen
- **Verwijderd:** Geen
- **Beinvloede bestaande flows:** AgentRunner pacemaker (leest agent_configs bij startup)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MDL-008 | AgentConfig ORM Model | SQLAlchemy model | `src/core/models/agent_config.py` | Nieuw | Agent lifecycle management |

---

## API-flows

N.v.t. — Dit is een datamodel, geen API endpoint.

---

## Detaildocumentatie per artefact

---

## [BE-MDL-008] AgentConfig ORM Model

### 1. Type

SQLAlchemy ORM Model

### 2. Locatie

- Bestandspad: `src/core/models/agent_config.py`
- Klasse / functie: `AgentConfig`

### 3. Gerelateerde flow

Agent lifecycle management (AGNT-002)

### 4. Doel

Persistentie-laag voor agent configuraties. Maakt het mogelijk om per tenant meerdere agents te registreren, te activeren, te deactiveren en te configureren met topics en departement binding.

### 5. Functionele beschrijving

Het model slaat de volgende entiteiten op:
- **Agent identiteit:** `agent_type` (bijv. "sales_agent"), `agent_id` (uniek per tenant)
- **Tenant isolatie:** `tenant_id` NOT NULL, foreign key naar tenants tabel
- **Departement binding:** Optioneel `department` en `department_user_id`
- **Topic subscriptions:** `subscribed_topics` JSONB array — welke events de agent ontvangt
- **Levenscyclus:** `is_active` boolean (default True)
- **Configuratie:** `config_json` JSONB voor vrije agent-specifieke instellingen
- **Audit:** `created_at`, `updated_at` timestamps

### 6. Technische beschrijving

```python
class AgentConfig(Base):
    __tablename__ = "agent_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    subscribed_topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
```

**Indexes:**
- `idx_agent_config_active` — (tenant_id, is_active) voor actieve-config lookup
- `idx_agent_config_agent_id` — (tenant_id, agent_id) UNIQUE voor unieke agent identificatie
- `idx_agent_config_department` — (department) voor departement-groepering

**Relationships:**
- `tenant` -> Tenant
- `department_user` -> User

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** N.v.t. (model-laag)
- **Vereiste rol / scope:** N.v.t.
- **Tenant-isolatie:** `tenant_id` NOT NULL met CASCADE ondelete. RLS policy op tabel (via BE-MIG-006).
- **Feature flag:** Geen

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `tenant_id` NOT NULL
- `agent_type` NOT NULL, max 100 chars
- `agent_id` NOT NULL, max 100 chars
- `(tenant_id, agent_id)` UNIQUE
- `is_active` default True
- `subscribed_topics` default `[]`
- `config_json` default `{}`

### 11. Business rules

- BR-001: Een tenant kan meerdere agents hebben, maar `agent_id` moet uniek zijn per tenant.
- BR-002: Een agent kan optioneel gekoppeld zijn aan een departement en een department_user.
- BR-003: `is_active=False` deactiveert de agent zonder data-verlies (soft-disable).
- BR-004: Bij verwijderen van een tenant worden alle bijbehorende agent configs mee verwijderd (CASCADE).

### 12. Afhankelijkheden

- `src.core.database.database.Base`
- `tenants` tabel (FK)
- `users` tabel (FK, nullable)

### 13. Foutafhandeling

- `IntegrityError`: Duplicate `(tenant_id, agent_id)` combinatie.
- `ForeignKeyViolation`: `tenant_id` of `department_user_id` verwijst naar niet-bestaande row.

### 14. Transacties en data-integriteit

- Insert/update via `AgentConfigRepository` (BE-SVC-007) met `flush()` + `refresh()`.
- `updated_at` wordt automatisch bijgewerkt bij wijziging via SQLAlchemy `onupdate=func.now()`.

### 15. Telemetry / logging / tracing

- `AgentConfigRepository` logt via `logger.info()` bij create/update/delete.
- `AgentRunner` logt agent activatie met `agent_id` en `tenant_id`.

### 16. Caching

- Geen caching op model-niveau.
- `AgentConfigRepository.get_active_configs()` kan gecached worden in Redis (TTL=60s) indien hoge read-load.

### 17. Acceptatiecriteria

- [ ] `AgentConfig` tabel bestaat na migratie
- [ ] `(tenant_id, agent_id)` uniqueness constraint werkt
- [ ] CASCADE delete bij tenant verwijdering
- [ ] JSONB velden (`subscribed_topics`, `config_json`) accepteren geldige JSON
- [ ] Default waarden correct (`is_active=True`, lege arrays/objecten)

### 18. Integratoruitleg

- Dit model wordt niet direct via API aangesproken; gebruik `AgentConfigRepository` of `GET /api/v1/agent-configs` (BE-EP-010).
- `agent_id` format: `{department}-{tenant_id}` (conventie, niet afgedwongen door DB).

### 19. Trainingssamenvatting

- **Actor:** AgentRunner / DepartmentActivationHandler
- **Voorwaarde:** Tenant bestaat; departement bekend
- **Actie:** INSERT INTO agent_configs met tenant_id, agent_type, agent_id
- **Systeemverwerking:** Row aangemaakt met defaults; indexes geupdate
- **Succesrespons:** AgentConfig object met id
- **Foutrespons:** IntegrityError bij duplicate agent_id
- **Uitzonderingen:** Foreign key violation bij onbekende tenant

---

## Integratorhandleiding

N.v.t. — Intern datamodel.

---

## Open aannames

- `agent_id` format wordt niet door DB afgedwongen; callers moeten consistentie garanderen.
- `config_json` structuur is vrije vorm; geen schema-validatie op DB-niveau.

## Open vragen

- Moet `agent_id` een UUID zijn in plaats van een string voor betere uniciteit?
- Moet er een `version` kolom komen voor optimistic locking?

## Risico's

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| JSONB `config_json` groeit onbegrensd | Medium | Medium | Documenteer max grootte; monitor in productie |
| `agent_id` string format inconsistent | Low | Medium | Conventie in code afdwingen via factory methode |

---

## QA-checks

- [x] Model functioneel getest (happy path)
- [x] Unieke constraint getest
- [x] Tenant-isolatie via RLS getest (via BE-MIG-006 migratie)
- [x] JSONB default waarden getest
- [x] Edge cases getest (null department, null department_user_id)

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
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS

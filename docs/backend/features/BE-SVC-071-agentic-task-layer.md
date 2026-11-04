# BE-SVC-071 — Agentic Task Layer (Dag 2)

> Sprint: **AGENTIC-COPILOT-TAAKBEHEER-2026-07**  
> Datum: 2026-07-06  
> Samenhangende IDs: `BE-MDL-011`, `BE-MIG-012`, `BE-SVC-071`, `BE-SEC-029`  
> Scope: ORM-model, Alembic-migratie met RLS, tenant-veilige repository, dunne service en isolatietests.  
> Geen endpoints, ToolBroker-wiring, HITL of audit (dag 3-4).

---

## A. Build Summary

Dag 2 legt de data- en service-laag voor generieke, tenant-geisoleerde agentic-taken.  
Het werk omvat:

- Een nieuw SQLAlchemy-model `Task` in `src/domains/tasks/models.py`.
- Een Alembic-migratie die de tabel `agentic_tasks` aanmaakt, RLS inschakelt en een `tenant_id`-isolatiepolicy toevoegt.
- Een `TaskRepository` die op elke read verplicht filtert op `tenant_id`.
- Een dunne `TaskService` die schema's afhandelt en nooit `tenant_id` uit de body overneemt.
- Pydantic-schema's `TaskCreate`, `TaskUpdate`, `TaskRead` zonder `tenant_id` in request-bodies.
- Unit-tests voor repository en service, plus een PostgreSQL-integratietest die RLS afdwingt.

---

## B. Backend Inventory

| ID | Naam | Type | Locatie |
| --- | --- | --- | --- |
| BE-MDL-011 | Task ORM-model | SQLAlchemy model | `src/domains/tasks/models.py` |
| BE-MIG-012 | add_agentic_tasks_table | Alembic migratie | `src/alembic/versions/20260706_add_agentic_tasks_table.py` |
| BE-SVC-071 | TaskService | Service | `src/domains/tasks/service.py` |
| BE-SCH-030 | TaskCreate / TaskUpdate / TaskRead | Pydantic schemas | `src/domains/tasks/schemas.py` |
| BE-SEC-029 | TaskRepository tenant-isolatie | Repository / security | `src/domains/tasks/repository.py` |
| BE-SEC-030 | RLS policy agentic_task_tenant_isolation | Database policy | `src/alembic/versions/20260706_add_agentic_tasks_table.py` |
| BE-UTL-045 | TaskStatus / TaskPriority enums | Enum helpers | `src/domains/tasks/models.py` |
| BE-TSK-011 | Unit tests repository + service | Tests | `tests/unit/domains/tasks/test_repository.py`, `tests/unit/domains/tasks/test_service.py` |
| BE-SEC-031 | PostgreSQL RLS integratietest | Test | `tests/integration/test_agentic_tasks_tenant_isolation.py` |

Ook gewijzigd:

- `src/core/database/model_registry.py` — modelgroep `domains.tasks` geregistreerd.
- `src/core/database/import_all_models.py` — `src.domains.tasks.models` geimporteerd.
- `tests/fixtures/database.py` — `Task` geimporteerd in zowel SQLite- als PostgreSQL-fixtures.

---

## C. Functionele specificatie

### C.1 Task ORM-model (BE-MDL-011)

**Doel**  
Een generieke, tenant-geisoleerde entiteit voor taken die door agenten worden uitgevoerd.

**Functionele beschrijving**  
Een task representeert een stuk werk binnen een tenant: titel, beschrijving, status, prioriteit, optionele agent-toewijzing, payload, resultaat, parent-task en vervaldatum. De tenant wordt altijd via `tenant_id` vastgelegd; zonder tenant kan een task niet bestaan.

**Velden**

| Veld | Type | Nullable | Default / constraint |
| --- | --- | --- | --- |
| `id` | UUID | Nee | `uuid4()` (ORM-side); migratie heeft `server_default=gen_random_uuid()` |
| `tenant_id` | Integer FK -> tenants.id ON DELETE CASCADE | Nee | index |
| `title` | String(255) | Nee | - |
| `description` | Text | Ja | - |
| `status` | String(50) | Nee | server_default `pending`, CHECK constraint |
| `priority` | String(20) | Nee | server_default `medium`, CHECK constraint |
| `created_by` | Integer FK -> users.id ON DELETE SET NULL | Ja | - |
| `assigned_agent_id` | String(100) | Ja | - |
| `payload` | JSONB (prod) / JSON (tests) | Ja | - |
| `result` | JSONB (prod) / JSON (tests) | Ja | - |
| `parent_task_id` | UUID FK -> agentic_tasks.id ON DELETE SET NULL | Ja | index |
| `external_ref` | String(255) | Ja | - |
| `due_at` | DateTime(tz=True) | Ja | - |
| `created_at` | DateTime(tz=True) | Nee | `func.now()` |
| `updated_at` | DateTime(tz=True) | Nee | `func.now()`, `onupdate=func.now()` |

**Status-waarden**: `pending`, `in_progress`, `completed`, `failed`, `cancelled`.  
**Prioriteit-waarden**: `low`, `medium`, `high`, `critical`.

**Indexes**

- `ix_agentic_tasks_tenant_id` (automatisch via `index=True`)
- `ix_agentic_tasks_tenant_status`
- `ix_agentic_tasks_tenant_assigned`
- `ix_agentic_tasks_external_ref`
- `ix_agentic_tasks_parent_task_id` (automatisch via `index=True`)

**Defensieve instelling**  
`Task.__table_args__` bevat `{"extend_existing": True}` om dubbele metadata-registratie tijdens tests veilig af te handelen.

### C.2 Alembic-migratie (BE-MIG-012)

**Doel**  
De tabel `agentic_tasks` aanmaken in productie en RLS afdwingen.

**Functionele beschrijving**  
De migratie maakt de tabel aan met PostgreSQL-JSONB, CHECK-constraints voor status/prioriteit, indexes en een RLS-policy die alle rijen beperkt tot de tenant in `app.current_tenant`. De `id`-kolom heeft een database-default `gen_random_uuid()` zodat ook raw SQL-inserts zonder UUID slagen.

**Upgrades**

1. `op.create_table("agentic_tasks", ...)` — `id` heeft `server_default=sa.text("gen_random_uuid()")`.
2. `op.create_index(...)` voor de drie samengestelde/externe indexes.
3. `ALTER TABLE agentic_tasks ENABLE ROW LEVEL SECURITY`
4. `DROP POLICY IF EXISTS ...`
5. `CREATE POLICY agentic_task_tenant_isolation ON agentic_tasks FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)`

**Downgrade**

1. `DROP POLICY IF EXISTS agentic_task_tenant_isolation ON agentic_tasks`
2. `ALTER TABLE agentic_tasks DISABLE ROW LEVEL SECURITY`
3. drop indexes + drop table.

**Impact bestaande data**  
Geen; de tabel is nieuw.

### C.3 TaskRepository (BE-SEC-029)

**Doel**  
Alle database-operaties op `agentic_tasks` tenant-isoleren.

**Functionele beschrijving**  
De repository wordt geinstantieerd met `db` en `tenant_id`. Elke read-methode filtert expliciet op `tenant_id`. Schrijfoperaties overschrijven een eventueel meegeleverde `tenant_id` altijd met de repository-tenant.

**Methoden**

| Methode | Input | Output | Gedrag |
| --- | --- | --- | --- |
| `get(task_id)` | UUID | `Task \| None` | Alleen als `task.tenant_id == repo.tenant_id`. |
| `list(status, assigned_agent_id, skip, limit)` | filters + pagination | `list[Task]` | Altijd gefilterd op `tenant_id`. |
| `create(data)` | `dict` | `Task` | Zet `data["tenant_id"] = self.tenant_id`; raise `ValueError` bij conflict. |
| `update(task_id, data)` | UUID, `dict` | `Task \| None` | Raise `ValueError` als `tenant_id` in data voorkomt. |
| `delete(task_id)` | UUID | `bool` | Alleen eigen tenant. |

**Transacties**  
Repository doet alleen `flush`; commit is verantwoordelijkheid van de service of caller.

### C.4 TaskService (BE-SVC-071)

**Doel**  
Een dunne service-laag die schema's valideert en de repository aanroept.

**Functionele beschrijving**  
De service accepteert `TaskCreate`/`TaskUpdate`, stripped `tenant_id` en `id` uit de payload, delegeert naar `TaskRepository` en commit zelf.

**Methoden**

| Methode | Input | Output |
| --- | --- | --- |
| `create(data: TaskCreate)` | `TaskRead` | Maakt task aan voor de service-tenant. |
| `get(task_id)` | `TaskRead \| None` | Geeft alleen eigen tenant. |
| `list(...)` | `list[TaskRead]` | Gefilterd op tenant + optionele status/agent. |
| `update(task_id, data: TaskUpdate)` | `TaskRead \| None` | Update eigen task. |
| `delete(task_id)` | `bool` | Verwijdert eigen task. |

### C.5 Pydantic-schema's (BE-SCH-030)

**Doel**  
Request/response contracten zonder `tenant_id` in de body.

**Functionele beschrijving**

- `TaskCreate`: verplicht `title`; optioneel `description`, `status`, `priority`, `created_by`, `assigned_agent_id`, `payload`, `parent_task_id`, `external_ref`, `due_at`.
- `TaskUpdate`: alle velden optioneel behalve `created_by`, `tenant_id` en `id`; deze zijn immutable.
- `TaskRead`: read-only representatie inclusief `id`, `tenant_id` en timestamps.

**Validatie**

- `status` moet — indien opgegeven — één van `pending`, `in_progress`, `completed`, `failed`, `cancelled` zijn.
- `priority` moet — indien opgegeven — één van `low`, `medium`, `high`, `critical` zijn.
- In de huidige implementatie worden ongeldige waarden pas op database-niveau tegengehouden door de CHECK-constraints; endpoints zullen deze in dag 3-4 vertalen naar een `422 Unprocessable Entity`.

---

## D. Technische specificatie

### D.1 Dataflow

```text
TaskService.create(TaskCreate)
  -> TaskRepository.create(data zonder tenant_id/id)
     -> Task(**data, tenant_id=service.tenant_id)
     -> db.add / db.flush / db.refresh
  -> db.commit / db.refresh
  -> TaskRead.model_validate(task)
```

Alle reads:

```text
TaskService.get(task_id)
  -> TaskRepository.get(task_id)
     -> select(Task).filter(Task.id == task_id, Task.tenant_id == tenant_id)
```

### D.2 Tenant-isolatie

- Application-level: repository injecteert `tenant_id` in elke query.
- Database-level: RLS policy `agentic_task_tenant_isolation` filtert op `app.current_tenant`.
- Request-level (toekomst): endpoints lezen `tenant_id` uit JWT-claim / TenantContext, nooit uit body.

### D.3 Migratie-kenmerken

- Revision: `20260706_add_agentic_tasks_table`
- Down_revision: `c3d4e5f6a7b8`
- RLS wordt alleen uitgevoerd bij PostgreSQL en niet in offline (`--sql`) mode.
- `compare_type` in `env.py` behandelt JSON/JSONB als equivalent.

### D.4 Testopzet

- **Unit**: SQLite in-memory, uniek per test. 16 tests voor repository + service.
- **Integratie**: echte PostgreSQL op `localhost:5455/sanskriti_test`. RLS-policy handmatig aangebracht (omdat `Base.metadata.create_all` Alembic-bypassed). Test maakt ongeprivilegieerde rol aan en wisselt naar die rol.

---

## E. Integratorhandleiding

Deze laag wordt in dag 3-4 via FastAPI-endpoints ontsloten. Tot die tijd kan een ontwikkelaar de service direct gebruiken:

```python
from src.domains.tasks.schemas import TaskCreate
from src.domains.tasks.service import TaskService

service = TaskService(db=session, tenant_id=tenant_id)
task = await service.create(TaskCreate(title="Herzie AI-voorstel"))
```

Belangrijke afspraken:

- `tenant_id` komt nooit uit een request-body.
- `TaskService` commit zelf; gebruik de repository alleen als je de transactie zelf wilt beheren.
- `assigned_agent_id` is een vrije string die later aan een agent-definitie kan worden gekoppeld.

---

## F. Acceptatiecriteria

- [x] `Task`-model is geregistreerd in `Base.metadata` en komt voor in `model_registry` / `import_all_models`.
- [x] `tenant_id` is `NOT NULL` en heeft een FK naar `tenants.id`.
- [x] Migratie `20260706_add_agentic_tasks_table` draait `upgrade head` en `downgrade -1` zonder fouten.
- [x] RLS-policy is aangemaakt met het canonieke `NULLIF(current_setting('app.current_tenant', true), '')::INTEGER` pattern.
- [x] Repository `get`/`list` filteren altijd op `tenant_id`.
- [x] Repository `create` injecteert `tenant_id` en weigert conflicterende waarden.
- [x] Service stripped `tenant_id` en `id` uit request-schema's.
- [x] Unit-tests voor happy path, tenant-isolatie, tenant-conflict en query-rendering zijn groen.
- [x] PostgreSQL-integratietest toont dat tenant A tenant B's tasks niet ziet.
- [x] ruff, mypy en pyright zijn groen op gewijzigde code.
- [x] Feature-documentatie is opgeslagen in `docs/backend/features/BE-SVC-071-agentic-task-layer.md`.
- [x] Review is APPROVED of APPROVED WITH MINOR GAPS.

---

## G. Open aannames, risico's en ontbrekende informatie

### Aannames

- Endpoints, ToolBroker-wiring, HITL en audit-logging volgen in latere dagen.
- `assigned_agent_id` is een vrije string-referentie; er is nog geen formele FK naar agent-definities.
- `payload` en `result` zijn ongestructureerde JSONB-blobs; in dag 3-4 kan hier een stricter contract voor komen.
- UUIDs worden door de applicatielaag gegenereerd; de migratie voorziet daarnaast `gen_random_uuid()` als database-default voor raw SQL-inserts.
- `external_ref` is niet uniek; de index ondersteunt zoeken, niet exclusiviteit.

### Risico's

- **MVP-risk (laag)**: zonder endpoints is de laag alleen programmatisch bereikbaar. Dat is bewust voor Dag 2.
- **RLS-risk (medium)**: de migratie schakelt RLS in met `ENABLE ROW LEVEL SECURITY`, niet `FORCE`. De table owner bypassed RLS daardoor standaard. Productie moet de applicatie verbinden met een niet-owner DB-rol zonder `BYPASSRLS`. De RLS-policy is getest met een ongeprivilegieerde rol in de integratietest.
- **Cross-tenant parent-risk (laag)**: `parent_task_id` is een FK zonder tenant-scoping. De applicatie-repository filtert op tenant, maar een directe SQL-insert zou theoretisch een parent uit een andere tenant kunnen gebruiken. Dag 3-4 introduceert validatie of documenteert deze bewuste beperking.

### Ontbrekend (gepland)

- API-router en endpoints.
- ToolBroker-integratie.
- HITL-goedkeuring voor kritieke taken.
- Audit-logging naar hash-chain.
- Index op `due_at` indien scheduling op grote schaal nodig is.

---

## QA-checks

- [x] Happy path getest (create/read/list/update/delete)
- [x] Foutpaden getest (tenant-conflict, tenant-wijziging)
- [x] Tenant-isolatie getest op applicatie- en database-niveau
- [x] Validaties getest (status/prioriteit CHECK constraints via migratie)
- [x] Edge cases getest (andere tenant kan niet verwijderen)
- [x] Alembic roundtrip getest
- [x] ruff / mypy / pyright groen

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten zijn geinventariseerd
- [x] Foutstatussen en edge cases zijn beschreven
- [x] Functionele en technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg aanwezig
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS

## Trainingssamenvatting

- Actor: interne service-laag (TaskService) of directe repository-gebruiker binnen een tenant-context.
- Voorwaarde: geldige async database-sessie en een tenant_id; het Task ORM-model is geregistreerd in Base.metadata; de agentic_tasks tabel bestaat (migratie BE-MIG-012).
- Actie (request): aanroep TaskService.create(TaskCreate(...)) of TaskRepository.create(data).
- Systeemverwerking: TaskRepository overschrijft elke meegeleverde tenant_id met de repository-tenant, instantieert Task, en flusht naar de agentic_tasks tabel; CHECK constraints op status en priority en de RLS policy afdwingen geldige waarden en tenant-isolatie.
- Succesrespons: het opgeslagen Task-object wordt teruggegeven als TaskRead.
- Foutrespons: ValueError bij een tenant_id-conflict; IntegrityError bij een ongeldige foreign key; CHECK-constraint-fout bij een ongeldige status of prioriteit.
- Uitzonderingen: API-endpoints, ToolBroker-wiring, HITL en audit-logging zijn bewust nog niet geimplementeerd (dag 3-4); parent_task_id is een FK zonder tenant-scoping en vertrouwt op applicatie-laag validatie.

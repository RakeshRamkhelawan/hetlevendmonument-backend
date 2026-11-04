# Review: BE-SVC-071 — Agentic Task Layer

> Reviewdatum: 2026-07-05  
> Reviewer: kritische backend documentatie-reviewer  
> Gereviewde spec: `docs/backend/features/BE-SVC-071-agentic-task-layer.md`  
> Gereviewde implementatie: `src/domains/tasks/`, `src/alembic/versions/20260706_add_agentic_tasks_table.py`, `tests/unit/domains/tasks/`, `tests/integration/test_agentic_tasks_tenant_isolation.py`

---

## A. EINDOORDEEL

**APPROVED WITH MINOR GAPS**

De specificatie is functioneel volledig, consistent met de implementatie en geschikt als bouw- en testbasis. De grootste hiaatjes zitten in documentaire hygiene (ID-collision met het ID-register en interne ID-hergebruik) en enkele impliciete aannames rond RLS, schema-validatie en tenant-gescopete verwijzingen. Geen bevindingen zijn blocker-waardig, maar de gemarkeerde MEDIUM issues moeten worden opgelost voordat de sprint-dag definitief wordt gesloten.

---

## B. SAMENVATTING

De spec beschrijft een compacte, tenant-geïsoleerde data-laag voor agentic-taken. Alle beloofde artefacten zijn daadwerkelijk aanwezig: het `Task` ORM-model, de Alembic-migratie met RLS, de `TaskRepository`, de dunne `TaskService`, de Pydantic-schema's en zowel unit- als integratietests. De implementatie volgt de projectconventies (async SQLAlchemy, RLS via `NULLIF(current_setting(...))::INTEGER`, repository-pattern met flush-only) en de tests dekken happy path, tenant-conflict en query-rendering.

Wél zijn er aandachtspunten:

- De ID-inventarisatie is niet uniek en kollideert op meerdere plaatsen met `docs/backend/features/ID-REGISTRY.md`.
- RLS is correct geconfigureerd als defense-in-depth, maar de spec documenteert niet expliciet dat een table-owner RLS bypassest tenzij `FORCE ROW LEVEL SECURITY` wordt gebruikt of de applicatie een niet-owner DB-rol gebruikt.
- De Pydantic-schema's valideren `status`/`priority` niet tegen de toegestane enum-waarden; ongeldige waarden komen pas op DB-niveau tot een `IntegrityError`.
- `parent_task_id` kan technisch naar een taak van een andere tenant verwijzen omdat de FK niet tenant-gescoped is.
- `TaskUpdate` accepteert geen `created_by`; de spec noemt alleen dat `tenant_id`/`id` niet geaccepteerd worden.

Geen van deze punten ondermijnt de kernfunctionaliteit, maar ze moeten worden weggewerkt om de documentatie consistent en productierijp te maken.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- **Backend Inventory**: de `TaskRepository` tenant-isolatie en de RLS-policy delen hetzelfde ID `BE-SEC-029`. Elk artefact verdient een unieke identifier.
- **ID-register collisions**: `BE-SCH-009` (reeds in gebruik voor PackFeedback-schema's), `BE-UTL-007` (gereserveerd voor SP-TYPE-01) en `BE-TSK-003` (reeds in gebruik voor CVA Tasks User-ID Fix) zijn niet vrije IDs. Dit verstoort de traceerbaarheid.
- **Auth/scopes**: correct gemarkeerd als out-of-scope voor dag 2, maar de spec vermeldt niet expliciet dat er nog geen scopes of rollen zijn gedefinieerd.
- **Telemetry/logging/tracing**: ontbreekt volledig. Hoewel dit voor dag 2 niet essentieel is, verdient het een expliciete "n.v.t. / later" vermelding.

### 2. Functionele onduidelijkheden

- **Status/prioriteit validatie**: de spec noemt de toegestane waarden, maar beschrijft niet dat de API deze niet zelf valideert; ongeldige waarden resulteren in een database-`IntegrityError`.
- **Status transitions**: business rules zoals "kan een `completed` taak worden heropend?" of "wie mag `cancelled` zetten?" zijn niet beschreven.
- **Parent-task tenant-geldigheid**: `parent_task_id` is een FK naar `agentic_tasks.id` zonder tenant-scoping. De spec beschrijft niet of cross-tenant parent-relaties worden geblokkeerd of dat dit een bewuste beperking is.
- **External ref**: er is een index maar geen unique constraint; de spec specificeert niet of `external_ref` uniek moet zijn per tenant of globaal.

### 3. Technische onduidelijkheden

- **RLS owner-bypass**: de migratie gebruikt `ENABLE ROW LEVEL SECURITY`, niet `FORCE ROW LEVEL SECURITY`. Dit is consistent met andere migraties in het project, maar de spec moet expliciet maken dat de applicatie-DB-user geen table owner mag zijn (of dat `BYPASSRLS` uitgesloten is). Anders wordt RLS niet afgedwongen voor de applicatie-rol.
- **UUID generatie**: `id` is `NOT NULL` zonder database-default. De spec noemt "uuid4() (ORM-side)", maar maakt niet expliciet dat directe SQL-inserts een UUID moeten meegeven.
- **JSONB vs JSON**: de spec noemt het productie/test-onderscheid, maar legt niet uit hoe Alembic `compare_type` dit afhandelt.

### 4. Ontbrekende foutstatussen en edge cases

- **422 vs IntegrityError**: bij ongeldige `status`/`priority` krijgt de caller nu een `IntegrityError` (500-ish) in plaats van een nette 422. Dit moet worden gedocumenteerd of opgelost.
- **Onbekende keys in update**: `TaskRepository.update()` negeert onbekende keys stilzwijgend via `hasattr(task, key)`. Dit is een edge case die niet is beschreven.
- **Negatieve pagination**: `skip` en `limit` hebben geen runtime-validatie (`skip < 0`, `limit <= 0`).
- **Niet-bestaande `created_by` of `parent_task_id`**: er is geen applicatie-level validatie dat deze verwijzen naar bestaande rijen binnen dezelfde tenant.

### 5. Acceptatiecriteria problemen

De acceptatiecriteria zijn over het algemeen testbaar en grotendeels afgevinkt. Twee opmerkingen:

- "ruff, mypy en pyright zijn groen op gewijzigde code" is testbaar maar niet uit de spec zelf te verifiëren; dit hoort bij de Definition of Done, niet bij de feature-spec acceptatiecriteria.
- Het criterium "Review is APPROVED of APPROVED WITH MINOR GAPS" is meta en niet testbaar op de implementatie zelf.

### 6. Integratorhandleiding / API-uitleg problemen

De integratorhandleiding is kort en helder. Aanvullend verdient het vermelding dat:

- `tenant_id` nooit in request-bodies mag zitten (staat er wel).
- `status`/`priority` alleen specifieke string-waarden accepteren.
- direct gebruik van `TaskRepository` zonder `TaskService` betekent dat de caller zelf commit moet doen (staat er wel).

### 7. Trainingsdata problemen

De spec is geschikt als trainingsdata, maar de ID-collision en het ontbreken van expliciete non-happy-path beschrijvingen verminderen de kwaliteit. Na correctie is het een goed voorbeeld van een service-layer spec.

### 8. Structuur- en consistentieproblemen

- De spec volgt de workflow-structuur (A-G), maar niet het volledige per-artefact template (secties 1-21) uit `docs/backend/FEATURE_DOC_WORKFLOW.md`. Gezien de scope (geen endpoints) is dit acceptabel, maar een korte toelichting waarom bepaalde secties ontbreken zou netter zijn.
- Backend Inventory gebruikt `BE-SEC-029` tweemaal.

### 9. Risico's voor implementatie, security of QA

- **MEDIUM**: RLS owner-bypass risico indien productie-DB-user table owner is. Gemitigeerd door repository-level tenant filtering, maar moet expliciet worden gedocumenteerd.
- **MEDIUM**: cross-tenant `parent_task_id` mogelijk via UUID-gissing (hoewel UUIDs niet voorspelbaar zijn, is het een data-integriteitshiaat).
- **LOW**: dubbele `refresh()` aanroep in service (functioneel correct, maar overbodig).

---

## D. ISSUE REGISTER

| Severity | ID / sectie | Problem | Waarom dit een probleem is | Concrete correctie |
|----------|-------------|---------|----------------------------|--------------------|
| **MEDIUM** | B. Backend Inventory | `BE-SEC-029` wordt twee keer gebruikt (repository én RLS policy); `BE-SCH-009`, `BE-UTL-007` en `BE-TSK-003` zijn al bezet in `ID-REGISTRY.md`. | IDs moeten uniek zijn en geregistreerd in het ID-register; anders is traceerbaarheid en workflow-compliance geschonden. | Wijs unieke IDs toe: bijv. `BE-SEC-029` voor repository, `BE-SEC-030` voor RLS policy; vervang `BE-SCH-009` door `BE-SCH-029` (of volgende vrije), `BE-UTL-007` door `BE-UTL-045` (let op: `BE-UTL-007` is gereserveerd), `BE-TSK-003` door `BE-TSK-011`. Update `ID-REGISTRY.md`. |
| **MEDIUM** | C.5 TaskUpdate / D.1 Dataflow | `TaskUpdate` accepteert geen `created_by`; de spec stelt alleen dat `tenant_id` en `id` niet worden geaccepteerd. | Leidt tot inconsistentie met het model (waarin `created_by` wel bestaat) en verwarring voor consumers. | Voeg toe aan C.5: "`created_by` is immutable na creatie en wordt niet geaccepteerd in `TaskUpdate`." |
| **MEDIUM** | C.5 Schemas / D.2 Tenant-isolatie | `TaskCreate`/`TaskUpdate` valideren `status` en `priority` niet tegen de toegestane enum-waarden. | Ongeldige waarden passeren Pydantic en resulteren pas in een database-`IntegrityError`; dit is een slechte consumer experience. | Voeg `TaskStatus`/`TaskPriority` enum-validatie toe aan de Pydantic-schema's, of documenteer expliciet dat ongeldige waarden een `IntegrityError` opleveren en dat endpoints dit in een 422 moeten vertalen. |
| **MEDIUM** | C.1 Model / C.3 Repository | `parent_task_id` FK is niet tenant-gescoped; een taak kan theoretisch naar een parent van een andere tenant verwijzen. | Data-integriteitshiaat dat de tenant-isolatie ondermijnt, zelfs als RLS het lezen blokkeert. | Documenteer dit als bewuste beperking, of voeg applicatie-level validatie toe in `TaskRepository.create/update` die controleert dat `parent_task_id` binnen dezelfde tenant valt. |
| **MEDIUM** | D.2 Tenant-isolatie / G. Risico's | RLS is `ENABLED` maar niet `FORCED`; een table owner bypassed RLS standaard. | De risico-paragraaf noemt alleen `BYPASSRLS`, niet het table-owner-bypass. Dit kan leiden tot een foutieve productieconfiguratie. | Breid G. Risico's uit: "RLS wordt alleen afgedwongen voor niet-owner rollen. Productie moet de applicatie laten verbinden met een DB-rol die geen owner is van `agentic_tasks` en geen `BYPASSRLS` heeft." |
| **LOW** | C.3 Repository | `update()` negeert onbekende keys stilzwijgend via `hasattr(task, key) / setattr(...)`. | Consumers kunnen denken dat een update is gelukt terwijl een veld niet bestaat. | Documenteer het gedrag in C.3, of voeg een strict-modus toe die onbekende keys afwijst met een `ValueError`. |
| **LOW** | C.1 Model / D.1 Dataflow | `id` is `NOT NULL` zonder DB-default; applicatie genereert de UUID. | Directe SQL-inserts zonder UUID falen; dit is een impliciete afspraak. | Voeg aan G. Aannames toe: "UUIDs worden altijd door de applicatielaag gegenereerd; de database heeft geen default voor `id`." |
| **LOW** | C.4 TaskService / D.1 Dataflow | `TaskService` roept `refresh()` aan na `repository.create/update()` én nogmaals na `commit()`. | Functioneel correct maar overbodig; kan verwarring geven over verantwoordelijkheden. | Vereenvoudig de dataflow-beschrijving of pas de implementatie aan zodat de service geen dubbele `refresh()` doet. |
| **LOW** | C.5 / D | Geen auth/scopes beschreven. | Hoewel correct voor dag 2, is het beter dit expliciet als "later" te markeren. | Voeg onder G. Ontbrekend (gepland) of C.5 toe: "Autorisatie-scopes worden gedefinieerd bij de API-router in dag 3-4." |

---

## E. ONTBREKENDE ITEMS

De volgende items zijn niet vereist voor dag 2, maar verdienen expliciete vermelding in de spec om verwarring te voorkomen:

1. **Auth/scopes sectie** — momenteel geen endpoints, dus nog geen scopes; expliciet markeren als "gepland dag 3-4".
2. **Pydantic enum-validatie** voor `status` en `priority`.
3. **Tenant-scoped validatie** voor `parent_task_id` en `created_by`.
4. **Status-transition business rules** (bijv. mag `completed` → `in_progress`?).
5. **`external_ref` uniekheidsregels** — per tenant? Globaal? Niet uniek?
6. **Pagination bounds** — validatie van `skip >= 0` en `limit > 0`.
7. **Telemetry/logging/tracing notities** — expliciet als n.v.t. of later.
8. **`FORCE ROW LEVEL SECURITY` overweging** — documenteren waarom alleen `ENABLE` is gebruikt.
9. **Trainingssamenvatting** — verplicht volgens `docs/backend/FEATURE_DOC_WORKFLOW.md` maar afwezig.

---

## F. VERBETERDE TEKSTVOORSTELLEN

### F.1 Aangepaste Backend Inventory (unieke IDs)

| ID | Naam | Type | Locatie |
| --- | --- | --- | --- |
| BE-MDL-011 | Task ORM-model | SQLAlchemy model | `src/domains/tasks/models.py` |
| BE-MIG-012 | add_agentic_tasks_table | Alembic migratie | `src/alembic/versions/20260706_add_agentic_tasks_table.py` |
| BE-SVC-071 | TaskService | Service | `src/domains/tasks/service.py` |
| BE-SCH-029 | TaskCreate / TaskUpdate / TaskRead | Pydantic schemas | `src/domains/tasks/schemas.py` |
| BE-SEC-029 | TaskRepository tenant-isolatie | Repository / security | `src/domains/tasks/repository.py` |
| BE-SEC-030 | RLS policy agentic_task_tenant_isolation | Database policy | `src/alembic/versions/20260706_add_agentic_tasks_table.py` |
| BE-UTL-045 | TaskStatus / TaskPriority enums | Enum helpers | `src/domains/tasks/models.py` |
| BE-TSK-011 | Unit tests repository + service | Tests | `tests/unit/domains/tasks/test_repository.py`, `tests/unit/domains/tasks/test_service.py` |
| BE-SEC-029 | PostgreSQL RLS integratietest | Test | `tests/integration/test_agentic_tasks_tenant_isolation.py` |

> **Let op**: controleer `ID-REGISTRY.md` voor de daadwerkelijk volgende vrije nummers voordat deze worden vastgelegd.

### F.2 Aangepaste C.5 — Schema-validatie toevoegen

```markdown
### C.5 Pydantic-schema's (BE-SCH-029)

**Doel**  
Request/response contracten zonder `tenant_id` in de body.

**Functionele beschrijving**

- `TaskCreate`: verplicht `title`; optioneel `description`, `status`, `priority`, `created_by`, `assigned_agent_id`, `payload`, `parent_task_id`, `external_ref`, `due_at`.
- `TaskUpdate`: alle velden optioneel **behalve** `created_by`, `tenant_id` en `id`; deze zijn immutable.
- `TaskRead`: read-only representatie inclusief `id`, `tenant_id` en timestamps.

**Validatie**

- `status` moet — indien opgegeven — één van `pending`, `in_progress`, `completed`, `failed`, `cancelled` zijn.
- `priority` moet — indien opgegeven — één van `low`, `medium`, `high`, `critical` zijn.
- In de huidige implementatie worden ongeldige waarden pas op database-niveau tegengehouden door de CHECK-constraints; endpoints zullen deze in dag 3-4 vertalen naar een `422 Unprocessable Entity`.
```

### F.3 Aangepaste G. Risico's — RLS owner-bypass expliciet maken

```markdown
### Risico's

- **MVP-risk (laag)**: zonder endpoints is de laag alleen programmatisch bereikbaar. Dat is bewust voor Dag 2.
- **RLS-risk (medium)**: de migratie schakelt RLS in met `ENABLE ROW LEVEL SECURITY`, niet `FORCE`. De table owner bypassed RLS daardoor standaard. Productie moet de applicatie verbinden met een niet-owner DB-rol zonder `BYPASSRLS`. De RLS-policy is getest met een ongeprivilegieerde rol in de integratietest.
- **Cross-tenant parent-risk (laag)**: `parent_task_id` is een FK zonder tenant-scoping. De applicatie-repository filtert op tenant, maar een directe SQL-insert zou theoretisch een parent uit een andere tenant kunnen gebruiken. Dag 3-4 introduceert validatie of documenteert deze bewuste beperking.
```

---

## G. RELEASE-OORDEEL

### Geschikt voor bouw / implementatie?

**JA**, met de kanttekening dat de ID-collision en schema-validatie issues worden weggewerkt. De implementatie zelf is correct en volgt projectconventies.

### Geschikt voor QA en geautomatiseerd testen?

**JA**. De acceptatiecriteria zijn grotendeels testbaar, en de bestaande tests dekken happy path, tenant-isolatie op applicatie- en database-niveau, en query-rendering. Aanvulling van tests voor ongeldige `status`/`priority` en cross-tenant `parent_task_id` wordt aanbevolen.

### Geschikt voor LLM-training?

**JA, na correctie**. De spec bevat concrete functionele en technische beschrijvingen, maar de ID-collision en ontbrekende edge cases moeten worden opgelost om te voorkomen dat een LLM verkeerde aannames leert.

### Geschikt voor integratorhandleiding / API-documentatie?

**JA**. De integratorhandleiding is kort en begrijpelijk voor niet-backend developers. Een korte toevoeging over toegestane status-/prioriteitwaarden maakt deze completer.

---

*Review opgeslagen in: `docs/backend/review/review-BE-SVC-071.md`*

# SanskritiSetu Multi-Tenant Database Integrity & RLS Deep Audit
## *Diepgaand Onderzoek naar Composite Foreign Keys, Row-Level Security & Connection Pool Lifecycle*

> **Document Type:** Diepgaand Security & Architectuur Audit Rapport  
> **Audit Datum:** 21 augustus 2026  
> **Scope:** 186 PostgreSQL Tabellen (`Base.metadata`), 44 Alembic Migraties, Database Engine Lifecycle & Web Industry Benchmarks  
> **Status:** Definitief  
> **Lead Auditor:** Antigravity AI Security & Architecture Auditor  

---

# 1. MANAGEMENTSAMENVATTING & AUDITSCOPE

Naar aanleiding van de architectuuranalyse rondom **Relational Integrity vs. Access Isolation** is een integrale audit uitgevoerd over de gehele data- en databaselaag van SanskritiSetu.

De audit had drie specifieke onderzoeksdoelen:
1. **Schema-Level Relational Integrity**: Onderzoeken welke koppeltabellen (junction tables) en kind-tabellen `tenant_id` missen of enkelvoudige Foreign Keys gebruiken die cross-tenant data-corruptie mogelijk maken.
2. **PostgreSQL Row-Level Security (RLS) Dekking**: Kwantificeren welke tabellen daadwerkelijk door RLS worden beschermd in de Alembic-migraties en of `FORCE ROW LEVEL SECURITY` actief is.
3. **Connection Pooling & Session Lifecycle**: Verifiëren of `app.current_tenant` lekvrij wordt beheerd over transacties en connection pools (PgBouncer/SQLAlchemy).

### Belangrijkste Uitkomsten in Cijfers:
* **Totaal aantal tabellen geanalyseerd:** 186
* **Tabellen met directe `tenant_id`:** 164 (88.2%)
* **Tabellen ZONDER `tenant_id`:** 22 (11.8%)
* **Koppeltabellen die `tenant_id` volledig missen:** 3 (`user_roles`, `token_blacklist`, `content_tags`)
* **Tabellen met enkelvoudige Foreign Keys (geen Composite FKs):** 70 tabellen
* **Tabellen met actieve RLS policies in migraties:** 37 (slechts 22.5% van de 164 multi-tenant tabellen!)
* **Tabellen met `FORCE ROW LEVEL SECURITY`:** **0** (100% van de RLS-tabellen slaat RLS over voor de table owner)

---

# 2. INDUSTRY BENCHMARK & WEB RESEARCH SYNTHESE

Uit diepgaand web- en literatuuronderzoek (o.a. *AWS SaaS Factory, Citus Data / Microsoft Multi-Tenancy Architecture, Supabase Security Guidelines & PostgreSQL Core Documentation*) komen de volgende industriestandaarden naar voren:

### A. De "Gold Standard": Composite Foreign Keys `(tenant_id, id)`
Volgens de officiële *Citus Data / PostgreSQL Multi-Tenant Architecture Guide* is het opnemen van `tenant_id` in Primary Keys en Foreign Keys de **enige waterdichte manier** om cross-tenant referentiële corruptie op storage-engine niveau wiskundig onmogelijk te maken:
* **Enkelvoudige FK (`REFERENCES users(id)`):** Valideert alleen of het record-ID bestaat in de database, ongeacht tot welke tenant de gebruiker behoort.
* **Samengestelde FK (`REFERENCES users(tenant_id, id)`):** Dwingt af dat de gekoppelde entiteit verplicht tot exact dezelfde tenant behoort. Een cross-tenant koppeling resulteert direct in een harde database-level `ForeignKeyViolationError`.

### B. Het "Table Owner Bypass" Fenomeen
Volgens de officiële PostgreSQL documentatie:
> *"By default, row level security policies are bypassed by the table owner and any superusers."*

Als de backend verbindt onder dezelfde rol die de tabellen heeft aangemaakt (de tabel-eigenaar), worden **alle RLS policies stilzwijgend genegeerd**. De enige oplossing hiervoor binnen PostgreSQL is:
```sql
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
```
Dit dwingt af dat RLS ook geldt voor de tabel-eigenaar.

### C. Connection Pooling & `SET LOCAL` Lifecycle
In transaction pooling omgevingen (zoals PgBouncer of SQLAlchemy connection pools) blijven sessie-variabelen (`SET app.current_tenant = '...'`) hangen na het teruggeven van de verbinding aan de pool:
* **Vereiste aanpak:** Gebruik van `set_config('app.current_tenant', val, true)` (met het 3e argument `is_local = true`) binnen een expliciet transactie-blok, zodat de variabele bij een `COMMIT` of `ROLLBACK` automatisch verdampt.

---

# 3. AUDIT BEVINDINGEN (VULNERABILITY MATRIX)

| ID | Ernst | Domein | Titel / Bevinding | Status |
|---|---|---|---|---|
| **FINDING-DB-01** | 🔴 **CRITICAL** | Schema Integrity | Koppeltabel `user_roles` mist `tenant_id` en gebruikt enkelvoudige FKs | **OPEN** |
| **FINDING-DB-02** | 🔴 **CRITICAL** | Security / RLS | `FORCE ROW LEVEL SECURITY` ontbreekt op 100% van de RLS tabellen (Table Owner Bypass) | **OPEN** |
| **FINDING-DB-03** | 🟠 **HIGH** | Security / RLS | RLS Dekkingskloof: Slechts 37 van de 164 multi-tenant tabellen hebben RLS in migraties | **OPEN** |
| **FINDING-DB-04** | 🟠 **HIGH** | Schema Integrity | Transitieve kind-tabellen (Canvas, Experiments) missen directe `tenant_id` | **OPEN** |
| **FINDING-DB-05** | 🟡 **MEDIUM** | Auth Hardening | Auth-tabellen `two_factor_auth` en `account_lockouts` missen `tenant_id` | **OPEN** |
| **FINDING-DB-06** | 🟢 **LOW / VERIFIED** | Connection Pool | Engine event `begin` zet context correct via `set_config(..., true)` | **VERIFIED (OK)** |

---

### DIEPGAANDE ANALYSE PER BEVINDING

---

### 🔴 FINDING-DB-01: Koppeltabel `user_roles` mist `tenant_id` en gebruikt enkelvoudige FKs
* **Locatie:** [`src/core/models/rbac_models.py:36-43`](file:///c:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/core/models/rbac_models.py#L36-L43), [`src/alembic/versions/20260522_add_rls_core_tables.py:9`](file:///c:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/alembic/versions/20260522_add_rls_core_tables.py#L9)
* **Root Cause:** De `user_roles` koppeltabel is historisch aangemaakt als een pure 2-koloms associatietabel (`user_id`, `role_id`).
* **Impact:** 
  1. Een background worker, seed script of API-fout kan een Gebruiker uit Tenant A koppelen aan een Rol (bijv. "SuperAdmin") van Tenant B zonder dat de database klaagt.
  2. In migratie `20260522_add_rls_core_tables` staat letterlijk gedocumenteerd: `# user_roles junction table has no tenant_id column and is excluded.` Hierdoor valt de toewijzing van rollen buiten RLS.
* **Vereiste Oplossing:**
  1. Voeg `tenant_id INTEGER NOT NULL` toe aan `user_roles`.
  2. Voeg `UNIQUE (tenant_id, id)` constraints toe aan `users` en `roles`.
  3. Definieer samengestelde foreign keys `FOREIGN KEY (tenant_id, user_id)` en `FOREIGN KEY (tenant_id, role_id)`.
  4. Activeer `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` op `user_roles`.

---

### 🔴 FINDING-DB-02: `FORCE ROW LEVEL SECURITY` ontbreekt op 100% van de tabellen
* **Locatie:** Alle 44 Alembic migraties in `src/alembic/versions/`
* **Root Cause:** Migraties roepen uitsluitend `ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY` aan, maar nooit `FORCE ROW LEVEL SECURITY`.
* **Impact:**
  - In lokale ontwikkelomgevingen, Docker containers of cloud deployments waar de applicatie verbindt onder de database-rol die eigenaar is van het schema (`postgres` of de migratie-user), **wordt RLS stilzwijgend 100% omzeild**.
  - Dit creëert een vals gevoel van veiligheid: men denkt beschermd te zijn door RLS, terwijl PostgreSQL de policies voor de eigenaar simpelweg negeert.
* **Vereiste Oplossing:**
  - Voeg in een baseline-migratie `ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;` toe voor alle tabellen met RLS.

---

### 🟠 FINDING-DB-03: RLS Dekkingskloof (37 van de 164 tabellen gedekt)
* **Locatie:** 127 multi-tenant tabellen in `Base.metadata.tables`
* **Root Cause:** RLS is gefaseerd geïntroduceerd (begonnen met kern-tabellen in mei 2026), maar de overige 127 tabellen die wél een `tenant_id` kolom hebben, zijn nog niet voorzien van een `ENABLE ROW LEVEL SECURITY` migratie.
* **Voorbeelden van onbeschermde tabellen:** `agentic_tasks`, `activepieces_connections`, `dead_letter_entries`, `budget_usage`, `billing_events`, `scheduling_calendar_events`.
* **Impact:** Deze 127 tabellen leunen uitsluitend op de applicatielaag (SQLAlchemy `do_orm_execute` hook). Als een developer een raw SQL query (`db.execute(text("..."))`) uitvoert of een worker `TenantFilterBypass` aanroept, is er geen database-level isolatie.
* **Vereiste Oplossing:**
  - Genereer een centrale Alembic-migratie die `ENABLE + FORCE ROW LEVEL SECURITY` uitrolt over alle resterende 127 multi-tenant tabellen met het veilige `NULLIF(current_setting('app.current_tenant', true), '')::INTEGER` patroon.

---

### 🟠 FINDING-DB-04: Transitieve kind-tabellen missen directe `tenant_id`
* **Locatie:** 
  - Canvas kind-tabellen: `canvas_blocks`, `canvas_connections`, `canvas_collaborators`, `canvas_operations` (hangen aan `canvases.id`).
  - Experiment kind-tabellen: `experiment_variants`, `experiment_assignments`, `experiment_events` (hangen aan `experiments.id`).
* **Root Cause:** De ontwerper vertrouwde op *transitieve isolatie* (omdat `canvases` een `tenant_id` heeft, zou `canvas_blocks` automatisch veilig zijn).
* **Impact:** 
  - Directe queries op `canvas_blocks` kunnen niet via RLS worden gefilterd zonder een zware `JOIN canvases ON ...` in de RLS policy (wat een enorme performance bottleneck veroorzaakt).
  - Geen composite FK mogelijk tussen canvas en blocks.
* **Vereiste Oplossing:**
  - Denormaliseer `tenant_id NOT NULL` naar deze kind-tabellen en leg composite foreign keys aan `(tenant_id, canvas_id)`.

---

### 🟡 FINDING-DB-05: Auth-tabellen `two_factor_auth` en `account_lockouts` missen `tenant_id`
* **Locatie:** `src/core/auth/two_factor_auth.py`, `src/core/auth/models/account_lockout.py`
* **Root Cause:** Tabellen hebben alleen `user_id -> users.id`.
* **Impact:** Hoewel `users` tenant-gebonden is, kan de 2FA- of lockout-status niet direct tenant-scoped worden geaudit of verwijderd (bijv. bij een tenant GDPR wipe).
* **Vereiste Oplossing:**
  - Voeg `tenant_id` toe met een composite FK `(tenant_id, user_id) REFERENCES users(tenant_id, id)`.

---

### 🟢 FINDING-DB-06: Verificatie Connection Pooling Lifecycle (GOED BEVONDEN)
* **Locatie:** [`src/core/database/database.py:118-150`](file:///c:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/core/database/database.py#L118-L150)
* **Onderzoek:**
  - De functie `_zet_tenantcontext` luistert op `Engine.begin`.
  - Er wordt gebruik gemaakt van `SELECT set_config('app.current_tenant', val, true)` (met `is_local=true`).
  - Als de ContextVar leeg is, wordt `''` gezet, wat via `NULLIF(..., '')` resulteert in `NULL` (deny-by-default).
* **Conclusie:** Dit onderdeel is conform de hoogste industriestandaarden geïmplementeerd en voorkomt connection pool leaks tussen requests.

---

# 4. REMEDIATION ROADMAP (HERSTELPLAN)

### Fase 1: Schema Integrity Hardening (P0 Blocker)
1. **Alembic Migratie `harden_user_roles_composite_fks`**:
   - `ALTER TABLE users ADD CONSTRAINT uq_users_tenant_id UNIQUE (tenant_id, id);`
   - `ALTER TABLE roles ADD CONSTRAINT uq_roles_tenant_id UNIQUE (tenant_id, id);`
   - Voeg `tenant_id INTEGER NOT NULL` toe aan `user_roles` (backfill via `users.tenant_id`).
   - Definieer composite FKs `(tenant_id, user_id)` en `(tenant_id, role_id)`.
   - Activeer RLS + `FORCE RLS` op `user_roles`.
2. **Auth Tabellen Hardening**:
   - Voeg `tenant_id` toe aan `two_factor_auth`, `account_lockouts` en `token_blacklist`.

### Fase 2: Enterprise RLS Rollout (P1 High)
1. **Alembic Migratie `enable_rls_all_remaining_127_tables`**:
   - Loop over alle 127 multi-tenant tabellen.
   - Voer uit: `ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;`
   - Voer uit: `ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;`
   - Creëer policy: `CREATE POLICY {tbl}_tenant_isolation ON {tbl} FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER);`

### Fase 3: Transitieve Kind-Tabellen Denormalisatie (P2 Medium)
1. Voeg `tenant_id` toe aan `canvas_blocks`, `canvas_connections`, `experiment_variants` met composite foreign keys naar hun respectievelijke ouders.

---

# 5. CONCLUSIE

Het onderzoek bewijst dat de discussie over **Composite Foreign Keys** exact de vinger op de zere plek legde. 

Door **Composite Foreign Keys** te combineren met **`FORCE ROW LEVEL SECURITY`** en de bestaande **SQLAlchemy ORM hooks**, transformeert de SanskritiSetu database van een kwetsbaar "configuratie-afhankelijk" model naar een **wiskundig waterdicht Defense-in-Depth fundament**.

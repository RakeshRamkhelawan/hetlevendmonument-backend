# Backend Feature Specification

## Metadata

- Feature ID: BE-MIG-008
- Feature naam: Canvas Tabel Migratie naar Hoofd-Base
- Status: READY
- Auteur: Gemini CLI
- Reviewer: code-reviewer, quality-reviewer
- Sprint: SP-WE-17
- Datum: 2026-06-01

---

## Beschrijving

Deze migratie lost bevinding CG-002 op waarbij canvas-tabellen in productie ontbraken omdat ze afhingen van een geïsoleerde `CanvasBase`. Alle canvas-modellen (`Canvas`, `CanvasBlock`, `CanvasConnection`, `CanvasCollaborator`, `CanvasOperation`) erven nu van de centrale SQLAlchemy `Base` in `src.core.database.database`. Tevens is de canvas-domein geregistreerd in `ModelRegistry` zodat Alembic deze tabellen kan oppikken.

De Alembic-migratie (`20260601_canvas_tables_with_rls.py`) creëert deze 5 tabellen en implementeert de vereiste tenant-isolatie (RLS) op de parent `canvases` tabel via een database-policy, conform ADR-005.

## Architectuur & Beslissingen

- **Base Migratie (Option A)**: Consistentie met de rest van de codebase. `CanvasBase` bleef behouden voor unit test sandboxen, maar de productie-modellen erven direct van `Base`.
- **Registry**: Toegevoegd in `src.core.database.model_registry.py` om de autogenerate functionaliteit van Alembic te activeren en handmatige importfouten in `env.py` te vermijden.
- **RLS Policy**: Alleen de parent `canvases` tabel heeft een RLS policy `canvas_tenant_isolation`. De child-tabellen hebben geen expliciete `tenant_id` en zijn impliciet beveiligd via `ForeignKey` CASCADE regels.
- **RLS Syntax**: Conform de standaard wordt `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER` gebruikt in de DDL.
- **Offline Validatie**: PostgreSQL-specifieke `ALTER TABLE` statements zijn veilig afgebakend met `_is_offline()` en `_is_postgresql()`.

## Wijzigingen

1. **`src/domains/canvas/models.py`**
   - Import van `CanvasBase` verwijderd; `Base` geïmporteerd.
   - Alle 5 entiteiten omgezet van `(CanvasBase)` naar `(Base)`.

2. **`src/core/database/model_registry.py`**
   - Registry-entry `domains.canvas` met alle 5 modellen toegevoegd aan `_MODEL_GROUPS`.

3. **`src/alembic/versions/20260601_canvas_tables_with_rls.py`**
   - 5 `op.create_table()` statements.
   - `ALTER TABLE canvases ENABLE ROW LEVEL SECURITY`.
   - Volledige fallback via `downgrade()` in reverse order.

4. **Tests**
   - Unit test voor inheritance & metadata registratie (`tests/unit/test_canvas_model_registration.py`).
   - Integratie test voor creatie en de NOT NULL constraint (`tests/integration/test_canvas_migration.py`).
   - Tenant isolatie tests (PostgreSQL niveau, inclusief `SET ROLE rls_test_user` voor echte RLS validatie) in `tests/integration/test_canvas_tenant_isolation.py`.

## Trainingssamenvatting

| Veld | Waarde |
|------|--------|
| Actor | Platform (Alembic upgrade) |
| Voorwaarde | Database heeft geen canvas-tabellen; alembic head = 20260530a |
| Actie | `alembic upgrade head` uitvoeren |
| Systeemverwerking | Migratie 20260601_canvas_tables_with_rls aangemaakt; 5 tabellen + RLS policy |
| Succesrespons | `alembic heads` toont `20260601_canvas_tables_with_rls` als enige head; alle canvas-endpoints antwoorden 200/201/204 |
| Foutrespons | `alembic check` rapporteert drift -> fix down_revision |
| Uitzonderingen | Migratie is idempotent; bij heruitvoering op bestaande DB geeft `op.create_table` een fout -- gebruik `alembic upgrade head` niet twee keer op dezelfde DB |

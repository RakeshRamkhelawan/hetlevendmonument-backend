# BE-MDL-001: PackFeedback + GlobalPack ORM Models

## Overzicht

SQLAlchemy ORM modellen voor pack feedback en community-contributed packs,
geimplementeerd in `src/core/governance/models.py` als onderdeel van sprint SP-A02.

## Bestanden

| Bestand | Rol |
|---------|-----|
| `src/core/governance/models.py` | ORM modellen `PackFeedback` en `GlobalPack` |
| `src/alembic/versions/11ffd3a57d26_add_pack_feedback_global_packs_tables.py` | Alembic migratie met RLS policies |
| `tests/unit/test_sp_a02_pack_feedback_db.py` | Model tests |

## Model specificaties

### PackFeedback

| Kolom | Type | Constraints | Default |
|-------|------|------------|---------|
| id | UUID | PK | gen_random_uuid() |
| tenant_id | int | NOT NULL, FK(tenants.id), index | — |
| user_id | int | FK(users.id), nullable, SET NULL | — |
| pack_id | str(255) | NOT NULL, index | — |
| rating | int | NOT NULL, CHECK(1-5) | — |
| comment | Text | nullable | — |
| created_at | DateTime(tz) | NOT NULL | clock_timestamp() |

### GlobalPack

| Kolom | Type | Constraints | Default |
|-------|------|------------|---------|
| id | UUID | PK | gen_random_uuid() |
| tenant_id | int | NOT NULL, FK(tenants.id), index | — |
| contributor_user_id | int | FK(users.id), nullable, SET NULL | — |
| name | str(255) | NOT NULL | — |
| description | Text | nullable | — |
| pack_data | JSONB | NOT NULL, default=dict | — |
| created_at | DateTime(tz) | NOT NULL | clock_timestamp() |
| updated_at | DateTime(tz) | nullable, onupdate=func.now() | — |

## ADR-naleving

- **ADR-005**: `tenant_id NOT NULL` + RLS policy op beide tabellen
- **ADR-019**: `created_at` gebruikt `clock_timestamp()` voor serializable ordering

## Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Backend system (Alembic migration runner) |
| Voorwaarde | PostgreSQL beschikbaar, migratie chain intact |
| Actie | `alembic upgrade head` aanroepen |
| Systeemreactie | Tabellen `pack_feedback` en `global_packs` aangemaakt met RLS policies |
| Succesrespons | Migratie slaagt, `alembic check` toont geen drift, 1 head |
| Foutrespons | `alembic.util.exc.CommandError` bij chain-breuk; fix: herstel `down_revision` |
| Uitzonderingen | Offline dry-run (`--sql`) toont SQL maar voert niets uit; `sa.inspect()` verboden in migraties (CLAUDE.md) |

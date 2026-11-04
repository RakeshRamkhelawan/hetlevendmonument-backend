# BE-DATA-001: Agentic-domain tenant_id NOT NULL + RLS + live Alembic-keten

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 1 Groep 4
**Datum:** 2026-07-02
**Status:** APPROVED WITH MINOR GAPS
**ADR:** ADR-005, ADR-004

## Probleem

De 9 agentic-domain tabellen (prompt_templates, features, tool_definitions,
prompt_metrics, user_personas, agent_sessions, session_messages,
prompt_experiments, prompt_experiment_variants) bestonden alleen in een
verouderde, gearchiveerde migratie waarvan het schema niet meer overeenkomt
met de huidige ORM-modellen. 6 van de 9 modellen hadden `tenant_id
nullable=True`, geen RLS-policies actief.

## Oplossing

- Nieuwe live migratie `884d744f6aa9` maakt alle 9 tabellen aan op basis van
  het HUIDIGE modelschema (niet het gearchiveerde), met `tenant_id NOT NULL`
  vanaf aanmaak (geen backfill nodig -- pre-launch, geen productiedata,
  bevestigd door productowner) en RLS-policies volgens het bestaande
  `<tbl>_tenant_isolation`-patroon.
- Geverifieerd end-to-end tegen een verse Postgres-testcontainer: upgrade/
  downgrade-roundtrip slaagt, echte RLS-tenant-isolatie met een non-superuser-
  rol + FORCE ROW LEVEL SECURITY (tenant A ziet tenant B's rijen niet),
  NOT NULL-constraint wijst NULL-inserts af.
- `src/domains/agentic/models.py`: tenant_id nullable=False op de 6
  betrokken modellen.
- `tests/architecture/test_orm_hook_guards_nullable_tenant_id.py`
  (DB-AUDIT-003): regressiebeveiliging tegen toekomstige nullable-tenant_id-
  modellen zonder gedocumenteerde uitzondering.

## Kritieke, losstaande ontdekking (niet vandaag opgelost)

De volledige historische Alembic-keten kan niet vanaf een lege database
bootstrappen: `audit_logs` zelf wordt ook nergens aangemaakt (migratie
`0092fdf7d725` doet `ALTER TABLE` op een tabel die nooit `CREATE TABLE` heeft
gehad). Pre-existing, bevestigd niet veroorzaakt door dit werk. Gemeld aan
Rakesh als apart, prioritair actiepunt.

## Backlog (falende architecture-tests, SP-DATA-ARCH-1)

- 3 andere modellen (experiments, contact_opt_outs, email_bounces) hebben ook
  een undocumented nullable tenant_id -- 2 daarvan zelfs onzichtbaar voor de
  modelregistry (`register_all_models()` importeert die module niet).
- `run_seeds.py`/`seeder.py` construeren Feature/ToolDefinition zonder
  tenant_id -- breekt bij de eerstvolgende keer dat iemand ze draait (geen
  live call-sites vandaag).

## Trainingssamenvatting

- Actor: tenant-toepassing / service die een rij aanmaakt in een van de 9 agentic-domain
  tabellen (bijv. `SQLAlchemyPromptRepository.save_experiment()`)
- Voorwaarde: `INSERT` in `prompt_templates`, `features`, `tool_definitions`,
  `prompt_metrics`, `user_personas`, `agent_sessions`, `session_messages`, of
  `prompt_experiments`
- Actie: insert met of zonder `tenant_id`
- Systeemreactie: DB-laag weigert de insert bij ontbrekende `tenant_id` (NOT NULL);
  bij een aanwezige `tenant_id` filtert de RLS-policy welke rijen zichtbaar zijn per
  sessie (`app.current_tenant`)
- Succesrespons: rij aangemaakt, alleen zichtbaar voor de eigen tenant via zowel de
  ORM-auto-filter (`tenant_query_filter.py`) als de DB-laag RLS-policy
- Foutrespons: `IntegrityError` (NOT NULL constraint violation) bij ontbrekende
  `tenant_id`
- Uitzonderingen: `prompt_experiment_variants` heeft geen `tenant_id`-kolom -- isolatie
  loopt via de FK naar `prompt_experiments` (composite PK experiment_id+variant_id)

## Revisie (NO-GO -> gefixed, 2026-07-02)

Onafhankelijke Final Approver-review (aparte sessie, zonder context van de
implementatie) vond een reele BLOCKER: de migratie gebruikte
`sa.inspect(op.get_bind())` om `has_table()`-guards te bouwen -- expliciet
verboden (`.claude/rules/backend-patterns.md` #9), crasht bij een offline
dry-run. Reproduceerbaar aangetoond: `alembic upgrade head --sql` crashte met
`sqlalchemy.exc.NoInspectionAvailable`. `scripts/pre-deploy-check.sh` (regel
109-117) draait exact dit commando bij elke deploy en zou zijn gefaald met
"Migratie-keten KAPOT".

**Fix:** `upgrade()`/`downgrade()` herschreven naar raw SQL
(`CREATE TABLE IF NOT EXISTS` / `DROP TABLE IF EXISTS`), matchend met het
bestaande patroon in `20260404_gdpr_tables.py` -- geen `sa.inspect()` meer
nodig, `IF NOT EXISTS` regelt idempotency zonder DB-introspectie.

**Nieuwe regressiebeveiliging:**
`tests/architecture/test_no_sa_inspect_in_migrations.py` -- AST-scan over alle
live migraties die faalt zodra `sa.inspect(op.get_bind())` opnieuw wordt
geintroduceerd.

## Test bewijs

```
alembic -c src/alembic.ini upgrade head --sql
-- slaagt zonder crash (was: NoInspectionAvailable)

DATABASE_URL="postgresql://x:x@localhost/x" python -m alembic -c src/alembic.ini upgrade head --sql
-- exacte pre-deploy-check.sh-equivalent, PASS

alembic upgrade head / downgrade -1 / upgrade head -- roundtrip geslaagd tegen
verse Postgres-testcontainer (herhaald na de fix, identiek resultaat: 9
tabellen, RLS aan op 8, tenant_id NOT NULL op 8)

pytest tests/unit/agentic/ tests/integration/test_agentic_domain_tenant_isolation.py tests/unit/database/test_agentic_alembic_chain_complete.py tests/architecture/test_orm_hook_guards_nullable_tenant_id.py tests/architecture/test_no_sa_inspect_in_migrations.py -v
156 passed (excl. 2 intentionele SP-DATA-ARCH-1 backlog-reds)

pytest tests/architecture/ -q --tb=line --timeout=30
346 passed, 9 failed -- exact dezelfde 9 backlog-reds, 1 extra groen
(test_no_sa_inspect_in_migrations.py), geen nieuwe regressies

ruff check src/ -- 0 errors
python -m pyright -- 0 errors
```

## Reviewers

code-reviewer: GO WITH MINOR ISSUES -- migratie kolom-voor-kolom geverifieerd
tegen modellen, RLS-patroon exact matcht precedent. Vond dat seed-scripts nu
breken (SP-DATA-ARCH-1, vastgelegd met falende test).
onafhankelijke Final Approver (aparte sessie): NO-GO -- sa.inspect(op.get_bind())
blocker, reproduceerbaar aangetoond. Na fix: alle overige claims in de brief
onafhankelijk geverifieerd en correct bevonden.

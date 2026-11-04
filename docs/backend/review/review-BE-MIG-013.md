# Review BE-MIG-013: Edu-migratie-alignment (educational_access / study_collections / rol-enums)

STATUS: APPROVED

**Reviewer:** onafhankelijke review (plan-agent), zonder aannames, statisch geverifieerd tegen bron van `20260824_adr029_portal_v1.py` en `20260524e_add_newsletter_subscriptions.py`.
**Datum:** 2026-09-09

---

## B. Eindoordeel

CHANGES_REQUESTED — één CRITICAL (multi-head migratieketen, objectief aangetoond) en één HIGH (data-afhankelijke USING-cast) blokkeren productie-inzet; beide zijn klein te fixen.

## C. Samenvatting

De spec is ongewoon eerlijk en deels van goede kwaliteit: de DELETE-beslissing is verdedigbaar en goed gedocumenteerd, het enum-recreatiepatroon is transaction-safe, en de `values_callable`-keuze per enum klopt feitelijk. Maar de kernclaim "geen enkele bestaande migratie verwijst naar `20260824_adr029_portal_v1`, dus die is head" is **onwaar** (grep-bewijs: `20260715_add_prana_economy_tables` verwijst er wel naar), waardoor de nieuwe migratie een multi-head creëert en `alembic upgrade head` op productie faalt. Daarnaast kan de enum-USING-cast falen op echte data. Integratietests en alembic offline-SQL zijn in deze omgeving niet gedraaid; alle statische verificatie is wel uitgevoerd.

## D. Bevindingen per categorie (samengevat)

1. **Coverage gaps** — De 11 tests dekken het migratiepad zelf niet: ze draaien tegen een `create_all`-schema, dus `test_newsletter_status_enum_no_dead_lowercase_bounced` slaagt ook als migratie 20260909 niet zou bestaan (MEDIUM-3).
2. **Functionele onduidelijkheden** — Spec risico's beweert dat multi-head "pre-existing" is; de grep toont dat `20260824` vóór deze wijziging al een kind had (`20260715`) en dus géén head was.
3. **Technische onduidelijkheden** — De spec claimt als feit dat `20260824` head is ("zelf geverifieerd"); dat is gemeten onwaar.
4. **Ontbrekende foutstatussen/edge cases** — Geen pre-check of defensieve cast voor rijen met `status = 'bounced'` (HIGH-1). Geen rowcount-check na de DELETE's onder RLS (MEDIUM-1). Downgrade faalt op gevulde tabellen op twee punten (MEDIUM-2).
5. **Acceptatiecriteria** — "draait zonder fouten op een database waar 20260824 op gedraaid heeft" is niet gedekt door de nieuwe tests.
6. **Integratorhandleiding** — Voldoende voor een migratie-feature; eerlijk over data-verlies.
8. **Structuur/consistency** — `BE-MDL-016` ontbreekt in `ID-REGISTRY.md`; telling "+11 tests" = 10 nieuw + 1 gewijzigd; module-docstring `test_migrations.py` verouderd.

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| CRITICAL | Migratie regel 42 + spec | `down_revision = "20260824_adr029_portal_v1"` creëert multi-head: `20260715_add_prana_economy_tables.py:117` verwijst ook naar `20260824`. `alembic upgrade head` faalt met "Multiple head revisions". | Zet `down_revision = "20260716_backfill_prana_budgets"` (echte head; `20260716` heeft geen kinderen). Volgorde: 20260824 -> 20260715 -> 20260716 -> 20260909. Pas spec aan. |
| HIGH | Migratie regel 80 | `USING status::text::newsletter_status_enum` faalt op elke rij met lowercase `'bounced'` (geldig sinds 20260824). Hele migratie rolt terug. | Defensief: `USING (CASE WHEN status::text = 'bounced' THEN 'BOUNCED' ELSE status::text END)::newsletter_status_enum`. |
| MEDIUM | Migratie regels 88-89 | DELETE's zonder rowcount-verificatie, onder RLS mogelijk stille no-ops (gemengde leegte laat plaintext-codes als `code_hash` bestaan). | Rowcount-assert na DELETE's (count == 0) of expliciet `SET ROW SECURITY OFF`; documenteer eigenaar-vereiste. |
| MEDIUM | Migratie downgrade | `access_code String(20) nullable=False` zonder default faalt op gevulde tabel; `varchar(64)->varchar(20)` faalt op echte hashes. | Documenteer "alleen op lege tabellen; anders eerst TRUNCATE" in downgrade-docstring. |
| MEDIUM | test_migrations.py:263-274 | Enum-test test `create_all`-schema; zou slagen als migratie 20260909 niet bestond. Geen dekking van type-recreatiepad. | Offline-SQL-test (`alembic upgrade ... --sql` assert op RENAME/CREATE/DROP TYPE) of echte CI-draai tegen wegwerp-database. |
| LOW | Spec/registry | "+11 tests" = 10 nieuw + 1 gewijzigd; `BE-MDL-016` niet geregistreerd. | Telling corrigeren; BE-MDL-016 registreren (of vrijgeven). |
| LOW | test_migrations.py docstring | Zegt nog "5 migraties 20260524a-e". | Bijwerken. |

## F. Ontbrekende items

- Keten-verificatie (`alembic heads` == 1 head) als poort.
- Echte migratiedraai tegen gemigreerde wegwerp-database (CI).

## G. Verbeterde tekstvoorstellen

Spec: vervang de "zelf geverifieerd: 20260824 is head"-claim door: "down_revision `20260716_backfill_prana_budgets` (werkelijke head; `20260715` en `20260716` hangen onder `20260824`). Volgorde 20260824 -> 20260715 -> 20260716 -> 20260909; `alembic heads` blijft één head."

Migratie: `USING (CASE WHEN status::text = 'bounced' THEN 'BOUNCED' ELSE status::text END)::newsletter_status_enum` — defensief, mapt dode dubbele waarde.

## H. Release-oordelen

- Bouw/implementatie: **nee** (CRITICAL-1 maakt `upgrade head` onuitvoerbaar).
- QA/geautomatiseerd testen: **deels** (MEDIUM-3).
- LLM-training: **pas na fix**.
- Integratorhandleiding: **ja**, na correctie ketenclaim.

## Wat wél klopt

DELETE-beslissing verdedigbaar en gedocumenteerd; enum-recreatie transaction-safe met behoud van de 4 oorspronkelijke waarden; `values_callable` alleen op de twee rol-enums correct (andere enums bewust ongemoeid); RLS-policies en `idx_ea_tenant_email` ongemoeid; stijl/ASCII/geen secrets conform CLAUDE.md; tests in bestaande stijl.

---

## Addendum — Herreview 2026-09-09 (onafhankelijk, met commando's geverifieerd)

HERREVIEW-OORDEEL: **APPROVED**.

Alle 6 bevindingen geverifieerd opgelost:
1. CRITICAL multi-head — down_revision = "20260716_backfill_prana_budgets"; `alembic heads` toont exact één head; `alembic upgrade head --sql` eindigt exit=0 met volgorde 20260824 -> 20260715 -> 20260716 -> 20260909.
2. HIGH CASE-cast — aanwezig in migratie én in gegenereerde SQL; type-recreatie transaction-safe met exact 4 waarden.
3. MEDIUM-1 — rowcount-asserts na DELETE's; eigenaar-vereiste gedocumenteerd.
4. MEDIUM-2 — downgrade-docstring documenteert lege-tabellen-vereiste + redenen.
5. MEDIUM-3 — tests/unit/test_be_mig_013_offline_sql.py dekt het migratiepad (RENAME/CREATE/DROP TYPE, CASE-cast, rename, FK, indexen); 64 passed (5 offline + 59 models), 0 failed.
6. LOW — telling gecorrigeerd, BE-MDL-016 geregistreerd, docstring bijgewerkt, onware spec-claims gecorrigeerd.

Kanttekening (geen blocker): integratietests tegen echte Postgres en een echte `upgrade head`-draai op wegwerp-Postgres zijn nog niet gedraaid (geen Docker/testdatabase in deze omgeving). Echte CI-draai aanbevolen vóór productie. Gedocumenteerd als open item in de spec.

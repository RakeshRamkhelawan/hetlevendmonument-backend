# BE-DB-049 -- De applicatie krijgt een eigen databaserol

| | |
|---|---|
| **ID** | BE-DB-049 |
| **ADR** | ADR-036 Fase D / OP-151 |
| **Sprint** | SP-APP-ROLE-001, dag 1 |
| **Branch** | `fix/app-db-role` |
| **Commits** | `4abfd96c` (rode tests), `8b33a4e8` (implementatie) |
| **Datum** | 2026-08-16 |
| **Status** | GEDEELTELIJK -- de rol bestaat, de omschakeling is geblokkeerd (OP-154) |

---

## 1. Het probleem in een zin

De 138 Row-Level-Security-policies in de migratieketen beschermen niets, omdat PostgreSQL
ze niet toepast op de eigenaar van een tabel en de applicatie overal als die eigenaar
(`postgres`) verbindt.

## 2. Wat dat betekende

Gemeten op een verse database uit `alembic upgrade head`, tabel `agents` met een rij voor
tenant A en een voor tenant B:

| verbinding | zichtbare rijen |
|---|---|
| eigenaar `postgres` (de huidige situatie) | 2 van 2 |
| niet-eigenaar, tenantcontext gezet | 1 van 2 |
| niet-eigenaar, lege tenantcontext | 0 van 2 |

`FORCE ROW LEVEL SECURITY` helpt hier niet: dat werkt niet tegen een superuser. De
tenantscheiding rustte dus volledig op de applicatielaag
(`src/core/database/tenant_query_filter.py`). Een ontbrekende `WHERE` in een enkele query
lekt de gegevens van een andere klant, en de databaselaag die dat hoort af te vangen kon
dat niet.

## 3. Twee gebreken die de omschakeling zouden hebben gebroken

Deze zijn tijdens het werk gevonden, niet vooraf voorzien.

**a. De tenantcontext verdween bij de eerste commit.** `SET LOCAL app.current_tenant` is
transactie-gebonden. `database.py` zette hem eenmalig direct na het aanmaken van de
sessie, dus zodra een endpoint zelf `await db.commit()` deed -- de normale gang van zaken
-- draaide de rest van dat verzoek zonder tenantcontext. Gemeten: direct na `SET LOCAL`
`'42'`, na `commit()` `''`. Niet "ongezet" maar LEEG, en dat verschil bepaalt of een
policy nul rijen geeft of een foutmelding.

**b. Veertien policies gaven een foutmelding in plaats van nul rijen.** Elf gebruikten
`current_setting('app.current_tenant')` zonder `missing_ok`. De andere drie
(`agent_configs`, `ai_act_incident_reports`, `model_provenance_records`) had de meting
GEMIST: die zocht op de tekst `, true)` en zag ze aan voor veilig, terwijl ze de `NULLIF`
missen en dus struikelen over precies de lege waarde uit punt (a). Gevonden door de
gedragstest, niet door de meting -- de terugkerende fout in dit project is een zoektocht
die het woord vindt in plaats van het gedrag.

## 4. Wat er is gebouwd

**`20260818_applicatie_databaserol.py`** maakt de rol `sanskritisetu_app`: niet-eigenaar,
`NOLOGIN`, geen wachtwoord, `SELECT/INSERT/UPDATE/DELETE` op alle tabellen plus
`ALTER DEFAULT PRIVILEGES`, `USAGE, SELECT` op de sequences, GEEN `CREATE` op het schema,
en alleen `SELECT` op `alembic_version`.

`NOLOGIN` is een bewuste keuze, geen halfheid. Een wachtwoord in een migratie is een
geheim in de repository, en migratiebestanden worden ook offline als platte SQL
uitgedraaid (`pre-deploy-check.sh`, de CD-preflight). `SET ROLE` werkt wel op een
NOLOGIN-rol, dus CI en de integratietests oefenen de ECHTE rol met de ECHTE rechten uit,
en er verandert niets aan een draaiende omgeving tot iemand bewust een `ALTER ROLE` draait.

**`20260818_normaliseer_rls_expressie.py`** zet de veertien policies om naar
`NULLIF(current_setting('app.current_tenant', true), '')::INTEGER`. `company_templates`
apart: die tabel heeft geen `tenant_id`-kolom (de kolom heet `contributed_by_tenant_id`)
en een tweede, bewust tenant-overstijgende tak voor platformsjablonen die moest blijven
staan.

**`src/core/database/database.py`** zet de tenantcontext voortaan per TRANSACTIE, via een
`begin`-event op de klasse `Engine`. Op de klasse en niet op een enkele engine, omdat de
codebase zestien engines op dezelfde `DATABASE_URL` bouwt. Er wordt altijd iets gezet, ook
zonder tenant: zou het event dan niets doen, dan blijft een eerdere sessie-brede `SET`
staan en erft het volgende verzoek de tenant van het vorige -- een lek, geen lege
uitkomst. En `set_config(..., true)` in plaats van `SET LOCAL ... = :t`, want PostgreSQL
accepteert geen bindparameter in een utility-statement.

**Bijvangst:** `src/core/api/admin_digital_twin.py:54` had precies die verboden vorm.
Gemeten op het echte pad (SQLAlchemy + asyncpg): `PostgresSyntaxError`. Dat endpoint kon
nooit slagen. Meegefixt.

## 5. Vier guards

| Guard | Bewaakt |
|---|---|
| `test_the_application_role_is_confined_to_its_tenant.py` | de rol, de rechten en de isolatie in beide richtingen, tegen een verse database uit de keten |
| `test_every_engine_sets_the_tenant_context.py` | een NIEUWE eigen engine wordt geblokkeerd (OP-153) |
| `test_the_tenant_context_event_is_registered.py` | het `begin`-event blijft bestaan, zonder database, dus in de blokkerende CI-stap |
| `test_the_tenant_context_survives_a_commit.py` | de context overleeft een commit en lekt niet via de pool |

Alle vier mutatie-getest in beide richtingen, met een regel bewijs per bewaakt element.

## 6. Bewijs

```
migraties heen-terug-heen tegen PostgreSQL 15, acht eigenschappen:
  rol bestaat na upgrade, zonder login/superuser/bypassrls
  rol weg na downgrade; pg_default_acl leeg; boekhoudtabel weg
  0 onveilige policies na upgrade; 11 terug na downgrade
  tweede upgrade geeft exact dezelfde toestand
  een rol die de migratie NIET aanmaakte blijft na downgrade bestaan

24 tests groen (17 integratie + 4 + 3 architecture)
offline dry-run `upgrade head --sql` rc=0
alembic heads = 1 (20260818_rls_expr)
```

## 7. Wat NIET is opgelost

**De omschakeling zelf kan niet.** `users` heeft sinds mei een tenant-policy en het
inlogpad zoekt een gebruiker op e-mailadres voordat de tenant bekend is. Gemeten onder de
applicatierol: nul rijen. Inloggen, registreren en wachtwoordherstel zouden stilvallen.
Beide Gate 2-reviewers kwamen hier onafhankelijk op uit; de meting is daarna zelf
herhaald. Dat is OP-154, met twee verdedigbare oplossingen waartussen Rakesh moet kiezen.

Verder open: 27 tabellen met een `tenant_id` zonder policy (OP-155, drie daarvan vragen
eerst een codewijziging omdat de policy anders stil verkeerd uitpakt), en zestien
onderdelen met een eigen engine die per definitie geen tenant in de context hebben
(OP-153). Geen enkele `DATABASE_URL` is gewijzigd.

Runbook: `docs/runbooks/applicatie-databaserol.md`.

---

## Trainingssamenvatting

**Actor:** de applicatie zelf (geen eindgebruiker-interactie).

**Voorwaarde:** PostgreSQL, schema opgebouwd via `alembic upgrade head`.

**Actie:** de applicatie opent een databasesessie en voert queries uit.

**Systeemreactie:** bij het begin van elke transactie zet het systeem
`app.current_tenant` op het tenantnummer uit de JWT-context, of op leeg als er geen
tenant is. Row-Level-Security-policies filteren daarop.

**Succes:** een sessie met tenantcontext ziet uitsluitend de rijen van die tenant, ook als
de query zelf geen `WHERE tenant_id` bevat.

**Fout:** kan de tenantcontext niet worden gezet, dan faalt de transactie. Er wordt
bewust geen waarschuwing gelogd waarna de sessie doorgaat: het verschil tussen "geen
gegevens" en "geen context" mag niet onzichtbaar worden.

**Uitzonderingen:** zolang de applicatie als tabeleigenaar (`postgres`) verbindt, past
PostgreSQL de policies niet toe en is de bescherming inert. `audit_logs` heeft bewust geen
policy. De rol `sanskritisetu_app` bestaat wel maar heeft geen inlogrecht; de omschakeling
is geblokkeerd op het inlogpad (OP-154).

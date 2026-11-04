# Review BE-DB-049 -- De applicatie krijgt een eigen databaserol

| | |
|---|---|
| **Feature** | BE-DB-049 |
| **Branch** | `fix/app-db-role` |
| **Commits** | `4abfd96c` (rode tests), `8b33a4e8` (implementatie) |
| **Reviewers** | code-reviewer + security-reviewer (Gate 2, VOORAF) |
| **Datum** | 2026-08-16 |
| **Eindoordeel** | APPROVED WITH MINOR GAPS -- geen open CRITICAL of HIGH |

---

## 1. Verloop

De Gate 2-review is deze keer VOORAF gedraaid, op het ontwerp plus de rode tests, voordat
er migraties bestonden. Dat bleek de juiste volgorde: beide reviewers gaven
CHANGES_REQUESTED en de zwaarste bevinding zou anders pas na drie migraties zijn opgekomen.

Beide reviewers kwamen ONAFHANKELIJK op dezelfde blokkade uit -- het inlogpad. Die
convergentie was het signaal om zelf te meten in plaats van de verklaring over te nemen.

## 2. Wat de review heeft weggehaald

### Wat ik zelf niet zag

**De omschakeling is onmogelijk zonder een oplossing voor pre-authenticatie.** `users`
heeft sinds `20260522_add_rls_core_tables` een tenant-policy, en het inlogpad zoekt op
e-mailadres voordat de tenant bekend is. Zelf nagemeten: als eigenaar 1 rij, als
niet-eigenaar zonder tenantcontext 0. Zonder deze bevinding was er een rol opgeleverd die
niemand ooit had kunnen aanzetten. Nu OP-154, met een test die de blokkade als meetpunt
vastlegt. Een anker dat rood wordt zodra hij is opgeheven is er NIET: twee pogingen
bleken bij het mutatiebewijs zelf niets te betrappen en zijn verwijderd.

**De lek-test was hol in zijn eigen omgeving.** Mijn test claimde te bewaken dat een
hergebruikte verbinding uit de pool geen tenant meesleept, maar
`tests/integration/conftest.py` geeft `db_manager` een engine met `NullPool` -- er IS geen
hergebruik. De reviewer heeft dat gemeten met de foute implementatie erin: met
`QueuePool(1)` lekte `'4242'`, met `NullPool` bleef de test groen. Nu bouwt de test zijn
eigen engine met `pool_size=1, max_overflow=0` en assert hij op `pg_backend_pid()` dat
beide sessies dezelfde fysieke verbinding kregen.

**Een van de veertien policies ontsnapte aan de dekkingstest.** `company_templates` heeft
geen `tenant_id`-kolom, dus `test_every_table_with_a_tenant_column_has_a_policy` zag hem
nooit. Wie de crash-gevoelige vorm "oplost" door die policy te DROPPEN in plaats van te
herschrijven, kreeg alles groen. Nu een expliciet benoemde verzameling van veertien
(tabel, policynaam)-paren plus een aparte test dat de platformsjabloon-tak overleefde.

**De guard verbood versmalling.** `test_the_application_role_can_write_every_table` eiste
INSERT+UPDATE+DELETE op ELKE tabel. Daarmee was "geef de rol alles" de enige groene
uitkomst en zou elke hardening een rode test worden -- precies andersom dan de bedoeling.
Nu met een gedateerde uitzonderingslijst; `alembic_version` staat erin.

**`ALTER DEFAULT PRIVILEGES` blokkeert `DROP ROLE`.** Er blijft een rij in
`pg_default_acl` staan die geen enkele `REVOKE ... ON ALL ...` opruimt. De reviewer heeft
dat gereproduceerd. De downgrade doet nu eerst de `ALTER DEFAULT PRIVILEGES ... REVOKE`.

**Rollidmaatschap is de achterdeur die de vlaggen niet zien.** Een
`GRANT <andere_rol> TO sanskritisetu_app` geeft via INHERIT alsnog de rechten van die rol,
terwijl `rolsuper` en `rolbypassrls` op false blijven. Drie tests toegevoegd:
lidmaatschap, `rolreplication`, en tabeleigendom (die laatste bewaakt de UITKOMST waar
`cannot_change_the_schema` de WEG bewaakt).

### Wat ik heb gecontroleerd en NIET heb overgenomen

**"`SET LOCAL` met een bindparameter is syntactisch onmogelijk."** De reviewer schreef er
zelf bij dit niet te hebben gedraaid. Mijn eerste meting met psycopg2 gaf TOEGESTAAN --
maar dat meet het verkeerde pad, want psycopg2 interpoleert client-side. Op het echte pad
(SQLAlchemy + asyncpg, server-side prepared statements) gaf het wel
`PostgresSyntaxError`. De conclusie klopt dus, maar pas na de juiste meting; met de eerste
meting had ik hem ten onrechte verworpen.

**"Er is niets bij de 27 tabellen dat bewust tenant-overstijgend hoort te zijn."** Deze
onderbouwing (per tabel, met aanroepplekken) is overgenomen, maar de conclusie is niet
uitgevoerd: drie van die tabellen vragen eerst een codewijziging. Zie punt 4.

## 3. Een fout in mijn eigen guard, gevonden door de mutatietest

De mutatie "haal de `set_config`-aanroep uit de listener" liet
`test_the_tenant_context_event_is_registered` GROEN. Oorzaak: de guard doorzocht alle
string-constanten in de functie, en de docstring noemt `app.current_tenant` tien keer.
Dezelfde vorm als een guard die `ast.dump()` doorzoekt en de docstring meeleest -- de
terugkerende fout uit `.claude/rules/quality-gates.md`, deze keer in de guard die daar
juist tegen moest beschermen. Nu leest hij alleen de body zonder docstring, en alleen
binnen een `ast.Call`. Daarna gaan alle vier de mutaties de goede kant op.

## 4. Wat OPENSTAAT

| Nr | Wat | Borging |
|---|---|---|
| OP-154 | het inlogpad geeft nul rijen onder de applicatierol; keuze A of B is aan Rakesh | meetpunt vastgelegd; een staleness-anker ONTBREEKT (twee pogingen gemeten hol en verwijderd) |
| OP-155 | 27 tabellen met `tenant_id` zonder policy; drie vragen eerst een codewijziging | groene guard + gedateerde lijst + staleness-test |
| OP-153 | zestien onderdelen met een eigen engine, zonder tenant in de context | groene guard + gedateerde lijst + staleness-test |

Niet opgevolgd uit de security-review, met reden: **de grants op de auditketen zijn niet
versmald.** De reviewer wees erop dat de applicatierol UPDATE+DELETE krijgt op
`audit_logs` en `audit_chain_anchors`, wat betekent dat de rolwissel de weerbaarheid van
de ADR-019-keten NIET vergroot. Dat is hierbij expliciet vastgelegd in plaats van
stilzwijgend aangenomen. Versmallen vraagt per schrijver nagaan onder welke identiteit hij
draait (retentie, verificatiejob), en dat is een eigen wijziging met een eigen meting.
`alembic_version` is wel versmald, omdat daar precies een lezer is en die verifieerbaar
alleen leest.

## 5. Bewijs

```
4abfd96c   12 tests, 10 rood -- vastgelegd voor de fix
8b33a4e8   24 tests groen; migraties heen-terug-heen op 8 eigenschappen
           mutatiebewijs: 4/4 (engine-guard), 4/4 (event-guard)
           offline dry-run rc=0; alembic heads = 1
```

## 6. Eindoordeel

**APPROVED WITH MINOR GAPS.** De opgeleverde wijziging is inert voor draaiende omgevingen
(geen connectiestring gewijzigd, rol zonder inlogrecht) en repareert twee echte defecten
die los van de rolwissel bestonden: de tenantcontext die na een commit verdween, en een
endpoint dat nooit kon slagen. OP-153 en OP-155 zijn geborgd met guards die
nieuwe gevallen blokkeren en niet stil kunnen blijven staan. Voor OP-154 is dat NIET
gelukt; dat staat als zodanig in het runbook en in de ADR-rij.

Het belangrijkste resultaat van de dag is niet de rol maar de vaststelling dat de
omschakeling geblokkeerd is, met de meting erbij. Dat had zonder deze sprint pas op
staging gebleken, tijdens een deploy.

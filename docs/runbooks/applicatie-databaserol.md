# Runbook: de applicatie een eigen databaserol geven

**Status: UITGEVOERD OP STAGING, 2026-09-17.** Productie is NIET omgeschakeld -- die
staat sowieso niet ingericht (`docs/infra/AZURE_OMGEVINGEN.md`). De blokkade die
hieronder beschreven staat ("stap 5 en 6 breken het inloggen") is opgeheven: OP-154 stap
1 en 2 hebben de aparte pre-authenticatieverbinding opgeleverd, en op staging is
aangetoond dat inloggen werkt met de applicatierol.

Wat er op staging gemeten is NA de omschakeling, als `sanskritisetu_app`:

    170 tabellen met een klantnummer, 169 met een afschermingsregel
    170 tabellen met FORCE ROW LEVEL SECURITY, 171 policies
    `audit_logs` als enige zonder regel -- bewust, zie ADR-036 OP-40 en OP-246
    zonder klantcontext: users = 0, roles = 0
    met klant 1 aangenomen:  users = 1, roles = 3
    inloggen over HTTPS: 200 met een token

**Twee dingen die de omschakeling zelf blootlegde**, allebei dezelfde fout op een andere
plek, en allebei pas zichtbaar NA stap 6. Lees dit voordat je stap 6 in een volgende
omgeving doet:

1. `src/core/database/seed.py` maakt bij het OPSTARTEN de beheerder aan. Buiten een
   verzoek is er geen klantcontext, dus de INSERT werd geweigerd.
2. `app_lifespan.py::_verify_critical_data` controleert daarna of de beheerder bestaat.
   Zonder klantcontext zag die nul gebruikers en concludeerde dat hij ontbrak.

Elke opstartstap her-werpt, dus de container startte niet op -- twee keer, met dezelfde
melding (`RuntimeError: Database seeding failed after 3 attempts`). Beide zijn opgelost
met een `adopt_tenant`-blok. Beide waren onzichtbaar voor
`scripts/triage_tenantcontext_schrijfpaden.py`, want die kende alleen ORM-aanroepen en
deze twee gebruiken rauwe SQL; dat script kent sinds 2026-09-17 beide vocabulaires.

Laatst gemeten: 2026-09-17 tegen `sanskritisetu-staging` (PostgreSQL 16, Azure Flexible
Server). De eerdere meting van 2026-08-16 tegen een verse PostgreSQL 15 uit
`alembic upgrade head` staat verderop nog in de tekst; waar de twee verschillen, geldt de
nieuwste. ADR-036 OP-151.

---

## Waar dit over gaat, in gewone taal

De database heeft 138 regels ("policies") die per tabel afdwingen dat een klant alleen
zijn eigen rijen ziet. Die regels doen op dit moment **niets**, en dat is geen bug in de
regels: PostgreSQL past ze niet toe op de *eigenaar* van een tabel. De applicatie logt
overal in als `postgres`, en dat is precies die eigenaar.

Gemeten, op een tabel met een rij voor klant A en een rij voor klant B:

| verbinding | ziet |
|---|---|
| als `postgres` (nu) | 2 van 2 rijen -- dus ook de andere klant |
| als een gewone rol, met klantnummer gezet | 1 van 2 |
| als een gewone rol, zonder klantnummer | 0 van 2 |

Zolang de eerste regel geldt, rust de scheiding tussen klanten volledig op de
applicatiecode. Een vergeten `WHERE` in een enkele query lekt dan de gegevens van een
andere klant. De database hoort dat op te vangen en kan dat vandaag niet.

De oplossing is een tweede databaserol die *geen* eigenaar is en waarmee de applicatie
verbindt. Die rol bestaat sinds 2026-08-16 en heet `sanskritisetu_app`. Hij kan alleen nog
niet worden gebruikt.

---

## De blokkade: inloggen valt stil

Inloggen zoekt een gebruiker op e-mailadres **voordat** bekend is bij welke klant die
hoort. De tabel `users` heeft sinds mei een policy. Onder de nieuwe rol geeft die lookup
dus nul rijen. Gemeten:

```
SET ROLE sanskritisetu_app; SET app.current_tenant = '';
SELECT count(*) FROM users WHERE email = '...';   -->  0
```

Dat raakt inloggen, registreren en wachtwoordherstel. `TenantFilterBypass` helpt hier
niet: dat zet alleen het filter in de applicatiecode uit, PostgreSQL trekt zich daar niets
van aan.

### Besloten op 2026-08-17 door Rakesh: een APARTE VERBINDING

Er lagen twee alternatieven op tafel -- (A) drie `SECURITY DEFINER`-functies van de
eigenaar, en (B) een tweede rol met `BYPASSRLS` waar het authenticatiepad met `SET ROLE`
naartoe schakelt. Het is geen van beide geworden.

**Waarom B afvalt, gemeten op 2026-09-15 vanaf een ECHTE inlogverbinding als
`sanskritisetu_app` (PostgreSQL 15.19):**

```
rol gegrant, INHERIT     ->  SET ROLE lukt  ->  ALLE tenants zichtbaar
rol gegrant, NOINHERIT   ->  SET ROLE lukt  ->  ALLE tenants zichtbaar
rol NIET gegrant         ->  permission denied to set role
```

Het grant dat B nodig heeft, geeft de applicatieverbinding een **permanente** uitweg uit
alle policies -- niet alleen binnen een bypass-blok. `NOINHERIT` verandert daar niets aan:
`BYPASSRLS` is een rol-attribuut en geen overerfbaar privilege, en `NOINHERIT` geldt niet
voor rol-attributen ([PostgreSQL 15,
21.2](https://www.postgresql.org/docs/15/role-attributes.html)).

**De gekozen oplossing.** Het pre-authenticatiepad krijgt een eigen verbinding naar een
eigen rol `sanskritisetu_bypass`, die NIET aan de applicatierol wordt gegrant. De
veiligheid zit volledig in "niet koppelen": zonder grant is de rol onbereikbaar vanaf de
applicatieverbinding, met grant is hij dat niet. Zie
`src/core/database/bypass_session.py` en `src/alembic/versions/20260915_bypass_databaserol.py`.

De rol heeft `NOLOGIN`, geen wachtwoord, en mag alleen `SELECT` op de vier tabellen die
het inlogpad aantoonbaar leest (`users`, `roles`, `user_roles`, `account_lockouts`). Hij
omzeilt per definitie elke policy, dus hoe minder hij mag zien, hoe minder een lek op die
verbinding waard is.

**De verbinding aanzetten (hoort bij stap 5/6 hieronder, niet eerder).** Het pad staat uit
zolang `BYPASS_DATABASE_URL` leeg is; dan gedraagt de applicatie zich exact zoals vandaag.
Aanzetten vraagt twee dingen, allebei buiten de repository:

```sql
-- 1. de rol inlogbaar maken, per omgeving, wachtwoord uit een generator
ALTER ROLE sanskritisetu_bypass
    LOGIN PASSWORD '<32+ tekens>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT
    CONNECTION LIMIT 10;
```

```bash
# 2. de applicatie de aparte verbinding geven (Key Vault, niet git)
BYPASS_DATABASE_URL="postgresql+asyncpg://sanskritisetu_bypass:<wachtwoord>@<host>:5432/<db>"
```

Let op: dit is een NIEUW geheim per omgeving, en dat is een echte verslechtering ten
opzichte van `sanskritisetu_app` (die bewust `NOLOGIN` is). Zet er een rotatiedatum bij.

Bij het opstarten toetst `initialize_bypass_engine()` dat deze verbinding daadwerkelijk
een rol met `BYPASSRLS` is en GEEN superuser, en weigert anders te starten. Zonder die
toets zou een DSN die per ongeluk naar `DATABASE_URL` is gekopieerd stil nul rijen geven
op het inlogpad -- de storing die deze hele verbinding moet voorkomen.

**Verboden, en getoetst:** `GRANT sanskritisetu_bypass TO sanskritisetu_app`. Dat geeft de
applicatieverbinding met een enkel `SET ROLE` toegang tot alle tenants, permanent. Bewaakt
door `test_de_bypass_rol_is_niet_gegrant_aan_de_applicatierol`.

**Wat je NIET moet doen:** de policy openzetten met "of het klantnummer is leeg". Dan
wordt "vergeten het klantnummer te zetten" gelijk aan "zie alles", en dat is precies het
lek dat we wilden dichten.

### De valkuil bij het omzetten van de aanroepplekken

Acht functies LEZEN vandaag binnen een `TenantFilterBypass`-blok en SCHRIJVEN daarbuiten.
Verplaats je alleen het lezen naar de aparte verbinding, dan draait die schrijf onder de
applicatierol zonder tenantcontext. Gemeten 2026-09-15:

```
UPDATE users SET hashed_password=... WHERE email=...   ->  0 rijen geraakt
commit()                                               ->  slaagt, geen foutmelding
werkelijk opgeslagen waarde                            ->  nog steeds de oude
```

Wachtwoordherstel meldt dan succes en verandert niets. Lezen en schrijven horen allebei
binnen hetzelfde blok. Bewaakt door
`tests/architecture/test_bypass_lezen_en_schrijven_blijven_bij_elkaar.py`, dat de acht
bekende gevallen bij naam noemt en een negende blokkeert.

---

## Wat er verder eerst af moet

| Wat | Waarom | Waar |
|---|---|---|
| Stap 2 van OP-154: de acht aanroepplekken omzetten | het mechanisme bestaat sinds 2026-09-15, maar niemand roept het aan; tot dat gebeurt kan niemand meer inloggen na de omschakeling | OP-154 |
| 30 tabellen krijgen alsnog een policy | ze hebben wel een klantnummer maar geen regel; onder de nieuwe rol zijn ze voor elke klant leesbaar. Hermeting 2026-08-30: de guard voert 30 uitzonderingen (29 zonder `audit_logs`); het eerder genoteerde getal 27 kwam uit een migratietelling met deels andere tabellen. Twee ontbreken in beide lijsten: `scheduling_sync_conflicts` en `scheduling_webhook_registrations` | OP-155 |
| Vijftien onderdelen met een eigen databaseverbinding | die zetten geen klantnummer; onder de nieuwe rol zien ze nul rijen en melden dat niet. Hermeting 2026-08-30: vijftien, waarvan veertien zonder tenantcontext (eerder genoteerd als zestien) | OP-153 |
| Drie stukken code die stil verkeerd gaan | `check_profiling_opt_out()` (`src/core/governance/ai_transparency_service.py:467`, fail-open op `:497-499`) zegt "geen bezwaar" als de rij onzichtbaar is; `_get_or_create_consent()` maakt dan een duplicaat; de rechtencontrole levert in een worker een lege rechtenlijst | OP-155 |

De workers zijn het lastigste punt: die werken opdrachten van *alle* klanten af en hebben
dus per opdracht een klantnummer nodig, of een eigen rol die de policies mag negeren. Ook
dat is een keuze voor Rakesh.

---

## De stappen, als het zover is

Volgorde is niet vrijblijvend. Stap 1 tot en met 4 zijn al gedaan of risicoloos; vanaf
stap 5 gaat er echt iets om.

**1. (klaar)** De tenantcontext wordt per transactie gezet, op elke databaseverbinding.
Commit `8b33a4e8`.

**2. (klaar)** Veertien policies die een foutmelding gaven in plaats van nul rijen zijn
rechtgezet. Zelfde commit.

**3. (klaar)** De rol `sanskritisetu_app` bestaat, met leesrechten en schrijfrechten op de
tabellen, zonder rechten op het schema, en zonder inlogrecht. Zelfde commit.

**4. (open)** De punten uit de tabel hierboven.

**5. De rol een wachtwoord geven -- per omgeving.**

```sql
ALTER ROLE sanskritisetu_app
    LOGIN PASSWORD '<32+ tekens uit een wachtwoordgenerator>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT
    CONNECTION LIMIT 100;
```

Het wachtwoord gaat in de Key Vault, niet in git en niet in een migratie. Zet er een
rotatiedatum bij.

Verboden: `GRANT <een andere rol> TO sanskritisetu_app`. Daarmee erft de rol de rechten
van die andere rol, en is dat de eigenaar, dan zijn we terug bij af terwijl alle vlaggen
netjes op "geen superuser" staan. Een test bewaakt dit
(`test_the_application_role_is_not_a_member_of_another_role`).

**6. De connectiestring omzetten -- maar niet die van de migraties.**

Dit is het punt waar het vaakst iets misgaat. Migraties maken tabellen aan en hebben
daarvoor rechten nodig die de applicatierol expres niet heeft. Draai je `alembic upgrade
head` als `sanskritisetu_app`, dan faalt de deploy.

- `DATABASE_URL` -> `sanskritisetu_app`
- migratiestap -> een aparte variabele met de eigenaar erin

In `cd-staging.yml` en `cd-production.yml` verwijzen de migratie-job en de app-container
vandaag naar hetzelfde Key-Vault-geheim `database-url`. Dat moeten er twee worden.

**Bijgewerkt 2026-10-23 voor `cd-staging.yml`:** de omschakeling van 2026-09-17 is met de hand in
Azure gedaan en stond niet in de workflow; een uitrol zou de app dus terugzetten op de eigenaar.
Nu staan er twee geheimen in: de migratietaak houdt `STAGING_DATABASE_URL` (eigenaar, Key Vault
`database-url`), en API, werker, planner en leerwerker krijgen `STAGING_APP_DATABASE_URL` (rol
`sanskritisetu_app`, container-app-geheim `app-database-url`). De aparte inlogverbinding komt uit
`STAGING_BYPASS_DATABASE_URL`. De preflight faalt als de twee eerste dezelfde rol bevatten of de
app-URL niet `sanskritisetu_app` is. Productie (`cd-production.yml`) is NIET omgezet. De volledige
lijst voor de uitrol staat in `docs/infra/UITROL-STAGING-2026-10.md`.

**7. Rooktest op staging, in deze volgorde.** Inloggen, registreren, wachtwoord
herstellen, een agent-actie die door de Council gaat, een workerrun, en een retentierun.
Kijk bij de laatste twee niet alleen of ze slagen maar ook of ze *iets deden*: een worker
die nul rijen ziet meldt vrolijk "0 verwerkt".

**Uitgevoerd 2026-09-17. Wat er uitkwam, eerlijk per onderdeel:**

| Onderdeel | Uitkomst |
|---|---|
| Inloggen | 200 met een token -- dit is waar de hele omschakeling om draaide |
| Wachtwoord herstellen | 200 |
| Registreren | **500**, en NIET door de omschakeling: `column tenants.domain does not exist`. Het ORM-model en de migraties zijn 31 kolommen over 9 tabellen uit elkaar gelopen. Zie ADR-036 OP-245 |
| Council-actie | **403**, ook niet door de omschakeling: de beheerder heeft geen rijen in `user_roles`, dus elk endpoint met een scope weigert. Een INSERT zonder klantcontext faalt LUID en zo'n fout staat niet in de logs, dus er is niets stil weggevallen |
| Workerrun | de worker en de scheduler starten en verbinden onder de applicatierol; 16 taken ingepland |
| Retentierun | **NIET gedraaid.** Die verwijdert rijen, en dat is een data-rakende handeling op een gedeelde omgeving -- die wacht op een expliciet woord van Rakesh |

In plaats van de retentierun is het onderliggende risico read-only gemeten, want daar gaat
de waarschuwing hierboven over: ziet een achtergrondtaak zonder klantcontext nul rijen? Ja,
en dat is nu ook zichtbaar in plaats van stil. Gemeten als `sanskritisetu_app` op dezelfde
verbinding, per tabel, zonder en met klant 1 aangenomen: `users` 0 tegen 1, `roles` 0 tegen
3, en nul in beide gevallen voor de lege tabellen. Een taak die de klant NIET aanneemt ziet
dus werkelijk niets -- dat is precies waarom OP-153 alle achtergrondpaden langsloopt.

**8. Productie**, met een terugweg die alleen `DATABASE_URL` terugzet naar de eigenaar.

---

## Twee valkuilen bij het oplossen van storingen

**"De applicatie kan geen tabel aanmaken."** Los dat NOOIT op met `GRANT CREATE ON SCHEMA
public TO sanskritisetu_app`. Wie een tabel aanmaakt is er de eigenaar van, en een
eigenaar omzeilt alle policies op die tabel -- dan is de rol precies zo waardeloos als de
oude situatie. Twee stukken code doen runtime-DDL (`conversation_persistence.py` en
`domain_isolation.py`); beide hebben vandaag geen enkele aanroeper. Verwijder ze liever
dan ze rechten te geven.

**"Een nieuwe tabel geeft permission denied."** De rechten voor toekomstige tabellen zijn
gekoppeld aan de rol die ze aanmaakt. Draait een omgeving haar migraties met een andere
rol dan `postgres`, dan mist de applicatie de rechten op alles wat daarna is aangemaakt.
Gemeten: tabel door `postgres` -> rechten wel; tabel door een andere migratierol ->
rechten niet. Dit is een storing, geen lek, en
`test_the_application_role_can_read_every_table` betrapt het op een verse database.

---

## Controleren of het klopt

```bash
docker start sanskritisetu_test_db
python -m pytest tests/integration/security/test_the_application_role_is_confined_to_its_tenant.py -v
python -m pytest tests/architecture/test_the_tenant_context_event_is_registered.py \
                 tests/architecture/test_every_engine_sets_the_tenant_context.py -v
```

De eerste bouwt een verse database uit de migraties en meet de rol, de rechten en de
isolatie in beide richtingen. `test_the_login_lookup_finds_nothing_under_the_application_role`
hoort daar vandaag te SLAGEN: die legt de blokkade vast als MEETPUNT.

```bash
python -m pytest tests/architecture/test_bypass_lezen_en_schrijven_blijven_bij_elkaar.py -v
python scripts/bewijs_op154_guard.py    # het mutatiebewijs, een regel per element
```

**Wat sinds 2026-09-15 WEL geborgd is, en wat niet.** Er is nu een anker voor STAP 2 van
OP-154: `test_lijst_is_niet_verouderd` wordt rood zodra een van de acht aanroepplekken is
omgezet zonder dat de lijst is bijgewerkt, en `test_geen_nieuwe_gevallen` blokkeert een
negende. Dat is gemeten, niet aangenomen -- zie het mutatiebewijs hierboven, dat elk van de
acht elementen apart betrapt plus beide tegenrichtingen.

Er is nog steeds GEEN test die rood wordt zodra STAP 3 (de omschakeling van `DATABASE_URL`)
is uitgevoerd. Twee eerdere pogingen daartoe zijn gemeten en bleken niets te betrappen; ze
zijn verwijderd in plaats van blijven staan. Wie die omschakeling doet, moet dit runbook en
de ADR-rij OP-154 dus ZELF bijwerken -- daar herinnert niets hem aan.

Op 2026-09-17 is dat ook precies zo gegaan: de omschakeling op staging is met de hand in
dit runbook en in ADR-036 OP-151 bijgewerkt, want niets vroeg erom. Dat de omschakeling
twee echte fouten blootlegde die geen enkele test had gevonden (zie de twee punten
bovenaan dit bestand) is het bewijs dat die ontbrekende test iets kost. De reparatie is
niet "een test die rood wordt na stap 3" -- die is twee keer geprobeerd en betrapte
niets -- maar de OP-153-triage die ALLE achtergrondpaden langsloopt, inclusief de rauwe
SQL die zij tot 2026-09-17 niet kon zien.

# Backend Feature Specification

## Metadata

- **Feature ID:** BE-SEC-053
- **Feature naam:** Geen database-wachtwoord in de uitvoer: hulpfunctie, 28 plekken, guard voor database-URL en omgevingsvariabelen
- **Status:** Gereed op code en meting (Gate 2 afgerond, zie de review). Rotatie van het stagingwachtwoord is een besluit van Rakesh (interlock 1) en NIET genomen.
- **Auteur:** bouwsessie 7f/98 (tak `iter/dbwachtwoord`)
- **Reviewer:** security-reviewer (subagent, Gate 2)
- **Datum:** 2026-10-23
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-23-sprint-dag-geen-database-wachtwoord-in-de-uitvoer.md` (bevinding D1 van `2026-10-23-sprint-dag-geen-geheim-in-de-uitvoer.md`)
- **Gerelateerde router / module:** `src/core/utils/url_zonder_wachtwoord.py`, `src/alembic/env.py`, `src/alembic/env_new.py`, `src/core/database/database.py`, `src/core/app_factory.py`, `src/config.py`
- **Gerelateerde frontend endpoints:** geen
- **Gerelateerde database tabellen:** geen (GEEN migratie, GEEN tabel; `env.py` is geen migratie)
- **Versie:** 1.0

## Doel en scope

### Doel

Een database-URL (`postgresql+asyncpg://gebruiker:wachtwoord@host:5432/db`) komt nooit meer in een `print`, een logregel of een foutmelding, ook niet gedeeltelijk. Voor de eerste staging-uitrol moet het ophouden dat de migratiejob de eerste 50 tekens van de URL in de containerlog zet.

1. **Een hulpfunctie** `database_url_zonder_wachtwoord()` (`src/core/utils/url_zonder_wachtwoord.py`) geeft alleen schema, host, poort en databasenaam terug; nooit gebruiker, wachtwoord of queryparameters. Een onleesbare URL, of een URL met meer dan een `@` (een ruwe `@` in het wachtwoord) geeft `<database-url>`; een ontbrekende URL geeft `<geen database-url>`.
2. **Alle gemeten plekken** gebruiken die functie: `src/alembic/env.py` (regel 81 en de foutmelding in `run_migrations_online`), `src/alembic/env_new.py`, `src/config.py`, `src/ensure_demo_user.py`, `src/core/shared/config.py`, `src/core/database/database.py`, `src/core/app_factory.py`, `src/scripts/dr_test_runner.py` en 17 bestanden in `scripts/`.
3. **De guard** `tests/architecture/test_geen_geheim_in_de_uitvoer.py` dekt nu ook database-URL-namen (`database_url`, `db_url`, `dsn`, `os.getenv("DATABASE_URL")`, `config.get_main_option("sqlalchemy.url")`), de tekst van een `raise`, omgevingsvariabelen met een willekeurige naam (`os.getenv(var)`) en `engine.url`.

### Buiten scope

Geen wachtwoord roteren, geen log openen, geen `.env` openen, geen migratie. Niet gedekt door de guard (eigen brief): `repr(settings)`, `print(os.environ)`, `private_key_pem`, `encryption_key`, en een geheim in de uitzondering van een bibliotheek (bijvoorbeeld een asyncpg-fout met een DSN).

## Besluiten van de bouwer (aannames, niet van Rakesh)

- **De helper leest met `sqlalchemy.engine.make_url`**, dus precies zoals de applicatie de URL leest. Een wachtwoord met `/`, `#`, `?`, `:` of `%`-codes komt er niet in (gemeten met verzonnen waarden, 15 tests).
- **Een ruwe `@` in het wachtwoord geeft `<database-url>`.** `make_url` leest `postgresql://u:pa@ss@host/db` als host `ss@host`; de helper zou dan het staartdeel van het wachtwoord tonen. Gemeten door de reviewer; daarom 5 tests (ook met een `?` en een `@` in het wachtwoord, gemeten in ronde 2) en een regel die een URL met meer dan een `@` weigert; een `@` in de query valt daar ook onder, en dat is veilig.
- **De helper staat in `src/core/utils/`** en niet naast `url_converter.py`: de pakketketen daar is licht, zodat losse scripts hem kunnen importeren zonder de applicatieconfiguratie te laden. Scripts in `scripts/` en `src/scripts/` krijgen een eigen `sys.path`-voorloop (de repo-root), anders start `python scripts/<naam>.py` niet (gemeten: `ModuleNotFoundError` bij `src/scripts/dr_test_runner.py` zonder die voorloop; hersteld).
- **Een variabele die uit een gewone functie komt is geen geheim.** De guard telt een geheim alleen door als de functie het teruggeeft (`str`, `repr`, een methode erop, `.format`). Zonder die regel gaf de eerste versie dertig valse alarmen (`response = client.post(json={"password": p})`).
- **Een kale `token` en een kale `key` zijn bewust geen geheimnaam** (RRULE-onderdeel, tokenbudget, `jti`, cachesleutel).

## Welke runs het geraakt KUNNEN hebben (gemeten zonder een log te openen)

Waar de regel stond: `src/alembic/env.py` print `database_url[:50]` sinds 2025-11-09 (commit `7049e56a`); de foutmelding met de hele URL (`DATABASE_URL={url}`) sinds 2026-04-13 (commit `90989235`). De eerste 50 tekens van `postgresql://gebruiker:wachtwoord@host...` laten 37 tekens van `gebruiker:wachtwoord@host` zien: bij een korte gebruiker en een kort wachtwoord staat het wachtwoord er helemaal in, anders het begin ervan.

Waar de uitvoer terechtkomt, per workflow (gemeten in de workflowbestanden):

| Plek | Wat er draait | URL | Uitvoer | Kan het wachtwoord bevatten? |
|---|---|---|---|---|
| `cd-staging.yml` stap "Validate migration chain" (regel ~238) | `alembic upgrade head --sql` en `heads` op de GitHub-runner | `postgresql+psycopg2://dummy:dummy@localhost/dummy` | `--sql` naar `/dev/null` | Nee: dummy |
| `cd-production.yml` stap "Validate migration chain" (regel ~172) | idem | dezelfde dummy | idem | Nee: dummy |
| `ci-feature.yml` (regel 332 en 843) | `alembic upgrade head` tegen de CI-databaseservice, en `--sql` | `postgres:postgres@localhost` (openbaar in de workflow) en `x:x@localhost` | GitHub-log | Nee: openbare testgegevens |
| `cd-staging.yml` stap "Run migrations" (regel 426) | start de Azure Container Apps-job `migration-job`; de GitHub-stap meldt alleen de status ("Controleer de migration-job logs in Azure") | `DATABASE_URL` uit de Key Vault (`sanskriti-kv-stg`, geheim `database-url`) | containerlog van de job in Azure | **Ja: het echte stagingwachtwoord, de eerste 50 tekens van de URL** |
| `cd-production.yml` migratiejob (regel ~334) | zelfde opzet met `sanskriti-kv-prd` | uit de Key Vault | containerlog in Azure | In principe ja, maar zie hieronder: nooit uitgevoerd |
| de app-containers | `RUN_MIGRATIONS` staat alleen op de migratiejob; `scripts/entrypoint-prod.sh` slaat migraties anders over | n.v.t. | n.v.t. | Nee |

**Gemeten met `gh run list` en `gh run view --json jobs` (alleen metadata: stapnaam en uitslag):**

- `cd-staging.yml`: 288 runs tussen 2026-04-03 en 2026-09-12. In **139 runs is de stap "Run migrations" uitgevoerd** (138 geslaagd, 1 mislukt), van 2026-06-05 tot 2026-09-11 (juni 97, juli 1, augustus 10, september 31). In de overige runs bestond de stap niet (140) of is hij overgeslagen (9). Bij elke uitgevoerde stap heeft de Azure-job `env.py` met de echte stagingURL gedraaid.
- `cd-production.yml`: 35 runs tussen 2026-04-03 en 2026-04-19; in geen enkele is een migratiestap uitgevoerd. Er is dus geen productie-uitvoering gemeten.
- GitHub-logs: de GitHub-stap bevat alleen status en tellers; de uitvoer van de job staat in Azure. De GitHub-runs bevatten het wachtwoord dus NIET via deze weg (niet gemeten op GitHub zelf; afgeleid uit de workflowtekst).
- De plek waar het kan staan: de logs van de Azure Container Apps-job `migration-job` (Log Analytics van de staging-omgeving), een uitvoering per run uit de lijst hieronder.

De run-ID's van de 139 stagingruns waarin de migratiestap draaide:

27027988264, 27028598148, 27031146362, 27032726654, 27197250852, 27199788883, 27200803524, 27236002021, 27303253568, 27303961299, 27305051334, 27340156951, 27401864689, 27403395544, 27403800856, 27404522529, 27419476407, 27424094306, 27425645703, 27428218332, 27429808531, 27461550137, 27461742849, 27462015785, 27464051247, 27466219965, 27466798330, 27679433265, 27681383239, 27706791647, 27710953704, 27714523554, 27717529671, 27975091841, 27982563357, 27985329716, 28008977178, 28009461790, 28049931162, 28075159822, 28075953560, 28076843357, 28096787312, 28108822979, 28110628643, 28111294761, 28120722523, 28129116327, 28129840520, 28155404367, 28167754980, 28189570201, 28194419793, 28223686453, 28283958661, 28284160373, 28284894457, 28288411017, 28289038900, 28290512999, 28292025455, 28295929007, 28296101595, 28296431300, 28296666277, 28296976285, 28297193188, 28298208263, 28298651075, 28299074104, 28299314767, 28299508066, 28299777275, 28300613320, 28301228276, 28302635305, 28303437821, 28304950904, 28318481469, 28319185084, 28319588027, 28320136727, 28321411943, 28321990939, 28323065689, 28323800426, 28332231856, 28336081630, 28337364245, 28365449235, 28386645130, 28393471305, 28395031712, 28396913765, 28401490633, 28402972140, 28405229074, 30300484990, 33228387204, 33229004822, 33229616430, 33231173356, 33271832726, 33324736956, 33334595106, 33336075365, 33338020341, 33339104311, 33645735256, 33648559343, 33818018005, 34058500705, 34061139081, 34105646178, 34124096936, 34127712326, 34130541681, 34221019441, 34224049179, 34227970588, 34282031523, 34290014196, 34345468731, 34351321905, 34359332840, 34393183774, 34400271192, 34411906393, 34420708741, 34453259662, 34467926769, 34476177350, 34569552173, 34598480775, 34602548518, 34608168103, 34629335653, 34638360852, 34650512997

**Besluit voor Rakesh (interlock 1, secret-rotatie):** moet het stagingwachtwoord in de Key Vault (`database-url`) worden vervangen? Ik heb geen log geopend en niet gemeten of het wachtwoord er daadwerkelijk in staat; de lengte van gebruiker en wachtwoord bepaalt of het geheel of gedeeltelijk zichtbaar was. De bouwer roteert niets.

## Trainingssamenvatting

### Een database-URL tonen in een melding (ontwikkelaar of beheerder die een script of de migratie draait)

- **Actor:** een ontwikkelaar of beheerder die `alembic`, een script uit `scripts/` of de migratiejob draait.
- **Voorwaarde:** de omgeving heeft een `DATABASE_URL` met gebruiker en wachtwoord (lokaal, staging of productie).
- **Actie:** `alembic -c src/alembic.ini upgrade head` of een script starten dat meldt met welke database het verbindt.
- **Systeemreactie:** de melding noemt alleen schema, host, poort en databasenaam, bijvoorbeeld `[Alembic] Using DATABASE_URL: postgresql://db.example.invalid:5432/meetdb`; nooit gebruiker, wachtwoord of queryparameters.
- **Succes:** de uitvoer, de log en de foutmelding bevatten geen deel van het wachtwoord; `alembic heads` toont een head.
- **Fout:** een URL die niet te lezen is of een ruwe `@` in het wachtwoord heeft geeft `<database-url>`; een ontbrekende URL geeft `<geen database-url>`.
- **Uitzondering:** een ontwikkelaar die zelf een URL wil tonen gebruikt `database_url_zonder_wachtwoord(url)`; de guard `tests/architecture/test_geen_geheim_in_de_uitvoer.py` faalt op een print, log of `raise` die de URL, een deel ervan of een omgevingsvariabele met een onbekende naam toont.

## Open punten

- D2, D3 en D4 uit de eindmelding van brief `geen-geheim-in-de-uitvoer` (harde dev-wachtwoorden in scripts, scripts die opzettelijk een nieuw token tonen) staan bij de regie voor een eigen brief.
- De guard kent `repr(settings)`, `print(os.environ)`, `private_key_pem` en `encryption_key` niet.
- Een uitzondering van asyncpg of psycopg die de DSN bevat en elders wordt doorgegeven is niet onderzocht.

## Regressierisico's

- Een script in `scripts/` start los (`python scripts/<naam>.py`) met alleen de nieuwe importregels: de `sys.path`-voorloop is toegevoegd en `src/scripts/dr_test_runner.py` is na de review hersteld; de gewijzigde scripts zijn niet uitgevoerd (ze vragen een database of server), alleen gecompileerd en door ruff op F821/F841 gehaald.
- `alembic -c src/alembic.ini upgrade head --sql` met een verzonnen URL en wachtwoord: voor de fix stond het volledige verzonnen wachtwoord in de uitvoer, erna alleen `postgresql://db.example.invalid:5432/meetdb`; `alembic heads` toont een head en geen wachtwoord.

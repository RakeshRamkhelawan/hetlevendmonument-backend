STATUS: APPROVED

# Review BE-SEC-053: Geen database-wachtwoord in de uitvoer

- **Datum:** 2026-10-23
- **Spec:** `docs/backend/features/BE-SEC-053-geen-database-wachtwoord-in-de-uitvoer.md`
- **Reviewers:** security-reviewer (subagent, alleen lezen)
- **Bouwer:** bouwsessie 7f/98, tak `iter/dbwachtwoord`
- **Rondes:** twee; er is geen derde ronde gehouden

## Gate 2 -- ronde 1 (commit ee887e4b)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| security-reviewer | NO-GO | HOOG B1: `src/scripts/dr_test_runner.py` startte niet meer als los script (`ModuleNotFoundError: No module named 'src'`, gemeten): de nieuwe import had geen `sys.path`-voorloop. HOOG B2: twee bestaande lekken die de guard miste omdat de variabelen generieke namen hebben: `scripts/fase0_validate.py:52` (toonde de eerste 30 tekens van elke vereiste omgevingsvariabele, `DATABASE_PASSWORD` zelfs geheel) en `scripts/start_performance_workers.py:116` (logde `value[:20]` van elke sleutel uit `.env.test`). MIDDEL B3: de helper toonde bij een ruwe `@` in het wachtwoord een staartdeel (`postgresql://u:pa@ss@host:5432/db` gaf `postgresql://ss@host:5432/db`). LAAG: `src/core/database/database.py:257` (`safe_url.split('@')[1]`) en `src/core/app_factory.py:259` (`engine.url` met de gebruiker). |

## Wat ermee gedaan is (commit 4c8d01cf)

Eerst rode tests, dan de reparatie:

- B1: `src/scripts/dr_test_runner.py` kreeg dezelfde `sys.path`-voorloop als de scripts (`parents[2]`); `python src/scripts/dr_test_runner.py --help` werkt (gemeten).
- B2: beide scripts tonen alleen "set" of de sleutelnaam. De guard kreeg een regel voor omgevingsvariabelen met een willekeurige naam (`os.getenv(var)`, `os.environ[naam]`; een HOOFDLETTER-constante telt als vaste naam) en voor `engine.url`; die vond nog drie echte lekken die ook zijn gerepareerd: `scripts/check_env.py` (eerste en laatste 4 tekens van API-sleutels) en `scripts/validate_production_env.py` (eerste 10 tekens van elke productievariabele, twee plekken).
- B3: de helper geeft `<database-url>` zodra er meer dan een `@` in de URL staat; 3 nieuwe tests, eerst rood.
- LAAG: beide logregels gaan via de helper.
- Gevonden bij het testen van mijn eigen guard (eerst rood): de nieuwe regel voor `os.environ[naam]` werd nooit geraadpleegd (de tak voor een niet-constante sleutel ontbrak); hersteld en getest.

## Gate 2 -- ronde 2 (commit 4c8d01cf)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| security-reviewer | GO | B1, B2 en B3 zijn weg (gemeten). R2-1 MIDDEL, niet blokkerend: een wachtwoord met zowel `?` als `@` liet een staartdeel door (`postgresql://u:pa?x@ho@st/db` gaf `postgresql://ho@st/db`), omdat de regel alleen voor de eerste `?` telde. LAAG: `scripts/verify_cva_ceo_mode.py:104` toont `token[:10]` (de JWT-kop, geen geheim; geen actie). |

R2-1 is in dezelfde ronde hersteld (de regel telt nu `@` over de hele URL; 2 nieuwe tests, eerst rood, 17 groen).

## Eindmeting

- `tests/architecture/test_geen_geheim_in_de_uitvoer.py` en `tests/unit/database/test_database_url_zonder_wachtwoord.py`: 80 tests groen.
- Mutatiebewijs op de echte bestanden, kopie als terugweg: `env.py:81` terug naar `database_url[:50]` rood; de foutmelding met de hele URL rood; de helper die gebruiker en wachtwoord teruggeeft rood (5 tests); een onleesbare URL ongewijzigd teruggeven rood; de ruwe-`@`-regel weg rood (3 tests); `fase0_validate`, `check_env`, `validate_production_env` en `app_factory` weer met waarde of `engine.url` rood; een onschuldige wijziging via de helper blijft groen.
- Live: `alembic -c src/alembic.ini upgrade head --sql` met een verzonnen URL en wachtwoord: voor de fix stond het volledige verzonnen wachtwoord in de uitvoer, erna alleen `postgresql://db.example.invalid:5432/meetdb`; `alembic heads` toont een head en geen wachtwoord.
- ruff schoon, pyright 0, `run_mypy_audit.py` 0, Any-ratel 7026 gelijk aan de baseline.

## Wat niet is gemeten

- De 17 scripts zijn niet uitgevoerd (ze vragen een database, server of websocket); alleen gecompileerd en door ruff op F821/F841 gehaald (43 meldingen voor en na, geen nieuwe).
- Geen Azure- of GitHub-log is geopend; of het wachtwoord er daadwerkelijk in staat is niet vastgesteld. Zie de spec voor de 139 runs waarin het kan.
- Een asyncpg- of psycopg-uitzondering met de DSN die elders wordt doorgegeven is niet onderzocht.
- `repr(settings)`, `print(os.environ)`, `private_key_pem` en `encryption_key` vallen buiten de guard.

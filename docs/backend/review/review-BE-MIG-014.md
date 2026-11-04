# Review BE-MIG-014: Sprint C datamodel — visibility, ContentType-uitbreiding, target_age_group

STATUS: APPROVED

**Reviewer:** onafhankelijke review-agent (Gate 2, code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; read-only gereviewd. Alle claims hieronder zijn met eigen commando's geverifieerd, niet overgenomen uit de spec of ID-REGISTRY.
**Datum:** 2026-09-10
**Scope:** commit `398694438` op `iter/be-mig-014` (diff t.o.v. `develop`): migratie `src/alembic/versions/20260910_adr029_sprint_c_datamodel.py` (nieuw, 156 regels), `src/core/models/foundation_content.py` (+45), `tests/unit/test_be_mig_014_offline_sql.py` (nieuw, 126), `tests/unit/test_foundation_models.py` (+115), `tests/integration/foundation/test_migrations.py` (+55/-1), `docs/backend/features/BE-MIG-014-sprint-c-datamodel.md`, `docs/backend/features/ID-REGISTRY.md`. Totaal 611 insertions, 2 deletions, 7 bestanden — allemaal spec-genoemd, geen scope-kruip (git diff --stat geverifieerd).

---

## B. Eindoordeel

APPROVED. Geen HIGH- of blokkerende MEDIUM-bevindingen. De bewuste casing-afwijking (hoofdletter-labels op `content_type_enum` in plaats van de lowercase uit de spec-tekst) is **correct geredeneerd en door mij zelf tegen de bestaande code en een echte database geverifieerd**: `content_type_enum` is in migratie `20260524b_add_foundation_content_and_tags.py:54-63` aangemaakt met hoofdletter member-namen (`STORY`, `ARTWORK`, ...) en de `type`-kolom (`foundation_content.py:152-155`) gebruikt `PGEnum` zonder `values_callable`, dus SQLAlchemy serialiseert member-NAMEN. Lowercase labels toevoegen zou dode duplicaten hebben gegeven en ORM-inserts zouden op de hoofdletterwaarde blijven falen. De lowercase `.value`'s blijven bovendien het API-contract (Pydantic serialiseert de str-enum naar `"video"` etc.), dus de spec-intentie blijft op API-niveau intact. De migratie-roundtrip op echte Postgres (pgvector, poort 5435, eigen wegwerp-DB) is volledig groen, inclusief zelf getest backfill-scenario (privacy=COMMUNITY → visibility=community).

## C. Samenvatting

De migratie voegt precies toe wat audit-bevinding N-2 (regels 125-153) eist: een apart `visibility_enum` (`public`/`edu`/`community`), een NOT NULL `visibility`-kolom met server_default `'public'` en backfill vanuit `privacy`, zes nieuwe `content_type_enum`-waarden, `target_age_group` String(50) nullable, en de index `idx_fc_tenant_visibility_status` voor de Sprint-D edu-lijstquery (O7). De volgorde-eis (regels 379-382: Sprint C vóór Sprint D) is gehonoreerd — er is geen enkele endpoint-wijziging meegepakt.

Gemeten verificatie (eigen runs, venv `.venv/Scripts/python.exe`):

- **Unit: 80/80 groen** — `pytest tests/unit/test_foundation_models.py tests/unit/test_be_mig_014_offline_sql.py tests/unit/test_be_mig_013_offline_sql.py -q` (87.7s). NB: het in de opdracht genoemde pad `test_be_mig_013_edu_alignment_offline_sql.py` bestaat niet; het werkelijke bestand is `tests/unit/test_be_mig_013_offline_sql.py`.
- **Migratie op echte Postgres** (container `sanskritisetu_postgres`, `ankane/pgvector` PG15, poort 5435, eigen DB `bemig014_review`):
  - `upgrade head` vanaf scratch: groen, inclusief `[BE-MIG-014] backfill visibility: 0 rijen` op lege tabel.
  - Schema verifieerd via `pg_enum`/`information_schema`/`pg_indexes`: `content_type_enum` = 12 labels (6 bestaande hoofdletters + `VIDEO`, `EDUCATIONAL_WORKBOOK`, `EDUCATIONAL_VIDEO`, `TEACHER_GUIDE`, `EVENT_REPORT`, `ART_DOCUMENTATION`); `visibility_enum` = `public, edu, community`; `visibility` = NOT NULL met default `'public'::visibility_enum`; `target_age_group` nullable; index aanwezig.
  - **Backfill zelf getest**: downgrade naar `20260909_adr029_edu_alignment`, twee rijen ingevoerd (privacy `PUBLIC` resp. `COMMUNITY`), `upgrade head` → `visibility` = `public` resp. `community`, log `[BE-MIG-014] backfill visibility: 2 rijen bijgewerkt`.
  - **Roundtrip**: `downgrade -1` + `upgrade head` groen; het autocommit-blok is daarmee twee keer over dezelfde DB gelopen — `CREATE TYPE`-duplicate_object-vangst en `ADD VALUE IF NOT EXISTS` zijn daadwerkelijk idempotent bewezen.
  - `alembic -c src/alembic.ini heads` = exact 1 head (`20260910_adr029_sprint_c_datamodel`).
  - **ORM-insert zelf bewezen** tegen de gemigreerde DB: `FoundationContent(type=ContentType.EDUCATIONAL_WORKBOOK, visibility=Visibility.EDU, target_age_group="12-14")` insert + read roundtrip correct (DB-label hoofdletters, Python-enum roundtrip, visibility lowercase via `values_callable`). Tijdelijk check-script is na afloop verwijderd.
- **Integratie: 30/31 groen** — `pytest tests/integration/foundation/test_migrations.py` (15.4s). De enige failure is de bekende pre-existing testbug (zie E, MEDIUM-1): op een develop-worktree met dezelfde database faalt exact dezelfde test identiek (`assert 'code ' not in row[0]` — de substring `'code '` zit in de index-NAAM `idx_ea_tenant_code` zelf, vóór `ON`). Niet door deze branch veroorzaakt; deze branch raakt die test niet.
- **ruff**: `All checks passed!` op alle vijf gewijzigde codebestanden.
- **mypy**: `Success: no issues found in 2 source files` op de twee gewijzigde src-bestanden.
- **Non-ASCII-scan** op alle `+`-regels van de diff in `src/` en `tests/`: 0 hits (regel "NOOIT non-ASCII in code/comments" gehonoreerd — de Nederlandse commentaren zijn bewust ASCII-only, bv. "recreeen").
- **down_revision-keten** geverifieerd: `20260910` → `20260909_adr029_edu_alignment` → `20260716_backfill_prana_budgets`; de hele keten draait vanaf scratch.

## D. Bevindingen per categorie (samengevat)

1. **Migratie-kwaliteit** — Sterk. Autocommit-blok klopt (Postgres staat gebruik van een nieuwe enum-waarde niet toe in dezelfde transactie als het `ALTER TYPE`; audit regels 150-153 correct vertaald). `CREATE TYPE` idempotent via DO-blok met `duplicate_object`-vangst (Postgres kent geen `CREATE TYPE IF NOT EXISTS` — correct alternatief). Backfill is defensief (`CASE privacy::text ... ELSE 'public'`) met rowcount-verificatie die hard stopt bij mismatch en offline mode (`--sql`, geen rowcount) correct skipt. Downgrade compleet (index, kolommen, `DROP TYPE IF EXISTS visibility_enum`); het achterlaten van de zes `content_type_enum`-waarden is een gedocumenteerde, technisch correcte keuze (Postgres kan enum-waarden niet verwijderen zonder type-recreatie). Finesses: `print()` i.p.v. logger in de migratie is acceptabel voor alembic-stdout; de rowcount-check dekt niet het theoretische geval dat rijen *tussen* de UPDATE en de COUNT worden geinsert (beide in dezelfde transactie, dus onder standaard isolation geen issue — geen bevinding).
2. **Casing-afwijking (adversarial getoetst)** — De redenering klopt volledig met de bestaande code (zie B). Gezocht naar plekken waar lowercase wél verwacht wordt: (a) geen raw SQL in `src/` die `content_type_enum`-waarden als string filtert (`grep` op `'story'`/`'STORY'`/literal filters: alleen hits in de model-definitie en Pydantic-schemas); (b) de Pydantic-schemas (`schemas.py:35,60,99,149`) gebruiken `Literal["story", ...]` — dat is het API-contract op `.value`-niveau en is ongewijzigd consistent; (c) bestaande endpoints filteren op enum-objecten (`FoundationContent.privacy.in_(privacy_filter)`, `content.py:67`), nooit op strings. De `visibility_enum` (lowercase + `values_callable`, `foundation_content.py:168-182`) volgt exact het `PortalRole`/`EducationalRole`-precedent (`foundation_content.py:331-342, 498-508`). Conclusie: niets breekt; de afwijking is de enige correcte implementatie.
3. **Model** — `values_callable=lambda e: [m.value for m in e]` correct; `server_default="public"` aanwezig naast Python-side `default=Visibility.PUBLIC` (beide geverifieerd via `sa_inspect` in de nieuwe unit-test én via `information_schema` op de echte DB); index zowel in `__table_args__` (`foundation_content.py:136`) als in de migratie (`20260910...:141-144`) met identieke naam en kolomvolgorde. `target_age_group` bewust String(50) geen enum (O4) — verdedigbaar.
4. **Tests** — Betekenisvol: offline-SQL-tests dekken het migratiepad zelf (niet alleen het model-schema via create_all — dat was de historische blinde vlek), inclusief downgrade-asserties en de negatieve assertie dat de downgrade `content_type_enum` niet aanraakt. De nieuwe integratietests (enum-labels, kolom-nullability + default, index-definitie) zijn tegen de echte DB geverifieerd groen. Instantiatie-tests bewijzen de Python-default. Zwakte: de offline-SQL-fixture *skipt* i.p.v. faalt als alembic offline niet draait (zelfde patroon als BE-MIG-013; LOW-3).
5. **Regels/conventies** — Geen non-ASCII, geen `datetime.now()`, ruff + mypy groen, ID-REGISTRY bijgewerkt met eerlijke afwijkings-documentatie, DoD-items van de spec allemaal aantoonbaar afgevinkt.

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| MEDIUM (pre-existing, niet door deze branch) | `tests/integration/foundation/test_migrations.py:487` | `assert "code " not in row[0]` faalt altijd: de substring `'code '` zit in de index-NAAM (`... idx_ea_tenant_code ON public.educational_access ...`). De test bewijst dus nooit wat hij beweert te bewijzen (dat de index op `code_hash` zit en niet op een `code`-kolom) en is bovendien structureel rood. Bevestigd identiek falend op `develop` (eigen worktree-run, 22.2s) — NIET veroorzaakt door BE-MIG-014; deze branch raakt de test niet. | Aparte fix, niet in deze branch: assert op het kolomgedeelte van de indexdef, bv. `cols = row[0].split("(")[-1]` en daarin `"code_hash" in cols and "code," not in cols`, of parse via `pg_get_indexdef` met kolomlijst. Advies: eigen ticket; CI die deze file blokkerend draait is nu rood of skipt hem. |
| MEDIUM (toekomstrisico, nu onbereikbaar) | `src/core/api/v1/foundation/content.py:57-67` i.r.t. spec Sprint D | De publieke archief-lijst filtert op `privacy`, niet op `visibility`. Vandaag is dat veilig (geverifieerd: `FoundationContentCreateRequest` heeft geen `visibility`-veld en de `type`-Literal in `schemas.py:99` sluit alle zes nieuwe types uit — er kan via de API geen edu-content ontstaan). Maar de kern-eis uit audit N-2 ("edu NOOIT in het publieke archief") wordt door het datamodel alleen *mogelijk* gemaakt, niet *afgedwongen*: zodra Sprint D edu-content kan aanmaken terwijl `content.py` op `privacy` blijft filteren, verschijnt edu-content met default `privacy=PUBLIC` gewoon in het publieke archief. | Leg in de BE-EP-039-spec als hard acceptatiecriterium vast: publieke endpoints filteren op `visibility == 'public'` (niet `privacy`), met een integratietest "edu-content niet in publieke lijst/detail/map". Overweeg daarnaast een DB-niveau CHECK/trigger of in elk geval een architecture-test die deze invariant bewaakt. |
| LOW | `src/core/models/foundation_content.py:165-182` | Tijdelijke dubbele administratie: `privacy` en `visibility` lopen semantisch door elkaar (PUBLIC↔public, COMMUNITY↔community) tot de opruim-migratie van `privacy` er komt. Die opruim-migratie heeft geen ID, eigenaar of sprint. Verdubbelde velden zonder exit-plan worden permanent. | Maak een follow-up-ID aan voor de `privacy`-deprecatie/opruim en verwijs ernaar vanuit de spec ("Out of scope" noemt hem wel, maar zonder tracking). |
| LOW | Migratie `20260910...:141-144` | `op.create_index` zonder `CONCURRENTLY` (kan niet binnen alembic-transactie; blokkeert kortstondig writes). Nu irrelevant (tabel is klein), maar dit bestand wordt het copy-paste-sjabloon voor toekomstige migraties op een dan grote `foundation_content`. | Geen actie nu; neem in de database-regels (`.claude/rules/database.md` of het lokale equivalent) op dat index-migraties op grote tabellen een aparte niet-transactionele migratie met `CONCURRENTLY` vereisen. |
| LOW | `tests/unit/test_be_mig_014_offline_sql.py:51-55` | De offline-SQL-fixture doet `pytest.skip` als alembic offline niet draait. In een stukke CI-omgeving verdwijnen deze 10 asserts dan geruisloos uit het signaal. (Zelfde patroon als BE-MIG-013; consistent, maar zwak.) | Overweeg skip alleen bij een expliciete env-flag, of markeer de skip als xfail-strict zodat stille regressie zichtbaar blijft. |

## F. Ontbrekende items

- Fix voor de pre-existing testbug in `test_migrations.py:487` (MEDIUM-1) — hoort niet in deze branch, maar moet wél een eigen ticket krijgen; hij staat nu structureel rood.
- Follow-up-ID voor de `privacy`-opruim-migratie (LOW, zie E).
- Harde Sprint-D-eis + test voor "edu-content nooit in publieke archief-endpoints" (MEDIUM-2) — moet in de BE-EP-039-spec, niet hier.

Geen ontbrekende items binnen de scope van BE-MIG-014 zelf: alle DoD-punten uit de spec zijn aantoonbaar afgerond (roundtrip groen, backfill geverifieerd met testdata, 1 head, unit-tests groen, ruff/mypy groen, ID-REGISTRY bijgewerkt, review aanwezig — dit document).

## G. Verbeterde codevoorstellen

Voor de pre-existing testbug (aparte fix):

```python
async def test_educational_access_tenant_code_index_on_code_hash(self, postgres_session):
    result = await postgres_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'educational_access' "
            "AND indexname = 'idx_ea_tenant_code'"
        )
    )
    row = result.fetchone()
    assert row is not None
    assert "UNIQUE" in row[0]
    columns_part = row[0].rsplit("(", 1)[-1].rstrip(")")
    assert "tenant_id" in columns_part
    assert "code_hash" in columns_part
    # er is geen kale 'code'-kolom; de naam-match op 'code ' mag alleen
    # uit de indexnaam komen, niet uit de kolomlijst
    assert "code," not in columns_part and columns_part.strip() != "code"
```

Voor Sprint D (in de BE-EP-039-spec opnemen als acceptatiecriterium):

```python
# publieke lijst: filter op visibility, niet privacy
.where(
    FoundationContent.tenant_id == tenant.id,
    FoundationContent.status == ContentStatus.APPROVED,
    FoundationContent.visibility == Visibility.PUBLIC,  # edu lekt nooit mee
)
# + integratietest: seed content met visibility=EDU -> afwezig in list/detail/map
```

## H. Release-oordelen

- Bouw/implementatie: **ja** (migratie-roundtrip, backfill en ORM-serialisatie onafhankelijk bewezen op echte Postgres).
- QA/geautomatiseerd testen: **ja** voor deze scope; de pre-existing rode test in hetzelfde bestand moet als los ticket weg — hij ondermijnt het vertrouwen in de hele file.
- LLM-training: **ja** — de migratie is een schoolvoorbeeld van correcte Postgres-enum-behandeling (autocommit, idempotentie, casing-documentatie).
- Integratorhandleiding / spec: **ja**; de spec is na implementatie consistent met de code (casing-afwijking is in migratie-docstring, model-commentaar én ID-REGISTRY gedocumenteerd).

## Wat wél klopt

- De casing-afwijking is niet alleen verdedigbaar maar **de enige correcte keuze**, en hij is op drie plekken consistent gedocumenteerd (migratie-docstring, model-commentaar, ID-REGISTRY). De audit-intentie (lowercase API-waarden) blijft intact via de str-enum `.value`'s en de Pydantic-Literals.
- Autocommit-blok + `IF NOT EXISTS`/duplicate_object-vangst is idempotent **bewezen** (twee upgrades over dezelfde DB gedraaid, tweede run no-op zonder fout).
- Backfill is defensief (`ELSE 'public'`), geverifieerd met eigen testdata (PUBLIC→public, COMMUNITY→community, exacte rowcount gelogd) én beveiligd met een harde stop bij rowcount-mismatch.
- Downgrade is compleet en roundtrip-bewezen; het achterlaten van onverwijderbare enum-waarden is expliciet en correct gedocumenteerd.
- Offline-SQL-tests dekken het migratiepad zelf (upgrade én downgrade), niet alleen het create_all-schema — precies de dekking die de 22 onopgemerkte failures uit OP-11 hadden voorkomen.
- Nieuwe integratietests pinnen het echte DB-contract vast (enum-labels, NOT NULL + server_default-tekst, indexdef) in plaats van alleen het model.
- Scope-discipline: exact de zes audit-waarden, geen verzonnen extras (O5); geen endpoint-wijzigingen meegepakt; `alembic heads` = 1.
- Kwaliteitsgates: ruff groen, mypy groen, 0 non-ASCII in nieuwe code, geen `datetime.now()`, geen scope-kruip.

## Devil's Advocate — waarom faalt deze oplossing in de toekomst?

1. **De veiligheid van de subsidie-eis rust nu op een belofte, niet op afdwijing.** Audit N-2 eist dat edu-content NOOIT in het publieke archief verschijnt. Na deze migratie is dat alleen *mogelijk*, niet *gegarandeerd*: het publieke endpoint filtert nog op `privacy` en de database kent geen constraint die `visibility='edu'` uit publieke resultaten houdt. Als Sprint D onder tijdsdruk de filter-switch "even later" doet, of een toekomstige developer een nieuw publiek endpoint bouwt dat dit patroon kopieert, lekt edu-content naar buiten — met directe subsidie-/reputatieschade. De mitigatie (hard acceptatiecriterium + test in BE-EP-039) staat nog nergens vast.
2. **Het dual-casing-model is een permanente valkuil voor raw SQL en BI.** `content_type_enum` spreekt hoofdletters, `visibility_enum` lowercase; wie straks in Metabase, een datadump of een handmatige migratie `WHERE type = 'video'` schrijft, krijgt stil 0 rijen. De integratietest pinnen de labels wel vast, maar beschermt alleen de CI, niet de mens met psql. De les van BE-MIG-013 (alles naar lowercase `.value`'s migreren) is bewust alleen op nieuwe enums toegepast; `content_type_enum` blijft een inconsistentie-eiland dat elke toekomstige raw-SQL-schrijver opnieuw moet kennen.
3. **Enum-waarden zijn een eenrichtingsweg.** De zes hoofdletter-labels kunnen nooit meer uit Postgres. Als Sprint D of een latere content-strategie `art_documentation` hernoemt of splitst, blijven de dode labels voor altijd in het type staan en elke `pg_enum`-inspectie vervuilen. De keuze is nu goed gedocumenteerd, maar de documentatie verdwijnt uit beeld zodra dit bestand uit het actieve geheugen van het team zakt.
4. **`server_default 'public'` faalt open, niet dicht.** Elk toekomstig insert-pad (bulk-import, OAI-PMH-harvest in Sprint E, een management-commando) dat `visibility` vergeet, publiceert stil naar het meest open kanaal. Voor een archief met privacy- en subsidiegevoelige content is fail-open de verkeerde kant op; de veilige kant (expliciete keuze afdwingen op app-niveau, geen stille default) is nu alleen via conventie geborgd.
5. **`privacy` + `visibility` dubbel veld zonder exit-plan wordt domeinvervuiling.** Tot de opruim-migratie komen ze overeen (PUBLIC≈public, COMMUNITY≈community); daarna gaan ze gegarandeerd divergeren zonder dat iemand het merkt, want geen test assert de correspondentie. "Welk veld is leidend?" wordt een vraag die elke nieuwe developer opnieuw moet beantwoorden — precies het soort technische schuld dat als "tijdelijk" begint.
6. **`target_age_group` als vrije String(50) verzamelt vuil vóór de validatie bestaat.** Sprint D moet de metadata-schema's leveren; elke rij die vóór die validatie wordt geschreven ("12-14", "groep 7/8", "12 t/m 14 jaar") is toekomstige opschoningsdata. Er is geen mechanisme dat schrijven vóór Sprint D voorkomt.

Punten 1, 4 en 5 zijn met kleine, expliciete acties af te dekken (Sprint-D-acceptatiecriterium, follow-up-ID voor `privacy`-opruim, en het dual-casing als bekende inconsistentie vastleggen in de database-regels); de migratie zelf is technisch degelijk en volledig geverifieerd.

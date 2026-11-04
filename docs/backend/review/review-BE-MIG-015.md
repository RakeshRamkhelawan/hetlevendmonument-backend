# Review BE-MIG-015: Migratieketen draait vanaf een lege database naar head (edu_alignment defensief)

STATUS: APPROVED WITH MINOR GAPS

**Reviewer:** onafhankelijke Gate 2-review-agent (code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; geen voorkennis van de fix; alles zelf geverifieerd met commando's op een echte PostgreSQL, niet op aannames.
**Datum:** 2026-09-24
**Scope:** commit `fd6141aa5` op branch `iter/wk1-migratieketen` (worktree hlm-wk1-migratieketen) -- `src/alembic/versions/20260909_adr029_edu_alignment.py` (herscheving), `tests/integration/foundation/test_migratieketen_verse_db.py` (nieuw), spec `docs/backend/features/BE-MIG-015-migratieketen-verse-db.md`. Meeglezen: `20260917_modelkolommen_zonder_migratie.py` (ongemoeid, maar inhoudelijk de helft van het verhaal), `.claude/rules/database.md`, `20260824_adr029_portal_v1.py`, `20260915_adr029_audit_hardening.py`, het model `src/core/models/foundation_content.py`.

---

## B. Eindoordeel

APPROVED WITH MINOR GAPS -- de kernclaim is op echte PostgreSQL bewezen: `alembic upgrade head` op een verse database slaagt (zelf gedraaid, exit 0), de eindtoestand van educational_access/study_collections klopt kolom-voor-kolom met wat de spec belooft, en beide roundtrips (rond edu_alignment, en dieper door kolomdrift's eigen downgrade heen) zijn groen. De bewijsvoering voor het herschrijven van een bestaande migratie ("hij kon in deze ketenpositie nooit hebben gedraaid") houdt stand onder vijandige toetsing, met een benoemde restkant (bewijs van een negatief, deels secondhand). Twee gaps: (1) het model eist `ondelete="CASCADE"` op de study_collections-FK maar de keten levert een FK zonder CASCADE -- door kolomdrift veroorzaakt, door deze fix bewust cementeerd, en nergens als drift geregistreerd; (2) de twee alternatieve codepaden (alleen-`code`, alleen-`code_hash`) zijn ongetest -- de integratietest oefent alleen het beide-kolommen-pad. Beide zijn klein te dichten en blokkeren de merge niet.

## C. Samenvatting

De fix doet wat hij claimt en de spec is eerlijk. Zelf gemeten op PostgreSQL 15.18 (testserver poort 5455, wegwerp-database `review_d_mig015_x7q`, na de metingen gedropt):

- `alembic -c src/alembic.ini upgrade head` vanaf LEEG: **exit 0**, `alembic_version = 20260924_merge_adr029_tenant_llm_heads`.
- Eindtoestand educational_access: alleen `code_hash` varchar(64) NOT NULL (geen `code`); precies EEN unieke sleutel op code_hash (`uq_educational_access_code_hash`, die van kolomdrift); `idx_ea_tenant_code` UNIQUE op (tenant_id, code_hash).
- Eindtoestand study_collections: alleen `educational_access_id` integer NOT NULL (geen `access_code`); FK naar educational_access(id); `ix_study_collections_educational_access_id` aanwezig; `idx_sc_tenant_code` op (tenant_id, educational_access_id).
- Roundtrip 1: `downgrade 20260917_kolomdrift` -> beide kolommen terug (`code` naast `code_hash`, `access_code` naast `educational_access_id`), kolomdrift-objecten onder kolomdrift-namen intact; `upgrade head` -> eindtoestand weer exact.
- Roundtrip 2: `downgrade 20260915_rls_rest` (dus DOOR kolomdrift's eigen downgrade heen) -> exit 0; `upgrade head` -> exit 0. Dit bewijst dat het niet-hernoemen van kolomdrift's constraint-namen werkt zoals de redenering zegt.
- Nieuwe integratietest: **6 passed in 121.27s** (spec meldt 59.75s; zelfde uitslag, ander tempo -- geen discrepantie van betekenis).
- `tests/unit/database/test_agentic_alembic_chain_complete.py` + `tests/unit/test_be_mig_013_offline_sql.py`: **10 passed in 18.49s** (met `env -u GIT_CONFIG_VALUE_0 -u GIT_CONFIG_KEY_0`, zoals de opdracht waarschuwde).
- `alembic heads`: exact 1 (`20260924_merge_adr029_tenant_llm_heads`).
- ruff op beide gewijzigde bestanden: All checks passed. mypy op het migratiebestand: no issues found. Beide bestanden + spec: ASCII-only (zelf gedecodeerd).
- Oude versie bekeken via `git show fd6141aa5^`: onvoorwaardelijke `alter_column(code, new_column_name="code_hash")` en onvoorwaardelijke `add_column(educational_access_id)` bevestigd -- met kolomdrift ervoor is DuplicateColumn deterministisch, geen kwestie van timing.
- Claim "`MigrationContext.is_offline_mode` bestaat niet op alembic 1.13.1" nagetrokken: klopt (`'is_offline_mode' in dir(MigrationContext)` -> False); de MockConnection-detectie is dus geen workaround voor een bestaande API.
- Herkoppeling geverifieerd: merge-commit `d2224bc53` (2026-09-18) introduceerde `down_revision = "20260917_kolomdrift"` in edu_alignment; ketenbeeld in de spec klopt met `alembic history`.

## D. Bevindingen per categorie (samengevat)

1. **Correctheid** -- Kern volledig geverifieerd (zie C). Een semantische drift: het model declareert `ForeignKey("educational_access.id", ondelete="CASCADE")` (foundation_content.py:548), maar kolomdrift maakte de FK zonder ondelete, en edu_alignment laat kolomdrift's FK bewust staan. Gemeten in het eindschema: `FOREIGN KEY (educational_access_id) REFERENCES educational_access(id)` -- geen CASCADE. Het oude/offline pad had wel CASCADE gemaakt. ORM-cascade op relationship-niveau kan dit deels maskeren, maar de database handhaaft NO ACTION (MEDIUM-1).
2. **Migratie-hygiene (database.md)** -- "Never modify an existing migration" is hier overtreden, maar met een bewijsvoering die de regel honoreert in geest: de regel beschermt omgevingen die de migratie al hebben gedraaid, en de fix bewijst (a) verse DB faalde, (b) staging miste code_hash op 2026-09-17 (kolomdrift-docstring) dus edu_alignment had daar nooit gedraaid -- had hij dat wel, in de oude positie, dan zou code_hash er juist WEL hebben gestaan, (c) productie niet ingericht. De redenering is intern consistent en ik heb hem op elk schakelbaar punt nagetrokken. Restkant: het is een bewijs van een negatief en de staging-schakel is secondhand (zie LOW-2).
3. **Overlap-dekking** -- Alle vijf de gedocumenteerde overlaps zitten erin en zijn in de eindtoestand-meting bevestigd. Zelf gezocht naar verdere overlaps tussen 20260917 en 20260909 EN daarbuiten: alleen 20260824 (maakt de originele objecten), 20260915_adr029_audit_hardening (alleen FORCE RLS, geen kolom-DDL) en 20260910_adr029_sprint_c_datamodel (raakt de tabellen niet) komen in aanraking met deze tabellen. Geen zesde overlap gevonden. De naam-onafhankelijke FK-check (`_fk_op_kolom`) en de defensieve unieke-constraint-loop zijn de juiste abstracties.
4. **Transactie-veiligheid** -- Introspectie loopt via `sa.inspect(op.get_bind())` op dezelfde connectie/transactie als de DDL; Postgres transactionele DDL rolt bij elke fout de hele revisie terug en alembic_version blijft consistent. Geen stille rollback mogelijk: een mislukte statement abort de transactie en alles daarna faalt luid. Offline-guards (`_is_offline()` via MockConnection, geverifieerd tegen alembic 1.13.1) voorkomen introspectie op een MockConnection; short-circuit `not online or ...` in downgrade is correct.
5. **Downgrade-semantiek** -- Klopt met de nieuwe werkelijkheid: "de toestand van voor deze migratie" is sinds 2026-09-18 de post-kolomdrift-toestand, en dat is precies wat de nieuwe downgrade terugzet (gemeten in roundtrip 1 en 2). Het theoretische restgeval (database die edu_alignment in de OUDE positie toepaste en nu door deze revisie heen downgradet) levert een afwijkende toestand op (LOW-1); die databases zijn gemeten afwezig.
6. **Tests** -- De nieuwe integratietest is betekenisvol: echte verse DB, eindtoestand op catalogus-niveau (niet via create_all), roundtrip als regressie-bewaker, xdist-veilige databasenaam. Gaten: alleen het beide-kolommen-pad wordt online geoefend; het rename-pad (alleen `code`) en het al-aligned-pad (alleen `code_hash`) zijn online ongetest (MEDIUM-2). De CASCADE-afwijking wordt door geen test bewaakt.
7. **Regels** -- ASCII-only geverifieerd, ruff/mypy groen, heads = 1, keten-pin ongewijzigd en groen, geen nieuwe migratie toegevoegd (juist: een bovenop-migratie kan een mid-chain DuplicateColumn niet repareren).

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| MEDIUM | `20260917_modelkolommen_zonder_migratie.py:182-188` + `20260909_adr029_edu_alignment.py:_study_collections_online` + model `foundation_content.py:548` | Het model eist `ondelete="CASCADE"` op study_collections.educational_access_id; de keten-eindtoestand heeft een FK ZONDER cascade (kolomdrift maakte hem zo; edu_alignment laat hem bewust staan om kolomdrift's downgrade niet te breken). Gemeten: `pg_get_constraintdef` toont geen CASCADE. Het oude/offline pad maakte wel CASCADE. Gedragsverschil: verwijderen van educational_access met gekoppelde study_collections faalt nu met een FK-violation in plaats van te cascaden. Pre-existing in kolomdrift, maar DEZE fix is het moment waarop het permanent wordt. Nergens geregistreerd: niet in de spec ("Open aannames" noemt alleen constraint-NAMEN), niet als OP-item. | Registreer expliciet als drift (OP-150 of eigen OP-item) met de beoogde eindkeuze (CASCADE toevoegen in een nieuwe migratie die de FK onder kolomdrift-compatibele naam dropt+hermaakt, of het model aanpassen). Een nieuwe migratie KAN dit wel repareren -- de keten bereikt head weer. Minimaal: benoem in de spec dat de FK-cascade bewust afwijkt. |
| MEDIUM | `tests/integration/foundation/test_migratieketen_verse_db.py` | Alleen het beide-kolommen-pad (de werkelijke keten) wordt online geoefend. `_educational_access_rename_pad` online (alleen `code` aanwezig) en het al-aligned-pad (alleen `code_hash`) zijn online ongetest; de offline-test pint alleen SQL-strings, voert ze niet uit. Een regressie in die paden wordt door niets gevangen. | Goedkope dekking: twee extra scenario's in de integratietest op een wegwerp-DB -- (1) keten tot en met 20260824 + handmatig de tussenliggende revisies stempelen tot vlak voor edu_alignment, dan edu_alignment alleen draaien (rename-pad); (2) na een geslaagde upgrade head edu_alignment nogmaals "draaien" via directe aanroep of een tweede upgrade (al-aligned-pad is dan de no-op). Of: de paden expliciet als "alleen offline/blind relevant" bestempelen en de online-takken verwijderen als ze toch onbereikbaar zijn. |
| LOW | module-docstring + spec "Risico's" | Een database die edu_alignment in de OUDE positie (pre-2026-09-18) toepaste en nu door deze revisie heen zou DOWNGRADEN, krijgt de nieuwe downgrade-semantiek: die laat code_hash/educational_access_id staan terwijl de werkelijke oude pre-toestand die kolommen niet had. De spec dekt de upgrade-kant ("voert de nieuwe inhoud nooit uit") maar niet de downgrade-kant. Zulke databases zijn gemeten afwezig, dus theoretisch. | Een zin in de migratie-docstring: de downgrade gaat uit van de post-kolomdrift pre-toestand en is niet bedoeld voor databases uit de oude ketenpositie. |
| LOW | bewijsvoering "nooit gedraaid", staging-schakel | Het bewijs dat edu_alignment nooit op staging draaide berust op kolomdrift's eigen docstring-meting van 2026-09-17 (secondhand voor deze review; niet meer reproduceerbaar zonder staging-toegang). De redenering is intern consistent (had edu_alignment daar gedraaid, zou code_hash er juist wel staan), maar het blijft een bewijs van een negatief over omgevingen zonder register. | Geen code-actie. Voor de toekomst: bij herkoppelingen van migraties een expliciete `alembic current`-dump per omgeving vastleggen als artefact, zodat de volgende review het niet hoeft af te leiden. |
| LOW | spec "Gemeten verificatie-output" | Spec meldt "6 passed in 59.75s"; ik mat 121.27s op dezelfde testserver. Zelfde uitslag, ander tempo; geen inhoudelijke discrepantie, maar de spec presenteert het getal zonder bandbreedte. | Niets; alleen benoemd zodat niemand de 59.75s als norm gaat gebruiken in CI-timeout-beslissingen. |

## F. Ontbrekende items

- Registratie van de FK-cascade-drift (MEDIUM-1): nu onzichtbaar voor OP-150/alembic-check-opruiming.
- Online-testdekking voor het rename-pad en het al-aligned-pad (MEDIUM-2).
- Docstring-zin over downgrade-semantiek versus de oude ketenpositie (LOW-1).

## G. Verbeterde codevoorstellen

Geen code-wijziging nodig voor merge. Voor de opvolging van MEDIUM-1 (in een NIEUWE migratie, na merge):

```python
# CASCADE alsnog op de bestaande FK -- naam behouden zodat kolomdrift's
# downgrade hem blijft herkennen:
op.drop_constraint(
    "fk_study_collections_educational_access_id", "study_collections", type_="foreignkey"
)
op.create_foreign_key(
    "fk_study_collections_educational_access_id",
    "study_collections",
    "educational_access",
    ["educational_access_id"],
    ["id"],
    ondelete="CASCADE",
)
```

Voor MEDIUM-2: zie de twee scenario's in E; beide passen in het bestaande fixture-patroon van `test_migratieketen_verse_db.py` (wegwerp-DB + `_alembic`-helper).

## H. Release-oordelen

- Bouw/implementatie: **ja** -- de markt-blokker is aantoonbaar weg; keten van leeg naar head gemeten groen.
- QA/geautomatiseerd testen: **ja** -- de integratietest bewaakt precies het defect; de twee ongeteste paden zijn MINOR, geen blokkade.
- LLM-training: **ja**.
- Integratorhandleiding / spec: **ja, na opname** van de cascade-drift in "Open aannames" (een regel volstaat).

## Wat wel klopt

- De strategie-keuze is de enige werkbare: kolomdrift bijsnijden vereist bewijs van een negatief dat er niet is; een nieuwe migratie bovenop de keten kan een mid-chain DuplicateColumn niet repareren (de keten bereikt de kop nooit); edu_alignment herschrijven raakt aantoonbaar geen enkele omgeving die hem al heeft.
- Alle vijf de overlaps afgedekt en in de gemeten eindtoestand bevestigd: exact een unieke sleutel op code_hash, exact een FK op educational_access_id, beide model-indexen, composite unique index op (tenant_id, code_hash).
- Het niet-hernoemen van kolomdrift's constraint-namen is bewezen correct: roundtrip 2 draaide kolomdrift's eigen downgrade groen, wat alleen kan als die zijn objecten onder zijn eigen namen terugvindt.
- Offline-gedrag bewust en bewezen behouden: BE-MIG-013's gepinde SQL-test ongewijzigd groen; de MockConnection-detectie is nodig (is_offline_mode bestaat niet op alembic 1.13.1 -- nagetrokken).
- Naam-onafhankelijke FK-detectie (`_fk_op_kolom`) in plaats van op twee bekende namen checken -- dat is de defensieve vorm die hier hoort.
- De count-checks na DELETE (RLS-eigenaar-vereiste) zijn ongemoeid; fail-loud boven stille no-op blijft gehandhaafd.
- Spec dekt code en metingen een-op-een: elk acceptatiecriterium dat "[gemeten: GROEN]" zegt, heb ik onafhankelijk groen gemeten.
- De nieuwe integratietest test de keten zoals migraties hem bouwen, niet zoals create_all hem bouwt -- precies de blinde vlek die dit defect negen maanden onzichtbaar maakte.

## Devil's Advocate -- waarom faalt deze oplossing in de toekomst?

1. **Het bewijs van een negatief is het hele fundament.** "Deze migratie heeft nergens gedraaid" rust op: een docstring-meting van staging (2026-09-17, secondhand), een afwezige productie, en een deterministisch faalbewijs op verse databases. Er is geen register van omgevingen. Een vergeten CI-snapshot, een lang-levende dev-database of een pilot-installatie die edu_alignment in de oude positie heeft toegepast, bestaat niet volgens dit bewijs -- maar als hij toch bestaat, sterft zijn volgende upgrade in kolomdrift (DuplicateColumn op code_hash), en DEZE fix kan hem dan niet meer redden: edu_alignment draait daar nooit opnieuw. De fix verandert niets aan dat scenario, maar de review van het volgende migratieconflict zal naar dit precedent wijzen.
2. **"Never modify" is nu "never modify, tenzij je kunt argumenteren dat niemand het draaide".** De regel in database.md had zijn kracht in zijn absolutheid; deze commit introduceert een redeneer-uitzondering. De redenering hier is degelijk, maar de volgende auteur zal hem goedkoper voeren. Zonder een vast protocol (omgevingsinventaris + bewijsartefacten) slijt de regel.
3. **De CASCADE-drift wordt een landmijn.** Het model zegt CASCADE, de database zegt NO ACTION. De eerste keer dat iemand via de ORM een educational_access met study_collections verwijdert en de relationship-cascade om wat voor reden dan ook niet engage (bulk delete, raw SQL, toekomstige cleanup-job), krijgt hij een IntegrityError die niemand begrijpt, want "de migraties en het model zijn toch aligned sinds BE-MIG-015". Ze zijn dat niet -- op dit ene punt, bewust, ongedocumenteerd.
4. **Twee van de vier paden zijn ongeteste code.** Het rename-pad en het al-aligned-pad bestaan voor toestanden die "in deze keten niet voorkomen". Dat is vandaag waar, maar het zijn precies die paden die een toekomstige herkoppeling of een handmatig gepatchte database zal activeren -- en niets in de suite wordt dan rood. Defensieve migratielogik zonder test is optimisme met introspectie.
5. **De test bewaakt de keten, niet de wereld.** De integratietest vertrouwt op een mens die SANSKRITISETU_TEST_DATABASE_URL zet (terecht, OP-243), dus in CI zonder die variabele draait hij helemaal niet. Als CI deze test niet blokkerend draait, is het regressie-bewijs een eenmalige meting. De volgende kolomdrift-achtige migratie introduceert hetzelfde defect opnieuw, en het duurt weer een markt-review om het te vinden.

Geen van deze punten blokkeert de merge: het defect is gemeten weg en de restkanten zijn benoemd met een eigenaar-loze maar concrete opvolgroute (E en G).

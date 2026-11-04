# BE-AGT-044 -- De eerste tool die echt resolvet (`query_hr_database`)

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-044 |
| Datum | 2026-08-02 |
| ADR | ADR-036 D10 stap 3; AVG art. 16/17; AI Act art. 14 |
| Sprint | ADR-036 Fase B / Fase 2 / dag 3 |
| Rode tests | `bf937547` (9 rood) |

---

## 1. Wat dit oplost

Van de 27 tools die in 135 skill-manifesten staan gedeclareerd, resolveerde er tot vandaag
**nul** (BE-AGT-039 F1). Een skill die er een probeerde kreeg "Unknown tool category" terug.
`query_hr_database` is de eerste die werkt, en daarmee is de keten voor het eerst end-to-end
aantoonbaar: manifest-allowlist -> D5-denylist -> Council -> permissieprofiel ->
risicoclassificatie -> registry -> tenant-gescoped lezen -> resultaat terug.

`KNOWN_UNRESOLVED_BROKER_TOOLS` verliest zijn eerste regel.

## 2. De vondst die de dag herdefinieerde: er is geen HR-data

Het contract in BE-AGT-039 par. 3 beschrijft een tool die "medewerker-, rol- en
trainingsgegevens" leest. **Die data bestaat niet.** Alle tabellen nagelopen: geen
`employees`, `skills`, `trainings`, `competencies`. Wel `users`, `roles` en `role_permissions`
(RBAC, tenant-gescoped); de `learning_*`-tabellen gaan over agent-leren (ADR-022), niet over
opleidingen van mensen.

De vlaggenschiptaak uit de evaluatieset van dag 1 -- *"Welke medewerkers in afdeling Finance
missen de certificering IFRS?"* -- is daarmee onbeantwoordbaar. Afdeling en certificering
bestaan allebei niet.

**Besluit Rakesh (2026-08-02):** bouwen over de data die er is, naam blijft. Het ontbrekende
HR-domein staat als **OP-26** en is een productbeslissing.

## 3. Wat de tool doet

```json
{"success": true,
 "roles": [{"role": "Finance Analyst", "user_count": 12, "active_count": 11}],
 "role_count": 1, "truncated": false, "applied_limit": 50, "applied_offset": 0}
```

| Parameter | Gedrag |
| --- | --- |
| `role` | Ondersteund. Moet een string van maximaal 50 tekens zijn, anders geweigerd |
| `limit` / `offset` | Ondersteund; niet-gehele of negatieve waarden worden **geweigerd**, boven het maximum wordt afgekapt en dat is zichtbaar via `applied_*` |
| `department` | **Geweigerd** -- bestaat niet in het datamodel |
| `employee_id` | **Geweigerd** -- deze tool geeft geen individuele personen terug |

Niets wordt stil genegeerd. Een genegeerd filter levert meer terug dan gevraagd terwijl de
aanroeper denkt dat er gefilterd is; voor een adviserende skill die daarop een advies baseert
is dat een stille onwaarheid, en dat is precies de klasse fouten die deze ADR blootlegt.

## 4. Waarom tellingen en geen personen

Alles wat een tool teruggeeft belandt in **drie** bewarende sinks: de event bus
(`_publish_tool_event`), de leeropslag (`learning_event_handler._record_tool_event` schrijft
`payload` en `result` als `observation_data`) en de auditketen
(`ToolAuditRepository.log_execution`), die per ADR-019 onuitwisbaar is.

Rij-data zou dus persoonsgegevens in een leeropslag zetten -- dezelfde klasse als de
audit-keten-bevinding uit de Gate 2-review van BE-AGT-042, via een kanaal waar niemand naar
had gekeken. Voor een gap-analyse zijn aantallen per rol bovendien bruikbaarder dan een
namenlijst.

Die keten is vandaag **latent**: geen enkele aanroeper geeft een `event_publisher` mee, dus
`_publish_tool_event` keert direct terug. Dat maakt het juist gevaarlijk -- het is een
constructor-argument van live, en dan geldt het platformbreed. Vastgelegd als **OP-27**.

## 5. Tenantgrens

Drie lagen, en dat is geen overdaad:

1. **Expliciet op beide tabellen.** `user_roles` heeft zelf geen tenantkolom, dus filteren op
   alleen `Role.tenant_id` zou bij een vervuilde associatierij gebruikers van een andere
   tenant meetellen.
2. **De tenant komt uit de executiecontext**, niet uit de payload. De payload is de
   `json.loads` van een TOOL_CALL-directive en dus modeloutput. `execute_tool` overschreef
   `payload["tenant_id"]` weliswaar met de context, maar `context` is een **optionele**
   parameter: bleef hij weg, dan overleefde de door het model gekozen tenant tot in de
   WHERE-clause. Geen live aanroeper deed dat, maar een invariant die op gewoonte rust is geen
   invariant. De broker resolvet de tenant nu en geeft hem als los argument door; de
   payload-sleutel wordt eruit gefilterd.
3. **De ADR-004-hook blijft aan** en filtert als tweede laag mee.

### 5.1 Waarom niet `TenantFilterBypass` -- en wat dat stilletjes repareerde

De eerste opzet zette de auto-filter uit met `TenantFilterBypass`, zodat de isolatietest
mutatie-doodbaar bleef. Teruggedraaid na de Gate 2-review, om twee redenen: het venster
omvatte ook het opzetten van de sessie (een taak die daarin ontstaat erft `bypass=True`), en
het produceerde bij **elke** routineuze leesactie een WARNING "tenant filter DISABLED" --
een detectiesignaal tot ruis gedegradeerd.

De vervanging -- de tenant-ContextVar zetten en herstellen -- repareerde bovendien een bug die
in de SQLite-unittests onzichtbaar is. `users` heeft Postgres-RLS
(`20260522_add_rls_core_tables.py`), en `db_manager.get_session()` emit alleen
`SET LOCAL app.current_tenant` wanneer die ContextVar gezet is. De bypass-versie zette hem
nooit, dus **op PostgreSQL vanuit een worker zou de query nul rijen hebben teruggegeven en
`{"success": true, "roles": []}` hebben gemeld** -- exact de stille leegte die de oude
docstring beweerde te voorkomen.

De mutatie-doodbaarheid is overgenomen door een test op de **gecompileerde SQL**: die eist dat
beide tenant-predicaten en het soft-delete-predicaat erin staan. Dat is een sterkere borging
dan de runtime-test, want die zou nu door de omgevingsfilter gered worden.

## 6. AVG art. 17

`dsar_service` voert een wisverzoek uit als soft delete met respijtperiode (`is_active=False`,
`deleted_at` gezet). Zonder filter zou een ex-medewerker die om verwijdering vroeg de telling
blijven ophogen -- en dat getal belandt in de leeropslag. De query filtert daarom op
`User.deleted_at IS NULL`, met een eigen test en in de compiled-SQL-guard.

## 7. Twee defecten die deze tool zichtbaar maakte

**Een tool die zelf `{"success": false}` teruggaf, telde als geslaagd.** Zowel in `act()` als
in de broker. `act()` kende alleen excepties als fout, dus een tool die netjes de
gecontracteerde foutvorm teruggaf belandde in `results` -- en de OODA-lus rekende prana af
voor werk dat niet gebeurde. In de broker was `success=True` hardcoded, waardoor het
leersubsysteem een geweigerde aanroep als goed patroon zou leren en de ADR-019 hash-keten een
onwaar record zou vastleggen dat wel geldig geketend is. Dat laatste is erger dan een gat.

Beide zijn dezelfde bevinding die BE-AGT-039 F3 voor deelfouten oploste, maar die voor deze
vorm bleef staan -- onzichtbaar tot er een tool was die hem kon produceren. Let op de
reikwijdte: `local_registry` geeft `{"success": False}` voor "File not found" en "Access
Denied", dus dit verandert ook het gedrag van lokale tools. Bewust, en consistent met F3.

**De payload lekte op het foutpad.** De redactie zat eerst alleen op het succespad, terwijl
`except ToolBrokerException` en `except Exception` de payload verbatim publiceerden -- precies
wanneer er iets misgaat. Nu is er een enkel punt van controle vóór de `try`
(`src/core/tool_broker/redaction.py`), dat ook de auditregel dekt.

## 8. Trainingssamenvatting

**Flow 1 -- de piloot vraagt rolbezetting op**

- Actor: ALS-piloot-skill `skillsgaptraining`
- Voorwaarde: geldige initiator, tool in de manifest-allowlist, Council keurt goed
- Actie: de skill emit `TOOL_CALL: query_hr_database {"role": "Finance Analyst"}`
- Systeemreactie: tenant-gescoped tellingen per rol, gewiste gebruikers uitgezonderd
- Succes: `{"success": true, "roles": [...]}`
- Fout: bij een onbereikbare database een generieke melding; de details staan in het log
- Uitzonderingen: geen persoonsgegevens in de respons, ongeacht de vraag

**Flow 2 -- een filter dat niet bestaat**

- Actor: dezelfde skill
- Voorwaarde: het model vraagt om `department` of `employee_id`
- Actie: de tool wordt aangeroepen
- Systeemreactie: expliciete weigering met reden en verwijzing naar het open punt
- Succes: n.v.t.
- Fout: `{"success": false, "error": "filter '...' wordt niet ondersteund: ..."}`
- Uitzonderingen: geen. Stil negeren is uitgesloten

**Flow 3 -- een uitvoering zonder tenant in de context**

- Actor: een aanroeper die `context` weglaat
- Voorwaarde: n.v.t.
- Actie: `execute_tool` wordt aangeroepen
- Systeemreactie: de aanroep wordt geweigerd; de payload gaat geredigeerd de sinks in
- Succes: n.v.t.
- Fout: `ToolExecutionException`
- Uitzonderingen: geen -- de tenant mag nooit uit modeloutput komen

## 9. Tests

`tests/unit/tool_broker/test_hr_registry.py` -- 25 tests: resolutie via `execute_tool`,
tenant-isolatie (drie invalshoeken), gecompileerde SQL, AVG art. 17, geweigerde filters,
geen persoonsgegevens in respons en payload, foutpad-redactie, databasefout gelogd maar niet
doorgegeven, paginering, risicoclassificatie.

`tests/unit/als/test_agent_governance_hardening.py` -- de piloot doet via de echte ingang een
geslaagde tool-aanroep, plus de gestructureerde-faalvorm.

**Mutatie-getest, zes richtingen na het herontwerp:** tenantfilter, soft-delete-filter,
redactie-allowlist, redactie op het foutpad, pagineringsweigering, faalmelding in de broker.
Elk maakt exact de bijbehorende test rood.

## 10. Blast radius

`query_hr_database` staat in **15** manifesten, maar alleen `skillsgaptraining` heeft een
brokerprofiel in `config/tool_permissions.yml`. De ADR-015 default-deny houdt de andere 14
tegen. Die containment is nu het enige tussen een naam in een YAML en een echte leesactie op
de gedeelde `users`-tabel: wie het volgende profiel toevoegt, erft alles hierboven.

## 11. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/tool_broker/hr_registry.py` | nieuw -- de registry |
| `src/core/tool_broker/redaction.py` | nieuw -- payload-redactie per tool, platformbreed bedoeld |
| `src/core/tool_broker/service.py` | instantie, categoriecheck, dispatch, tenant uit de context, faalstatus, redactie op alle publicatiepunten |
| `src/core/als/agents/specialist_base.py` | gestructureerde toolfout telt als fout |
| `src/core/config/tool_risk_levels.yml` | `query_hr_database: medium` |
| `tests/architecture/test_tool_profile_namespaces.py` | uitzondering weg, `_is_executable` uitgebreid |
| `docs/adr/036-...md` | OP-26, OP-27 |

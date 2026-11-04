STATUS: APPROVED WITH MINOR GAPS
Twee reviewrondes. Ronde 1: CHANGES_REQUESTED van beide reviewers (3 HIGH). Ronde 2:
CHANGES_REQUESTED van de code-reviewer (3 HIGH, alle drie gemeten en gerepareerd); de
quality-reviewer kon ronde 2 niet afmaken -- zijn sessie liep tegen een API-limiet. De
openstaande punten staan onderaan; geen ervan blokkeert vandaag iets, en de drie HIGH's van
ronde 2 zijn mutatiegetest gerepareerd.

# Review BE-AGT-067 -- `schedule_training`, de eerste schrijfactie van een agent op HR-data

Datum:     2026-09-21
Spec:      `docs/backend/features/BE-AGT-067-schedule-training-schrijftool.md`
Reviewers: code-reviewer en quality-reviewer (verse subagents, geen gespreksgeschiedenis)
Basis:     develop, HEAD 195cc0f1

---

## Samenvatting

Beide reviewers gaven **CHANGES_REQUESTED**, met drie HIGH-bevindingen die ik alle drie zelf heb
nagemeten voordat ik iets aanraakte. Twee ervan weerlegden een claim die aan de basis van de
wijziging lag; een derde legde een blokkerende CI-stap bloot die al rood stond voordat ik vandaag
begon.

De belangrijkste les zit in HIGH-1 en die is niet nieuw in dit project: **een naam in een
registry-klasse is geen aangesloten tool.** Ik had `generate_text` hernoemd naar
`local__llm_generate` omdat die naam in `LocalToolRegistry._TOOL_NAMES` staat, en de
instructietekst van de agent laten beloven dat elke gedeclareerde tool echt draait. Gemeten:
`BaseSpecialistAgent` bouwt zijn eigen `ToolBrokerService` zonder `local_registry`, dus die tak
gooit "Local tool registry not initialized". Dat is dezelfde fout als de productieguard van drie
commits terug, die naar een AFGELEIDE NAAM keek in plaats van naar een capaciteit -- binnen een
dag herhaald op een andere plek.

---

## Bevindingen en wat ermee is gedaan

### HIGH-1 -- de prompt beloofde iets dat voor een van de vier tools onwaar was

*code-reviewer.* `local__llm_generate` stond in manifest en profiel, maar kan op het enige
runtimepad van deze skill niet draaien.

**Zelf nagemeten:**

```text
broker type       : ToolBrokerService
local_registry    : None
hr_registry       : HRToolRegistry
```

**Gedaan:** de tool is uit manifest EN profiel gehaald; de piloot houdt drie tools. Niet gewired,
en dat is een besluit met een reden: een skill die personeelsdata leest en daarna vrije tekst naar
een extern model mag sturen, is een uitgaand kanaal dat de redactielaag niet dekt (dat is ook de
tweede reviewer zijn MEDIUM-4). Die afweging hoort niet mee te liften op een wijziging waarvan de
scope "een schrijftool" is. De eenregelige wiring bestaat al in `base_agent.py:235`; er komt een
eigen brief voor.

**En de meting is meeveranderd**, want die had dezelfde blinde vlek: `acceptance_thread.py` stap 3
en de nieuwe guard tellen nu de registries van het OBJECT dat de skill in handen heeft, niet de
klasse-attributen. Aangetoond met een mutatie: `local__read_file` in het manifest -- een tool die
BESTAAT maar niet gewired is -- maakt stap 3 nu rood en de guard ook.

### HIGH-2 -- de generator zou het manifest bij de eerste regeneratie slopen

*code-reviewer.* Alleen de instructietekst was meeveranderd; `DEPARTMENT_TOOLS["hr_culture"]` gaf
nog de zes oude namen (drie niet-bestaand) en `manifest_version` kwam er niet in.

**Zelf nagemeten:** `build_manifest("skillsgaptraining", ...)` gaf
`['query_hr_database', 'search_documents', 'generate_text', 'send_notification', 'schedule_training']`
en `manifest_version: None`, met een prompt die belooft dat alles werkt. Een generator die je niet
kunt draaien zonder schade is geen generator.

**Gedaan:** `DEPARTMENT_TOOLS["hr_culture"]` is teruggebracht tot `["query_hr_database"]` (in
ronde 1 stond er ook `analyze_skill_gap` bij met "veilig voor iedere HR-skill" als toelichting --
ronde 2 wees terecht aan dat dat de lijst VERBREEDDE naar 14 skills en dat "veilig" een bewering
was), de piloot krijgt zijn twee extra tools via een nieuwe `SKILL_TOOL_OVERRIDES` -- per naam in
plaats van per departement, want dat is precies het punt van MEDIUM-1 -- en `SKILL_MANIFEST_VERSIONS`
zorgt dat het versieveld meekomt. Nieuwe guard `test_the_generator_and_the_committed_manifest_do_not_drift`
vergelijkt drie velden en is mutatiegetest.

### HIGH-3 -- de Any-ratel stond BLOKKEREND rood, en niet alleen door mij

*quality-reviewer.* `scripts/check_any_gate.py --mode acknowledged`: baseline 7111, gemeten 7119.

**Zelf nagemeten, en de splitsing is de kern:**

| Bestand | Delta | Herkomst |
|---|---|---|
| `src/core/api/v1/admin/llm_providers_router.py` | 0 -> 3 | commit 415929bb, GISTEREN, ongemeld |
| `src/core/api/v1/admin/dependencies.py` | 1 -> 4 | idem |
| `src/core/tool_broker/hr_registry.py` | 6 -> 8 | vandaag, van mij |

**Gedaan:** terug naar exact 7111, zonder schuld te boeken. `dict[str, object]` waar alleen
`.get()` gebeurt, `int | None` waar pyright `object` terecht afwees, en `list[Any]` vervangen door
een `ProviderRegel`-Protocol met `Sequence`. Die laatste corrigeert ook een onware toelichting van
mijzelf: ik had opgeschreven dat een echt type "een gedeeld antwoordmodel vraagt en dus groter is
dan deze feature". Een Protocol voor de RIJ doet precies wat nodig is en is geen import over de
ADR-033-grens.

Dat de +6 van gisteren ongemeld op `develop` stond, is een eigen bevinding: de Any-poort wordt
niet gedraaid in de reeks die ik als Gate 3 gebruikte.

### MEDIUM -- acht bevindingen, alle gerepareerd

| # | Bevinding | Gedaan |
|---|---|---|
| M1 | Log forging (CWE-117): een regeleinde in de trainingsnaam maakte er twee logregels van, waarvan de tweede een succes claimde | `_een_logregel()` slaat plat en kapt af; eigen test, mutatiegetest |
| M2 | De tool kon `completed` zetten -- afronding vastleggen is geen inplannen, en de HITL-goedkeurder leest de toolnaam, niet de status | alleen `assigned`; afronding wordt een eigen tool |
| M3 | Onbekende payloadvelden werden stil genegeerd; `{"participants": 3}` gaf EEN rij terwijl het model drie mensen rapporteert | geweigerd, met een test in beide richtingen. De uitzondering was in ronde 1 een HANDMATIGE lijst en dat was fout -- zie ronde 2, HIGH-1: hij miste `user_id` en maakte de tool onbruikbaar. Nu afgeleid uit `BROKER_INJECTED_KEYS` |
| M4 | Mijn WHY over de event bus was gemeten ONWAAR: de broker digest resultaat en fout al | docstrings gecorrigeerd naar "tweede laag", met het pad dat WEL rauw is (`act()` naar de LLM-context) |
| M5 | `schedule_training` staat in 14 andere manifesten; die skills krijgen later elk een profiel | nieuwe guard: een HIGH-tool in een broker-profiel vraagt een gedateerde reden per agent, plus staleness-test |
| M6 | Stap 6 van de acceptatieketen logde de risicoklasse en meldde altijd GEHAALD | eist nu `ToolRiskLevel.HIGH` |
| M7 | `manifest_version` 1 -> 2 zonder canary, terwijl de regel in dat bestand staat | besluit met reden opgeschreven: een ONWARE instructie gefaseerd uitrollen laat de fout bij een deel van de tenants staan, en er zijn nul productietenants |
| M8 | De faalroute (`SQLAlchemyError`) was ongetest, terwijl `StatementError.__str__` de SQL plus gebonden parameters draagt | test met een echte `OperationalError` die het e-mailadres in de SQL heeft |

### LOW -- zes, alle gerepareerd

- Dode `except _InvalidArgument` in de dispatch: `_schedule_training` gooit die nergens. Weg.
- Het succesantwoord gaf de SPELLING van het model terug (de lookup is hoofdletter-ongevoelig),
  niet de catalogusnaam. Veld weg.
- Twee losse modelimports in het testbestand -> `import src.core.database.import_all_models`, de
  kanonieke plek die door een architecture-test wordt bewaakt.
- "Hier staat geen enkele patch" was onwaar: `tests/unit/tool_broker/conftest.py` legt drie
  autouse-fixtures op. De zin is nu "geen patch OP DE PERMISSIELAAG" en noemt ze.
- Geen enkele test liep via `ToolBrokerService.execute_tool`. Er is er nu een die de weigering
  zonder goedgekeurd ticket vastlegt EN dat er niets is geschreven.
- Lengtegrenzen op de payloadvelden. In ronde 1 stonden ze op 320/150/32 met "gelijk aan de kolombreedtes" als toelichting; ronde 2 mat dat `User.email` `String(255)` is en `status` `String(20)`. Nu 255/150/20, en de test leest de breedte uit het model.

---

## Wat de reviewers expliciet GOED vonden, zodat het niet bij het repareren verdwijnt

- Tenant-isolatie op het schrijfpad, inclusief de ContextVar-timing: zetten VOOR de sessiefabriek
  is noodzakelijk (het `begin`-event van de engine zet daarmee `app.current_tenant`) en het staat
  er, met herstel in `finally`.
- Een payload kan de tenant niet beinvloeden: de broker eist een expliciete `context["tenant_id"]`
  en stript de payloadsleutel.
- De rollback kan geen ongecommit werk van een request weggooien: `HRToolRegistry` wordt nergens
  geinjecteerd, dus de sessie is altijd vers.
- HIGH -> HITL werkt echt, met verzilvering die tenant, toolnaam EN payload bindt.
- Het testbestand: "het sterkste dat ik in deze repo heb gereviewd -- 12 van 12 mutaties rood,
  beide richtingen, geen enkele hangende assertie" (quality-reviewer, ronde 1).

---

## Openstaand na deze ronde

1. **`local_registry` is niet gewired** in `BaseSpecialistAgent`. Eigen brief; de afweging is
   inhoudelijk (exfiltratiepad), niet technisch.
2. **De 134 manifesten zijn niet geregenereerd.** De generator is nu correct, de bestanden op
   schijf houden `schedule_training` tot iemand regenereert. De nieuwe profielguard houdt de echte
   deur dicht.
3. **`tests/test_tool_broker_local.py` faalt** -- nagemeten in een verse worktree op 195cc0f1, dus
   niet van deze wijziging. Dat bestand staat buiten de vier poortmappen en draait nergens
   blokkerend. Eigen brief.
4. **De keten komt tot stap 4 van 7.** Stap 5 vraagt proefdata, stap 7 een echt taalmodel.

---

# Ronde 2 -- de reparaties gereviewd

De code-reviewer heeft de reparaties getoetst en vond **drie nieuwe HIGH's**, alle drie zelf
gemeten met een script in plaats van beredeneerd. Twee ervan raken precies de plekken die ik in
ronde 1 had aangeraakt; dat is geen pech maar het patroon dat `quality-gates.md` beschrijft: een
guard die je schrijft om je eigen fout te vangen deelt je blinde vlek.

De quality-reviewer is halverwege gestopt op een API-limiet. Zijn ronde-1-bevindingen zijn alle
zes gerepareerd en mutatiegetest; zijn ronde-2-verificatie ontbreekt en dat is de reden dat dit
document niet op APPROVED staat.

## HIGH-1 (ronde 2) -- mijn veldweigering brak de enige echte weg. GEMETEN.

De broker injecteert TWEE sleutels uit de executiecontext, niet een: `service.py:190-195` zet
`tenant_id` EN `user_id` in de payload, en filtert er daarna alleen `tenant_id` weer uit. Mijn
uitzonderingslijst noemde `tenant_id` en `_hitl_ticket_ref` met de hand -- en miste `user_id`.

```text
PAYLOAD BIJ DE REGISTRY: {'user_email': ..., 'training_name': ..., '_hitl_ticket_ref': 't-1',
                          'user_id': 7}
RESULT: {'success': False, 'error': 'onbekende velden: user_id ...'}
```

Gevolg: mens keurt goed -> `redeem_approval` zet het ticket op `consumed` -> de tool weigert. De
goedkeuring is verbruikt en niet herhaalbaar. **Er was geen enkel pad waarop deze tool kon
slagen** -- de tool die ik vandaag heb gebouwd was in de praktijk onbruikbaar, en mijn eigen test
deelde de blinde vlek omdat hij dezelfde twee namen opsomde als de code.

**Gerepareerd** door de verzameling AF TE LEIDEN: `redaction.BROKER_INJECTED_KEYS` (de bestaande
bron, met een AST-guard die hem gelijk houdt aan de injectieplekken) plus de `_`-prefix-conventie
die `approval_binding` al gebruikt. De test leest nu diezelfde bron en heeft een assertie die
faalt als `user_id` er ooit uit verdwijnt.

## HIGH-2 (ronde 2) -- de goedkeurroute meldde SUCCES bij een weigerende tool

`hitl_router._voer_goedgekeurde_actie_uit` keek alleen naar uitzonderingen. Het toolcontract
schrijft `{"success": false, ...}` voor, en `_schedule_training` gebruikt die vorm op zes takken.
Zonder controle: ticket op `consumed`, API meldt geslaagd, geen rij geschreven -- succes zonder
werk op het enige toezichtspunt dat dit systeem heeft. Dezelfde fout is op het SKILLpad al onder
BE-AGT-044 gerepareerd; deze route was toen overgeslagen. Mijn wijziging is wat hem live maakte.

**Gerepareerd** met een expliciete controle en vier tests
(`tests/unit/api/test_een_geweigerde_tool_is_geen_geslaagde_goedkeuring.py`), waaronder de
tegenrichting: een tool die GEEN `success`-veld teruggeeft mag niet ineens als mislukt gelden.
Daarom `is False` en niet `is not True` -- beide richtingen mutatiegetest.

## HIGH-3 (ronde 2) -- mijn nieuwe guard was blind op het profiel dat het meest telt

De guard sloeg elk profiel over dat geen `namespace: broker_tool` had. `ToolPermissionManager`
kent dat veld niet; het bestaat om LEZERS te helpen. Het `copilot`-profiel staat op
`council_action` en is tegelijk de DEFAULT uitvoerende identiteit van de goedkeurroute. Gemeten:
een mutatie die `schedule_training` aan `copilot` gaf bleef GROEN, en dat profiel hield al een
HIGH broker-tool (`delete_task`) zonder gedateerde reden.

Dat is precies de aanscherping van 2026-09-18 die ik niet had toegepast: **muteer in de sleutel
die al wordt vrijgesteld.** Mijn mutatie zat binnen de verzameling die de filter al doorliet.

**Gerepareerd:** de filter is weg, `copilot: delete_task` staat met een gedateerde vastlegging in
de lijst, en de mutatie op het `copilot`-profiel is nu ROOD.

## De MEDIUM's van ronde 2

| # | Bevinding | Gedaan |
|---|---|---|
| M1 | De lengtegrenzen waren NIET de kolombreedtes: `User.email` is `String(255)`, niet 320 -- `String(320)` kwam in heel `src/` alleen in mijn eigen twee comments voor. Het venster 256-320 passeerde dus, terwijl de testnaam beloofde dat het werd geweigerd | grenzen naar 255/150/20, en de test LEEST de kolombreedte uit het model en toetst op grens+1 |
| M2 | Het e-mailadres stond WEL in het logbestand: `str(exc)` van een SQLAlchemy-fout draagt de SQL plus de gebonden parameters. De vierde sink, die de redactielaag niet dekt | alleen het TYPE in de boodschap, traceback via `exc_info`; de test asserteert nu ook op `caplog` (gefilterd op deze logger, want `caplog.records` bevat ook de aiosqlite-records van de eigen seeding) |
| M3 | "connected" in de promise-guard was smaller dan "will really run": het permissieprofiel en de aanwezigheid van `hitl_store` vielen ertussen | twee asserties erbij (profiel == manifest voor een geprofileerde skill; `hitl_store is not None` als het manifest een HIGH-tool declareert), beide mutatiegetest |
| M4 | `config/tool_permissions.yml` kent de tool vier regels boven een comment dat dossiermutaties verbiedt "ook niet met goedkeuring" -- maar dat comment verwijst naar D5, dat de ADR zelf als "vervangen door B7" markeert | NIET opgelost: dat is een besluit over governance-tekst, geen codewijziging. Eigen brief |
| M5 | Ik had `hr_culture` niet alleen VERKLEIND maar ook verbreed: `analyze_skill_gap` stond er niet en zou bij een regeneratie aan 14 skills worden toegekend. "Veilig voor iedere HR-skill" was een bewering, geen meting | teruggebracht tot `["query_hr_database"]`; de piloot krijgt zijn twee extra tools via `SKILL_TOOL_OVERRIDES` |

## De LOW's van ronde 2

- **Drie onware WHY's** in `specialist_base.py`, `hitl_repository.py` (2x): ze zeiden dat
  `copilot` en `skillsgaptraining` "alleen `send_notification`" delen. Na deze wijziging delen ze
  NIETS. Gecorrigeerd -- de conclusie werd sterker, de bewering was onwaar.
- **Verouderde kop** in `test_tool_profile_namespaces.py` ("de piloot, wiens vijf tools nog
  gebouwd moeten worden"). Bijgewerkt.
- **Een test die om een andere reden slaagde dan hij zei**: de HITL-weigering kwam uit
  "HITLStore is not configured", niet uit de verzilvering. Er is nu een tweede geval met een
  store die `False` teruggeeft.
- **BestandsIO op moduleniveau** in de evaluatieset: `DECLARED_TOOLS = _declared_tools()` werd
  een `@lru_cache`-functie, zodat een verkeerde cwd een test laat falen in plaats van de hele
  collectie.
- **Vier definities van "uitvoerbaar"** in de codebase (`is_known_tool`, `_high_tools`,
  `_uitvoerbare_toolnamen`, `BUSINESS_TOOLS`). NIET opgelost. Dat is de kern van de
  Devil's Advocate hieronder en het is een eigen wijziging.

## Wat de code-reviewer expliciet goedkeurde in ronde 2

- De tenant-ContextVar-timing (zetten VOOR de sessiefabriek, want `SELECT 1` opent de transactie
  en het `begin`-event leest de ContextVar).
- Het `ProviderRegel`-Protocol: "Dit is Contract 1 zoals bedoeld, en de vorige toelichting
  ('vraagt een gedeeld antwoordmodel') was inderdaad onjuist." `Sequence` in plaats van `list` om
  de juiste reden (covariantie).
- De Any-ratel op exact 7111, nagemeten.
- Dat het gecommitte manifest de juiste bron is voor de promise-guard, en geen derde bron.

## Mutatiebewijs ronde 2 -- negen mutaties, alle betrapt

| Mutatie | Betrapt door |
|---|---|
| brokervelden weer met de hand opgesomd (`user_id` mist) | `test_the_fields_the_broker_injects_are_not_unknown` |
| de `_`-prefix-conventie valt weg | idem |
| lengtegrens terug op de verzonnen 320 | `test_a_value_longer_than_its_column_is_refused` |
| exceptietekst weer in het logbestand | `test_a_database_failure_leaks_neither_the_email_nor_the_sql` |
| goedkeurroute kijkt niet naar `success: False` | `test_a_refusing_tool_is_not_a_successful_approval` |
| `is False` verbreed naar `is not True` (tegenrichting) | `test_a_tool_without_a_success_field_still_counts` |
| `copilot` krijgt de HIGH-schrijftool | `test_no_profile_gains_a_high_risk_tool_without_a_dated_reason` |
| permissie weg, manifest en belofte onveranderd | `test_the_prompt_only_promises_working_tools_while_they_all_work` |
| `hitl_store=None` in `specialist_base.py` | idem |

Een tiende poging was een EQUIVALENTE mutatie (`hitl_store=None or HITLStore(...)` evalueert naar
hetzelfde) en is opnieuw gedaan in de juiste vorm. Ook in ronde 1 is een equivalente mutatie
weggelaten met de reden erbij; zo'n mutatie is geen ongedekt gat en hem als "niet betrapt"
opschrijven zou een gat suggereren dat er niet is.

## Openstaand na ronde 2 -- alles met een brief, niets met een registerrij

1. **Vier definities van "uitvoerbaar", negen guards die samen EEN invariant bewaken.** De
   Devil's Advocate van de reviewer is hier scherp en ik neem hem over: de uitweg is niet een
   tiende guard maar EEN afgeleide bron -- een functie die per `agent_id` teruggeeft wat hij mag
   EN kan (profiel, manifest, registry, risiconiveau, aanwezige store) -- en guards die die ene
   functie bevragen. Eigen brief.
2. **`employee_trainings` heeft geen herkomst.** Geen `assigned_by`, geen ticketverwijzing, geen
   spoor dat aan een besluit hangt; het auditspoor leeft in een andere tabel met een andere
   levensduur. Bij de eerste DSAR-vraag "wie heeft mij deze training toegewezen" is het antwoord
   een join over een gedigeste payload. Die kolom hoort erbij VOORDAT er productiedata is.
3. **Geen ratelimiet op HIGH-goedkeuringen** en geen aggregatie die de goedkeurder laat zien wat
   hij vandaag al heeft goedgekeurd. Bij volume wordt een poort-per-aanroep een stempel, en dat
   raakt de bewering "HIGH is genoeg" die nu in meerdere comments staat.
4. **`local_registry` is niet gewired** in `BaseSpecialistAgent`, bewust niet in deze knip.
5. **De governance-tegenspraak** in `tool_permissions.yml` rond D5/B7.
6. **`tests/test_tool_broker_local.py` faalt** -- pre-existent, buiten de poortmappen.
7. **De 134 manifesten zijn niet geregenereerd.**

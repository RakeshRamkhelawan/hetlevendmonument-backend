# BE-AGT-067 -- `schedule_training`: de eerste schrijfactie van een agent op HR-data

Datum:        2026-09-21
Sprint-dag:   ADR-036 D10, vervolg op BE-AGT-044 (query_hr_database) en OP-26 (analyze_skill_gap)
Branch:       develop
Basis:        195cc0f1

---

## 1. Waarom dit er is

De acceptatiemeting (`scripts/acceptance_thread.py`) legt EEN keten af -- van de vraag "welke
medewerkers missen welke vaardigheid" tot een opgeslagen besluit -- en meldt tot welke stap hij
komt. Die stond op **stap 2 van 7**. Stap 6 vraagt: "de schrijfactie bestaat en heeft een
risicoklasse". Zolang de HR-registry alleen kon LEZEN, kon die keten per definitie nooit een
besluit opleveren; een gap-analyse die niemand kan opvolgen is een rapport, geen automatisering.

Dit is die schrijfactie: de aanbevolen training aan een medewerker toewijzen.

Na deze dag komt de keten tot **stap 4 van 7** (gemeten, zie paragraaf 7).

---

## 2. Wat de tool doet, en wat hij met opzet NIET doet

`schedule_training` wijst een BESTAANDE training uit de catalogus van de tenant toe aan een
BESTAANDE medewerker van diezelfde tenant.

| Payloadveld | Verplicht | Wat het is |
|---|---|---|
| `user_email` | ja | de medewerker; wordt tenant-gescoped en hoofdletter-ongevoelig opgezocht |
| `training_name` | ja | de training uit de catalogus van deze tenant, idem |
| `status` | nee | ALLEEN `assigned` (ook de default) |

Antwoord bij succes: `{"success": true, "assigned": n, "updated": n, "status": "assigned"}`.
Antwoord bij weigering: `{"success": false, "error": "..."}`.

**Elke andere sleutel wordt GEWEIGERD**, niet genegeerd. Dezelfde regel als `_UNSUPPORTED_FILTERS`
voor de leestools, en hier zwaarder: de oude evaluatieset stuurde letterlijk
`{"training": ..., "participants": 3}`. Stil negeren levert EEN toegewezen rij op terwijl het
model rapporteert dat er drie mensen zijn ingeschreven -- bij een leestool een te ruim antwoord,
hier een besluit dat niemand nam.

**De uitzondering daarop is AFGELEID en niet opgesomd, en dat is de duurste les van deze dag.**
De eerste versie had een eigen lijstje `{"tenant_id", "_hitl_ticket_ref"}`. De broker injecteert
er TWEE uit de executiecontext (`service.py:190-195`: `tenant_id` EN `user_id`) en filtert er
daarna alleen `tenant_id` weer uit. Gemeten in Gate 2 ronde 2: op het goedkeuringspad kwam de
tool aan met `user_id` erbij en weigerde hij, NADAT `redeem_approval` het ticket op `consumed`
had gezet. De menselijke goedkeuring was verbruikt en niet herhaalbaar -- er was geen enkel pad
waarop deze tool kon slagen. En mijn eigen test somde dezelfde twee namen op als de code, dus
twee kopieen van een handmatige lijst konden elkaar niet controleren.

De verzameling komt nu uit `redaction.BROKER_INJECTED_KEYS` (met een AST-guard die hem gelijk
houdt aan de injectieplekken in `service.py`) plus de `_`-prefix-conventie die `approval_binding`
al gebruikt voor servermetadata.

**Hij zet alleen `assigned`, en dat is nauwer dan de tabel toestaat.**
`EMPLOYEE_TRAINING_STATUSES` kent ook `in_progress` en `completed`, en het model kiest de waarde
vrij. Vastleggen dat iemand een training heeft AFGEROND is een ander besluit dan hem inplannen:
het is een bewering over de werkelijkheid waarvoor deze tool geen bewijs heeft, hij is met een
tweede aanroep weer uit te wissen (`EmployeeTraining` houdt geen historie), en het gaat over
Annex III punt 4-data. De HITL-poort is daar geen verdediging tegen -- de goedkeurder leest de
toolnaam "schedule_training", niet de statuswaarde. Afronding vastleggen hoort een eigen tool
met een eigen risicoregel.

**Hij maakt geen training aan en geen medewerker.** Bestaat een van de twee niet binnen de
tenant, dan is het antwoord een weigering. Zou de tool ze aanmaken, dan zet een agent met een
typefout een nieuwe "training" in de catalogus van een klant -- en die catalogus is bedrijfsdata,
geen bijproduct van een agentbesluit.

**Hij doet precies EEN rij per aanroep.** De onderliggende repository doet batches, maar de
HITL-poort werkt per tool-aanroep: een batch van twintig medewerkers zou twintig besluiten achter
een enkele menselijke goedkeuring verstoppen.

---

## 3. Waar de remmen zitten

| Rem | Waar | Wat hij doet |
|---|---|---|
| Risicoklasse HIGH | `src/core/config/tool_risk_levels.yml` | alleen HIGH opent de HITL-poort in `tool_broker/service.py`; een mens ziet de aanroep voor hij gebeurt |
| Vereist recht `admin` | idem, `tool_required_permission` | het recht van de AANVRAGENDE MENS; verscherpt van `write` (zie hieronder) |
| Agent-allowlist | `config/tool_permissions.yml` | alleen de piloot-skill heeft een broker-profiel; de andere 134 skills zijn default-deny |
| Tenantgrens | `HRTrainingsRepository.upsert_employee_trainings` | expliciete `tenant_id`-filter op medewerker EN training; de tenant komt uit de executiecontext, nooit uit de payload |
| RLS-context | `_schedule_training` | de tenant-ContextVar wordt gezet VOOR de sessiefabriek, want het `begin`-event van de engine zet daarmee `app.current_tenant` |
| Redactie | `tool_broker/redaction.py` | `user_email` en `training_name` worden gedigest; alleen `status` blijft leesbaar in het log |
| Geen stil succes | `api/v1/tool_broker/hitl_router.py` | de goedkeurroute toetst nu ook de RETURNWAARDE: `{"success": false}` geeft een MISLUKTE goedkeuring in plaats van "geslaagd" met een verbruikt ticket |

### Het recht is verscherpt van `write` naar `admin`

`schedule_training: write` stond al in `tool_required_permission`, meegeschreven toen de naam
nog alleen in een manifest stond. Dat is LOSSER dan het LEZEN van dezelfde data
(`query_hr_database: admin`, `analyze_skill_gap: admin`), en dat is niet te verdedigen: wie de
bezetting niet mag opvragen, hoort niet via een agent een training te kunnen toewijzen.
Vastgelegd in `tests/unit/tool_broker/test_hr_schedule_training.py::
TestScheduleTrainingIsGoverned::test_writing_is_never_looser_than_reading_the_same_data`, die de
twee waarden tegen elkaar meet in plaats van er een te bevriezen.

Bijwerking: `tests/unit/auth/test_user_scope_covers_broker_tools.py::
test_two_tools_can_have_two_different_thresholds` gebruikte `schedule_training` als voorbeeld van
schrijfrecht. Dat voorbeeld is `local__write_file` geworden -- die test gaat over het VERSCHIL
tussen twee drempels, niet over deze twee namen.

---

## 4. Waarom het antwoord geen persoonsgegeven bevat

Alles wat een tool teruggeeft gaat de event bus op (`tool_broker/service.py::_publish_tool_event`)
en wordt door het leersubsysteem gepersisteerd (`learning_event_handler._record_tool_event`
schrijft `observation_data`). Dat is dezelfde reden waarom de twee leestools tellingen teruggeven
en geen namen (ADR-036 OP-27).

**Correctie op wat hier eerst stond, en de reden dat het telt.** Ik schreef dat de tekst
onuitwisbaar in de leeropslag belandt. Een Gate 2-reviewer heeft dat nagemeten en het is niet
meer zo: `service.py` digest het resultaat EN de fout voor elke bewarende sink
(`safe_digest_result`, `safe_value_digest`), en de leerhandler slaat precies dat gedigeste veld
op. Deze laag is dus de TWEEDE en niet de enige. De discipline blijft -- via `act()` komt het
resultaat ook in de LLM-context terug en dat pad is niet gedigest -- maar een onbewezen oorzaak
in vijf bestanden is precies wat `quality-gates.md` verbiedt, en de correctie staat nu in de
docstrings zelf.

Twee gevolgen, beide met een test eronder:

1. **Het e-mailadres gaat niet mee in het antwoord**, ook niet bij succes. De aanroeper kent het
   adres al -- hij gaf het zelf mee -- dus teruggeven voegt niets toe en zet een persoonsgegeven
   in een opslag die daar niet voor is.
2. **Een foutmelding citeert niets uit de payload.** `upsert_employee_trainings` zet de ontvangen
   trainingsnaam wel in zijn melding, en dat is daar terecht: daar komt hij uit een bestand dat
   een mens heeft geupload. Hier komt hij uit een `TOOL_CALL`-directive, dus uit het model. Een
   model dat `training_name="Jan Jansen salaris 82000"` stuurt, zou die tekst anders via de
   foutmelding in een onuitwisbare opslag krijgen. De volledige melding van de repository gaat
   naar het logbestand; het antwoord noemt alleen de oorzaak.

Bij SUCCES mag de trainingsnaam wel terug: op dat punt heeft hij een rij in de catalogus van deze
tenant gevonden en is hij dus bedrijfsdata, dezelfde soort als de rolnamen die de leestools
teruggeven.

---

## 5. Het manifest van de piloot: van zes tools naar drie

Dit hoort bij dezelfde wijziging, want zonder dit blijft de keten op stap 3 staan.

Het manifest (`src/core/als/agents/skills/manifests/skillsgaptraining.yml`) declareerde zes tools
waarvan er drie niet bestonden, en de systeemprompt vertelde het model: *"Some listed tools are
not connected yet; the ToolBroker refuses those with an error. That is expected."*

Dat is precies wat je niet doet. Een gedeclareerde tool die weigert, maakt het voor een model
onmogelijk om te bepalen of een opdracht uitvoerbaar is -- en dat, niet de weigering zelf, is de
gemeten hoofdoorzaak van verzonnen toolresultaten. Een tool moet dus werken of niet gedeclareerd
zijn.

| Naam | Besluit | Meting |
|---|---|---|
| `query_hr_database` | blijft | bestaat sinds 2026-08-02 |
| `analyze_skill_gap` | blijft | bestaat sinds 2026-08-15 |
| `schedule_training` | blijft | vandaag gebouwd |
| `generate_text` | WEG | de capaciteit bestaat als `local__llm_generate`, maar is op DIT pad niet aangesloten -- zie hieronder |
| `search_documents` | WEG | er is geen documentmodel in deze codebase -- geen tool en geen data om op te bouwen |
| `send_notification` | WEG | er is wel notificatie-infrastructuur, maar die is geen broker-tool; `local__send_email` is echte SMTP en dus iets anders. Deze skill adviseert; melden is vandaag niet zijn taak |

### De tussenstap die is teruggedraaid: `local__llm_generate`

Eerst is `generate_text` hernoemd naar `local__llm_generate`, de echte naam van dezelfde
capaciteit. Een Gate 2-reviewer mat dat die tool op dit pad NIET kan draaien, en ik heb het
nagemeten: `BaseSpecialistAgent` bouwt zijn eigen `ToolBrokerService` met alleen
`serena_client`, `seq_thinking_client` en `hitl_store`. `local_registry` valt daarmee op `None`
en de `local__`-tak gooit "Local tool registry not initialized" voordat er iets van een LLM
langskomt.

```text
local_registry = None
hr_registry    = HRToolRegistry
```

Daarmee zou de prompt iets beloven wat voor een van de vier tools onwaar is -- precies de fout
die ik met het verwijderen van de waarschuwing wilde herstellen. Twee redenen om hem eruit te
halen in plaats van de wiring erbij te bouwen:

1. **Hij is niet nodig.** Deze skill heeft zijn eigen LLM (`_get_llm_service`) en schrijft zijn
   advies in het tekstantwoord. `generate_text` was er om een plan te formuleren, en dat doet hij
   al.
2. **Hij is een eigen beslissing.** Een skill die personeelsdata leest en daarna vrije tekst naar
   een extern model mag sturen, is een uitgaand kanaal dat de redactielaag niet dekt. Die afweging
   hoort niet mee te liften op een wijziging waarvan de scope "een schrijftool" is.

De piloot houdt dus DRIE tools, en voor alle drie geldt dat de broker die hij werkelijk in handen
heeft ze kan uitvoeren.

`manifest_version` is 1 -> 2 en de belofte in de prompt is nu waar. Die belofte kan niet stil
onwaar worden: `tests/unit/scripts/test_generate_skill_manifests_stopgap.py::
test_the_prompt_only_promises_working_tools_while_they_all_work` vergelijkt de zin met de tools
die het profiel toekent, dus een tool die verdwijnt maakt de test rood. Op diezelfde plek stond
tot vandaag het omgekeerde: de prompt MOEST "not connected yet" zeggen. Dat was juist zolang geen
enkele piloottool bestond.

`KNOWN_UNRESOLVED_BROKER_TOOLS` in `tests/architecture/test_tool_profile_namespaces.py` is
daarmee LEEG -- er staat geen tool meer in een broker-profiel die niet bestaat. Beide
staleness-tests daar hebben dat zelf afgedwongen: ze werden rood toen de laatste vier namen
verdwenen.

---

## 6. Welke bestaande tests zijn aangepast, en waarom dat geen versoepeling is

Vier testbestanden leunden op `send_notification` of `search_documents` als piloottool. Nu de
manifest-filter die namen weigert voor de broker ze ziet, meetten die tests niets meer -- ze
liepen groen of rood om een andere reden dan waarvoor ze geschreven zijn.

| Bestand | Was | Is |
|---|---|---|
| `tests/unit/als/test_act_partial_tool_failure.py` | twee tool-calls, tweede `send_notification` | `query_hr_database` + `schedule_training`, met de payload van de echte tool |
| `tests/unit/als/enterprise/test_pack_orchestrator_execute_step.py` | `send_notification` | `query_hr_database` (een leestool: `schedule_training` zou terecht op de HITL-poort stuklopen) |
| `tests/unit/tool_broker/test_skillsgaptraining_tool_permissions.py` | `send_notification` | `query_hr_database` |
| `tests/unit/als/test_skillsgaptraining_evaluation_set.py` | T2 op `search_documents`, T3 op `send_notification`; `DECLARED_TOOLS` een handmatige kopie van vijf namen | T2 op `analyze_skill_gap`, T3 op `analyze_skill_gap` + `schedule_training`; `DECLARED_TOOLS` wordt uit het manifest GELEZEN |
| `tests/unit/auth/test_user_scope_covers_broker_tools.py` | `schedule_training` als voorbeeld van schrijfrecht | `local__write_file` -- die test gaat over het VERSCHIL tussen twee drempels, niet over deze namen |

Die laatste is meer dan een naamwissel. De handmatige kopie miste `analyze_skill_gap` (bestaat
sinds 2026-08-15) en noemde drie namen die vandaag zijn verdwenen -- een lijst die je opsomt in
plaats van afleidt, meet op een dag iets anders dan wat er draait, en juist die verzameling is de
meetlat voor "mag deze skill die tool aanroepen".

### En de meting zelf is twee keer bijgesteld -- de tweede keer is de belangrijkste

`scripts/acceptance_thread.py` stap 3 keek naar de business- en de HR-registry, maar niet naar de
LOKALE. Dat leek de fout: een bestaande lokale tool werd geteld als niet-bestaand. Bij het
repareren van de Gate 2-bevindingen bleek de omgekeerde fout ernstiger.

**Een naam in een registry-KLASSE zegt niets over wat deze agent kan aanroepen.** De klasse
`LocalToolRegistry` kent `local__read_file`, maar de broker die de skill werkelijk in handen
heeft, heeft geen `local_registry`. De meting vraagt het daarom nu aan het OBJECT:

```python
broker = SkillsGapTrainingSkill(tenant_id=1).tools
for attribuut in ("business_registry", "hr_registry", "local_registry"):
    ...
```

Dat is dezelfde les als de productieguard van drie commits terug: een controle op een AFGELEIDE
NAAM is een controle op een tekst. Binnen een dag herhaald op een andere plek, en deze keer door
een reviewer betrapt in plaats van door mijzelf.

Bewust de EXPLICIETE namen en niet `service.is_known_tool()`: die functie laat ook een prefix
passeren, dus `local__wat_ik_maar_verzin` zou als bestaand tellen. Dan kan deze stap groen worden
op een tool die niemand heeft gebouwd -- de faalvorm die dit script juist moet vangen, in het
meetinstrument zelf.

**Aangetoond dat de stap rood kan, in twee vormen:**

```text
- deze_bestaat_helemaal_niet  -> stap 3 NIET GEHAALD, keten zakt naar stap 2
- local__read_file            -> stap 3 NIET GEHAALD, keten zakt naar stap 2
```

De tweede is de interessante: die tool BESTAAT als naam en is toch terecht rood, want deze agent
kan hem niet uitvoeren.

**Stap 6 asserteerde niets.** Hij logde de risicoklasse en meldde GEHAALD, wat de uitkomst ook
was: met `schedule_training: low` zei het script nog steeds GEHAALD terwijl de HITL-poort dan
niet meer opengaat. Nu eist de stap `ToolRiskLevel.HIGH`. Een holle stap in het instrument dat
holle code moet aanwijzen -- dezelfde vorm die stap 5 al eens had.

---

## 7. Meting

```text
python scripts/acceptance_thread.py

  taalmodel-provider: mock   <-- NAMAAK, geen bewijs
  1  [GEHAALD        ] het manifest van de HR-specialist is te laden
  2  [GEHAALD        ] de specialist is te construeren uit dat manifest
  3  [GEHAALD        ] elke tool die het manifest noemt, kent de ToolBroker ook echt
       alle 3 tools bestaan
  4  [GEHAALD        ] de instructietekst staat toe dat de agent tools aanroept
  5  [NIET GEHAALD   ] de kloofanalyse levert echte rijen uit de database
       de tool werkt maar geeft nul rijen -- de database bevat geen proefdata
  6  [GEHAALD        ] de schrijfactie bestaat en heeft een risicoklasse
       schedule_training bestaat en staat op HIGH, dus achter de HITL-poort
  7  [NIET GEHAALD   ] na goedkeuring staat het besluit als rij in de database
       provider is 'mock' -- een besluit uit een namaakmodel telt niet als bewijs

  Keten komt tot stap 4 van 7
  Losse stappen gehaald: 5   niet te toetsen: 0
```

Was stap 2 van 7 (nulmeting 2026-09-20, HEAD 819f2129). **Wat er NIET beweegt en waarom:** stap 5
vraagt proefdata in de testdatabase (functieprofielen, medewerkerscores, trainingen via
`/api/v1/hr/skills/import`) en stap 7 vraagt een echt taalmodel in plaats van het namaakmodel
waarop een los Python-proces terugvalt. Beide zijn een eigen taak; geen van beide is code.

### Gate 3

```text
python -m ruff check src/ tests/ scripts/     All checks passed!
python scripts/run_mypy_audit.py              Total errors: 0   Baseline errors: 0
python -m pyright                             0 errors, 35 warnings, 0 informations
python scripts/check_any_gate.py --mode acknowledged --baseline docs/any_type_baseline.json
                                              Baseline 7111; gemeten 7111
```

**Die laatste regel is meer dan een vinkje.** De Any-ratel is een BLOKKERENDE CI-stap en stond
rood voordat ik vandaag iets deed: 7111 -> 7117, binnengekomen met commit 415929bb
(BE-LLM-003, gisteren) en door niemand gemeld. Mijn eigen wijziging maakte er 7119 van. Een
Gate 2-reviewer heeft dat gevonden; ik heb het nagemeten en beide teruggebracht zonder schuld te
boeken:

| Bestand | Was | Nu | Hoe |
|---|---|---|---|
| `src/core/tool_broker/hr_registry.py` | 6 -> 8 | 6 | `dict[str, object]` op de nieuwe methode; die doet alleen `.get()` en versmalt zelf met `isinstance` |
| `src/core/api/v1/admin/llm_providers_router.py` | 0 -> 3 | 0 | twee returntypes en een interne helper naar `dict[str, object]` |
| `src/core/api/v1/admin/dependencies.py` | 1 -> 4 | 1 | `user_id: int \| None` (pyright wees `object` terecht af), `details: dict[str, object]`, en een `ProviderRegel`-Protocol in plaats van `list[Any]` |

Die laatste is de interessante. De toelichting bij `list[Any]` zei dat een echt type een gedeeld
antwoordmodel vraagt en dus "groter is dan deze feature". Dat was onjuist: een PROTOCOL voor de
rij noemt WAT de router uitleest zonder WELKE klasse hem levert, en dat is geen import over de
ADR-033-grens maar precies de bedoeling ervan. `Sequence` en niet `list`, want `list` is
invariant en dan vervult de servicelaag het Protocol niet.

### Tests

`tests/unit/tool_broker/test_hr_schedule_training.py` -- 29 tests, groen. Bewust een EIGEN
bestand: `test_hr_registry.py` heeft een autouse-fixture die `ToolPermissionManager.is_tool_allowed`
patcht, en een assertie over een HIGH-tool in een bestand waar de permissiecontrole is uitgezet is
precies de holle vorm die `.claude/rules/quality-gates.md` beschrijft. Wel aangescherpt na de
review: `tests/unit/tool_broker/conftest.py` legt drie ANDERE autouse-fixtures op dit bestand
(`prana_guard`, `council_gate`, `_deterministic_pseudonymisation_key`). Geen ervan raakt wat hier
wordt gemeten -- het mutatiebewijs toont dat empirisch -- maar "hier staat geen enkele patch" was
voor een lezer die het natrok onwaar.

Nieuw in ronde 2: een test die over de ECHTE weg loopt (`ToolBrokerService.execute_tool`) en
vastlegt dat deze HIGH-tool zonder goedgekeurd ticket niet draait EN niets schrijft. Alle andere
tests roepen de registry direct aan; dan komen de permissielaag en de HITL-poort er niet aan te
pas, en toetsten de `IsGoverned`-tests alleen YAML.

Ook nieuw: `tests/architecture/test_een_high_schrijftool_komt_niet_stil_in_een_profiel.py`. Die
komt uit een reviewbevinding: `schedule_training` staat in VEERTIEN andere skill-manifesten, en
`config/tool_permissions.yml` zegt zelf dat die skills er later elk een profiel bij krijgen. Op
die dag zou een pauzeherinnering schrijfrecht op `employee_trainings` hebben. De guard eist per
agent een gedateerde reden voor elke HIGH-tool en heeft een staleness-test.

### Ronde 2 van Gate 2 -- wat de reparaties zelf opleverden

De code-reviewer vond in de REPARATIES drie nieuwe HIGH's. Twee ervan raken precies de plekken
die ik in ronde 1 had aangeraakt, en dat is het patroon dat `quality-gates.md` beschrijft: een
guard die je schrijft om je eigen fout te vangen deelt je blinde vlek.

| Wat | Gevolg | Gerepareerd met |
|---|---|---|
| Mijn veldweigering miste `user_id` | de tool weigerde op ELKE goedgekeurde aanroep, nadat het ticket al was verbruikt | de verzameling afleiden uit `BROKER_INJECTED_KEYS` |
| De goedkeurroute keek alleen naar uitzonderingen | `{"success": false}` gaf "geslaagd", ticket `consumed`, geen rij | expliciete controle plus vier tests, inclusief de tegenrichting |
| Mijn nieuwe guard filterde `namespace` weg | blind op het `copilot`-profiel, dat de DEFAULT uitvoerende identiteit is en al een HIGH-tool hield | de filter weg; `copilot: delete_task` met gedateerde vastlegging |
| Mijn lengtegrenzen waren verzonnen | `User.email` is `String(255)`, niet 320 -- het venster 256-320 passeerde | grenzen uit de modellen, en de test leest de kolombreedte |
| `str(exc)` ging naar het logbestand | de SQL plus de gebonden parameters, dus het e-mailadres leesbaar in de vierde sink | alleen het type in de boodschap, traceback via `exc_info` |
| Ik had `hr_culture` niet alleen verkleind maar ook verbreed | een regeneratie zou 14 skills `analyze_skill_gap` geven | terug naar `["query_hr_database"]` |

De volledige lijst met de metingen staat in `docs/backend/review/review-BE-AGT-067.md`.

### Mutatiebewijs, 21 + 9 mutaties, alle betrapt

Met `scripts/mutation_harness.py`, en de tegenrichting (ongemuteerd) groen -- 42 tests over vier
bestanden. Elke mutatie zit in PRODUCTIECODE of CONFIGURATIE, nooit in een test.

| Mutatie | Betrapt door |
|---|---|
| `await session.commit()` weg | `test_the_tool_commits_itself_and_does_not_lean_on_its_factory` |
| `await session.rollback()` weg | `test_a_refused_row_is_rolled_back_instead_of_committed` |
| foutmelding citeert de repository-melding (met de payload erin) | `test_a_failed_assignment_does_not_repeat_the_payload` |
| `user_email` toegevoegd aan het succesantwoord | `test_the_email_is_never_in_the_answer` |
| logregel niet platgeslagen (regeleinde uit de payload) | `test_the_log_line_cannot_be_split_by_the_model` |
| `error_detail=str(exc)` bij een databasefout | `test_a_database_failure_leaks_neither_the_email_nor_the_sql` |
| statuscontrole uit: elke tabelstatus mag weer | `TestScheduleTrainingOnlyAssigns` |
| onbekende velden worden stil genegeerd | `test_an_unknown_field_is_refused_and_nothing_is_written` |
| brokervelden gelden ook als onbekend (weiger-alles) | `test_the_fields_the_broker_injects_are_not_unknown` |
| lengtegrens weg | `test_a_value_longer_than_its_column_is_refused` |
| vocabulaire loopt uit de pas met de redactielaag | `test_the_vocabulary_has_one_source` |
| `Training.tenant_id == tenant_id` uit de repository | `test_a_training_of_another_tenant_cannot_be_assigned` |
| `User.tenant_id == tenant_id` uit de repository | `test_an_employee_of_another_tenant_cannot_be_assigned` |
| `schedule_training: high` weg | `test_the_write_tool_lands_in_the_hitl_gate` |
| dezelfde mutatie | `test_every_executable_tool_has_an_explicit_risk_level` (bestaande bewaker) |
| `high` -> `medium`: de HITL-poort gaat niet open | `TestScheduleTrainingGoesThroughTheHitlGate` |
| `admin` -> `write` | `test_writing_is_never_looser_than_reading_the_same_data` |
| `user_email` leesbaar in de redactielaag | `test_the_payload_policy_keeps_the_email_out_of_the_log` |
| een TWEEDE profiel krijgt de HIGH-schrijftool | `test_no_profile_gains_a_high_risk_tool_without_a_dated_reason` |
| generator raakt uit de pas met het manifest | `test_the_generator_and_the_committed_manifest_do_not_drift` |
| de belofte in de prompt wordt geherformuleerd | idem -- en dit is de mutatie waar de EERSTE versie van de guard groen op bleef |
| `local__read_file` (bestaat, maar niet gewired) in het manifest | `test_the_prompt_only_promises_working_tools_while_they_all_work` |

**Ronde 2 voegde negen mutaties toe**, op de reparaties zelf: de handmatige veldenlijst terug
(mist `user_id`), de `_`-prefix-conventie weg, de verzonnen lengtegrens terug, de exceptietekst
terug in het log, de success-controle uit de goedkeurroute, die controle verbreed naar `is not
True` (tegenrichting), `copilot` krijgt de HIGH-tool, de permissie weg terwijl de belofte blijft,
en `hitl_store=None`. Alle negen betrapt.

**Een mutatie die is WEGGELATEN, met de reden.** `status=TOEGESTANE_SCHEDULE_STATUS` vervangen
door `status=str(velden["status"]).strip()` bleef groen, en terecht: na de statuscontrole kan die
waarde alleen `assigned` zijn, dus de mutatie verandert niets. Een equivalente mutatie is geen
ongedekte mutatie, en hem als "niet betrapt" opschrijven zou een gat suggereren dat er niet is.

**Wat het mutatiebewijs NIET dekt, en dat is een echte grens.** Dat de tool zelf commit is
bewezen op de AANROEP (een sessiefabriek die commits telt), niet op de database. De unit-fixture
gebruikt SQLite met een `StaticPool`: alle sessies delen EEN verbinding, dus een niet-gecommitte
rij is ook zichtbaar voor een "verse" sessie. Op die opstelling kan geen enkele assertie over de
tabel onderscheid maken tussen wel en niet committen -- de bewering zou groen staan om de
verkeerde reden. Een bewijs op de database vraagt de PostgreSQL-fixture, met twee verbindingen.

---

## 8. Wat NIET is gedaan

- **Geen leespad op `employee_trainings`.** Een agent kan nu toewijzen maar niet opvragen wat er
  al is toegewezen. `hr_training_models.py` schreef "vandaag leest niets deze tabel uit"; er
  SCHRIJFT nu iets, en de privacyafweging die die docstring bij een leespad aankondigt is daarmee
  nog niet gemaakt.
- **De keten is niet ongemockt doorlopen tot stap 7.** Dat vraagt proefdata en een echt
  taalmodel (paragraaf 7).
- **Geen koppeling van `analyze_skill_gap` naar `schedule_training`.** De agent moet zelf de
  brug leggen; er is geen code die een gemeten kloof omzet in een voorgestelde training.
- **De 14 andere manifesten die `schedule_training` noemen zijn NIET aangeraakt.** Gemeten: geen
  van die skills heeft een broker-profiel in `config/tool_permissions.yml`, dus ze zijn
  default-deny en krijgen door deze wijziging geen nieuwe bevoegdheid. Zodra een van die skills
  een profiel krijgt, is dat een eigen beslissing met een eigen afweging.
- **`local_registry` is NIET gewired in `BaseSpecialistAgent`.** Gemeten: `local_registry = None`
  op het skillpad, terwijl `base_agent.py:235` het wel goed doet. De eenregelige fix bestaat dus
  al elders. Ik heb hem hier NIET gedaan: `local__llm_generate` toegankelijk maken voor een skill
  die personeelsdata leest, is een uitgaand kanaal dat de redactielaag niet dekt, en dat is een
  eigen afweging. Eigen brief.
- **Een pre-existente rode test buiten de testpoort.** `tests/test_tool_broker_local.py` faalt met
  "Agent 'None' is not authorized to use tool 'local__read_file'" -- nagemeten in een verse
  worktree op 195cc0f1, dus niet door deze wijziging veroorzaakt. Dat bestand staat in `tests/`
  en niet in een van de vier poortmappen, dus het draait nergens blokkerend. Eigen brief.
- **De 134 overige manifesten zijn NIET geregenereerd.** `DEPARTMENT_TOOLS["hr_culture"]` bevat
  `schedule_training` niet meer, dus een regeneratie haalt de naam uit de veertien HR-manifesten
  waar hij nu nog staat. Dat raakt 134 bestanden en is een eigen wijziging; tot die tijd houdt de
  nieuwe profielguard de echte deur dicht.

---

## 9. Trainingssamenvatting

**Flow 1 -- de agent wijst een training toe, met menselijke goedkeuring**

- Actor: de piloot-skill `skillsgaptraining`, namens een aanvrager met het recht `admin`
- Voorwaarde: de medewerker en de training bestaan binnen DEZE tenant; de tenant komt uit de
  executiecontext en nooit uit de payload
- Actie: `TOOL_CALL: schedule_training {"user_email": "...", "training_name": "..."}`
- Systeemverwerking: de broker classificeert HIGH, maakt een HITL-ticket en voert NIETS uit; een
  mens keurt goed; `redeem_approval` toetst tool, tenant EN payload en zet het ticket op
  `consumed`; de registry zet de tenant-ContextVar (voor RLS), schrijft EEN rij met status
  `assigned` en commit expliciet
- Succesrespons: `{"success": true, "assigned": 1, "updated": 0, "status": "assigned"}` -- geen
  e-mailadres, geen trainingsnaam
- Foutrespons: `{"success": false, "error": "de toewijzing is niet uitgevoerd: de medewerker of de
  training bestaat niet binnen deze tenant"}`, met een rollback, en de repository-melding op EEN
  regel in het logbestand
- Uitzonderingen: onbekend veld in de payload (geweigerd met de veldnaam), status anders dan
  `assigned` (geweigerd), waarde langer dan de kolom (geweigerd), databasefout (de aanroep gooit
  `ToolExecutionException` zonder de SQL of het adres), en een tool die weigert terwijl het ticket
  al verzilverd is (de goedkeurroute meldt MISLUKT met classificatie `tool_failure`)

**Flow 2 -- dezelfde toewijzing een tweede keer**

- Actor: idem
- Voorwaarde: er staat al een rij voor deze medewerker en deze training
- Actie: dezelfde `TOOL_CALL`
- Systeemverwerking: `upsert_employee_trainings` werkt de bestaande rij bij in plaats van een
  tweede toe te voegen
- Succesrespons: `{"success": true, "assigned": 0, "updated": 1, "status": "assigned"}`
- Foutrespons: n.v.t.
- Uitzonderingen: geen -- de unieke sleutel is (tenant, medewerker, training)

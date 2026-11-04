# BE-AGT-045 -- Tool-payloads gepseudonimiseerd in plaats van verbatim bewaard

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-045 |
| Datum | 2026-08-03 |
| ADR | ADR-036 OP-27 (payload-kant); AI Act art. 12(2) (toetsbare logging) en art. 14 (menselijk toezicht, de HITL-uitzondering); AVG art. 4(5), art. 5 en art. 17 |
| Sprint | ADR-036 Fase B / OP-27 |
| Commits | `2446c78b` (rode tests) -> `72cec596` (implementatie) -> `608f741e` (rode tests ronde 2) -> fix ronde 2 |

---

## 1. Probleem

Een tool-payload is bij agent-gedreven uitvoering de `json.loads` van een `TOOL_CALL`-directive
en dus door een taalmodel geschreven. Die dict ging verbatim naar **vier bewarende sinks**:

| Sink | Pad |
| --- | --- |
| Event bus | `ToolBrokerService._publish_tool_event` |
| Leeropslag | `learning_event_handler._record_tool_event` schrijft `payload` als `observation_data` |
| Auditketen | `ToolAuditRepository.log_execution(tool_input=...)`, per ADR-019 onuitwisbaar |
| Uitvoeringsgeschiedenis | `tool_execution_history` (`api/v1/tool_broker_shared.py`), proces-globaal en ongelimiteerd, uitleesbaar via `GET /api/v1/tools/history/recent` |

Die vierde stond in de eerste ronde in geen enkele telling. De architectuur-guard bewaakte
AANROEPEN van sinks, en dit is een dict-assignment -- dus de claim "elke aanroep van die sinks is
gedekt" was waar en dekte minder dan hij suggereerde.

Alleen `query_hr_database` had sinds dag 3 een allowlist. De lokale, business- en externe paden
publiceerden rauw. Een tool kon dus zorgvuldig geen persoonsgegevens *retourneren* en toch
persoonsgegevens laten vastleggen, simpelweg omdat het model ze in de vraag had gezet -- ook in
een sleutel die de tool weigert.

## 2. Waarom blanken fout was -- en waarom de onderbouwing daarvoor niet klopte

**CORRECTIE (2026-08-03, bij de bron nagemeten).** Dit document en de ADR stelden vier rondes
lang: "AI Act art. 12 vraagt automatische logging over de levensduur van het systeem en art. 19
noemt de invoer die tot het resultaat leidde als verplicht logveld." **Dat is onjuist.**

- Art. 12(3) eist invoer-logging uitsluitend voor high-risk systemen uit **Annex III punt 1(a)**:
  biometrische identificatie op afstand. De vier minimumvelden (gebruiksperiode, de
  referentiedatabase, de invoer waarvoor de zoekopdracht een match gaf, en de identiteit van de
  personen die het resultaat verifieerden) gelden alleen voor die categorie. SanskritiSetu valt
  onder **Annex III punt 4** -- werkgelegenheid en personeelsbeheer.
- Art. 12(1) en 12(2) eisen dat het systeem gebeurtenissen automatisch KAN vastleggen, met het oog
  op risico-identificatie, post-market monitoring en toezicht op de werking. Niet: de invoer.
- Art. 19 noemt invoer helemaal niet. Het gaat over BEWAREN: minimaal zes maanden, en expliciet
  "unless provided otherwise in the applicable Union or national law, **in particular in Union law
  on the protection of personal data**". De AVG kan die termijn dus juist verkorten.
- En: pseudonimisering **verwijdert het persoonsgegeven niet**. Een pseudonym vermindert de
  identificeerbaarheid; het blijft een persoonsgegeven onder de AVG. De plichten uit art. 5 en
  art. 17 gelden er onverkort voor.

**Wat dat betekent voor de keuze.** Er was nooit een wettelijke plicht om waarden leesbaar te
houden. De keyed digest blijft de juiste keuze -- forensische bruikbaarheid, manipulatiedetectie,
en herkenbaarheid van herhaling zonder de waarde te kennen -- maar het is een **product-afweging,
geen wetsplicht**, en hij kost een AVG-verplichting die blanken niet zou kosten. Dat sluit aan bij
de OpenTelemetry GenAI-conventie, waar het vastleggen van prompt- en tool-inhoud standaard UIT
staat en expliciet aangezet moet worden. Dat is precies het model dat hier nu geimplementeerd is:
gepseudonimiseerd als default, onbewerkt alleen na een expliciete opt-in in een omgeving zonder
echte gegevens.

De oorspronkelijke onderbouwing stond in vier documenten en een moduledocstring. Ik heb de
wettekst pas bij de bron gelezen nadat de reviewers vier rondes lang lekken hadden gevonden -- dat
had als eerste gemoeten, niet als laatste.


Mijn eerste ontwerp verving niet-toegestane waarden door `"<redacted>"`. Dat is verworpen, maar op
grond van de drie argumenten die WEL standhouden -- niet op grond van een wetsplicht:

1. **Forensische bruikbaarheid.** Wie de originele waarde heeft, kan de digest narekenen. Bij een
   marker kun je achteraf niet meer vaststellen welke invoer bij welk resultaat hoorde, en dat is
   precies wat art. 12(2) van de logging verlangt: risico's kunnen identificeren en de werking
   kunnen volgen.
2. **Herhaling blijft zichtbaar zonder de waarde te kennen.** Dezelfde vraag geeft dezelfde
   digest, dus een patroon is te zien zonder het gegeven te lezen. Een marker maakt elke aanroep
   identiek en dus onbruikbaar voor patroonherkenning.
3. **Manipulatiedetectie.** Een digest verandert als de invoer verandert; een marker niet.

De prijs staat in de correctie hierboven: een pseudonym blijft een persoonsgegeven. Blanken zou
die prijs niet hebben. De afweging is dus bewust en niet afgedwongen.

## 3. Waarom keyed, en per tenant

**Niet een naakte SHA-256.** Een hash van een e-mailadres of een naam heeft lage entropie en is
met een woordenboekaanval terug te rekenen. Zo'n digest blijft dus een persoonsgegeven en is
geen bescherming. HMAC met een sleutel die alleen de server kent maakt er pseudonimisering van
in de zin van AVG art. 4(5).

**Niet `SECRET_KEY`.** Die heeft een gepubliceerde default
(`"a_default_secret_key_that_must_be_overridden_in_production"`) en is buiten productie
optioneel. Wie die waarde kent kan elke digest terugrekenen.

**Per tenant gescheiden, en die tenant komt van de aanroeper.** De tenant gaat mee in de
domeinscheiding, zodat hetzelfde e-mailadres in twee tenants verschillende digests geeft. Zonder
dat kan iemand met leesrechten op twee tenants personen over die grens correleren -- in strijd
met de isolatie die ADR-003/004/005 juist afdwingen.

De eerste versie las die tenant uit `payload["tenant_id"]`, met terugval op de constante
`"unscoped"`. Dat is in ronde 2 weerlegd door code te draaien: twee aanroepers van
`execute_tool` geven geen `context` mee (`tool_broker/router.py`,
`knowledge/sops/sop_executor.py`), dus daar deelden **alle** tenants een scope, en omdat de
payload modeloutput is kon een model bovendien zijn eigen scope kiezen. De tenant is nu een
verplichte keyword-parameter: resolutie via `context` -> de ADR-003 ContextVar -> harde fout.
Geen terugval, want beide alternatieven zijn erger dan een fout -- een gedeelde constante maakt
personen correleerbaar, en een per-proces willekeurige waarde sloopt *stil* de koppelbaarheid
waarop het art.-12(2)-argument rust. Dat laatste is exact de reden waarom de sleutel buiten
development ook hard faalt in plaats van iets te verzinnen.

Dit was dezelfde fout die een dag eerder in `hr_registry.py` is gesloten (BE-AGT-044 HIGH-4):
de tenant uit een door een model geschreven payload lezen.

**Wat leesbaar blijft volgt uit de wiring, niet uit een naam.** De eerste versie had een vaste
lijst van acht sleutelnamen die "de broker zelf zet". Twee daarvan zet hij (`tenant_id`,
`user_id` -- en alleen als er een `context` is); de overige zes kon het model zelf verzinnen, en
`_requested_by` is elders letterlijk `current_user.email`. Een e-mailveld altijd-leesbaar
verklaard binnen een PII-filter. De aanroeper geeft nu in `broker_keys` op welke sleutels hij
zelf uit de executiecontext heeft geinjecteerd; een naam kan niet onderscheiden wie een sleutel
schreef, de wiring wel.

**Niet idempotent, met opzet.** De vorige `_is_already_pseudonymised()` controleerde of een
waarde de vorm `{"hmac": ...}` had zonder naar de inhoud te kijken, zodat
`{"hmac": "<e-mailadres>"}` verbatim passeerde. De functie wordt per uitvoering precies eenmaal
op de rauwe payload toegepast, dus idempotentie was nooit nodig -- alleen de controle die het lek
veroorzaakte.

**Een beoordeelde sleutel is nog geen vertrouwde waarde (ronde 3).** De allowlist besliste op de
sleutelNAAM, terwijl de waarde eronder volledig modeloutput is -- en deze functie loopt voordat
de tool zijn parameters valideert. `{"role": "jan.jansen@acme.nl"}` ging daardoor verbatim door,
net als `{"limit": "salaris 82000"}` (vrije tekst in een veld dat een getal hoort te zijn) en een
hele geneste subboom onder een beoordeelde sleutel. Dezelfde fout als hierboven, een niveau
lager: een naam beslist iets wat het model beheerst.

Een waarde blijft nu alleen leesbaar als hij een **opsombare vorm** heeft: een getal binnen een
bereik, een korte code (`pending`, `high`), of een UUID. Vrije tekst en geneste structuren worden
altijd een digest. `role` staat daarom niet meer op de lijst: een rolnaam en een persoonsnaam
zijn qua vorm niet te onderscheiden.

**Ook de sleutelnaam is modeloutput (ronde 3).** Een sleutel bleef verbatim, ongeacht wat erin
stond. Een payload kon de persoonsgegevens dus in de SLEUTEL zetten met `None` als waarde, en dan
zag de vastgelegde regel er volledig schoon uit -- geen digest te bekennen. Een sleutel blijft nu
alleen zichtbaar als hij op een parameternaam lijkt (begint met een letter, alleen letters,
cijfers en liggende streepjes, maximaal 40 tekens). Al het andere wordt zelf een pseudonym met
een eigen domeinscheiding, zodat dezelfde naam binnen een tenant dezelfde uitkomst geeft en de
vorm van de aanroep traceerbaar blijft.

**Sleutels blijven zichtbaar, waar dat kan.** Zonder de sleutelnamen is de vorm van de aanroep
niet meer vast te stellen, en dat is wat art. 12(2) toetsbaar wil houden -- vandaar de
parameternaam-toets en niet "alles digesten".

## 4. De vierde sink, en waarom die de uitzondering is

`hitl_requests` toont `tool_input` aan de mens die de actie moet goedkeuren. Dat pad wordt
**bewust niet geredigeerd**: wie goedkeurt moet zien wat hij goedkeurt, anders is het toezicht
uit AI Act art. 14 een formaliteit.

De guard is gericht op het echte schrijfpad (`tool_broker/router.py`) en niet op
`hitl_store.create_ticket` -- die heeft nul aanroepers. Een eerdere versie controleerde dat
verkeerde bestand en zou groen zijn gebleven terwijl het schrijfpad wel geredigeerd raakte.

## 5. De sleutel

| Situatie | Gedrag |
| --- | --- |
| `TOOL_PAYLOAD_PSEUDONYM_KEY` gezet, >= 32 tekens | Gebruikt |
| Gezet maar korter dan 32 tekens | **Harde fout.** Met bekende klaartekst-paren (opsombare velden als `status` of `None`) is een korte passphrase offline te kraken tegen een hash per gok |
| Niet gezet, omgeving in `{development, test, local}` | Per-proces willekeurige sleutel, met waarschuwing |
| Niet gezet, elke andere omgeving | **Harde fout** |

Die laatste regel is een **allowlist en geen blocklist**, en dat is bewust.
`shared/config.is_production()` matcht alleen `"production"`, terwijl de vloot ook `staging`,
`blue` en `green` gebruikt -- en blue/green is een productietechniek. Met een blocklist vielen
die stil open op een per-proces sleutel, en dan geeft dezelfde waarde per Gunicorn-worker (en
na elke recycle, ADR-011) een andere digest. Precies de koppelbaarheid waarop het
art.-12(2)-argument rust valt dan weg zonder dat iemand het merkt.

## 6. Waarom de blocklist-sanitizer niet volstaat

`audit_utils.sanitize_tool_output` is een blocklist op sleutelnamen (`password`, `secret`,
`token`, `api_key`, `ssn`, `email`, `phone`). Een door een model geschreven payload kan elke
sleutelnaam hebben: `{"employee_id": "jan.jansen@acme.nl"}` bevat geen verboden naam en glipt er
ongehinderd door. Die functie blijft als tweede laag op de UITVOER staan, waar de vorm door de
tool zelf wordt bepaald; de docstring zegt nu eerlijk wat hij niet dekt.

## 7. Wat NIET gedekt is

**OP-27 is niet gesloten.** Alleen de payload. `result` en `error_detail` gaan nog ongefilterd
naar dezelfde sinks -- bij `local__read_file` is `result` bestandsinhoud, bij
`local__llm_generate` modeltekst, en `error_detail=str(exc)` echoot routinematig de
aanstootgevende invoerwaarde. Dat is **OP-29** en het moet gedicht zijn voordat er ergens een
`event_publisher` of `audit_repository` wordt aangesloten. Sinds ronde 2 heeft het een eigen
guard (`test_tool_results_are_registered_as_open.py`) met de vier bekende plekken als gedateerde
uitzondering, zodat er geen NIEUWE bij kan komen. In ronde 1 had deze bevinding geen enkele
guard, terwijl de bevinding ernaast (OP-28) er wel een kreeg -- in strijd met de NOOIT-regel.

**OP-28 is breder dan een kolom.** Niet alleen `tool_input`, maar ook `task_id`,
`error_detail`, `hitl_ticket_ref` en `hitl_approved_by` vallen buiten `compute_audit_hash`. Die
vijf staan in een keten die manipulatie hoort te detecteren, zonder zelf gedekt te zijn -- en
sinds deze wijziging draagt `tool_input` het gepseudonimiseerde spoor van de invoer,
terwijl `hitl_ticket_ref` en `hitl_approved_by` het bewijs dragen WELKE mens toestemming gaf.
De eerste versie van de guard noemde alleen `tool_input` en had de andere vier in de lijst "geen
aangeleverde invoer" staan, die bovendien twee namen bevatte die geen kolom van dit model zijn
(`created_at`, `metadata`) zonder dat de staleness-test daarnaar keek. Nu allebei de lijsten
gedateerd, met reden per regel en een staleness-test op beide. Niet opgelost, want de
hashberekening wijzigen raakt de ketenverificatie van bestaande regels en vraagt een
migratiebesluit.

**Ook niet gedekt: de exceptie-context.** `clients.py` en `mcp_client.py` zetten de rauwe payload
respectievelijk het rauwe resultaat in de `context` van een `ToolExecutionException`. Dat is geen
bewarende sink maar wel een uitleespad via logging, en het hoort bij dezelfde familie als
`error_detail`. Geregistreerd als gedateerde uitzondering in de payload-guard, met OP-29 als
plek waar het gedicht wordt.

**Correctie op de eerste versie van dit document: de sleutel is nu WEL boot-time verplicht.**

De eerste versie stelde dat `TOOL_PAYLOAD_PSEUDONYM_KEY` bewust niet aan
`config_validator.PRODUCTION_REQUIRED_VARS` was toegevoegd omdat dat "het opstarten in de
testomgeving brak". **Dat is nagemeten en onjuist.** `src/main.py:55` slaat
`validate_config_at_startup()` over zodra `TESTING=1` of `PYTEST_CURRENT_TEST` gezet is, en
`validate()` doorloopt die lijst alleen als `ENVIRONMENT` `production` of `staging` is. Toevoegen
kon de testomgeving dus niet breken. Er was een validatiefout gezien tijdens een testrun en daar
is een verklaring bij bedacht in plaats van hem te meten.

De conclusie was daarmee ook verkeerd. De runtime-fail-closed werd als voldoende gepresenteerd,
maar hij verplaatst een luide deploy-fout naar een stille toolstoring: de deploy slaagt, en de
eerste tool-aanroep faalt. De juiste ordening is provisioneren, dan de check aanzetten -- en die
is nu uitgevoerd:

| Plek | Wijziging |
| --- | --- |
| `.github/workflows/cd-staging.yml` | `check_secret STAGING_TOOL_PAYLOAD_PSEUDONYM_KEY` (blokkerend), Key Vault-secret, container-app-secret + env-var |
| `.github/workflows/cd-production.yml` | `check_secret PROD_TOOL_PAYLOAD_PSEUDONYM_KEY` (blokkerend), Key Vault-secret, `BASE_ENVVARS`-secretref |
| `deployment/blue_green/docker-compose.{blue,green}.yml` | env-var op alle vier de backend-services per bestand |
| `config_validator.PRODUCTION_REQUIRED_VARS` | toegevoegd, met test `test_a_production_process_refuses_to_start_without_the_key` |

**Actie voor Rakesh, VOOR de volgende deploy:** twee GitHub-secrets aanmaken, anders stopt CD bij
de secret-check (met opzet -- dat is beter dan een backend die elke tool weigert):

```text
STAGING_TOOL_PAYLOAD_PSEUDONYM_KEY
PROD_TOOL_PAYLOAD_PSEUDONYM_KEY
```

Genereren met `python -c "import secrets; print(secrets.token_urlsafe(32))"`, minimaal 32 tekens,
en daarna **niet meer wijzigen**: bestaande digests in de auditketen zijn dan niet meer na te
rekenen, en narekenbaarheid is precies de eigenschap waarvoor ze bestaan.

Er is geen `.env.example` in deze repo; die stap uit de oorspronkelijke lijst bestaat dus niet.
Blue/green wordt door de boot-check niet geraakt -- zie OP-30 -- maar daar dekt de
runtime-fail-closed het, omdat die een allowlist van omgevingen gebruikt.

## 8. Trainingssamenvatting

**Flow 1 -- een agent roept een tool aan met persoonsgegevens in de vraag**

- Actor: ALS-skill met een permissieprofiel
- Voorwaarde: geldige initiator, Council keurt goed, sleutel aanwezig
- Actie: het model stuurt `{"employee_id": "jan.jansen@acme.nl", "role": "Analyst"}`
- Systeemreactie: `role` blijft leesbaar (beoordeeld), `employee_id` wordt een keyed digest;
  beide sleutels blijven zichtbaar
- Succes: het log toont welke vorm de aanroep had, zonder de persoonsgegevens
- Fout: n.v.t.
- Uitzonderingen: het HITL-ticket toont de echte waarden aan de goedkeurder

**Flow 2 -- een omgeving zonder sleutel**

- Actor: elke aanroeper
- Voorwaarde: `TOOL_PAYLOAD_PSEUDONYM_KEY` ontbreekt en de omgeving is niet development/test/local
- Actie: een tool wordt aangeroepen
- Systeemreactie: de aanroep faalt; er wordt niets gepubliceerd met onbeschermde waarden
- Succes: n.v.t.
- Fout: `RuntimeError` met de reden en het gegenereer-advies
- Uitzonderingen: geen -- geen terugval op een naakte hash of op `SECRET_KEY`

## 9. Tests

`tests/unit/tool_broker/test_payload_pseudonymisation.py` -- vorm van de digest, sleutels
zichtbaar, digest verandert mee met de sleutel, tenant-scheiding via de PARAMETER, een onbruikbare
tenant wordt geweigerd, alleen door de aanroeper geinjecteerde sleutels blijven leesbaar (en
dezelfde naam wordt gedigest als hij dat niet is), een waarde in digest-vorm wordt alsnog gedigest,
fail-closed en ephemeer per omgeving, boot-check op de sleutel, elke tool gedekt,
HITL-uitzondering.

`tests/unit/tool_broker/test_pseudonymisation_leaks.py` -- de vier lekken uit ronde 2, op
GEDRAGSNIVEAU via `execute_tool` en de gepubliceerde event-data: geen gedeelde scope tussen
tenants, het model kan zijn scope niet kiezen, een payload-`tenant_id` gaat niet door voor
contextveld, vijf context-achtige namen worden gedigest, een digest-vormige waarde wordt gedigest,
geen tenant is een harde fout, en zonder sleutel gaat de tool niet af zonder dat er iets
onbeschermd wordt gepubliceerd.

`tests/unit/tool_broker/test_pseudonymisation_sinks.py` -- de auditregel legt het goedgekeurde
ticket in zijn eigen kolom vast, en de proces-globale uitvoeringsgeschiedenis (de vijfde sink)
bewaart geen rauwe payload.

`tests/architecture/test_tool_payloads_are_pseudonymised.py` -- allowlist-guard op sink-aanroepen
EN dict-literals, met `**`-unpacking en positionele argumenten als overtreding; vangnet dat de
guard iets vindt; gedateerde uitzondering voor de exceptie-context plus staleness-test;
HITL-schrijfpad; geen `SECRET_KEY` in code; elke uitvoerbare tool heeft een beoordeelde allowlist.

`tests/architecture/test_audit_hash_covers_persisted_input.py` -- OP-28-guard, vijf gedateerde
uitzonderingen met reden per regel, staleness-test op BEIDE lijsten.

`tests/architecture/test_tool_results_are_registered_as_open.py` -- OP-29-guard met vier
gedateerde uitzonderingen, staleness-test en mutatietests in beide richtingen.

**Mutatie-getest.** Ronde 1, vijf richtingen: default weer doorlaten, naakte hash, fail-closed
weg, sleutels weglaten, redactie uit `service.py`. Ronde 2 aanvullend: de payload-guard is met
een tijdelijk bestand in het bewaakte pad in beide richtingen getoetst -- gemeten op 2026-08-03
bleef de vorige versie 5/5 groen met `log_execution(**{"tool_input": payload})` en
`store["x"] = {"payload": payload}` aanwezig. Die twee vormen zijn nu synthetische zelftests,
samen met een test die aantoont dat de guard de CORRECTE vorm niet verwerpt.

## 10. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/tool_broker/redaction.py` | Keyed, per-tenant digest; tenant als verplichte parameter met validatie; `broker_keys` in plaats van een namenlijst; idempotentiecheck verwijderd; sleutellevensloop |
| `src/core/tool_broker/service.py` | Tenant centraal en fail-closed bepaald (ook voor de HITL-lookup, die hem eerder uit de payload las); `broker_keys` uit de context-injectie; sink-parameter heet `publish_payload`; tenant-routing via parameter; `hitl_ticket_ref` naar de auditregel |
| `src/core/api/v1/tool_broker/execution_router.py` | Vijfde sink: payload geredigeerd voor hij in `tool_execution_history` belandt |
| `src/core/config/config_validator.py` | `TOOL_PAYLOAD_PSEUDONYM_KEY` verplicht bij opstarten in productie/staging |
| `.github/workflows/cd-{staging,production}.yml` | Sleutel geprovisioneerd: blokkerende secret-check, Key Vault, env-var |
| `deployment/blue_green/docker-compose.{blue,green}.yml` | Sleutel op alle backend-services |
| `src/core/tool_broker/audit_utils.py` | Docstring eerlijk over wat een blocklist niet dekt |
| `src/core/tool_broker/audit_repository.py` | Waarom hier niet nog eens geredigeerd wordt; OP-28 (vijf kolommen) en OP-29 benoemd |
| `tests/fixtures/tool_execution_tenant.py` | Fixture die de tenant-ContextVar zet voor tests die echt een tool uitvoeren |
| `docs/adr/036-...md` | OP-27 bijgewerkt met ronde 2 en NIET gesloten; OP-28 verbreed; OP-29 met guard; OP-30 toegevoegd |

---

## Ronde 5 (2026-08-04) -- drie fixes erbij, en waar de grens nu ligt

Gate 2 ronde 5 gaf van beide reviewers CHANGES_REQUESTED terwijl alle vier de gates op de norm
stonden (pyright 0, ruff schoon, mypy 52, alembic 1 head, suite 15.144/0). Dat is het punt van die
gates: ze meten of de code compileert en de tests slagen, niet of het ontwerp klopt.

### De zesde sink -- en de vier die niet liepen

De belangrijkste vondst kantelt het risicobeeld van deze hele feature. Van de vijf bewarende sinks
die OP-27 hardde zijn er **vier latent**: nergens in `src/` wordt een `ToolBrokerService` met een
`audit_repository` of een `event_publisher` geconstrueerd, dus die code loopt vandaag niet. De enige
van de vijf die wel loopt is de proces-globale `tool_execution_history`, en die is geredigeerd.

Intussen bestond er een **zesde** sink die niemand had geteld, en die is volledig live:
`copilot/council/audit_writer.py` zet `proposal.action_params` -- dezelfde dict die
`copilot/service.py:418-425` als `payload` aan `execute_tool` geeft -- verbatim in
`council_decisions.action_params` (JSONB, NOT NULL) en verbatim in de canonieke JSON waarover
`decision_hash` wordt berekend. Voor dezelfde uitvoering stond in `tool_audit_logs.tool_input` netjes
een digest.

De bestaande architectuurguard kon dit structureel niet zien: zijn `SCAN_ROOTS` waren alleen
`src/core/tool_broker` en `src/core/api/v1/tool_broker`, en `GUARDED_DICT_KEYS` kende `action_params`
niet.

**Gefixt in `persist()`, en de plek is een eis en geen stijlkeuze.** De redactie staat op de
aanroepplek en niet in `compute_canonical_json()`, omdat twee onafhankelijke verifiers
(`chain_verifier.py:92` en `report_generator.py:72-100`) de hash herberekenen uit `row.action_params`.
Zat de redactie in de hashfunctie, dan redigeren zij een al geredigeerde waarde nog eens en meldt
elke historische rij zich als gemanipuleerd. `dataclasses.replace()` maakt een geredigeerde kopie,
zodat het voorstel dat daarna naar `execute_tool` gaat de echte waarden houdt -- en dat is precies
waarom de redactie ook niet in `ProposalBuilder` kan.

**Dezelfde transactie had een tweede deur.** `OfficerVerdictRow.evidence` gaat onbewerkt mee en
wordt meegehasht. Een AST-scan over alle evidence-constructies van alle zeven officers wees precies
een echt lek aan: `privacy_officer` legde de rauwe `action_params["tenant_id"]` vast op het
VETO-pad. Dat is nu de vergelijkingsUITKOMST plus het type; de detectie en het VETO blijven intact.

**De grens die daaruit volgt, expliciet:** wat uit `action_params` komt valt onder OP-33 en is
gefixt. Wat uit `message` of `reasoning` komt valt onder OP-38 en is dat niet -- die twee kolommen
dragen dezelfde tekst onbewerkt, dus redigeren van een afgeleide in `evidence` zou daar niets
sluiten. Het is bovendien art.-14-materiaal en verdient een eigen afweging over wat een mens moet
kunnen lezen.

### De sleutelafleiding, voor de eerste deploy

`pseudonymisation_key()` deed een enkele `hashlib.sha256(configured)` en de enige eis was LENGTE --
`"a" * 43` haalde die. Nu `hashlib.scrypt` met `n=2**14` (16 MB; `2**15` tikt tegen de standaard
`maxmem` van OpenSSL aan) en een vaste salt, want een willekeurige salt zou de afleiding per proces
anders maken en daarmee stil de koppelbaarheid slopen.

De sterkte-eis heeft **twee** regels, en dat is een meetresultaat en geen ontwerpkeuze. Over 200.000
uitkomsten per generator zakt `token_urlsafe(32)` niet onder 22 verschillende tekens, maar
`token_hex(16)` zakt tot 8 -- en `"abcdefgh" * 6` heeft er ook 8. Een drempel op het aantal
verschillende tekens kan een sleutel met 128 bits entropie dus niet van een triviale onderscheiden.
Daarom: drempel 8 PLUS een herhalingsregel die ook AFGEKAPTE herhalingen vangt (de klassieke
`s in (s + s)[1:-1]`-truc laat `("SanskritiSetu" * 4)[:45]` door). Verificatie: 300 sleutels per generator over de VIER generatoren in `KEY_GENERATORS` (`token_urlsafe` 24/32, `token_hex` 16/32)
uit vijf generatoren, nul afwijzingen.

De eis staat in EEN functie -- `key_strength_problem()` -- met twee aanroepers: de runtime gooit
ermee, `config_validator` meldt ermee. Een eigen kopie per kant is precies de divergentie waarvoor
de lengte-eis daar al stond: een variabele die de boot-check haalt maar door de runtime wordt
geweigerd betekent een geslaagde deploy waarna elke tool-aanroep faalt. Bij het uitvoeren bleek die
divergentie breder dan de twee plekken: `_check_secret_strength()` draaide alleen bij
production/staging, terwijl de runtime een zwakke sleutel in ELKE omgeving weigert. De sterkte-check
staat nu ongeconditioneerd.

`_HMAC_DOMAIN` is naar `:v2` omdat de afleiding is gewijzigd. Dat was gratis omdat er nog niets is
gedeployed; na de eerste productie-digest is het een breaking change.

**Wat de sterkte-eis niet is:** een raadbaarheids-orakel. `sanskritisetu-staging-key-2026-08` heeft
16 verschillende tekens en is geen herhaling, dus die komt erdoor. Dat staat als grens in de
docstring; de echte verdediging is generatie met `secrets`.

### De goedkeuringspoort

Bij het narekenen van de OP-31-onderbouwing bleek `src/core/tool_broker/router.py` nul importeurs te
hebben in `src/`: `/v1/tools/hitl/*` wordt niet geserveerd (OP-37, en de frontend roept die vier
endpoints wel aan). De HITL-poort die de app daadwerkelijk aanbiedt is
`POST /api/v1/gatekeeper/hitl/approve` en `/reject` -- en daarin kwam `get_current_user` nul keer
voor. Elke gebruiker met een geldig tenant-token kon dus elk openstaand ticket goedkeuren, met een
zelfgekozen naam in het veld dat OP-28 registreert als de kern van het art.-14-toezicht.

Beide endpoints eisen nu een beheerdersrol en halen de identiteit uit het token; het body-veld blijft
bestaan maar wordt genegeerd, hetzelfde "context wint"-patroon dat `service.py:162` al voor
`payload["tenant_id"]` gebruikt.

**Het admin-vocabulaire is een keuze en geen consolidatie.** Er zijn zeven admin-checks in drie
onverenigbare vocabulaires (OP-40); deze fix consolideert er twee. Een `system_admin` is admin in
het hele `admin/`-domein maar wordt hier geweigerd. Dat staat vastgepind in een tabel van zes
gevallen, zodat een latere verschuiving een zichtbare testwijziging is.

### Wat er nog open staat

Twaalf OP-nummers in ADR-036 (OP-32, OP-34 t/m OP-44), waarvan vijf (OP-35, OP-36, OP-39, OP-41, OP-42) nog GEEN guard hebben en alleen een voorgestelde remedie -- gemeten in ronde 7 met `git grep` over `tests/`. De overige met een guard of een gedateerde
uitzondering plus staleness-test. De twee die het meest wegen: **OP-36** -- er is voor geen van de
drie plekken waar tool-invoer bewaard wordt een wisroute, en met het intrekken van de art.-19-claim
is er ook geen wettelijke bewaargrond meer die dat dekt -- en **OP-35**, een geweigerde tool-aanroep
laat geen auditspoor achter omdat vier fail-closed weigeringen raisen voor de `try` waarvan de
`finally` de auditregel schrijft.

## Dag 1 (2026-08-06) -- de goedkeuringslus, en het laatste live klaartekstpad

Dit is de eerste dag van vijf uit het plan dat na de audit van onderaf is vastgesteld. De audit
draaide de prioriteit om: niet meer sinks dichtzetten, maar eerst de lus sluiten waar de payload
vandaan bleef komen.

### Waarom dit eerst moest

Er bestaan twee gescheiden goedkeuringssystemen. `hitl_requests` wordt gevuld door de gatekeeper en
heeft een geserveerde goedkeuringsroute -- een gesloten lus. `hitl_tickets` wordt gevuld door de
copilot, en de approve/reject-routes daarvoor stonden in een bestand met **nul importeurs**. De
poort in `tool_broker/service.py` leest juist die tweede tabel.

Gevolg: een HIGH-risk actie via de copilot maakte een ticket, kon nooit worden goedgekeurd, bleef
permanent geblokkeerd, en zijn onbewerkte inhoud bleef eeuwig staan. Redigeren-bij-goedkeuring, wat
het eerste plan wilde, zou dode code zijn geweest -- er wordt namelijk nooit goedgekeurd.

### Wat er is gebouwd

**Een eigen `hitl_router.py` met precies vier routes.** Het plan zei "mount `tool_broker/router.py`".
De review op dat voornemen mat dat dat bestand elf routes bevat, waaronder een tokenendpoint dat het
wachtwoord niet tegen de database controleert en het opgegeven e-mailadres in het token zet -- terwijl
de authenticatielaag de echte gebruiker uit die claim oplost. De guard ernaast vergelijkt de
omgevingsnaam exact, zonder kleine letters, dus staging viel erbuiten. Zelf nagemeten. Die router is
dus niet gemount; de vier goedkeuringsroutes zijn mechanisch verplaatst naar een eigen bestand.

**Van een afgehandeld ticket blijft alleen het besluit staan.** Bij goedkeuren, afwijzen en verlopen
wordt de payload in dezelfde UPDATE herbouwd: wie het vroeg, wanneer, welk besluit-id, welke tool en
welk risiconiveau blijven; alle door het model geschreven parameters verdwijnen. In plaats daarvan
komt er een keyed digest van wat er stond, met dezelfde per-tenant scheiding als de rest van deze
feature. Zo blijft narekenbaar WAT er is goedgekeurd zonder dat de inhoud bewaard blijft.

Een pending ticket blijft wel volledig zichtbaar. Dat is bewust: wie goedkeurt moet zien wat hij
goedkeurt (AI Act art. 14).

**De websocket zond het rauwe commando rond.** Alle drie de meldfuncties zetten het volledige ticket
op een kanaal dat alleen op tenant filtert, zonder rolcheck. De route aanbieden zonder deze fix zou
de situatie slechter hebben gemaakt dan ervoor -- zonder gemounte route werd er nooit goedgekeurd en
lekte er dus ook niets. Het veld wordt nu weggeprojecteerd in de notifier zelf, niet vertrouwd op
opruimen bij resolutie: dat laatste is timing-afhankelijk en de eerste melding vuurt juist eerder.

**De goedkeurder wordt niet meer verzonnen.** Bij een onbekende gebruiker gaf de code een vast
e-mailadres terug, in beide takken, plus een kale except die elke fout opslokte. Dat veld is precies
wat de schermen tonen als de mens die de actie goedkeurde. Nu leeg als de gebruiker niet bestaat; de
database-verwijzing is het bewijs, het adres is presentatie.

**Een retentie-actor MET een plek in de planning.** Verwijdert afgehandelde tickets na 395 dagen.
Bij het bouwen bleek het voorbeeld dat ik wilde kopieren zelf nergens ingepland te staan -- een
retentiebelofte die niemand nakomt, zonder dat er ooit een foutmelding komt. Daar staat nu een guard
op: elke opruimactor moet in de planning voorkomen, met dat ene bestaande geval als gedateerde
uitzondering plus een test die afgaat zodra die uitzondering onterecht blijft staan.

### Wat bewust NIET is gebouwd

De review vroeg om een guard die elke route zonder eigen authenticatiecontrole blokkeert. Gemeten op
de samengestelde applicatie: 155 van de 839 routes zouden opvallen. Een uitzonderingslijst van die
omvang kan ik niet per regel onderbouwen, en een lijst die je niet kunt onderbouwen is geen borging.
De meting is geregistreerd zodat hij niet opnieuw gedaan hoeft te worden; triage eerst, guard daarna.

### Twee eigen fouten, gevangen door de verplichte regressiecheck

De registry-file groeide over de architectuurgrens van 80 regels, en ik voegde een tweede
import-statement toe uit een module waarmee het koppelingsbudget al vol was. Beide zijn regressies
die ik zelf maakte terwijl ik iets anders repareerde. De blokkerende check ving ze allebei; daarna
opnieuw koud gedraaid.

### Meting na dag 1

15.270 tests geslaagd, 1 gefaald, nul worker-crashes. Die ene is het bekende volgorde-probleem: hij
slaagt los, en het is elke run een andere test. Pyright nul (twee keer gemeten), mypy nul, ruff
schoon, een enkele migratiekop, 33 integratietests groen tegen een echte database.

## Verwerking van twee blinde reviewrondes (2026-08-06/07)

Dag 1 leverde een goedkeuringslus op die geserveerd was. Twee blinde rondes daarna toonden dat hij
niet werkte, en waarom mijn eigen tests dat niet konden zien.

### Wat er niet werkte, en waarom geen test het zag

**De goedkeuring was onverzilverbaar.** De broker schrijft de tenant en de gebruiker uit de
uitvoeringscontext in de gegevens VOORDAT de goedkeuringspoort draait. Die twee velden telden mee in
de vergelijking bij uitvoering, en niet bij goedkeuring -- want op het moment van goedkeuren bestaan
ze nog niet. De twee kanten kwamen dus per definitie op een andere waarde uit, en elke menselijke
goedkeuring werd geweigerd.

Mijn tests konden dat niet zien omdat ze aan BEIDE kanten dezelfde handgemaakte gegevens
gebruikten. Zo'n test bewijst alleen dat een functie tweemaal hetzelfde antwoord geeft. Wat het wel
vangt is een rondgang over de ECHTE producent: ticket aanmaken zoals de copilot het doet,
goedkeuren zoals de route het doet, uitvoeren zoals de broker het doet. Die test staat er nu, tegen
een echte database.

**De opruimer draaide voor de tweede keer niet.** Eerst startte het proces nergens. Dat had ik
gerepareerd -- waarna bleek dat het proces wel draaide maar zijn opdrachten naar een wachtrij in
zijn eigen geheugen stuurde, met "succesvol in de wachtrij gezet" in het logboek. En daarna bleek
dat de werker die ze had moeten uitvoeren helemaal niets uit de echte wachtrij las, door een
ontbrekend stukje in zijn startopdracht.

Drie lagen, drie keer dezelfde vorm: iets meldt zich gezond en doet niets.

### De blokkerende bevinding

De naam van de actie komt uit het taalmodel en had geen enkele begrenzing -- geen maximumlengte,
geen toegestane waarden -- terwijl het veld ernaast er wel een heeft. Die naam belandde onbewerkt in
het logboek dat per ontwerp nooit meer gewijzigd kan worden. Een prompt-injectie kon daar dus tot
256 tekens eigen tekst permanent in laten vastleggen, en het auditscherm gaf hem terug aan elke
beheerder.

De asymmetrie die dat veroorzaakte: op het uitvoerpad valideert de broker de naam, en de code zegt
dat ook letterlijk in een opmerking. Op het goedkeuringspad -- dezelfde aanvraag, een beslissing
verschil -- gebeurde dat niet.

Opgelost in drie lagen. Aan de rand een vorm-eis, zodat vrije tekst niet eens representeerbaar is.
Bij de ticketgrens dezelfde validatie die de uitvoerder al deed, uit EEN definitie zodat de twee
paden niet opnieuw uiteen kunnen lopen. En bij het logboek zelf een normalisatie die een onbekende
naam vervangt door een markering plus een versleutelde vingerafdruk. Die derde laag is de enige die
de belofte onvoorwaardelijk maakt: de eerste twee kunnen door een latere wijziging stilvallen.

### Wat dit over de bewakingen zei

Elke ronde vond dat mijn eigen bewaking te zwak was. Een bewaking die een tekst zoekt in een
configuratiebestand bleef groen toen de reviewer het echte startcommando verving en de naam in een
opmerking liet staan. Een controle die `"tenant_id" in sql` toetst slaagt altijd, want die kolom
staat sowieso in de opvraging. Een toelaatlijst noemde drie velden die het antwoord nooit oplevert,
en de bewaking ernaast bevestigde vrolijk dat ze in de lijst stonden -- die toetste de lijst in
plaats van het antwoord.

Elke bewaking wordt sindsdien in beide richtingen mutatie-getest: kapot maken wat hij hoort te
vangen, en controleren dat een legitiem geval er niet in blijft hangen.

### Twee reviewbevindingen die bij nameten niet klopten

Een reviewer stelde dat het zusterpad dezelfde regel nodig heeft dat je je eigen aanvraag niet mag
goedkeuren. Dat model kent echter geen menselijke aanvrager -- die aanvragen komen van een agent. Een
controle bouwen op een veld dat niet bestaat is schijnzekerheid; vastgelegd als openstaande vraag
met de meting erbij.

Een reviewer beweerde dat een guard vacuum was en dat de auditregel bij afwijzing ontbrak. Beide
door mij nagemeten en beide onjuist. Een reviewer heeft niet automatisch gelijk.

### Stand

Alle bevindingen uit beide rondes zijn verwerkt. Er is nog GEEN blinde ronde over die verwerking
gegaan -- alles hierboven is door mijzelf gerepareerd en door mijzelf nagemeten. Zie
`docs/backend/review/review-BE-AGT-045.md` voor de volledige lijst en voor wat Rakesh moet doen
voordat dit in staging kan werken.

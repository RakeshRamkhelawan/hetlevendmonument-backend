# Review BE-AGT-045 -- Payload-pseudonimisering

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-045 |
| Datum | 2026-08-03 |
| Datum laatste ronde | 2026-08-04 |
| Reviewvorm | Gate 2 vooraf gedraaid, **vijf rondes** plus een planreview door Rakesh; ronde 2 t/m 5 op een commit-hash en niet op de working tree |
| Omvang | ~330 regels productiecode in 6 bestanden + 4 deploy-bestanden; na ronde 5 uitgebreid met 3 fixes in 5 bestanden en 4 nieuwe guards |
| Uitkomst | Ronde 1-5 alle CHANGES_REQUESTED. Ronde 5 verwerkt in 9 commits (2940dccf t/m 7c5b6d5b); **ronde 6 uitstaand** -- zie par. 7 |

---

## 1. De procesfout die ik zelf maakte

De eerste Gate 2-ronde is deels onbruikbaar, en dat is mijn schuld. Ik draaide mutatietests op de
working tree terwijl beide reviewers die aan het lezen waren. Ze hebben elk gebroken
tussentoestanden gezien -- een met een naakte hash, een met het fail-closed-pad achter
`if False:` -- en allebei terecht geconcludeerd dat een oordeel op een bewegende tree niet
overdraagbaar is.

De les is niet "beter opletten" maar structureel: **mutatietests horen op een kopie, en een
reviewer krijgt een commit-hash mee, niet een werkmap.** De tweede ronde verwijst expliciet naar
`git show 72cec596`. Een commit staat per definitie stil, ongeacht wat er in de tree gebeurt --
zo kon de documentatie parallel worden geschreven zonder de review te vervuilen.

Bijkomend leerpunt: dat beide reviewers de mutatie betrapten en er een CRITICAL van maakten, is
precies waarom de gate bestaat. Hun `if False: raise`-observatie legde bovendien een echte
vacuum-assertie in mijn guard bloot die ook zonder de mutatie fout was.

## 2. Wat het vooronderzoek weerlegde, vóór de review

Mijn eerste ontwerp verving waarden door `"<redacted>"`. Dat is verworpen op grond van
forensische bruikbaarheid, zichtbaarheid van herhaling en manipulatiedetectie -- **niet** op grond
van een wetsplicht, zoals ik hier eerst schreef. Zie par. 6c: die onderbouwing klopte niet, en het
heeft tot ronde 4 geduurd voordat ik de wettekst bij de bron heb gelezen. En een naakte SHA-256
volstaat niet: een hash van een e-mailadres is met een woordenboekaanval terug te rekenen.

Dat een blocklist niet werkt is geen theorie: `sanitize_tool_output` somt `email`, `phone`,
`ssn` op, maar `{"employee_id": "jan.jansen@acme.nl"}` glipt erdoor. Een door een model
geschreven payload kan elke sleutelnaam hebben.

## 3. Bevindingen uit ronde 1 en hun verwerking

| Bevinding | Severity | Verwerking |
| --- | --- | --- |
| Sink-guard ving alleen de letterlijke `payload=payload`; aliassen, kopieen en positionele argumenten glipten erdoor (7 van 8 varianten aangetoond) | HIGH | Omgedraaid naar een **allowlist**: elk bewaakt argument moet exact `publish_payload` zijn; positionele argumenten zijn een overtreding. Scope uitgebreid van alleen `service.py` naar de hele tool_broker- en API-laag |
| `any(ast.Raise)` was te voldoen met dode code | CRITICAL | Assertie verwijderd. Fail-closed wordt afgedwongen door de GEDRAGSTEST, die aantoonbaar sterft onder de mutatie |
| `tenant_id` en `_hitl_ticket_ref` werden gedigest -> tenant-routing op de event bus en de koppeling auditregel-ticket braken | HIGH | `ALWAYS_PUBLISHABLE` voor velden die de broker zelf uit de context zet. Die zijn geen modeloutput; digesten beschermde niets en brak twee dingen |
| Rauwe payload op beide foutpaden en in `tool_input` | HIGH | Een punt van controle, en de aanroep staat nu binnen de `try` zodat een ontbrekende sleutel geclassificeerd en geaudit wordt |
| `is_production()` matcht alleen "production"; staging, blue en green vielen stil open | HIGH | Omgedraaid naar `EPHEMERAL_KEY_ENVIRONMENTS`; al het overige fail-closed |
| Zwakke passphrase geaccepteerd | MEDIUM | `MIN_KEY_LENGTH = 32`, fail-closed |
| Geen tenant-scheiding in de sleutel -> cross-tenant correlatie | MEDIUM | Tenant in de domeinscheiding van de HMAC, met test |
| Race op `_cached_key`; testvervuiling | MEDIUM | `threading.Lock`; autouse-fixture die voor EN na opruimt |
| Niet-idempotent, alleen gedocumenteerd | MEDIUM | `_is_already_pseudonymised()` |
| `_NOTHING_PUBLISHABLE` dode config met vier niet-bestaande tool-namen | LOW | Weg; namen gecorrigeerd tegen de echte handlers |
| `None` werd een digest; `default=str` gaf per run een andere digest | LOW | `None` blijft `None`; vaste fallback-marker |
| HITL-guards controleerden `hitl_store` (nul aanroepers) | MEDIUM | Gericht op het echte schrijfpad `router.py` |
| OP-28 werd genoemd maar bestond niet; OP-27-tekst stale | HIGH | OP-28 en OP-29 toegevoegd; OP-28 met guard; OP-27 expliciet NIET gesloten |
| Geen enforcement dat een nieuwe tool een beoordeelde allowlist krijgt | MEDIUM | Guard die de uitvoerbare tools enumereert en een expliciete regel eist |

## 4. Twee vacuum-tests van mijzelf

Beide gevonden doordat een mutatie ze niet doodde -- niet door ze te lezen.

**`test_digest_is_keyed_not_a_bare_hash`.** Ik vergeleek met `sha256(waarde)` terwijl de code de
JSON-vorm hasht, dus de digests verschilden altijd en de test slaagde ook bij een naakte
hash-implementatie. Vervangen door een eigenschapstest: de digest moet veranderen als de sleutel
verandert. Die sterft correct onder de mutatie.

**`test_secret_key_is_never_used_as_the_pseudonymisation_key`.** De sleutel wordt altijd naar 32
bytes gehasht en kan per constructie nooit gelijk zijn aan de `SECRET_KEY`-string. Zou iemand
`_configured_key()` naar `SECRET_KEY` laten wijzen -- exact het defect dat de test claimde te
vangen -- dan bleef hij groen. Verwijderd; de AST-guard doet dit betekenisvol.

Dit is dezelfde fout die ik in deze sprintreeks bij andermans werk drie keer heb aangewezen.

## 5. Bevindingen uit ronde 2 -- drie bewezen lekken, en een claim van mij die niet klopte

Beide reviewers gaven opnieuw CHANGES_REQUESTED, en ze hadden op alle punten gelijk. Wat deze
ronde onderscheidt van de eerste: ze hebben de lekken niet beredeneerd maar **code gedraaid**.

| Bevinding | Severity | Verwerking |
| --- | --- | --- |
| De pseudonimiseringsscope viel zonder `context` terug op `payload["tenant_id"]`, en zonder die sleutel op de constante `"unscoped"`. Twee aanroepers geven geen context mee, dus daar deelden ALLE tenants een scope; en omdat de payload modeloutput is, kon een model zijn eigen scope kiezen | HIGH | Tenant is een verplichte keyword-parameter met validatie. Resolutie: `context` -> ADR-003 ContextVar -> harde fout. Geen terugval |
| `ALWAYS_PUBLISHABLE` bevatte acht NAMEN; de broker zet er twee, en alleen als er een context is. De overige zes kon het model zelf verzinnen -- `_requested_by` is elders letterlijk `current_user.email` | HIGH | `broker_keys`: de aanroeper geeft op welke sleutels hij zelf uit de context injecteerde. Wiring in plaats van naam |
| `_is_already_pseudonymised` controleerde de VORM `{"hmac": ...}` zonder naar de waarde te kijken; `{"hmac": "<e-mailadres>"}` passeerde verbatim naar alle bewarende sinks | HIGH | Verwijderd. De functie wordt per uitvoering precies eenmaal op de rauwe payload toegepast, dus idempotentie was nooit nodig -- alleen de check die het lek maakte |
| Een VIJFDE sink: `tool_execution_history` bewaart payload en resultaat verbatim in een proces-globale, ongelimiteerde dict, uitleesbaar via `GET /api/v1/tools/history/recent` | HIGH | Payload geredigeerd; resultaat naar OP-29. De guard ziet dict-literals nu ook |
| De guard was blind voor `**`-unpacking (`keyword.arg is None`) en voor dict-assignments | HIGH | Beide zijn overtredingen; met een tijdelijk bestand in het bewaakte pad gemeten dat de oude guard 5/5 groen bleef. Nu synthetische zelftests in beide richtingen |
| OP-29 stond alleen in de ADR en had geen architecture-test, terwijl OP-28 er wel een kreeg | HIGH | Eigen guard met vier gedateerde uitzonderingen, staleness-test en mutatietests |
| De OP-28-guard definieerde "invoerkolom" te smal: vijf echte invoerkolommen stonden in de lijst "geen aangeleverde invoer", die bovendien twee namen bevatte die geen kolom van dit model zijn | HIGH | Vijf gedateerde uitzonderingen met reden per regel; staleness-test op BEIDE lijsten |
| De HITL-koppeling hing aan het overleven van een payload-sleutel, terwijl `log_execution` een eigen kolom `hitl_ticket_ref` heeft die de broker nooit vulde -- en dat was het argument om die naam altijd-leesbaar te verklaren | MEDIUM | Kolom wordt gevuld met het GEVALIDEERDE ticket; de naamuitzondering is daarmee overbodig |
| Geen test op de fail-closed wiring in `service.py` | MEDIUM | `test_no_pseudonymisation_key_means_no_execution` |
| Onware docstring-verwijzingen (een naar `PRODUCTION_REQUIRED_VARS` waar de sleutel niet in stond, een naar een niet-bestaand testbestand) | LOW | Beide gecorrigeerd; de eerste is nu waar geworden |

### De claim die niet klopte

De eerste versie van dit document zei dat `TOOL_PAYLOAD_PSEUDONYM_KEY` niet aan
`config_validator.PRODUCTION_REQUIRED_VARS` was toegevoegd omdat dat het opstarten in de
testomgeving brak, en presenteerde dat als een afweging.

**De security-reviewer heeft dat nagemeten en het klopt niet.** `src/main.py:55` slaat
`validate_config_at_startup()` over zodra `TESTING=1` of `PYTEST_CURRENT_TEST` gezet is, en
`validate()` doorloopt die lijst alleen als `ENVIRONMENT` `production` of `staging` is. Toevoegen
kon de testomgeving dus niet breken. Ik heb een validatiefout gezien tijdens een testrun en daar
een verklaring bij bedacht in plaats van hem te meten -- precies de fout waar ik in deze
sprintreeks anderen op heb aangesproken, en ik heb hem als vaststaand doorgegeven.

De conclusie was daarmee ook verkeerd. De runtime-fail-closed die ik als voldoende presenteerde,
verplaatst een luide deploy-fout naar een stille toolstoring. De juiste ordening is eerst
provisioneren, dan de check aanzetten -- en dat is nu gedaan: blokkerende secret-check plus Key
Vault plus env-var in beide CD-workflows, de sleutel op alle backend-services in beide
blue/green-compose-bestanden, en daarna de boot-check met een eigen test. Er is geen
`.env.example` in deze repo, dus die stap uit de oorspronkelijke lijst bestond niet.

## 6. Compliance

| Regel | Status |
| --- | --- |
| Gate 1 plan | OK -- goedgekeurd, met vijftien vooraf getoetste twijfels |
| Gate 2 dubbele reviewer-GO | Ronde 1 CHANGES_REQUESTED, verwerkt; ronde 2 CHANGES_REQUESTED op commit `72cec596`, verwerkt (par. 5); ronde 3 uitstaand |
| Gate 3 pyright / ruff / mypy | 0 / schoon / 52 (gelijk aan baseline, en geen fout in een aangeraakt bestand) |
| Rode test vóór de fix, eigen commit | OK -- ronde 1 `2446c78b` (9 rood); ronde 2 `608f741e` (13 rood, elk met de juiste foutmelding gecontroleerd) |
| Mutatie-getest | OK -- vijf richtingen in ronde 1; de guard in ronde 2 in beide richtingen, met een gemeten probe die de oude versie 5/5 groen liet |
| Bevinding zonder fix heeft borging | OK -- OP-28 (5 kolommen), OP-29 en de exceptie-context elk met guard + staleness-test; OP-30 in de ADR met reden waarom hij niet in deze dag past |
| ASCII-only | OK |
| Sprint-dag-brief | OK -- geschreven vóór de code |

## 6b. Bevindingen uit ronde 3

Beide reviewers weer CHANGES_REQUESTED, weer met gedraaide code. Twee bevindingen waren fouten
die ik in de ronde-2-commit zelf had gemaakt.

| Bevinding | Severity | Verwerking |
| --- | --- | --- |
| Een beoordeelde sleutel is nog geen vertrouwde waarde: `{"role": "<e-mailadres>"}` ging verbatim, net als vrije tekst in een getalveld en een hele geneste subboom | HIGH | Waarden blijven alleen leesbaar met een opsombare vorm (getal / korte code / UUID). `role` valt daarmee af |
| Ook de sleutelNAAM ging verbatim. Met `None` als waarde zag de regel er volledig schoon uit terwijl de persoonsgegevens in de sleutel stonden | CRITICAL | Een sleutel blijft alleen zichtbaar als hij op een parameternaam lijkt; anders zelf een pseudonym met eigen domeinscheiding |
| De rauwe payload lekte via `str(exception)` naar het `error`-veld van dezelfde regel, en naar de HTTP-500-body. Het redigeren van het `payload`-veld was dus omzeilbaar door de tool te laten falen | HIGH | Payload uit de exceptie-context bij de BRON gehaald (`clients.py`, `mcp_client.py`); router bewaart en toont alleen het exceptietype. `error` toegevoegd aan de OP-29-guard, wat meteen een tweede plek vond |
| **Mijn eigen fout:** ik beoordeelde de worker verkeerd en meldde dat als gerustheid. De worker voert tools WEL in-process uit (`src/core/tasks/workflow_tasks.py` -> `AutonomousAgent` -> lokale `ToolBrokerService`). Ik had `src/workers/` gegrepped en `src/core/tasks/` gemist -- een redenering over een importgraaf, met het voorbehoud er zelf bij genoemd | HIGH | Sleutel op beide worker-apps en op alle drie de services in `docker-compose.prod.yml` |
| **Mijn eigen fout:** de ronde-2-commit introduceerde een bootfout. `docker-compose.prod.yml` zet `ENVIRONMENT=production` zonder de sleutel die ik net verplicht maakte bij het opstarten | HIGH | Zie hierboven; in de `${VAR:?reden}`-vorm die dat bestand al gebruikte |
| Productie verwees naar `secretref:tool-payload-pseudonym-key` zonder app-level secret-definitie -- de enige secretref in dat bestand zonder | HIGH | Definitie toegevoegd; nagemeten: 6 refs, 8 definities, 0 zonder |
| De boot-check controleerde aanwezigheid, niet de minimumlengte -- een korte sleutel kwam erdoor en werd daarna door de runtime geweigerd | MEDIUM | Lengte-eis in `_check_secret_strength` |
| Een niet-gezette `ENVIRONMENT` viel binnen de ephemere-sleutel-allowlist, want de settings-default is `development` | MEDIUM | `_environment()` leest nu `os.environ` direct: geen omgeving is geen ontwikkelomgeving |
| `GET /tools/history/recent` gaf de hele regel terug, inclusief payload. Daarmee kon een gebruiker zelf een waarde insturen en de digest vergelijken met die van iemand anders -- de pseudonimisering omzeild zonder de sleutel | MEDIUM | Dezelfde projectie als `GET /history`; payload en resultaat gaan er niet meer uit |
| Vacuum-test op `hitl_store` (module zonder aanroepers) kon niet om een echte reden falen | LOW | Verwijderd; de architecture-guard doet dit op het echte schrijfpad |

## 6c. De onderbouwing die vier rondes lang niet klopte

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

## 7. Conclusie

De payload-kant is nu inhoudelijk in orde: pseudonimisering in plaats van blanken is de juiste
keuze en is onderbouwd met de wettekst, de sleutel is keyed, de scope is per tenant gescheiden
*en komt van de aanroeper*, wat leesbaar blijft volgt uit de wiring, en de guards zijn omgedraaid
van "zoek een verkeerde spelling" naar "eis de juiste waarde" -- inclusief de twee vormen die
ronde 1 aantoonbaar miste.

Wat blijft staan, met borging: **OP-27 is niet gesloten** (`result` en `error_detail` gaan nog
ongefilterd naar dezelfde sinks; bij `local__read_file` is dat bestandsinhoud), **OP-28** (vijf
kolommen die aangeleverde gegevens dragen vallen buiten de audit-hash) en **OP-30** (de
boot-check draait niet voor blue/green). Elk met een guard of een expliciete ADR-registratie met
reden.

De belangrijkste les gaat over mijzelf, en het zijn er twee.

Procedureel: ik heb de gate die ik vooraf plaatste vervuild door tegelijk mutatietests op de
working tree te draaien. Beide reviewers merkten dat. De structurele fix -- een reviewer krijgt
een commit-hash, geen werkmap -- werkte in ronde 2.

Inhoudelijk, en dit weegt zwaarder: in `redaction.py` heb ik twee fouten herhaald die één dag
eerder in `hr_registry.py` waren gesloten. De tenant uit een door een model geschreven payload
lezen, en een namenlijst gebruiken waar een herkomstcheck hoort. Beide reviewers wezen me op mijn
eigen oplossing van de dag ervoor. Dat een fix op één plek is doorgevoerd zegt niets over de
volgende module; de vraag "wie schrijft deze waarde" hoort bij elk nieuw bestand opnieuw gesteld
te worden, niet één keer per sprint.

En daarnaast: ik heb een oorzaak *beredeneerd* waar meten mogelijk was, en dat als vaststaand
doorgegeven (par. 5). De reviewer had het in één commando weerlegd.

---

## 7. Ronde 4 en 5, en de planreview door Rakesh

### 7.1 Ronde 4 -- de vorm-versus-herkomst-fout, derde iteratie

Beide reviewers weer CHANGES_REQUESTED. De kern in hun eigen formulering:

> Een filter dat toetst hoe iets ERUITZIET in plaats van waar het VANDAAN KOMT, verplaatst het lek
> naar wat die vorm toelaat.

Drie rondes, drie niveaus: een lijst NAMEN (ronde 2, het model koos de naam zelf), een TEKENKLASSE
(ronde 3, `Jan_Jansen_salaris_82000` en `Jan-Jansen` passeerden), en toen een OPSOMMING (ronde 4,
lidmaatschap van `TaskStatusLiteral`). Die opsomming stond alle drie de keren al gedeclareerd, twee
bestanden verderop.

Daarnaast bleek de vangrail te vragen of de regel BESTOND in plaats van of hij WAAR was. Gevolg:
zes afwijkingen tussen `PAYLOAD_POLICY` en de tools, waarvan er twee door reviewers werden gevonden
en vier pas bij gericht zoeken (`list_tasks: offset` leest `skip`; `test__slow: seconds` leest
`delay_seconds`; `test__echo` leest geen benoemde sleutel; `local__llm_generate: model` leest alleen
`prompt`; `create_task`/`update_task` 5 velden in de tabel versus 10 in het Pydantic-schema). Drie
ervan vielen buiten de guard omdat `LocalToolRegistry` geen `known_tool_names()` had -- inclusief
`local__run_shell` en `local__send_email`.

### 7.2 Ronde 5 -- de vier gates waren groen, de bevindingen niet

Gemeten voor de ronde: pyright 0 errors / 54 warnings, ruff schoon, mypy 52 (= baseline), alembic
1 head, suite 15.144/0. Alle vier op de norm.

Beide reviewers CHANGES_REQUESTED. Wat eruit kwam, gegroepeerd naar wat het werkelijk was:

**Ontbrekende borging (blokkerend).** OP-31 en OP-32 werden door architecture-tests aangehaald met
fase en prioriteit terwijl de OP-tabel bij OP-30 eindigde. Daarmee was eis 1 van de vier uit
`quality-gates.md` niet vervuld voor een groene guard met gedateerde uitzondering, en gold formeel
de hoofdregel (rode test).

**Een onjuiste bewering op de gevaarlijkste plek (blokkerend).** De in ronde 3 weerlegde
art.-19-claim stond nog in twee ASSERTIEMELDINGEN van
`test_audit_hash_covers_persisted_input.py`. Wie die test ziet falen leest de melding als argument
en concludeert dat de invoer leesbaar moet blijven -- precies de afweging die vier rondes de
verkeerde kant op ging.

**Een steekproef die zich als dekking voordeed (blokkerend).** De driftdetector itereert over
`_IMPLEMENTATIONS`, een handmatig literaal van twaalf tools, en niets controleerde of dat literaal
compleet was. De reviewer bewees het met een mutatie: een nieuwe tool met drie fouten in zijn
policy-regel gaf 18 tests groen.

**Een bewarende sink die WEL live is.** Van de vijf sinks die OP-27 hardde zijn er
vier LATENT (een `git grep` op `audit_repository=` of `event_publisher=` over `src/` is leeg).

> **Correctie 2026-08-05 (ronde 7).** Deze kop zei "een zesde bewarende sink, en de enige die
> live is". Dat was op beide helften onjuist: ronde 6 vond een ZEVENDE (`hitl_tickets.payload`
> via `copilot/service.py:528`, OP-47 -- ook live, en rauw), dus er zijn er minstens twee live.
> De actuele opsomming met de stand per plek staat op EEN plek: de moduledocstring van
> `src/core/tool_broker/redaction.py`. Vier kopieen van dat getal is precies waarom het drie
> keer misging.
Intussen zet `copilot/council/audit_writer.py` dezelfde dict die naar `execute_tool` gaat verbatim
in `council_decisions.action_params` en verbatim in de gehashte canonieke JSON. De bestaande guard
kon dat structureel niet zien: `SCAN_ROOTS` dekt alleen twee tool_broker-mappen.

**En de onderbouwing van OP-31 was zelf niet gemeten.** `src/core/tool_broker/router.py` heeft nul
importeurs in `src/`; die endpoints worden niet geserveerd. De fix is correct maar preventief, en de
ernstclaim over tickets die openlagen voor iedere ingelogde collega ging over een route die de app
niet aanbiedt. Dezelfde klasse als de art.-19-claim die net was rechtgezet.

### 7.3 Drie dingen die geen reviewer vond

Gevonden bij het zelf natrekken van hun bevindingen, en dat is het argument om dat natrekken te
doen in plaats van een reviewrapport over te nemen:

1. **Een geweigerde tool-aanroep laat geen auditspoor achter.** In `service.py::execute_tool` staat
   de `try` waarvan de `finally` de ADR-019-regel schrijft op regel 274, maar vier fail-closed
   weigeringen raisen daarvoor: permissiecheck (169), onbekende categorie (184), ontbrekende tenant
   (197) en de HITL-poort (210). Gevolg twee: `status="blocked"` is onschrijfbaar en
   `get_blocked_tools_count()` telt een status die nergens geschreven wordt -- een dashboard toont
   permanent nul geblokkeerde pogingen. Geregistreerd als OP-35.
2. **De art.-17-wisroute bereikt `tool_audit_logs.tool_input` noch `council_decisions.action_params`.**
   Geen enkele DSAR-implementatie raakt die tabellen, en `ToolAuditLog` heeft geen retentie terwijl
   `council_decisions` na 395 dagen wordt opgeruimd. OP-36.
3. **De telling van de wetsclaim was drie keer fout.** 13, toen 27, toen 35, en na het aanvullen van
   de ADR 44 treffers. Elke keer miste het zoekpatroon een spelling -- eerst `art.-12/19` met
   koppelteken, daarna `.claude/` en `.github/` buiten de zoekmap. Dat is exact les 6.6 uit de
   overdracht, gemaakt tijdens het VERIFIEREN van die les.

### 7.4 De planreview door Rakesh

Rakesh heeft het fixplan zelf nagemeten en zes dingen gevonden. Drie ervan zouden het plan
inhoudelijk kapot hebben gemaakt:

- **De entropie-eis alleen in de runtime zou de regressie herhalen die deze sprint al gefixt heeft.**
  `config_validator.py` toetst bij het opstarten alleen de LENGTE, en het commentaar drie regels
  erboven is door deze sprint geschreven en legt uit waarom: een variabele die de boot-check haalt
  maar door de runtime wordt geweigerd betekent een geslaagde deploy waarna elke tool-aanroep faalt.
  De eis staat nu in EEN functie met twee aanroepers. Bij het uitvoeren bleek de divergentie
  bovendien breder: `_check_secret_strength()` draaide alleen bij production/staging, terwijl de
  runtime een zwakke sleutel in ELKE omgeving weigert.
- **Een regelnummerlijst voor de wetsclaim was het verkeerde instrument** -- en het was het enige
  punt in het plan zonder borging, terwijl elk ander punt een OP-nummer kreeg. Nu een groene guard
  met een exacte verwachte telling per bestand.
- **De consolidatie van het admin-begrip was schijnzekerheid.** Er zijn ZEVEN admin-checks in DRIE
  onverenigbare vocabulaires (OP-40); de fix consolideert er twee. Het gekozen vocabulaire staat nu
  vastgepind in een 403-test, inclusief het geval `system_admin` dat hier bewust geen toegang krijgt.

En drie lekken in de sink die het plan zelf ging dichten:

- **`OfficerVerdictRow.evidence` gaat verbatim mee** in dezelfde `persist()`-transactie. Bij het
  natrekken bleek er precies EEN echt lek te zitten (de rauwe `params_tenant` van de
  PrivacyOfficer); wat uit `message`/`reasoning` komt is gedekt door OP-38 omdat die kolommen
  dezelfde tekst onbewerkt dragen. Die grens staat nu expliciet: uit `action_params` = OP-33, uit
  `message`/`reasoning` = OP-38.
- **`bind_execution_result` bindt het toolRESULTAAT aan dezelfde onuitwisbare rij** -- alleen de
  hash, geen klaartekst, dus milder. OP-39.
- **Er is een TWEEDE verifier.** Het argument dat er geen migratie nodig was, noemde alleen
  `chain_verifier.py:92`, maar `report_generator.py:72-100` reconstrueert onafhankelijk een
  `Proposal` uit de rij en draait `compute_canonical_json` opnieuw. Dat legt een harde eis op de
  implementatie: redigeer op de AANROEPPLEK in `persist()`, nooit binnen `compute_canonical_json` --
  anders wordt een al geredigeerde waarde nog eens geredigeerd en meldt elke historische rij zich
  als gemanipuleerd. Dat is de gevaarlijkste vondst van de hele ronde, en hij is voorkomen door een
  verifier na de eerste niet als DE verifier aan te nemen.

### 7.5 Wat ronde 5 heeft opgeleverd

Drie fixes met rode tests in aparte commits ervoor (sleutelafleiding, council-sink,
goedkeuringsgat), 14 nieuwe OP-rijen met borging, en vijf guards die eerlijker zijn geworden dan ze
waren:

| Guard | Was | Is |
| --- | --- | --- |
| wetsclaim | niets | groene guard, exacte telling per bestand, 4 spellingen, vangnet in beide richtingen |
| driftdetector | dekking = handmatig literaal | plus een test dat het literaal alle uitvoerbare tools dekt, en geen fantomen bevat |
| `_bounded_int`-grenzen | hardgecodeerd op een tool | elke grens heeft een geregistreerde herkomst, met staleness-test |
| `DEPLOY_ENVIRONMENTS` | handmatig literaal | gelezen uit `deployment/blue_green/docker-compose.*.yml` |
| officer-evidence | niets | elke construeerbare officer wordt UITGEVOERD met een merkwaarde; dekkingstest dwingt een beslissing af voor een nieuwe officer |

Alle nieuwe guards zijn mutatie-getest in BEIDE richtingen. Die van de officers in een `git worktree`
op `HEAD` buiten de hoofdmap, om niet te herhalen wat ronde 1 onbruikbaar maakte.

Twee fouten zaten in de TESTS en niet in de code, en beide wezen een verkeerde oorzaak aan:
`CouncilDecision.proposal_id` moet aan het voorstel gekoppeld zijn (zo doet productie het op alle
drie de constructieplekken) en `OfficerVerdict.verdict_id` heeft een eigen default-factory die in
`compute_officer_verdicts_hash` meegaat. Zonder die correcties faalde de hertelling-test op
identiteit terwijl de melding over redactie ging.

**De les die overblijft.** Vier van de zes dingen die Rakesh vond, en de drie die bij het natrekken
naar boven kwamen, hebben dezelfde vorm: een grens die te vroeg is getrokken. Een naamlijst die een
spelling mist, een dekkingsverzameling die een steekproef is, een verifier waarvan er twee zijn, een
canonieke plek die er twee van zeven is. Het patroon is niet onzorgvuldigheid -- het is stoppen met
zoeken op het moment dat er een antwoord ligt. De tegenmaatregel die in deze ronde werkte is per
vondst de vraag stellen: is dit HET geval, of het EERSTE geval?

## Dag 1 (2026-08-06) -- goedkeuringslus en het live klaartekstpad

Uitgevoerd volgens `docs/agent-briefs/generated/2026-08-05-sprint-dag-BE-AGT-045-dag1.md`.

**Taak 2-review op het VOORNEMEN gaf CHANGES_REQUESTED, en dat heeft een authenticatie-omzeiling
voorkomen.** Het plan zei "mount `tool_broker/router.py`". Gemeten: dat bestand bevat elf routes,
waaronder `POST /v1/tools/auth/token` -- dat het wachtwoord niet tegen de database controleert en
het opgegeven e-mailadres in het token zet, waarna `auth/dependencies.py` de echte gebruiker uit
die claim oplost. De guard ernaast vergelijkt `environment == "production"` exact, zonder
`.lower()`, dus staging valt erbuiten. Zelf nagemeten, beide helften. Geregistreerd als OP-61;
opgelost door een EIGEN `hitl_router.py` met alleen de vier goedkeuringsroutes.

**De volgorde in het plan was aantoonbaar erger dan de bestaande toestand.** Alle drie de
notify-functies zetten het volledige ticket -- inclusief onbewerkt `tool_input` -- op kanaal
`hitl:{tenant_id}`, en `/ws/hitl/{tenant_id}` was al gemount met alleen een tenantcheck en geen
rolcheck. De route aanbieden zonder die fix zou bij elke goedkeuring het shell-commando naar iedere
tenantgebruiker hebben gestuurd. OP-58, gesloten in dezelfde reeks.

| OP | Wat | Uitkomst |
| --- | --- | --- |
| OP-37 | goedkeuringslus was niet geserveerd | GESLOTEN. Twee oorzaken: de router was niet gemount EN de frontend riep `/v1/tools/hitl/...` aan zonder `/api`, terwijl hij elders consequent `/api/v1/...` gebruikt |
| OP-47 | rauwe payload in `hitl_tickets` | GESLOTEN. Alleen het besluit blijft, met een keyed digest als bewijs van wat er is goedgekeurd; plus een retentie-actor MET scheduler-entry |
| OP-58 | websocket zond rauw `tool_input` rond | GESLOTEN |
| OP-59 | verzonnen goedkeurder bij onbekende gebruiker | GESLOTEN |
| OP-60 | `cleanup_agent_critiques` staat in geen planning | OPEN, met guard + gedateerde uitzondering |
| OP-61 | tokenendpoint zonder wachtwoordcontrole | OPEN, latent (nul importeurs) |
| OP-62 | 155 van 839 routes zonder route-eigen auth | OPEN, bewust zonder guard |

**Bewust NIET gebouwd:** de route-brede auth-guard die de review vroeg. Gemeten: 155 van de 839
routes zouden opvallen. Een uitzonderingslijst van die omvang kan ik niet verantwoord onderbouwen,
en dat is precies de vorm van borging waar `quality-gates.md` voor waarschuwt. Als OP-62
geregistreerd met de meting.

**Twee eigen regressies, gevangen door de verplichte regressiecheck:** `optional.py` groeide naar
89 regels (ADR-033 max 80) en `agent_runtime->governance` ging van 7 naar 8 koppelingen doordat ik
een tweede import-statement uit dezelfde module toevoegde. Beide gefixt en opnieuw koud gedraaid.

**Gate 3 na dag 1:** 15.270 passed, 1 failed (`test_workflow_real_routing` -- het bekende
OP-46-slachtoffer: volgorde-afhankelijk, slaagt los, nul worker-crashes), pyright 0 (twee keer
gemeten), mypy 0, ruff schoon, alembic 1 head, 33 integratietests groen.


## Gate 2 ronde 3 op de verwerking, en wat de vraag "loop de HELE keten na" opleverde (2026-08-07)

De blinde securityreview gaf CHANGES_REQUESTED met zes blokkers. Maar de belangrijkste bevinding
kwam niet uit die review: Rakesh vroeg de volledige flow na te lopen in plaats van alleen mijn eigen
twijfels. Dat legde bloot dat er tussen "een mens wordt om goedkeuring gevraagd" en "de actie
gebeurt" VIER onafhankelijke breuken zaten -- en dat ik er twee nooit had kunnen zien, omdat ik de
hele sprint alleen de backend had bekeken.

| Schakel | Status voor 2026-08-07 |
| --- | --- |
| Copilot maakt een ticket | werkte |
| `/hitl/pending` serveert het | werkte |
| Het scherm toont het | **STUK** -- las een lokale lijst die nooit werd gevuld |
| De goedkeurknop | **STUK** -- postte naar een endpoint dat niet bestaat (404) |
| Goedkeuring -> uitvoering | **STUK** -- niets schreef ooit een ticketverwijzing |
| Verzilvering bij medium-tools | **STUK** -- poort vuurde alleen bij HIGH |

Alles wat deze sprint aan begrenzing was gebouwd -- binding aan tool en parameters, eenmalig
verbruik, vervaltermijn, auditketen -- zat dus in een doodlopende straat. De feature was veiliger
geworden zonder ooit te werken.

**Dat is ook het eerlijke antwoord op "waarom blijven reviewers blokkers vinden".** Ik verifieerde
de backend in isolatie, en een reviewer beoordeelt wat je hem aanwijst. Niemand volgde de keten van
begin tot eind tot daar expliciet om werd gevraagd.

### Wat er is gebouwd

Besluit Rakesh: direct uitvoeren bij goedkeuren, daarna wissen. Dat is de enige volgorde die zijn
eerdere wisbesluit verenigt met een werkende lus -- na het wissen zijn de parameters weg. De
goedkeuringsroute bleek precies de aanroeper die ontbrak; al het bindingswerk werd daarmee dragend
in plaats van dood.

Twee voorwaarden kwamen uit het narekenen van twijfels, niet uit de review: de poort moest ook
vuren bij medium risico (anders wordt een ticket voor drie van de vijf tools nooit verzilverd), en
er mag geen ticket ontstaan voor een tool die de uitvoerder niet mag draaien.

### Zes blokkers, elk met de mutatie die de vorige versie overleefde

OP-91 (planner-eis per omgeving), OP-92 (Redis-guard per commando), OP-93 (mijn holle
SQL-vergelijking), OP-94 (de Redis-URL brak bij 47,6% van de sleutels), OP-95 (modeltekst in de
gehashte raadsketen), plus M1/M4/M5/M6 als OP-96 t/m OP-99.

**Bij OP-95 had ik het eerst mis, en een bestaande test hield mij tegen.** Ik wilde de onderbouwing
van de raad integraal filteren; die test legt een bewuste keuze vast dat dat juist NIET moet, omdat
reason codes en tellingen dan onleesbaar worden. Het lek zat bij de bron. Gemeten dat niets die
tekst gebruikte -- hij ging het onuitwisbare logboek in zonder een enkele afnemer.

### De onderliggende reden, nu vastgelegd

Zeven holle guards in een week, drie ervan van mijzelf, twee daarvan als reparatie van een eerdere
holle guard. Een guard die je schrijft om je eigen fout te vangen deelt je blinde vlek. Sinds
2026-08-07 staat in `.claude/rules/quality-gates.md`: een guard is pas af als je hem hebt zien
sterven, gemuteerd in BEIDE richtingen, met die mutatie in de docstring.

### Stand

15.354 tests groen, nul worker-crashes, 24 integratietests tegen echte Postgres. De ene failure is
het bekende volgorde-punt (OP-46) en slaagt los; er is geen bestand in dat gebied aangeraakt.
Pyright 0, ruff schoon, 9 importcontracten, Any-teller 34.

**Het kostenbesluit is genomen (2026-08-08).** Productie krijgt de planner-app: `scheduler-prod`
in `cd-production.yml`, exact een replica, 0.25 vCPU / 0.5 Gi. De uitzonderingslijst in de guard is
leeg -- hij staat nu op eigen benen. Wat overblijft is een handeling van Rakesh: de deploy gaat via
een tag, en die maak ik niet aan.

**Status: nog niet goedgekeurd.** Er is geen blinde ronde gedraaid op DEZE verwerking. Gate 2 op de dag-1-wijzigingen is nog niet gedraaid.

> **Deze zin luidde eerst "NIET <goedgekeurd-in-het-Engels>", en daarmee sprong de doc-gate op
> GROEN.** `scripts/validate_feature_docs.py:205` toetst met een kale substring-check of dat Engelse
> woord ergens in het bestand voorkomt -- en een ontkenning bevat het woord ook. Dat is ADR-036
> OP-42, en het is hier daadwerkelijk opgetreden: ik maakte een rode poort per ongeluk groen door op
> te schrijven waarom hij rood hoorde te zijn. Daarom staat de status hierboven in het Nederlands, en
> is het Engelse woord in deze alinea BEWUST niet uitgeschreven -- doe ik dat wel, dan is de poort
> weer groen. Zolang die check zo werkt, kan dit reviewdoc zijn eigen uitkomst niet eerlijk
> beschrijven. Dat is geen stijlkwestie maar een defect in de gate.

## Gate 2 op dag 1 -- twee blinde reviews, en wat ze vonden (2026-08-06)

Beide reviewers kregen alleen de commit-hashes, de bestandspaden en de testcommando's. Geen
samenvatting, geen bevindingen van de ander, geen oordeel van mij. Beiden gaven
CHANGES_REQUESTED, en ze kwamen ONAFHANKELIJK op dezelfde drie blokkers uit.

Ik heb alle drie zelf nagemeten voordat ik ze aannam. Alle drie klopten.

### De drie blokkers

**Een goedkeuring was een blanco volmacht (OP-63).** De poort toetste `status == "approved"` en
verder niets: geen vergelijking met de tool die werd uitgevoerd, geen vergelijking van de
parameters, en het ticket bleef daarna goedgekeurd staan. Omdat `ToolRiskClassifier` onbekende
tools standaard op HIGH zet, gold dat voor alles. Wie een onschuldige HIGH-actie liet goedkeuren en
de ticketverwijzing onthield, had een permanente volmacht voor de hele tenant.

**Dit was tot dag 1 latent, en dat is de scherpste les.** Zolang geen route een ticket op
`approved` kon zetten was de poort fail-closed maar dood. Mijn eigen fix van dag 1 (OP-37) heeft
hem levend gemaakt. Het commit dat goedkeuren mogelijk maakt is dus ook het commit dat de
begrenzing moet regelen -- dat had ik zelf moeten zien toen ik de lus sloot.

**De opruimplanner draaide nergens (OP-64).** `start_scheduler` had nul aanroepers buiten zijn
eigen `__main__` en er was geen scheduler-service in enige compose-opstelling. Mijn zin van dag 1,
"retentie MET planning", was dus onwaar: de actor stond in de configuratie van een proces dat
niemand start. Erger: `cleanup_expired_hitl_tickets` was de ENIGE handhaving van de SLA van 4 uur,
en `expires_at` werd nergens anders getoetst -- een ticket van een jaar oud was nog steeds goed te
keuren.

En mijn eigen guard kon dat niet zien. Hij toetste met een substring of de actornaam ergens in
`scheduler.py` voorkwam. De reviewer verwijderde het complete `add_job`-blok en de guard bleef
groen, want de naam stond nog in de runner-methode en in de import. Daarna ook de runner weg,
alleen een dode import over: nog steeds groen.

**Twee sleutels overleefden de opruiming op hun NAAM (OP-65).** `_BLIJFT` hield `_agent_id` en
`_task_id`, met als reden -- door mij opgeschreven -- dat ze "uit de request-body van de aanroeper"
komen. Dat geldt voor `/hitl/request`, en die route is niet gemount. Op het live pad zet
`create_hitl_request` ze niet; het is rauwe modeluitvoer.

Dit is dezelfde fout als de `ALWAYS_PUBLISHABLE`-naamlijst uit ronde 2 van deze sprint, die toen is
gesloten met exact het argument dat een naam niet kan onderscheiden wie een sleutel schreef. Ik heb
hem drie dagen later opnieuw gemaakt, in hetzelfde bestand.

### De bevinding die het pijnlijkst was om te lezen

De reviewer verving mijn digest-tak door `if True: return rebuilt` -- waarmee de digest volledig
verdween -- en draaide de suite: **72 tests groen.** `redacted_payload_digest` kwam in geen enkele
unit-test voor, en elke integratietest riep `approve`/`reject` aan ZONDER digest. De router geeft
er altijd een mee, dus juist de tak die in productie draait was ongetest. De code was correct; er
was alleen geen enkel bewijs voor.

### Overige bevindingen, alle verwerkt

| Wat | Uitkomst |
| --- | --- |
| Uitsluitlijst websocket te smal: `reason` (modeltekst) en `requested_by` gingen tenantbreed rond (OP-66) | Toelaatlijst |
| `/hitl/audit` idem, en mijn opgeschreven argument voor een uitsluiting is weerlegd door een meting (OP-67) | Toelaatlijst |
| Lijstverzoek deed ~4000 queries; `total` afgetopt op 2000; geen snelheidslimiet (OP-68) | Alles naar SQL, EEN e-mailquery, limieten toegevoegd |
| Motivering van de mens gevalideerd en weggegooid (OP-69) | Kolom `resolution_note` + migratie |
| Beheerder kon zijn eigen verzoek goedkeuren (OP-70) | Vergelijking op `_requested_by`, met vangnet-test |
| Router stond in de domeinlaag en viel buiten Contract 1, terwijl juist hij `database` en `governance` direct importeerde | Verplaatst naar `api/v1/tool_broker/`, via de facade, expliciet in Contract 1 |
| Any-teller 34 -> 43 | Terug op 34, gemeten in een worktree op de uitgangscommit |
| `jsonb_strip_nulls` om de digest heen wiste argumenten met waarde null | Alleen om de besluitprojectie |
| `/hitl/audit` ontbrak in de bewaakte paden terwijl de frontend hem aanroept | Toegevoegd |
| Exception-type ontbrak in een logregel; trailing whitespace | Gefixt |

### Nog drie punten opgepakt na het schrijven hiervan

**De volledige koude suite als blokkerende regressiecheck:** 15.292 geslaagd, **nul
worker-crashes**, en het volgorde-afhankelijke slachtoffer van OP-46 bleef deze run helemaal uit.
Een failure: de ketentest die de migratiekop vastpint wees nog naar de vorige migratie. Van mij,
direct gefixt.

**Het tokenendpoint is verwijderd (OP-61, `c8048f82`).** Met de vijf tests die zijn gedrag
vastlegden -- die beschreven precies het gat. De nieuwe guard is twee keer bijgesteld op een
meting: de eerste versie betrapte twaalf legitieme tokenfabrieken (die horen geen wachtwoord te
kennen), en de mutatietest bleef eerst groen omdat `git grep` alleen bestanden in versiebeheer
ziet.

**Elke beslissing schrijft nu een ADR-019 ketenregel (OP-71, `89f6b695`).** Bij goedkeuren en bij
afwijzen, na de primaire commit en in `best_effort`. Met een test die afdwingt dat er geen
modeltekst in die keten belandt -- zonder die assertie is "zet de hele payload erin" een geldige
oplossing, en dan wordt de onuitwisbare keten het achtste bewarende pad.

### Wat NA dit alles nog openstaat

1. **De planner draait niet in Azure.** In Docker nu wel. Azure Container Apps kent geen
   scheduler-app; die aanmaken kost geld en is een beslissing voor Rakesh (OP-64).
2. **Geen CSRF-dependency op de twee POST-routes**, terwijl vergelijkbare endpoints elders die wel
   hebben. `SameSite` dekt het vandaag af; het is een ontbrekende laag, geen open gat.
3. **155 van 839 routes zonder route-eigen authenticatie** (OP-62) -- eerst triageren, dan pas een
   guard.
4. **De frontend heeft geen test op de HITL-aanroepen** en de contract-guard dekt twee endpoints.
5. **De registratie van de router degradeert stil**: valt de import om, dan wordt hij niet gemount
   en logt de app een waarschuwing. Afgevangen door een test op de geassembleerde app, niet op
   runtime.
6. **Er is nog geen blinde ronde gedraaid op de VERWERKING van deze bevindingen.** Dat is de
   volgende stap, en tot die er is, is dit document geen bewijs van iets.

**Status: nog niet goedgekeurd.** Deze ronde is verwerkt; er is nog geen nieuwe blinde ronde op de
verwerking gedraaid.

## Gate 2 ronde 2 op de verwerking -- twee blinde reviews (2026-08-06/07)

Beide reviewers kregen opnieuw alleen de commit-hashes, de paden en de commando's, met de
expliciete instructie mijn commit-boodschappen en docstrings NIET als bewijs te nemen. Beiden
CHANGES_REQUESTED.

**Een procesfout van mijzelf eerst.** De securityreviewer zag mijn mutatietests in de werkboom
staan en heeft moeten uitwijken naar een eigen `git worktree`. Ik gaf hem een commit-hash mee maar
muteerde ondertussen de gedeelde boom -- exact wat ik mezelf in ronde 1 verweet. Zijn eerste twee
metingen liepen over een boom met mijn kapotgemaakte code erin.

### Wat er mis bleek, en wat ervan van mijzelf was

**Wat ik die dag bouwde werkte niet.** `execute_tool` schrijft `tenant_id` en `user_id` uit de
executiecontext in de payload VOORDAT de HITL-poort draait; die twee telden mee in de binding bij
uitvoering en niet bij goedkeuring. Elke menselijke goedkeuring was dus onverzilverbaar. Mijn
tests konden dat niet zien omdat ze aan BEIDE kanten dezelfde handgemaakte payload gebruikten --
zo'n test bewijst alleen dat een functie deterministisch is. (OP-75)

**Een tweede oorzaak van hetzelfde:** in de ontwikkelopstelling kreeg de backend geen
pseudonimiseringssleutel en de werker wel. Verschillende processen, verschillende efemere
sleutels, nooit een match.

**De opruimer draaide voor de TWEEDE keer niet.** Eerst startte het proces nergens; dat had ik
gerepareerd. Toen bleek het proces wel te draaien maar zijn opdrachten naar een `StubBroker` te
sturen -- een wachtrij in zijn eigen geheugen, met "enqueued successfully" in het log. (OP-76)

**En mijn bewaking daarop was opnieuw te zwak:** hij zocht een tekststring in het compose-bestand.
De reviewer zette het entrypoint op `sleep infinity` en liet de naam in een comment staan -- groen.
Nu wordt de YAML geparsed. (OP-77)

**De blokkerende bevinding:** `CopilotAction.action` had geen enkele begrenzing, en die
modelgeschreven naam belandde onbewerkt in de ADR-019 hashketen -- de ene plek die per ontwerp niet
te corrigeren is. Opgelost in drie lagen, waarvan de derde onvoorwaardelijk. (OP-78)

**Het derde tenantfilter** was door niets bewaakt, en mijn eerste vormtest ervoor was zelf hol:
`assert "tenant_id" in sql` slaagt altijd, want die kolom staat sowieso in de SELECT-lijst. Nu
toetst hij de voorwaarde met de waarde erin. Dezelfde holle vorm zat op nog twee plekken. (OP-79)

### Wat de reviewers als solide bestempelden

Negen guards stierven onder mutatie: de binding die parameters negeert, `tool_input` in de
audit-toelaatlijst, `reason` in de uitzending, de zelf-goedkeuringscheck uitgeschakeld, `expires_at`
uit `approve`, de poort terug naar alleen-status, de bindingvoorwaarde uit `redeem`, CSRF van
`/approve`, en de rolcheck van `/pending`. `redeem` heeft geen TOCTOU: een UPDATE, vier
voorwaarden, beslist op `rowcount`. De migratie klopt in beide richtingen. Het verwijderde
tokenendpoint was een echte authenticatie-omzeiling en de meegegane tests dekten niets anders.

### Nog open na deze ronde

Daarvan zijn er inmiddels vier gesloten (2026-08-07):

- **OP-80** -- het zusteroppervlak `gatekeeper_hitl_router.py` heeft nu ook CSRF op beide
  POST-routes. Zelfde patroon: override in de gedeelde testhelper, en een aparte klasse die hem
  juist NIET overschrijft.
- **OP-82** -- `/hitl/audit` had geen aanmaaktijdstip en geen risiconiveau: de toelaatlijst noemde
  velden die het antwoord nooit opleverde, en de guard ernaast toetste de LIJST in plaats van het
  ANTWOORD. Beide velden worden nu geleverd, `resolution_note` is toegevoegd, en een nieuwe guard
  roept de dict-opbouw AAN en vergelijkt de echte sleutels.
- **OP-83** -- een gegeven goedkeuring verouderde nooit. `redeem` heeft nu een venster van 24 uur,
  bewezen op echte Postgres met een goedkeuring van dertig dagen oud.
- **OP-81** -- de zelf-goedkeuringscheck op het gatekeeper-pad blijkt bij nameten NIET van
  toepassing: dat model heeft geen menselijke aanvrager, alleen een agent. Vastgelegd als vraag,
  niet als gat.

Nog open:

1. ~~Geen enkele werker consumeert de `cleanup`-wachtrij.~~ **Opgelost (OP-84), en het was geen
   keuze maar een fout.** De workflow-werker startte zonder brokerverwijzing en kreeg daardoor de
   StubBroker: hij consumeerde NIETS uit Redis, geen enkele wachtrij. De zusterwerker deed het al
   goed. Een `:redis_broker` in de startopdracht, met een guard erop.
   **Let op bij de deploy:** die werker heeft dus nooit iets verwerkt. Bij de eerstvolgende deploy
   begint hij de opgebouwde achterstand in Redis af te werken; wat daar staat is niet gemeten.
2. ~~Azure heeft geen scheduler-app.~~ **Toegevoegd (2026-08-07)** -- zie hieronder.
3. ~~E-mailadressen in logregels.~~ **Opgelost (OP-85).**
4. ~~Dode imports.~~ **Opgelost (OP-86)**, veertien stuks, met een gerichte guard.
5. **Er is nog geen blinde ronde gedraaid op de verwerking van deze ronde.** Dat blijft het
   grootste openstaande punt: alles hierboven is door mij gerepareerd en door mij nagemeten.

## Afsluiting 2026-08-07 -- de laatste drie punten, en een vierde die daarbij opdook

**OP-85 (e-mailadressen in logregels).** `hitl_router.py` zette `current_user.email` in de `extra`
van twee logregels en gaf hetzelfde adres door aan de notify-functies, die het nog een keer loggen.
`security.md` is daar ondubbelzinnig over. Het adres voegt niets toe dat het toezichtsrecord niet
al heeft: `resolved_by` is een FK naar `users.id`. Overal het gebruikersnummer, in de
`user:<id>`-vorm die de gatekeeper sinds OP-55 gebruikt.

**OP-86 (dode imports).** Veertien stuks, onzichtbaar omdat `F401` projectbreed uitstaat. Dat is
meer dan rommel: een dode import naar `jwt_handler` in het bestand waar net een
authenticatie-omzeiling uit is gehaald leest als "hier gebeurt nog iets met tokens", en
`ToolHITLApproval`/`ToolHITLRejection` suggereerden dat dit nog het HITL-schrijfpad is terwijl dat
sinds OP-37 elders zit. Verkeerde signalen op precies de plek waar iemand naar veiligheid zoekt.
Guard zet `F401` GERICHT aan voor een gedateerde lijst modules; bewust geen projectbrede regel,
want facade- en `__init__`-bestanden exporteren met opzet wat ze zelf niet gebruiken.

**De Azure-kant van OP-64.** `scheduler-staging` in `cd-staging.yml`: dezelfde image als de worker,
ander startcommando, exact een replica (deze jobs horen niet dubbel te draaien), 0.25 vCPU /
0.5 Gi. De planning blijft op EEN plek staan in `scheduler.py` in plaats van ook nog in
cron-definities in de workflow -- anders lopen die twee uiteen, en dat is het patroon dat deze hele
reeks kenmerkt. De guard kijkt sinds deze wijziging ook naar `cd-*.yml`: Azure draait geen compose,
dus een planner die alleen daar stond zou in de cloud nergens draaien.

**OP-87, opgedoken tijdens het bouwen daarvan.** De staging-worker kreeg bij AANMAAK geen
`REDIS_URL`, terwijl `workflow_worker.py:100-111` daar bij het IMPORTEREN een `RuntimeError` op
gooit. Een zo aangemaakte worker start dus nooit -- en omdat het entrypoint dramatiq is, is dat een
stille storing in plaats van een luide deploy-fout. Toegevoegd aan die stap.

### Wat Rakesh moet doen voordat dit naar staging kan

1. ~~Maak het GitHub-secret `STAGING_REDIS_URL` aan.~~ **Niet meer nodig (2026-08-07).** De
   deploy-job is toch al ingelogd op Azure, dus hij haalt de sleutel nu zelf op: uit de bestaande
   `STAGING_REDIS_HOST` volgt de resourcenaam, `az redis list-keys` levert de rest. Een expliciete
   `STAGING_REDIS_URL` wint als hij WEL is gezet -- dan werkt het ook voor een Redis buiten Azure.
   Lukt het ophalen niet, dan zegt de stap waarom: waarschijnlijk mist de service principal het
   recht `Microsoft.Cache/redis/listKeys/action`, en dan is het secret alsnog de uitweg.

   Twee dingen die daarbij opvielen: de UPDATE-tak van de staging-worker zette `REDIS_URL`
   helemaal niet (alleen de aanmaak-tak, terwijl de app al bestaat), en **productie had hetzelfde
   gat** -- gevonden door de nieuwe guard, niet door mij. Daar bestaat `PROD_REDIS_URL` wel, dus
   dat is een directe koppeling.
2. **Besluit over de kosten van de scheduler-app.** Het is een altijd-draaiende Container App
   (0.25 vCPU / 0.5 Gi, een replica). Die post ontstaat bij de eerste deploy na deze wijziging.
3. **Kijk voor de deploy naar wat er in Redis staat.** De worker heeft door OP-84 nooit iets
   verwerkt; bij de eerste deploy begint hij die achterstand af te werken. Wat daar staat is niet
   gemeten.

**Status: nog niet goedgekeurd.**

---

## Ronde 8 -- slotdag 2026-08-09: de acht blokkers uit twee blinde reviewrondes

Uitgevoerd volgens `docs/agent-briefs/generated/2026-08-09-sprint-dag-BE-AGT-045-slotdag.md`.
Nulpunt gemeten voor de eerste wijziging: 1597 gerichte tests groen, 0 rood.

### Wat er is gedaan

| # | Blokker | Commits | Mutatietest |
| --- | --- | --- | --- |
| T1 | B-1 -- gedeployde worker-images konden niet starten (OP-91) | `ef43f7ec` rood, `412a0e1c` groen | 4/4 |
| T2 | BLOCKER-1 -- de identiteitscontrole stond uit door een fixture (OP-103) | `a8ff248f` | 4/4 |
| T3 | H-1 -- de verzilvering stond 30 seconden niet vast | `faaf2b12` rood, `d87efb81` groen | commit weg -> rood |
| T4 | H-2 -- de keten dekte het bewijs niet | `8a8422f6` | 3/3 |
| T5 | M-1 -- de tokenguard onderzocht nul endpoints | `7991f718` | 4/4 |
| T6 | HIGH-3 -- de plannerguard liet vijf omzeilingen door | `dea1e823` | 6/6 |
| T7 | HIGH-2 -- OP-104/105/106 hadden geen enkele test | `b95a50b8` | 5/5 |
| T7d | MEDIUM-6 -- twee productiegeheimen in de shell-tekst | `faa0b714` | 4/4 |

### Wat de Gate 2-review op het PLAN veranderde

Beide reviewers gaven CHANGES_REQUESTED, en dat was terecht: in vijf van de acht blokkers zat de
bekende faalvorm nog in de VOORGESTELDE guard. De belangrijkste vier correcties:

1. **`test_tool_broker_hitl.py:1424-1430` was NIET geneutraliseerd** -- alleen `:1432-1439` wel.
   Mijn plan wilde beide verplaatsen en had daarmee de enige werkende assertie weggehaald.
2. **De H-2-digest zou over de RAUWE toolnaam gaan**, terwijl de auditregel `_safe_tool_name(...)`
   opslaat. Dan is de digest door niemand na te rekenen en is het geen bewijs.
3. **De digest werd geschreven maar nooit nagerekend.** Er zit nu een recompute-stap in
   `verify_entry`; zonder die stap was H-2 hetzelfde theater als de guards die deze dag repareert.
4. **De secrets-guard zou 14 van de 16 stappen moeten uitzonderen.** Een uitzonderingslijst die
   het merendeel bevat bewaakt niets; de guard toetst nu alleen WAARDE-dragende secrets.

### Wat het nameten zelf opleverde, boven op de brief

- **Een vierde gat in B-1**: de productie-worker had helemaal geen `DATABASE_URL`. Alleen een
  update-tak, dus nergens in versiebeheer een volledige definitie van die app.
- **Een derde ongehashte auditschrijver**: `security/enhanced_auth_deprecated.py`, gevonden door
  de nieuwe guard zelf.
- **Twee keer heeft de mutatietest mijn eigen guard afgekeurd** (T1): eerst verborg een
  samengevoegde omgeving het gat, daarna telde het vangnet scenario's in plaats van apps.

### Statuscorrecties

`OP-91` en `OP-103` stonden in ADR-036 als GESLOTEN terwijl dat niet klopte. Beide regels zijn
gecorrigeerd met de meting erbij, niet overschreven.

### Geregistreerd en bewust NIET opgelost

`OP-108` t/m `OP-113` in ADR-036. De zwaarste is OP-108: de auditketen is vandaag in elke
omgeving al gebroken, omdat de dagelijkse opruimactor ongehashte rijen schrijft en `verify_chain`
bij de eerste afwijking stopt. Daardoor is de opbrengst van H-2 end-to-end nog niet waarneembaar.
Dat verdient een eigen dag en is geen onderdeel van deze.

Vier van de zes hebben een groene guard met gedateerde uitzonderingslijst plus staleness-test.
Twee niet (OP-111 Azure, OP-113 RLS-rol), met de reden erbij: daar is geen repo-artefact om op te
toetsen, en een test die Azure bevraagt hoort niet in de architectuursuite.

### Oordeel

Deze ronde is door mijzelf uitgevoerd en door mijzelf nagemeten. Er is nog GEEN onafhankelijke
reviewer die deze dag heeft beoordeeld -- de blinde ronde op dit werk staat nog open, en zolang
die er niet is blijft de doc-gate rood.

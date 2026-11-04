# Review: BE-AGT-048 -- HITL_REQUIRED maakt een echt goedkeuringsticket aan

**Spec:** docs/backend/features/BE-AGT-048-hitl-required-ticket-creation.md (v1)
**Reviewer:** onafhankelijke doc-reviewer-agent
**Datum:** 2026-08-18
**Methode:** elke technische claim (functiesignaturen, regelverwijzingen, testnamen, gedrag,
DSM-Ce-meting, config/tool_permissions.yml-inhoud) is nagelopen tegen de daadwerkelijke
broncode/testbestanden in de werkboom, niet alleen tegen de spec-tekst. git status/git diff
is gebruikt om de daadwerkelijk gewijzigde bestanden vast te stellen. De drie genoemde
testbestanden zijn daadwerkelijk gedraaid (43 passed); calculate_instability("agent_runtime")
is daadwerkelijk uitgevoerd tegen de huidige broncode.

---

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

---

## B. SAMENVATTING

De inhoudelijke kern van deze spec is opvallend goed onderbouwd: alle geverifieerde
functiesignaturen, teststructuren, de exacte foutmeldingstekst, de DSM-Ce-meting (empirisch
herbevestigd op 225) en de _BLIJFT/_AUDIT_FIELDS-staleness-redenering kloppen woordelijk met
de broncode. De 43 genoemde tests zijn gedraaid en slagen. De claim dat copilot en
skillsgaptraining verschillende toolsets hebben in config/tool_permissions.yml is grotendeels
juist (query_hr_database is inderdaad exclusief voor de piloot), maar de gebruikte term
"DISJUNCTE toolset" is feitelijk onjuist: beide profielen delen send_notification.

Er zijn geen CRITICAL- of HIGH-bevindingen: tenant-isolatie en permissiegedrag zijn correct EN
volledig beschreven, en kloppen bij verificatie. Wel zijn er vijf MEDIUM- en twee
LOW-bevindingen, vooral rond precisie van regelverwijzingen en interne consistentie tussen de
"In scope"-sectie, de "Build summary" en de daadwerkelijke git-status-diff. Geen van deze
bevindingen blokkeert bouw, QA of implementatie; ze moeten wel gefixt worden voor een schone
LLM-trainingsbron en om te voorkomen dat een lezer op een verkeerde regel gaat zoeken.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- Build summary is incompleter dan de daadwerkelijke git-status-diff. De werkboom toont naast de
  vier in "Build summary -> Gewijzigd" genoemde bestanden ook wijzigingen in
  tests/fixtures/agent_governance.py (nieuwe hitl_ticket_repository-fixture) EN in drie
  conftest-bestanden die deze fixture re-exporteren: tests/unit/agents/conftest.py,
  tests/unit/als/conftest.py, tests/unit/tool_broker/conftest.py. De fixture wordt wel genoemd in
  "In scope" ("Testfixture hitl_ticket_repository ... plus mutatiebewijs in beide richtingen"),
  maar die belofte wordt niet doorgevoerd naar "Build summary" of "Backend inventory" -- en de
  drie conftest-bestanden worden nergens in de spec genoemd, ook niet in "In scope". Voor een
  document dat pretendeert een volledige inventaris te zijn is dit een reeel gat: een lezer die
  alleen "Build summary" leest, weet niet dat de testinfrastructuur van drie testbomen is
  aangepast.
- Documentatie-bijvangst (docs/adr/036-...md OP-163-rij, docs/backend/features/ID-REGISTRY.md) is
  ook gewijzigd (bevestigd via git status) maar wordt in de spec zelf niet als zodanig vermeld --
  verwacht en minder kritisch, want het template heeft geen slot voor "aangepaste documentatie",
  maar het versterkt hetzelfde patroon: de spec onderrapporteert wat er feitelijk in de commit
  zit.

### 2. Functionele onduidelijkheden

- Geen grote onduidelijkheden. Klein punt: als een enkele act()-aanroep MEERDERE tool_calls
  bevat die allemaal HITL_REQUIRED opleveren (mogelijk binnen budget.max_steps), ontstaan er
  meerdere, onafhankelijke tickets in een keer. De spec beschrijft dit niet expliciet (alleen het
  1-ticket-per-actie-geval wordt getest en gedocumenteerd) -- functioneel is dit waarschijnlijk
  het juiste gedrag (elke actie eigen goedkeuring), maar het verdient een regel in de functionele
  beschrijving of business rules, want het is niet uit de huidige tekst af te leiden zonder de
  code te lezen.

### 3. Technische onduidelijkheden

- Regelverwijzing specialist_base.py:369-403 (artefact BE-AGT-048, sectie 6) is onjuist voor de
  huidige broncode. De HITL_REQUIRED-tak loopt van regel 369 tot en met regel 409 (inclusief de
  return-statement met de ticketref op regel 406-409 EN de regel
  executing_identity=self.agent_id, op regel 404 -- precies de regel die de kern van deze fix is).
  De opgegeven range 369-403 knipt af VOOR die regel en voor de return-statement.
- Regelverwijzing "circa 679-692" voor de except Exception-vangst in act() (BE-AGT-048 sectie 13
  en BE-FLW-058 "Foutpaden") is onjuist. In de huidige broncode staat dit blok op regel 690 (try:)
  tot regel 703 (toewijzing van gate_error in de except-tak), niet op 679-692.

### 4. Ontbrekende foutstatussen en edge cases

- N.v.t. voor HTTP-statuscodes (correct gemotiveerd: geen HTTP-laag op dit pad). De genoemde
  Python-exceptions (ValueError, PermissionError) en hun afhandeling zijn compleet en
  geverifieerd.
- Ontbrekende edge case: zie categorie 2 (meerdere HITL_REQUIRED-tool_calls in een invocatie).
- Ontbrekende edge case: geen expliciete beschrijving van wat er gebeurt als de INSERT binnen
  create_hitl_request zelf faalt (bijv. een DB-verbindingsfout) NA een geslaagde permissiecheck.
  Sectie 14 beschrijft het generieke rollback-gedrag van get_db_session(), maar koppelt dat niet
  expliciet aan dit specifieke faalpad als "edge case" in de QA-checks-lijst.

### 5. Acceptatiecriteria problemen

- BE-AGT-048 par. 17, vijfde bullet ("Rode-dan-groene-proef ... met de productiecode teruggezet
  naar de vorige commit") is een eenmalig, procesmatig bewijs dat is uitgevoerd tijdens de bouw,
  geen herhaalbaar en automatiseerbaar acceptatiecriterium zoals de andere vier bullets in die
  lijst. Dat is verder correct en aantoonbaar consistent met de codewijziging (zonder de fix
  geeft create_hitl_request(..., executing_identity=...) een TypeError op de oude signatuur, en
  ontbreekt _executing_identity in de payload, dus KeyError bij de nieuwe test -- dat klopt), maar
  het hoort qua vorm eerder bij verificatiebewijs dan bij een QA-testbare acceptatie-eis. Geen
  inhoudelijke fout, wel een structuurpunt.

### 6. Integratorhandleiding / API-uitleg problemen

- Geen. De integratoruitleg is correct, kort en klopt met het feit dat er geen nieuwe of
  gewijzigde publieke HTTP-endpoints zijn; de instructie aan toekomstige aanroepers (geef
  executing_identity mee als de aanvragende identiteit niet copilot is) is concreet en bruikbaar.

### 7. Trainingsdata problemen

- De herhaalde claim "DISJUNCTE toolset" (Doel-sectie, en woordelijk herhaald in BE-SEC-046
  par. 4 "Doel") is feitelijk onjuist geverifieerd tegen de daadwerkelijke
  config/tool_permissions.yml. agent_profiles bevat twee profielen: copilot.allowed_tools bevat
  send_notification, navigate_to, read_data, write_data, create_task, list_tasks, update_task,
  delete_task, admin_action, create_meeting, cancel_meeting, reschedule_meeting,
  check_availability, list_meetings, clarify, confirm, unknown; skillsgaptraining.allowed_tools
  bevat query_hr_database, analyze_skill_gap, search_documents, generate_text, send_notification,
  schedule_training. Beide lijsten bevatten send_notification, dus de sets zijn NIET disjunct.
  Het enige feit dat de spec daadwerkelijk nodig heeft (en correct aanhaalt) is dat
  query_hr_database UITSLUITEND bij skillsgaptraining hoort; "disjuncte toolset" is een overclaim
  die als trainingsfeit een onjuiste generalisatie zou vastleggen. Dezelfde onnauwkeurige
  formulering staat overigens ook al in de ADR-036 OP-163-rij en in de code-comment boven
  _UITVOERENDE_IDENTITEIT in hitl_repository.py -- dit is dus geen nieuwe fout van deze spec, maar
  wel een fout die deze spec overneemt zonder verificatie en die hier voor het eerst als
  LLM-trainingsbron wordt vastgelegd.

### 8. Structuur- en consistentieproblemen

- Gebroken interne verwijzing. De In-scope-sectie verwijst met de tekst "(niet-autouse, zie
  Bekende risicoparagraaf)" naar een sectie die onder die naam niet bestaat; de daadwerkelijke
  sectiekop in dit document heet "Risicos", zonder het woord Bekende. Een
  lezer die de verwijzing volgt, vindt niets met die exacte naam.
- Build summary tegenover In scope tegenover de daadwerkelijke diff loopt uiteen, zie categorie
  1. Dit is precies het type conflict tussen build summary, inventory en detailsecties waar de
  reviewinstructie expliciet naar vraagt.

### 9. Risicos voor implementatie, security of QA

- Geen CRITICAL of HIGH risicos. Tenant-isolatie is correct beschreven EN geverifieerd
  (tenant_id=self.tenant_id, nooit uit params of modeloutput; bevestigd in
  HITLTicketRepository.create(), get() en approve()). Permissiegedrag (ADR-015 default-deny,
  is_tool_allowed en is_denied) is correct beschreven en geverifieerd tegen permission_manager.py
  en config/tool_permissions.yml.
- De categorie-7-onnauwkeurigheid (disjuncte toolset) heeft geen directe security-impact (de
  CODE-controle zelf is correct: ToolPermissionManager().is_tool_allowed(executing_identity,
  tool) toetst per tool, niet per toolset), maar een toekomstige lezer die op het PROZA vertrouwt
  in plaats van op de code, zou onterecht kunnen aannemen dat er geen enkele overlappende tool
  bestaat tussen profielen, een aanname die bij een volgend profiel met meer overlap fout kan
  aflopen.

---

## D. ISSUE REGISTER

| Severity | ID / sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Medium | BE-AGT-048 par. 6 (Technische beschrijving) | Regelverwijzing specialist_base.py:369-403 dekt de HITL_REQUIRED-tak niet volledig; de tak loopt tot en met regel 409. | De weggelaten regels (404, 406-409) bevatten precies executing_identity=self.agent_id en de return-statement met de ticketref, de kern van deze fix. Een lezer die de referentie volgt mist het belangrijkste deel. | Wijzig naar specialist_base.py:369-409. |
| Medium | BE-AGT-048 par. 13 (Foutafhandeling) en BE-FLW-058 (Foutpaden) | Regelverwijzing circa 679-692 voor de except Exception-vangst in act() klopt niet met de huidige broncode (690-703). | Foute regelverwijzing in een document dat expliciet bedoeld is als nauwkeurige technische bron en LLM-trainingsdata. | Wijzig naar circa 690-703. |
| Medium | Build summary, In scope, Backend inventory | tests/fixtures/agent_governance.py en drie conftest-bestanden (tests/unit/agents/conftest.py, tests/unit/als/conftest.py, tests/unit/tool_broker/conftest.py) zijn daadwerkelijk gewijzigd (bevestigd met git status) maar staan niet in Build summary onder Gewijzigd; de drie conftest-bestanden staan zelfs nergens in de spec. | Onvolledige inventaris; contradictie tussen wat In scope claimt te bouwen en wat Build summary rapporteert als gewijzigd. | Voeg alle vier bestanden toe aan Build summary onder Gewijzigd, met een regel die uitlegt dat de drie conftest-bestanden de nieuwe fixture enkel re-exporteren. |
| Low tot Medium | In scope, voetnoot over de risicoparagraaf | Verwijst naar een sectie die niet onder die naam bestaat; de daadwerkelijke sectiekop is Risicos. | Gebroken interne cross-reference. | Wijzig de verwijzing naar de daadwerkelijke sectienaam, of hernoem de sectie zodat de namen overeenkomen. |
| Medium | Doel-sectie en BE-SEC-046 par. 4 (Doel) | Claim disjuncte toolset tussen copilot en skillsgaptraining is feitelijk onjuist: beide profielen in config/tool_permissions.yml bevatten send_notification. | Overclaim in een sectie die de zwaarte van de bug onderbouwt; als trainingsfeit onjuist. | Herformuleer naar: een grotendeels afwijkende toolset, beide delen send_notification; query_hr_database staat uitsluitend bij skillsgaptraining. |
| Low | BE-AGT-048 par. 17, bullet 5 | De rode-dan-groene-proef staat tussen de acceptatiecriteria, maar is een eenmalig procesbewijs, geen herhaalbaar testbaar criterium. | Vermengt acceptatiecriterium (moet QA/CI herhaalbaar kunnen verifieren) met verificatiebewijs van de bouwfase. | Verplaats deze bullet naar een apart kopje Verificatiebewijs of naar de QA-sectie. |
| Low | Business rules (BE-AGT-048 par. 11) en functionele beschrijving | Gedrag bij meerdere HITL_REQUIRED-tool_calls binnen een act()-aanroep (meerdere tickets in een keer) niet expliciet beschreven. | Edge case die uit code wel af te leiden is maar niet uit de tekst; testbaarheid van dit gedrag is niet aangetoond. | Voeg een zin toe: meerdere tool_calls die alle HITL_REQUIRED opleveren binnen dezelfde invocatie resulteren in evenveel onafhankelijke tickets. |

---

## E. ONTBREKENDE ITEMS

- Vermelding van de drie conftest-bestanden (tests/unit/agents/conftest.py,
  tests/unit/als/conftest.py, tests/unit/tool_broker/conftest.py) in Build summary en In scope.
- Een expliciete regel over het gedrag bij meerdere gelijktijdige HITL_REQUIRED-tool_calls binnen
  een enkele act()-aanroep, zie rij 7 van sectie D.
- Geen test of documentatieregel die expliciet bevestigt dat een DB-fout tijdens de
  ticket-INSERT (na een geslaagde permissiecheck) de sessie laat rollbacken zonder een half
  aangemaakt ticket achter te laten. Het generieke gedrag van get_db_session() dekt dit
  impliciet, maar een expliciete regel of test zou dit vastklikken voor dit specifieke pad.

---

## F. VERBETERDE TEKSTVOORSTELLEN

Doel-sectie, tweede paragraaf, huidige tekst:

De piloot-skill (skillsgaptraining) heeft in config/tool_permissions.yml een DISJUNCTE toolset
van copilot (bijvoorbeeld query_hr_database staat alleen in het profiel van skillsgaptraining).

Voorstel:

De piloot-skill (skillsgaptraining) heeft in config/tool_permissions.yml een grotendeels
afwijkende toolset ten opzichte van copilot. Beide delen alleen send_notification.
query_hr_database, de tool die deze fix concreet raakt, staat UITSLUITEND in het profiel van
skillsgaptraining.

BE-AGT-048 par. 6, technische beschrijving, huidige tekst:

Bestandspad: src/core/als/agents/specialist_base.py:369-403 (na de bestaande
DecisionVerdict.APPROVED-check, voor de generieke rejection-string die voor
BLOCKED/DEFERRED/MODIFIED blijft gelden).

Voorstel:

Bestandspad: src/core/als/agents/specialist_base.py:369-409 (na de bestaande
DecisionVerdict.APPROVED-check op regel 366-367, voor de generieke rejection-string op regel 416
die voor BLOCKED/DEFERRED/MODIFIED blijft gelden).

BE-AGT-048 par. 13, Foutafhandeling, huidige tekst:

wordt door de bestaande brede except Exception-vangst in act() (regel circa 679-692) afgevangen.

Voorstel:

wordt door de bestaande brede except Exception-vangst in act() (regel circa 690-703) afgevangen.

In scope, laatste bullet voor Out of scope, huidige tekst:

Testfixture hitl_ticket_repository in tests/fixtures/agent_governance.py (niet-autouse, zie de
risicoparagraaf) plus mutatiebewijs in beide richtingen.

Voorstel:

Testfixture hitl_ticket_repository in tests/fixtures/agent_governance.py (niet-autouse, zie de
sectie Risicos) plus de drie conftest-bestanden die hem re-exporteren (tests/unit/agents/
conftest.py, tests/unit/als/conftest.py, tests/unit/tool_broker/conftest.py), plus mutatiebewijs
in beide richtingen.

Build summary, Gewijzigd, aanvulling:

- tests/fixtures/agent_governance.py (nieuwe hitl_ticket_repository-fixture, niet-autouse)
- tests/unit/agents/conftest.py, tests/unit/als/conftest.py,
  tests/unit/tool_broker/conftest.py (importeren de nieuwe fixture)

---

## G. RELEASE-OORDEEL

- Geschikt voor bouw en implementatie: ja. De code is al gebouwd, gereviewd (Gate 2, twee
  reviewers, GO) en de genoemde tests draaien daadwerkelijk groen (43 van 43 in deze review
  herbevestigd).
- Geschikt voor QA en geautomatiseerd testen: ja, met de aantekening dat bullet 5 van par. 17
  (de rode-dan-groene-proef) geherclassificeerd moet worden als verificatiebewijs, niet als
  doorlopend testbaar acceptatiecriterium, zie sectie D.
- Geschikt voor LLM-training: ja, met de correctie van de disjuncte-toolset-claim (categorie 7)
  en de twee regelverwijzingen (categorie 3). Zonder die correcties leert een trainingsproces op
  deze tekst twee onjuiste regelnummers en een overclaim over toolprofielen aan. Alle overige
  geverifieerde technische claims (functiesignaturen, foutmeldingstekst, DSM-Ce-meting,
  testnamen, de koppeling tussen _BLIJFT en _AUDIT_FIELDS) zijn woordelijk correct.
- Geschikt voor integratorhandleiding en API-documentatie: ja, zonder voorbehoud. Er is geen
  publieke API-wijziging, en dat is correct beschreven.

---

Volgens docs/backend/FEATURE_DOC_WORKFLOW.md Stap 3 mag de sprintdag sluiten: geen open CRITICAL
of HIGH bevindingen. De vijf MEDIUM- en twee LOW-bevindingen in dit register moeten verwerkt
worden in een volgende versie van deze spec (v2) voor een schone LLM-trainingsbron, maar
blokkeren geen merge.

---

## Ronde 2 -- verificatie van fixes (v2, zelfde dag)

Alle zeven bevindingen uit het Issue Register (D) zijn verwerkt in v2 van de spec, geverifieerd
tegen de daadwerkelijke bestanden (niet alleen tegen de spec-tekst):

| # | Bevinding | Verificatie |
| --- | --- | --- |
| 1 | Regelverwijzing 369-403 -> 369-409 | GEVERIFIEERD: `specialist_base.py` regel 366-367 (APPROVED-check), 369-409 (HITL_REQUIRED-tak), 416 (generieke rejection) rechtstreeks nagelezen en overeenkomstig aangepast. |
| 2 | Regelverwijzing circa 679-692 -> 690-703 | GEVERIFIEERD op BEIDE plekken (BE-AGT-048 par. 13 EN BE-FLW-058 Foutpaden) -- de review noemde dit een gecombineerde bevinding voor beide secties. `specialist_base.py` regel 690 (`try:`) t/m 703 rechtstreeks nagelezen. |
| 3 | Build summary/In scope incompleet (4 bestanden) | GEVERIFIEERD: `tests/fixtures/agent_governance.py` en de drie conftest-bestanden nu genoemd in zowel Build summary als In scope. |
| 4 | Gebroken interne verwijzing "Bekende risico's" | GEVERIFIEERD: gewijzigd naar de daadwerkelijke sectienaam "Risico's". |
| 5 | "DISJUNCTE toolset"-overclaim | GEVERIFIEERD en verder doorgetrokken dan gevraagd: naast de spec zijn ook de code-comments in `specialist_base.py` en `hitl_repository.py` (2x) en de bijbehorende rijen in het ADR-036-register en ID-REGISTRY.md gecorrigeerd -- dezelfde onnauwkeurigheid stond daar ook, zoals de review zelf al signaleerde. `grep -rn "DISJUNCTE"` op alle vijf bestanden geeft nu 0 treffers. |
| 6 | Rode-dan-groene-proef vermengd met acceptatiecriteria | GEVERIFIEERD: verplaatst naar een apart kopje "Verificatiebewijs" onder sectie 17, met een expliciete toelichting dat dit eenmalig bouwbewijs is en geen doorlopend CI-criterium. |
| 7 | Ontbrekende edge cases (meerdere HITL_REQUIRED-tool_calls; DB-insertfout) | GEVERIFIEERD: een regel toegevoegd aan Business rules (par. 11) resp. Foutafhandeling (par. 13). |

Geen nieuwe bevindingen bij deze verificatieronde. EINDOORDEEL blijft **APPROVED**, nu zonder
openstaande MEDIUM/LOW-punten.

---

## Ronde 3 -- verplichte blinde eindreview (final-approver-pijplijn)

**GO**, met een reeel testdekkingsgat gevonden via een eigen mutatietest die vervolgens gefixt is
in dezelfde sessie.

De blinde reviewer (geen kennis van deze sessie, alleen commit-hash en bestandspaden) bevestigde
onafhankelijk alle drie hoofdclaims (HITL_REQUIRED maakt een echt ticket; de hardcoded identiteit
werd een parameter; de DSM Ce-ceiling-fix via `importlib`) door zelf de code te lezen, de suite te
draaien, en zelf een mutatie uit te voeren op de Ce-fix (227 gereproduceerd na het teruszetten naar
statische imports). Geen security- of tenant-isolatieproblemen gevonden.

**Bevinding (testdekkingsgat, geen livebug):** de reviewer muteerde `approve_hitl_request()` zodat
`uitvoerende_identiteit` de default bleef in plaats van `ticket.payload["_executing_identity"]` te
lezen -- exact het scenario waarbij de permissiecheck bij AANMAKEN iets anders toetst dan wat er
bij UITVOEREN gebeurt. 352 bestaande tests (inclusief alle tests uit Ronde 1/2 van dit dossier)
bleven groen: geen enkele zet een ticket met een NIET-default `_executing_identity` neer en
controleert vervolgens met welke `agent_id` `broker.execute_tool()` wordt aangeroepen. De
productiecode was correct; alleen de dekking op DIT specifieke, veiligheidsrelevante koppelpunt
ontbrak.

**Fix (dezelfde sessie, geen backlog):** nieuw testbestand
`tests/unit/api/test_approve_executes_with_the_creating_identity.py`, met een `TestClient`
tegen de echte `hitl_router.router` (gemockte `HITLTicketRepository`/broker/`get_current_user`,
geen echte database nodig). Twee tests: een ticket met `_executing_identity="skillsgaptraining"`
moet `execute_tool(agent_id="skillsgaptraining", ...)` opleveren; een ticket zonder dat veld
(oudere tickets) moet terugvallen op de default `"copilot"`. Mutatiebewijs zelf uitgevoerd: de
EXACTE mutatie van de blinde reviewer (`uitvoerende_identiteit = _UITVOERENDE_IDENTITEIT`
hardcoded) maakt de eerste test rood met precies de verwachte assertiefout
(`AssertionError: ... 'copilot' == 'skillsgaptraining'`); de tweede blijft groen (bewijst dat de
mutatie niet toevallig alles rood maakt). Mutatie ongedaan gemaakt, `git diff --stat` op
`hitl_router.py` bevestigd leeg (bestand weer identiek aan de commit).

Twee kleine documentatie-onnauwkeurigheden ook gevonden en gefixt: drie regelverwijzingen in de
spec waren -- ondanks de expliciete "rechtstreeks nagelezen"-claim in Ronde 2 -- 2 regels
verschoven door latere edits (369-409 -> 369-411, regel 416 -> 418, circa 690-703 -> 692-705);
en sectie 5 impliceerde ten onrechte een live websocket-pushmelding bij ticketaanmaak op dit pad,
terwijl sectie 6 correct vermeldde dat die er niet is. Beide gecorrigeerd in v3.

EINDOORDEEL: **GO**, na het fixen van het testdekkingsgat en de twee documentatiepunten.

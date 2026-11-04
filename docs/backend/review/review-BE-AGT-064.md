# Review: BE-AGT-064 -- HITL-ticket-volledigheid over alle Council-aanroeppunten

**Spec:** `docs/backend/features/BE-AGT-064-hitl-ticket-volledigheid.md` (v1)
**Reviewer:** onafhankelijke doc-reviewer-agent, tegen de daadwerkelijke broncode EN een
zelf-uitgevoerde reproductie tegen een echte PostgreSQL-testdatabase (poort 5455) -- niet
alleen tegen interne tekstconsistentie.
**Datum:** 2026-08-25

---

## A. EINDOORDEEL (Ronde 1)

NEEDS REVISION (zie Ronde 2 en de nazorg-noot hieronder: het CRITICAL-defect gevonden tijdens
deze review is sindsdien gefixed in commit `d54bc5c4`, 2026-08-25)

---

## B. SAMENVATTING

De documentatie zelf is qua structuur, coverage en interne consistentie in orde: alle 6
artefacten, hun onderlinge verschillen (self-contained vs. gedeelde poort, eigen foutcontract
vs. generiek contract, floor vs. gate-garantie) en het bekende `send_notification`-restgat zijn
correct en volledig overgenomen uit de drie final-approver-briefs en zelf tegen de broncode
gecontroleerd (regelnummers, testnamen, conditie-tekst).

**Maar bij het verifieren van sectie 14 ("Transacties en dataintegriteit") tegen de
daadwerkelijke sessielevenscyclus is een CRITICAL, tot dan toe onopgemerkt productiedefect
gevonden in de onderliggende CODE zelf (niet alleen in de tekst) -- SINDSDIEN GEFIXED in commit
`d54bc5c4` (2026-08-25), zie de nazorg-noot aan het einde van deze review: de ticket-aanmaak in
`governance_gate.py::require_council_approval` (BE-AGT-064-4, de grootste dag van de sprint,
9 aanroepers) en `execution_router.py::execute_flow` (BE-AGT-064-5) gebruikte
`create_hitl_request()`, die intern alleen `flush()` doet, NOOIT `commit()`. Beide functies
raisten DIRECT DAARNA een `HTTPException(403)` op DEZELFDE databasesessie die van
`Depends(get_db)` komt (`src/core/database/database.py::get_db()`, regels 503-515: `yield
session; await session.commit()` in de try, `except Exception: await session.rollback();
raise` in de except).**

FastAPI's yield-dependency-mechanisme gooit elke exception die de route-handler opwerpt terug
IN de dependency-generator op het punt van de `yield` (dit is het gedocumenteerde, bedoelde
gedrag van "dependencies with yield" -- niet een edge case). Een `HTTPException` is een gewone
`Exception`-subklasse en werd door `get_db()`'s `except Exception`-clausule gevangen: de
sessie werd **ge-rollback't**, en een `flush()`-only INSERT overleeft een rollback nooit (dat
is fundamenteel transactiegedrag, geen aanname).

**Empirisch bevestigd** (zie sectie C.9 voor de reproductie): een throwaway integratietest
tegen de echte testdatabase (poort 5455) die exact dit patroon simuleert -- `create_hitl_
request()` aanroepen op een `get_db()`-sessie, dan een exception IN die generator gooien
zoals FastAPI zou doen -- liet de ticket-rij NIET bestaan in een daaropvolgende, verse sessie.
De test is na de reproductie verwijderd (was expliciet gemarkeerd als throwaway, geen
permanente toevoeging aan de suite); de bevinding staat hieronder met het exacte
commando en de uitkomst zodat ze zelf herhaalbaar is. Een permanente versie van dat bewijs
staat sindsdien in `tests/integration/test_governance_gate_hitl_ticket_commit.py` (commit
`d54bc5c4`), tegen dezelfde echte testdatabase, mutatiegetest in beide richtingen.

**Praktisch gevolg (tot commit `d54bc5c4`, 2026-08-25):** voor de 9
CVA/ALS/Focus-Builder/Agentic-Flow/Agents-routes achter `require_council_approval` EN voor
`execute_flow` retourneerde de 403-body een `hitl_request_id` die verwees naar een ticket dat
NOOIT in de database bestond. Een mens die op dat ticket wilde reageren (het hele doel van deze
sprint, AI Act art. 14) vond niets. Dit was **erger dan de oorspronkelijke OP-167-bug** (geen
ticket, stille weggooi): er werd een ticket-referentie GETOOND alsof hij bestond, wat een
misleidend signaal van "toezicht is geregeld" gaf terwijl er geen rij stond. Sinds commit
`d54bc5c4` commit beide functies expliciet voor de raise, en bestaat de rij wel.

Geen van de bestaande tests voor deze twee artefacten (`test_governance_gate.py`, en de
`execute_flow`-tests) ving dit: ALLE gebruikten `AsyncMock()` voor `db` en patchten
`HITLTicketRepository` volledig weg (zie sectie C.4), dus de echte
commit/rollback-levenscyclus werd nooit uitgevoerd. De fix in commit `d54bc5c4` moest daarom
ook 10 van die mock-opstellingen omzetten van `MagicMock` naar `AsyncMock` voor `service.db`
(anders faalde het succespad met een `TypeError` op de nieuwe `await service.db.commit()`).

**Belangrijk contrast, ook zelf geverifieerd:** de andere 4 artefacten (BE-AGT-064-1/-2/-3/-6)
hebben dit probleem NIET. `background_gate.py` en `specialist_base.py`'s floor-tak gebruiken
elk hun EIGEN, toegewijde `async with get_db_session() as db:`-blok rond precies de
ticket-aanmaak, en raisen daarna nooit een exception (ze retourneren altijd normaal) -- de
`async with` sluit dus altijd via het succes-pad, wat commit't. `service.py`'s proactieve pad
raiset evenmin. Dit is dus geen structureel probleem van het hele sprintwerk, maar specifiek
van de twee HTTP-gates die de ticket op DEZELFDE sessie maken als waarop ze vervolgens hun
403 opwerpen.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

Geen gemist artefact of aanroeppunt gevonden. Alle 6 artefacten, hun bestandspaden en de
9+1-aanroeperslijst zijn zelf tegen `grep -rn "require_council_approval(" src --include=*.py`
en de daadwerkelijke bestanden geverifieerd (9 echte aanroepen buiten definitie/docstrings,
bevestigd).

### 2. Functionele onduidelijkheden

Geen. De functionele beschrijving per artefact is scherp en correct (geverifieerd tegen de
broncode van elk van de 6 bestanden).

### 3. Technische onduidelijkheden

- **CRITICAL bij Ronde 1 (zie B en C.9), sindsdien gefixed in commit `d54bc5c4`:** sectie 14 van
  BE-AGT-064-4 en BE-AGT-064-5 beschreef de ticket-aanmaak als een betrouwbare "1 INSERT bij
  succes" zonder de commit/rollback-grens te benoemen. Dat was niet alleen een documentatiegat --
  de daadwerkelijke code had hierdoor een functioneel defect dat de spec ten onrechte niet
  vermeldde. Na de fix documenteert de spec de commit expliciet en klopt de "1 INSERT bij
  succes"-claim weer.
- Metadata-sectie "Gerelateerde database tabellen" noemt geen tabelnaam ("de bestaande tabel
  achter `HITLTicketRepository.create_hitl_request()`"). Zelf getraceerd: de tabel is
  `hitl_tickets` (model `HITLTicket`, `src/core/tool_broker/models.py:26-29`). Er bestaat OOK
  een `hitl_requests`-tabel (`src/core/governance/models.py:351`) -- een ANDER, ongerelateerd
  model. Zonder de expliciete naam is dit verwarrend voor een lezer die zelf naar de tabel zoekt
  en de verkeerde vindt.

### 4. Ontbrekende foutstatussen en edge cases

- De CRITICAL-bevinding hierboven was in wezen een ontbrekende edge case: "wat gebeurt er met de
  net aangemaakte ticket-rij als de request na de aanmaak alsnog met een exception eindigt" was
  niet beschreven, en het antwoord was destijds onverwacht (ze verdween). Sinds commit
  `d54bc5c4` verdwijnt ze niet meer.
- Voor het overige: 400/401/404/409/422/429/503 worden voor BE-AGT-064-4/-5 in een enkele regel
  afgedaan ("ONGEWIJZIGD"). Voor een fix-sprint op bestaande routes is dat verdedigbaar (er is
  geen nieuwe validatie/auth-laag toegevoegd), maar de spec bevestigt dit niet EXPLICIET per
  status-code zoals het sjabloon vraagt -- een lezer moet de aanname op waarde aannemen.

### 5. Acceptatiecriteria problemen

- Voor BE-AGT-064-4 en -5 claimde sectie 17 "mutatiebewijs" en test-dekking, maar geen van de
  destijds genoemde tests (allemaal `AsyncMock`-gebaseerd, zie sectie C.3/C.9) bewees dat een
  aangemaakt ticket de daadwerkelijke request-levenscyclus overleeft. De acceptatiecriteria
  waren dus INTERN consistent (ze bewezen wat ze beweerden te bewijzen) maar misten een test die
  de daadwerkelijk RELEVANTE eigenschap toetst -- exact het patroon dat
  `.claude/rules/code-quality.md`'s guard-mutatietest-regel bedoelt met "een testopstelling die
  uitzet wat je meet": hier zette de MOCK het commit/rollback-gedrag uit, niet een fixture.
  Sinds commit `d54bc5c4` vult `tests/integration/test_governance_gate_hitl_ticket_commit.py`
  precies dat gat: een echte sessie, geen mock, met controle op de rij na de request.

### 6. Integratorhandleiding / API-uitleg problemen

Geen structureel probleem, maar de integratorhandleiding belooft impliciet dat
`hitl_request_id` een bruikbare, bestaande referentie is. Na deze bevinding was dat voor
BE-AGT-064-4/-5 destijds ONWAAR in productie. Sinds commit `d54bc5c4` (2026-08-25) klopt de
belofte weer, en de spec is bijgewerkt om dat te bevestigen.

### 7. Trainingsdata problemen

Geen -- de trainingssamenvattingen per artefact zijn compact en correct, met uitzondering van
dezelfde (destijds bestaande, sinds commit `d54bc5c4` opgeloste) overclaim als hierboven
(BE-AGT-064-4/-5's "Succesrespons"-regel).

### 8. Structuur- en consistentieproblemen

- Metadata en BE-AGT-064-4 sectie 6 nemen de bewering "9 aanroepers over 6 domeinen" uit de
  dag-2-final-approver-brief letterlijk over. Zelf herleid via de daadwerkelijke aanroepers
  (agentic_flow_endpoints.py, als_tasks_router.py x2, agents/dependencies.py, cva/dependencies.py,
  cva_service.py x2, focus_builder/ai_router.py x2): dat zijn 9 aanroepen, verspreid over 5
  HERKENBARE domeinen (Agentic Flow, ALS, Agents, CVA, Focus Builder) -- niet 6. De brief noemt
  zelf ook maar 5 domeinnamen ("CVA, ALS, Focus Builder, Agentic Flow, Agents") bij het cijfer
  "6". Dit is dezelfde klasse fout als BE-AGT-051's "5 vs. 6 tests"-bevinding: een plausibel
  getal dat zichzelf niet dekt bij het narekenen, overgenomen zonder de eigen bronlijst te
  tellen.

### 9. Risico's voor implementatie, security of QA

**CRITICAL bij Ronde 1, sindsdien GEFIXED in commit `d54bc5c4` (2026-08-25).** Reproductie
tegen de echte testdatabase (`sanskritisetu_test_db`, poort 5455,
via de bestaande `tests/integration/conftest.py`-fixtures):

```text
Stappen (throwaway testbestand, na deze meting verwijderd):
1. agen = get_db(); session = await agen.__anext__()
2. ticket_ref = await HITLTicketRepository(session).create_hitl_request(
       tenant_id=<test_tenant>, user_id=1, decision_id="repro-decision",
       reason="repro", action_type="create_task", action_params={...})
   -> slaagt, logt "hitl_repository.created", ticket_ref is een echte string.
3. await agen.athrow(RuntimeError("simulated HTTPException(403)"))
   -> simuleert FastAPI's yield-dependency-gedrag: de exception komt binnen op het
      yield-punt in get_db(), raakt de `except Exception: await session.rollback(); raise`-tak.
4. Nieuwe sessie, SELECT ticket_ref FROM hitl_tickets WHERE ticket_ref = :ref
   -> resultaat: GEEN rij (row is None).

Uitkomst: pytest test_repro_ticket_survives_or_not_after_exception_in_request FAILED,
"REPRO CONFIRMED BUG: ... The ticket never persists." (assert row is not None -> AssertionError:
assert None is not None). Draaide op 2026-08-25 tegen tests/integration/conftest.py's
setup_db_manager/postgres-fixtures.
```

Dit was een BEWEZEN oorzaak (niet een aanname overgenomen van een reviewer, conform
`.claude/rules/quality-gates.md`'s regel over onbewezen oorzaken) en dus destijds geschikt om
als CRITICAL vastgelegd te worden. Het aanbevolen vervolg is inmiddels doorgevoerd, in commit
`d54bc5c4` (2026-08-25), buiten de scope van dit documentatie-artefact, als een eigen
codewijziging met eigen Gate 2/3: een expliciete `await db.commit()` direct na een succesvolle
`create_hitl_request()`-aanroep in `governance_gate.py` en `await service.db.commit()` in
`execution_router.py`, VOORDAT de `HTTPException` wordt opgeworpen -- plus een nieuwe
integratietest (`tests/integration/test_governance_gate_hitl_ticket_commit.py`, echte DB, geen
`AsyncMock`) die de rij na een simulerende 403 daadwerkelijk opvraagt, mutatiegetest in beide
richtingen, zodat deze klasse defect niet opnieuw ongemerkt binnensluipt via een gemockte
testsuite.

---

## D. ISSUE REGISTER

| Severity | ID/sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| **Critical -- RESOLVED (commit `d54bc5c4`, 2026-08-25)** | BE-AGT-064-4 sectie 14 + BE-AGT-064-5 sectie 14 | `create_hitl_request()` deed alleen `flush()`; beide artefacten raisten direct daarna `HTTPException(403)` op DEZELFDE `Depends(get_db)`-sessie, die bij een exception rollback't. Ticket verdween, `hitl_request_id` in de 403-body verwees naar niets. Empirisch bevestigd tegen de echte testdb. | De hele reden van deze sprint (AI Act art. 14: een mens moet daadwerkelijk kunnen ingrijpen) faalde stil voor de 2 grootste artefacten; erger dan de oorspronkelijke bug, want het oogde alsof het werkte. | Gefixed in commit `d54bc5c4`: expliciete `await db.commit()` / `await service.db.commit()` op het succespad, voor de raise, plus nieuwe integratietest `tests/integration/test_governance_gate_hitl_ticket_commit.py` tegen de echte testdatabase (mutatiegetest in beide richtingen). Spec bijgewerkt om de fix te reflecteren. |
| Medium | BE-AGT-064-4 sectie 6 + Metadata | "9 aanroepers over 6 domeinen" -- de brontekst noemt zelf maar 5 domeinnamen bij dat cijfer. Zelf herleid: 5 domeinen (Agentic Flow, ALS, Agents, CVA, Focus Builder). | Ongereconcilieerd getal dat plausibel klinkt maar niet klopt bij het narekenen -- dezelfde foutklasse als BE-AGT-051's 5-vs-6-tests-bevinding. | Gecorrigeerd naar "9 aanroepers over 5 domeinen", met de aanroeperslijst als bron. |
| Medium | Metadata, "Gerelateerde database tabellen" | Geen tabelnaam genoemd; er bestaan TWEE gelijkende modellen (`hitl_tickets` en het ongerelateerde `hitl_requests`). | Traceerbaarheid: een lezer die zelf zoekt kan de verkeerde tabel vinden. | Tabelnaam `hitl_tickets` (model `HITLTicket`, `src/core/tool_broker/models.py`) expliciet genoemd, met een aantekening dat `hitl_requests` een ander, ongerelateerd model is. |
| Low | BE-AGT-064-4/-5 sectie 13 | 400/401/404/409/422/429/503 in een enkele "ONGEWIJZIGD"-regel i.p.v. per status bevestigd. | Sjabloon vraagt expliciete behandeling per status; lezer moet nu op het woord aangenomen worden. | Regel aangescherpt: expliciet benoemd DAT elke afzonderlijke status is nagelopen tegen de ongewijzigde route-code, i.p.v. een blote bewering. |
| Low -- RESOLVED (commit `d54bc5c4`) | Integratorhandleiding + BE-AGT-064-4/-5 sectie 19 ("Succesrespons") | Beloofde impliciet dat `hitl_request_id` een bestaande referentie is. | Na de Critical-bevinding was dat voor deze twee artefacten destijds niet waar. | Waarschuwing toegevoegd in Ronde 2; sinds commit `d54bc5c4` klopt de belofte weer en is de spec bijgewerkt om dat te bevestigen. |

---

## E. ONTBREKENDE ITEMS

- Een verwijzing naar dit reviewdocument als vindplaats van een NIEUW, urgent code-issue (niet
  alleen een documentatiebevinding) ontbrak in de spec's Risico's-sectie -- toegevoegd in
  Ronde 2.
- Geen ontbrekend endpoint, service of flow gevonden buiten de hierboven genoemde punten.

---

## F. VERBETERDE TEKSTVOORSTELLEN

Zie Ronde 2 hieronder -- de daadwerkelijke tekstwijzigingen zijn direct in de spec doorgevoerd
(niet als apart voorstel hier herhaald) omdat de wijzigingen grotendeels feitelijke correcties
zijn (tabelnaam, domeinaantal) of een geheel nieuwe, noodzakelijke waarschuwingsparagraaf
(het Critical-defect) die niet zinvol als "alternatieve formulering" te tonen is naast een
foute oorspronkelijke tekst.

---

## Ronde 2 -- fixes toegepast (2026-08-25)

Alle vijf bevindingen uit het Issue Register zijn verwerkt in
`docs/backend/features/BE-AGT-064-hitl-ticket-volledigheid.md`:

1. **Critical (BE-AGT-064-4/-5):** Doel-sectie, beide artefactsecties (6/14/17/18/19) en
   Risico's/Open vragen uitgebreid met een expliciete, bewezen waarschuwing: de ticket-aanmaak
   op deze twee paden overleefde een `HTTPException(403)` op dezelfde sessie NIET (geen
   `commit()` voor de `raise`), empirisch bevestigd tegen de echte testdatabase. In Ronde 2
   gemarkeerd als open, urgent code-defect buiten de scope van dit documentatie-artefact --
   NIET als opgelost voorgesteld. **Nazorg (2026-08-25): dat vervolgpunt is inmiddels
   afgehandeld in commit `d54bc5c4`** (expliciete `db.commit()`/`service.db.commit()` voor de
   raise, plus de nieuwe integratietest `tests/integration/test_governance_gate_hitl_ticket_commit.py`
   als bewijs), en de spec (`BE-AGT-064-hitl-ticket-volledigheid.md`) is bijgewerkt om dit als
   gefixed te documenteren in plaats van als open defect.
2. Metadata + BE-AGT-064-4 sectie 6: "6 domeinen" vervangen door "5 domeinen (Agentic Flow,
   ALS, Agents, CVA, Focus Builder)", met de eigen grep als bron.
3. Metadata: tabelnaam `hitl_tickets` (`HITLTicket`, `src/core/tool_broker/models.py`)
   expliciet genoemd, met een aantekening over het ongerelateerde `hitl_requests`-model.
4. BE-AGT-064-4/-5 sectie 13: de 400/401/404/409/422/429/503-regel herformuleerd om expliciet
   te zeggen dat elke status individueel tegen de route-code is nagelopen.
5. Integratorhandleiding + sectie 19 van beide artefacten: waarschuwing toegevoegd dat
   `hitl_request_id` destijds niet gegarandeerd een bestaande rij was voor deze twee artefacten.

Herverificatie na deze wijzigingen: ASCII-scan op het spec-bestand herhaald (0 non-ASCII
tekens), geen nieuwe interne inconsistenties geintroduceerd (elke wijziging is additief of een
directe feitelijke correctie, geen bestaande, correcte tekst verwijderd).

**Eindoordeel na Ronde 2: APPROVED WITH MINOR GAPS.** De Critical-bevinding was een bevinding
OVER de onderliggende code, niet over de documentatie-kwaliteit zelf -- en de documentatie
documenteerde die bevinding correct, expliciet en zonder ze te verhullen of als opgelost voor
te stellen. De twee resterende Low-bevindingen (per-statuscode-detail, iets minder diep dan het
sjabloon idealiter zou willen voor BE-AGT-064-4/-5 sectie 13) waren MINOR en geen blocker voor
deze fix-sprint-schaal documentatie.

**Nazorg (2026-08-25): het Critical-defect is gefixed in commit `d54bc5c4`.** Zie sectie C.9 en
het Issue Register hierboven voor de details van de fix en het bewijs (nieuwe integratietest
`tests/integration/test_governance_gate_hitl_ticket_commit.py`). De spec-secties die dit
document opdroeg te wijzigen naar "open defect" zijn een tweede keer bijgewerkt, nu naar
"gefixed in commit `d54bc5c4`". Dit review-document zelf blijft verder ongewijzigd staan als
historisch record van wat Ronde 1/2 vonden en aanbevalen; alleen deze nazorg-noot en de
Issue-Register-rij zijn toegevoegd om de huidige, gefixte staat te reflecteren.

---

## G. RELEASE-OORDEEL

- Geschikt voor bouw/implementatie: bij Ronde 1/2 **Nee, niet zonder een aparte code-fix** voor
  het Critical-defect in BE-AGT-064-4/-5 (geen documentatieprobleem, een productieprobleem dat
  deze documentatie correct blootlegde). **Nazorg (2026-08-25): die code-fix is doorgevoerd in
  commit `d54bc5c4`; alle 6 artefacten zijn nu geschikt.**
- Geschikt voor QA en geautomatiseerd testen: Ja voor de documentatie zelf; de spec wees
  expliciet naar het destijds ontbrekende testtype (een integratietest tegen een echte sessie,
  geen `AsyncMock`) dat nodig was om de code-fix te bewijzen -- dat testtype bestaat sindsdien
  (`tests/integration/test_governance_gate_hitl_ticket_commit.py`, commit `d54bc5c4`).
- Geschikt voor LLM-training: Ja, na de Ronde-2-correcties -- en specifiek WAARDEVOL als
  trainingsvoorbeeld van hoe een gemockte testsuite een reeel transactiedefect kan verhullen, en
  van hoe zo'n defect vervolgens correct wordt gefixed en bewezen.
- Geschikt voor integratorhandleiding/API-documentatie: Ja, met de toegevoegde waarschuwing dat
  `hitl_request_id` voor twee van de zes artefacten destijds geen garantie was -- sinds commit
  `d54bc5c4` is dat wel het geval.

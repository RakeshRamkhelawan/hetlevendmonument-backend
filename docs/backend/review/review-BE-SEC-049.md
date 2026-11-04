STATUS: APPROVED

# Review BE-SEC-049 -- Zelf-goedkeuring blokkeren op het gatekeeper-HITL-pad

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-SEC-049-gatekeeper-hitl-zelfgoedkeuring.md` |
| Registerpunt | ADR-036 OP-81 |
| Reviewdatum | 2026-09-01 |
| Branch | `iter/op-81-zelfgoedkeuring-gatekeeper` |
| Commits | `82e4f0e8` (rode test), `5a0f781c` (fix + migratie) |
| **Status** | **APPROVED** |

---

## 1. Gemeten vergelijking: broker-pad versus gatekeeper-pad

Beide paden zijn gelezen voordat er een regel is geschreven. Dit is wat er feitelijk staat.

| Aspect | Broker-pad | Gatekeeper-pad (VOOR) | Gatekeeper-pad (NA) |
| --- | --- | --- | --- |
| Tabel | `hitl_tickets` | `hitl_requests` | `hitl_requests` |
| Model | `HITLTicket` | `HITLRequestModel` | idem |
| Aanvrager vastgelegd | `payload["_requested_by"]` (JSONB) | GEEN VELD | `requested_by_user_id` (kolom) |
| Gezet door | `HITLTicketRepository.create_hitl_request(user_id=...)` als `str(user_id)` | n.v.t. | `Gatekeeper._create_hitl_request` uit `context["user_id"]` |
| Uitvoerende agent apart | `payload["_executing_identity"]` | `agent_id`-kolom | idem |
| Zelf-goedkeuringscheck | `_refuse_self_approval` (OP-70) | AFWEZIG | `_refuse_self_approval` (OP-81) |
| Vergelijking | `str(requester) == str(current_user.id)` | n.v.t. | `requester == current_user.id` (beide int) |
| Toegepast op | approve + reject | n.v.t. | approve + reject |
| Bij ontbrekende aanvrager | fail-open, rolcheck blijft | n.v.t. | fail-open, rolcheck blijft |

**De registerrij klopte feitelijk, maar de conclusie niet.** OP-81 stelde vast dat
`HITLRequestModel` geen veld voor een menselijke aanvrager heeft en concludeerde dat de relatie
"de aanvrager keurt zichzelf goed" daar niet bestaat. De eerste helft is geverifieerd en juist.
De tweede helft niet: de agent handelt NAMENS een mens, en dat die schakel niet werd
opgeslagen is precies het gat, niet de reden om het open te laten.

**Wat de registerrij precies fout concludeerde.** De rij stelt: "Die tickets worden door een
AGENT aangemaakt, niet door een mens, dus de relatie 'de aanvrager keurt zichzelf goed' bestaat
er niet in dezelfde vorm", en daarom zou een check bouwen "schijnzekerheid" zijn.

De premisse is juist -- een agent maakt het ticket aan -- maar de gevolgtrekking slaat een
schakel over. Die agent handelt namens een MENS, en het is juist die mens die het ticket
vervolgens als beheerder kan goedkeuren. De relatie bestaat dus wel degelijk; hij was alleen niet
OPGESLAGEN. De ontbrekende kolom was daarmee geen argument tegen de check, maar de vindplaats van
het gat zelf. Precies zo staat het in ASVS 8.3.3: het besluit hoort te rusten op het
oorspronkelijke subject, en dat "de tussenliggende service het verzoek indiende" is nooit een
reden om dat subject buiten beschouwing te laten.

De rij vroeg terecht om "eerst een kolom voor de aanvragende identiteit en een besluit over wat
'aanvrager' betekent als de aanvrager een agent is". Dat besluit is nu genomen en luidt: de
aanvrager is de MENS, nooit de agent.

**Afwijking van de registerrij die gerapporteerd moet worden:** OP-81 verwijst naar
`governance/models.py:283-330`. Op develop (61c5a7c1) staat `HITLRequestModel` op regel
343-398. De inhoud van de meting klopt; alleen de regelnummers zijn verschoven.

---

## 2. De kernvraag: aanvragende mens of uitvoerende identiteit?

**Antwoord: de aanvragende MENS.** Onderbouwing, en het is niet mijn oordeel maar een eis:

> OWASP ASVS 5.0, V8.3.3 -- neem het autorisatiebesluit op basis van de permissies van het
> OORSPRONKELIJKE subject, niet van een tussenliggende service die namens hem handelt.

De agent is de tussenliggende service. Drie redenen waarom `agent_id` de verkeerde sleutel zou
zijn, los van de norm:

1. Een agent is geen tweede paar ogen en kan geen verantwoording dragen. Het vierogenprincipe
   gaat over menselijke aansprakelijkheid.
2. Toetsen op `agent_id` zou elk ticket van dezelfde agent aan elkaar knopen en niets zeggen
   over de mens die erachter zat -- een beheerder kan dan nog steeds zijn eigen aanvraag
   goedkeuren zolang hij een andere agent gebruikt.
3. Omgekeerd zou het een legitieme goedkeurder blokkeren die toevallig dezelfde agent gebruikt.

**Toetsing van het broker-pad tegen deze eis.** Gemeten in
`src/core/tool_broker/hitl_repository.py::create_hitl_request`: het zet `_requested_by =
str(user_id)`, waarbij `user_id` de INITIERENDE MENS is, en bewaart de agent SEPARAAT als
`_executing_identity` uitsluitend voor de tool-permissiecheck (OP-163).
`api/v1/tool_broker/hitl_router.py::_refuse_self_approval` vergelijkt vervolgens op
`_requested_by`.

**Conclusie: het broker-pad voldoet aan ASVS 8.3.3 en wijkt er niet van af.** Het scheidt de
twee identiteiten expliciet en hangt het autorisatiebesluit aan de mens. Er is dus geen
bevinding te rapporteren op het broker-pad; het patroon is terecht gekopieerd in plaats van
gecorrigeerd. Dit is precies het dual-identity/on-behalf-of-model (`sub` = mens, `act.sub` =
agent) dat de OBO-literatuur voorschrijft.

### 2.1 Legt de kolom de MENS vast, en kan hij uit een request body komen?

Twee vragen die apart beantwoord moeten worden, want ze hebben verschillende bewijzen.

**Legt hij de mens vast?** Ja. De waarde is `context["user_id"]`, doorgegeven aan
`Gatekeeper.evaluate_task`. Dat is per conventie in deze codebase het gebruikersnummer van de
mens namens wie de handeling loopt -- dezelfde sleutel die
`tool_broker/hitl_router.py::_voer_goedgekeurde_actie_uit` in de executiecontext zet. De agent
wordt NIET in dit veld geschreven: die heeft zijn eigen kolom (`agent_id`), en die kolom wordt
door de check niet gelezen. Beide identiteiten bestaan dus naast elkaar, en alleen de menselijke
draagt het autorisatiebesluit. `_als_gebruikersnummer()` weigert bovendien alles wat geen echt
geheel getal of zuiver decimale ASCII-string is (en expliciet `bool`), zodat er geen agentnaam of
vlag als "gebruiker" in terecht kan komen.

**Kan hij uit een request body komen?** Nee, en dat is structureel en niet alleen afgesproken.
Het veld wordt op precies EEN plek geschreven (`Gatekeeper._create_hitl_request`), en die plek
leest uitsluitend de `context`-parameter van een servicemethode. Er is geen Pydantic-schema met
dit veld, geen endpoint dat het accepteert, en de twee HITL-endpoints die er wel zijn LEZEN het
alleen. De bestaande body-velden `approved_by` en `rejected_by` worden sinds OP-43 al genegeerd.
Daarmee is ASVS 8.3.1 gehaald: de handhaving zit in een trusted service layer en hangt niet aan
iets dat de consumer kan zetten.

**Wat gebeurt er bij een agent zonder herleidbare mens?** Dan blijft de kolom NULL, en het
gedrag is ASYMMETRISCH (besluit Rakesh, 2026-09-01):

| Route | Gedrag bij `requested_by_user_id IS NULL` | Foutcode |
| --- | --- | --- |
| `POST /hitl/approve` | **403, fail-closed** | `REQUESTER_NOT_TRACEABLE` |
| `POST /hitl/reject` | **200, fail-open** | -- |

**Waarom fail-closed op goedkeuren.** Een goedkeuring is het bewijs waarop het menselijk toezicht
uit AI Act art. 14 rust. Kan niemand vaststellen wie erom vroeg, dan is niet vast te stellen dat
aanvrager en beslisser twee verschillende mensen zijn, en dan bewijst de goedkeuring niet wat ze
hoort te bewijzen. De huisregel van dit project is dan blokkeren, geen sentinel verzinnen.

**Waarom fail-open op afwijzen, en waarom dat de rest van het tegenargument wegneemt.** Mijn
eerste versie was symmetrisch fail-open, met als argument dat blokkeren de wachtrij zou
vastzetten. Rakesh heeft dat argument met mijn eigen meting weerlegd, en terecht:

1. **Er zijn geen rijen om vast te laten lopen.** `save_hitl_request` heeft nul aanroepers in
   `src/` -- en gemeten over de volledige branch-historie zelfs NOOIT een aanroeper gehad. De
   prijs die fail-closed volgens mijn eigen redenering zou kosten, bestaat hier niet.
2. **Zolang afwijzen mag, kan geen enkel ticket vastlopen.** Er is altijd een uitweg, terwijl een
   onbewijsbare goedkeuring onmogelijk wordt. Dat is fail-secure ZONDER vastgelopen wachtrij.

Afwijzen kan die kant op veilig openstaan omdat het de MINST bevoorrechte uitkomst is: het
verleent geen enkel recht en laat de HIGH-risk actie juist NIET gebeuren. Het art.-14-bewijs
blijft intact, want `rejected_by` komt nog steeds uit het token.

**Gevolg voor het broker-pad: dat heeft op dit punt een GAT.** Daar kan een ticket zonder bekende
aanvrager nog wel worden goedgekeurd. Het broker-pad was de referentie voor het PATROON (welke
identiteit is de sleutel) en blijft dat -- maar het is op de fail-open-vraag geen precedent. Dit
hoort een eigen bevinding te zijn, niet gekopieerd gedrag.

**De twee foutmeldingen zijn met opzet onderscheidend.** Een beheerder moet "jij mag dit
specifieke ticket niet" (`SELF_APPROVAL_FORBIDDEN`) kunnen scheiden van "dit ticket mist het
bewijs dat een goedkeuring geldig maakt" (`REQUESTER_NOT_TRACEABLE`) -- de vervolgactie is een
andere.

**ASVS 8.3.1 (handhaving in een trusted service layer, nooit op iets dat de consumer kan
manipuleren)** is eveneens gehaald: de aanvrager komt uit de server-side `context` van een
servicemethode, niet uit een request body. Dat is dezelfde grens die OP-43 trok toen
`approved_by` uit `request_body` werd gehaald.

---

## 3. Mutatiebewijs -- BEIDE richtingen, GEMETEN

Groene basis vooraf: `python -m pytest tests/unit/api/test_gatekeeper_hitl_refuses_self_approval.py -p no:randomly`
-> **6 passed**.

Terugweg via een KOPIE (`C:/tmp/op81_backup/`), nooit `git checkout --`.

| # | Mutatie (op de PRODUCTIECODE) | Gemeten uitkomst | Oordeel |
| --- | --- | --- | --- |
| 1 | `_refuse_self_approval(...)` verwijderd uit `approve_hitl` | **1 failed, 5 passed** -- `test_the_initiating_human_cannot_approve_their_own_request` | Betrapt |
| 2 | `_refuse_self_approval(...)` verwijderd uit `reject_hitl` | **1 failed, 5 passed** -- `test_the_initiating_human_cannot_reject_their_own_request` | Betrapt |
| 3 | Check verscherpt tot `if requester is not None:` (weiger IEDEREEN) | **2 failed, 4 passed** -- beide tests in `TestALegitimateApprovalStillWorks` | Betrapt (tweede richting) |
| 4 | `save_hitl_request` laat `requested_by_user_id=...` weg | **3 failed, 3 passed** -- de recording-test EN beide zelf-goedkeuringstests | Betrapt |
| 5 | `_require_traceable_requester(...)` verwijderd uit `approve_hitl` | **1 failed, 7 passed** -- `TestATicketWithoutATraceableRequester::test_it_cannot_be_approved` | Betrapt |
| 6 | `_require_traceable_requester(...)` OOK toegevoegd aan `reject_hitl` | **1 failed, 7 passed** -- `test_it_can_still_be_rejected` | Betrapt (tweede richting) |
| -- | Alles hersteld uit de kopie | **6 passed** (basis voor mutatie 1-4), **8 passed** (basis voor 5-6) | Basis terug |

**Waarom mutatie 1 en 2 apart staan.** De guard bewaakt een expliciet benoemde verzameling van
TWEE endpoints, `{approve, reject}`. De aanscherping in `quality-gates.md` (ADR-036 OP-124-
nazorg) eist een mutatieregel PER ELEMENT van die verzameling; vier mutaties op hetzelfde
endpoint zouden het gevoel van bewijs geven terwijl de helft van de oppervlakte ongetest bleef.
Elke mutatie raakte precies EEN test, wat aantoont dat de twee aanroepen onafhankelijk gedekt
zijn.

**Waarom mutatie 3 er moet zijn.** Zonder die richting is "weiger alle goedkeuringen" een
geldige oplossing voor mutatie 1 en 2, en dan sloopt de guard de wachtrij die hij hoort te
beschermen.

**Waarom mutatie 4 er moet zijn.** De guard kan alleen werken als de PRODUCENT de identiteit
vastlegt. Zonder deze mutatie zou een stille regressie in `save_hitl_request` de guard fail-open
maken terwijl alle endpointtests groen bleven.

---

## 4. Bewijs dat de test ROOD was voor de fix

Rode test in een EIGEN commit vooraf: `82e4f0e8`.

Geverifieerd tegen de commit-inhoud, niet tegen een backup:

```
git show 82e4f0e8:tests/unit/api/test_gatekeeper_hitl_refuses_self_approval.py | diff - <werkboom>
  -> identiek
git show 82e4f0e8:src/core/api/v1/gatekeeper/gatekeeper_hitl_router.py | grep -c self_approval
  -> 0
git show 82e4f0e8:src/core/governance/models.py | grep -c requested_by_user_id
  -> 0
```

Gemeten uitkomst op die commit: **3 failed, 3 passed**.

| Rode test | Reden van falen (de JUISTE reden) |
| --- | --- |
| `test_the_persisted_request_records_the_initiating_human` | `AttributeError: 'HITLRequestModel' object has no attribute 'requested_by_user_id'` |
| `test_the_initiating_human_cannot_approve_their_own_request` | `assert 200 == 403` -- de aanvrager keurde zijn eigen ticket goed |
| `test_the_initiating_human_cannot_reject_their_own_request` | `assert 200 == 403` |

De drie groene tests op die commit waren de legitieme-goedkeuring-tests en de tenant-isolatie.
Die moesten groen ZIJN en groen BLIJVEN.

**Loopt de test over de echte producent?** Ja, en dat is expliciet gecontroleerd. De keten in
de test is: echte `Gatekeeper(tenant_id=...)` -> echte `TaskData` -> echte `evaluate_task` ->
echte `_create_hitl_request` -> echte `GatekeeperRepository.save_hitl_request` -> echte
SQLAlchemy-rij -> echte FastAPI-route. Alleen de databaselaag is SQLite in geheugen en het
model komt onverkort uit `src/core/governance/models.py`. Er wordt nergens aan beide kanten van
een vergelijking dezelfde verzonnen waarde gezet.

---

## 5. Gate 3

| Gate | Commando | Uitkomst |
| --- | --- | --- |
| ruff | `python -m ruff check <7 geraakte bestanden>` | All checks passed |
| pyright | `python -m pyright <5 geraakte bronbestanden>` (expliciete bestandsargumenten) | 0 errors, 0 warnings |
| mypy | `python scripts/run_mypy_audit.py --fail-on-increase` | zie par. 5.1 |

Toolversies gecontroleerd tegen `requirements-test.txt` voor het meten: `mypy 2.3.0`,
`types-redis 4.6.0.20241004`, `types-requests 2.33.0.20260712`, `types-aiofiles`,
`types-PyYAML`, `types-python-dateutil` -- allemaal exact de gepinde versies. Zonder die
controle meet je iets anders dan de poort.

### 5.1 mypy-audit

```
Baseline errors: 0
Files with errors: 0

OK: No files increased their mypy error count.
[exited with code 0]
```

De baseline is 0 en blijft 0. Geen enkel bestand verhoogde zijn foutental. Aanvullend en
gerichter gemeten met dezelfde gepinde tool op alleen de vier geraakte bronbestanden:
`Success: no issues found in 4 source files`.

---

## 6. Regressie

| Suite | Uitkomst |
| --- | --- |
| `tests/unit/api/test_gatekeeper_hitl_refuses_self_approval.py` (nieuw) | 6 passed |
| `tests/unit/api/test_gatekeeper_hitl_requires_an_approver.py` (buurbestand) | 17 passed |
| `tests/architecture` + gatekeeper/als-bestanden | 772 passed, 0 failed |

Gemeten, alle drie zonder falen:

| Run | Commando | Uitkomst |
| --- | --- | --- |
| Nieuwe guard | `pytest tests/unit/api/test_gatekeeper_hitl_refuses_self_approval.py -p no:randomly` | **8 passed** |
| Beide HITL-bestanden | de twee gatekeeper-HITL-testbestanden samen | **25 passed** |
| Gerichte hoogrisico-set | de vier import/architectuurguards die mijn nieuwe import raken, plus beide HITL-bestanden | **30 passed**, exit 0 |
| Volledige architectuursuite | `pytest tests/architecture <4 gatekeeper/als-bestanden> -n 4 --timeout=300` | **772 passed in 522s**, exit 0 |

De gerichte hoogrisico-set bestond uit precies de guards die deze wijziging kan breken, want er
is EEN import toegevoegd aan een Laag-1-subrouter (`HITLRequestModel` via de
`dependencies`-facade):

- `test_gatekeeper_router_no_direct_db.py::test_gatekeeper_router_no_direct_db_imports` -- PASSED
- `test_importlinter_contract1_covers_sub_routers.py::test_sub_routers_do_not_directly_import_domain_logic` -- PASSED
- `test_adr034_contracts.py::test_lint_imports_no_parse_error` -- PASSED
- `test_governance_contract_persistence_is_consumed.py` -- PASSED

Dat de import via de facade loopt en niet rechtstreeks uit `src.core.governance.models` is
daarmee GEMETEN en niet aangenomen; ADR-033 Contract 1 blijft groen.

**Aanpassing in het buurbestand.** `_FakeHitl` in
`test_gatekeeper_hitl_requires_an_approver.py` heeft `requested_by_user_id = 999` gekregen. Dat
is bewust een ANDER nummer dan de testgebruiker (id 42), zodat dat bestand blijft toetsen wat
het altijd toetste -- de rol en de herkomst van de goedkeurdersidentiteit -- en niet
stilzwijgend op de nieuwe check stukloopt. De guard is NIET verzwakt om die tests te sparen:
`_refuse_self_approval` leest het attribuut rechtstreeks, dus een fake zonder dat veld zou
luid breken in plaats van stil fail-open te gaan.

Twee regels in dat bestand zijn door de projecteigen save-hook geherformatteerd (regels 449-465,
puur opmaak, semantisch identiek). Handmatig terugdraaien werd door de hook direct ongedaan
gemaakt; ze staan in de diff.

---

## 7. Bevindingen

### CRITICAL

Geen.

### HIGH

**H-1 (opgelost in deze wijziging).** De aanvrager kon zijn eigen gatekeeper-ticket goedkeuren
en afwijzen. Gemeten als 200 op beide routes.

### MEDIUM

**M-1 (NIET opgelost -- krijgt een eigen registerrij van Rakesh).** De tabel `hitl_requests` heeft vandaag geen
enkel productieschrijfpad. `GatekeeperRepository.save_hitl_request` is de enige schrijver en
heeft nul aanroepers in `src/`, `tests/` en `scripts/`. `Gatekeeper.evaluate_task` persisteert
alleen de DECISION, niet de HITL-aanvraag. Alle live ticketproducenten schrijven naar de andere
tabel (`hitl_tickets`).

Gevolg: de goedkeurroute is geserveerd en leest uit een tabel die niets vult. Deze fix is
daarmee op dit moment PREVENTIEF -- dezelfde situatie als bij OP-37, en om dezelfde reden geen
argument om het open te laten: "latent" is geen borging.

**Onderscheid dat hier telt: "de tabel bestaat" is niet "er schrijft iets naar".** De tabel wordt
aangemaakt door `552d3cb43362_add_gatekeeper_tables.py`, die in de huidige migratieketen zit en
op 2026-05-29 is samengevoegd. Elke omgeving die migraties heeft gedraaid HEEFT de tabel, en hij
KAN dus rijen bevatten. Maar geschreven is er nooit: gemeten over de volledige branch-historie
(`git log -S "save_hitl_request"` plus een `git grep` per gevonden commit) had de methode op GEEN
ENKEL commit een aanroeper buiten haar eigen definitiebestand. De zeven overige schrijfplekken
staan alle zeven in `tests/` (4 in `tests/integration/`, 3 in `tests/e2e/`);
`scripts/fix_gatekeeper_tests.py` bevat de naam alleen in stringliterals die TESTcode herschrijven.

Dit is een aparte bevinding en hoort een eigen OP-nummer te krijgen. Hij is hier GEMETEN, niet
opgelost, omdat een producent aansluiten buiten de scope van OP-81 valt en een eigen besluit is
over waar gatekeeper-tickets thuishoren (of de twee tabellen samengevoegd moeten worden).

**M-2 (bewuste keuze, en sinds het fail-closed-besluit met een GEVOLG).** In productie blijft
`requested_by_user_id` NULL zolang
`als/router.py::_check_gatekeeper` geen `context` meegeeft; `TaskData` draagt geen menselijke
aanvrager. Er is bewust GEEN identiteit verzonnen op die plek -- dat zou een sentinel zijn en
precies de schijnzekerheid opleveren die OP-81 terecht vreesde.

Gevolg van het fail-closed-besluit: zodra iets die producent aansluit ZONDER de context mee te
geven, zijn de resulterende tickets niet goed te keuren (wel af te wijzen). Dat is de bedoeling --
het dwingt de aanroeper om de aanvrager mee te geven in plaats van dat er stil een onbewijsbare
goedkeuring ontstaat -- maar het is een expliciete eis aan wie M-1 oppakt, en het hoort in die
registerrij te staan.

**M-3 (NIEUW, niet opgelost -- op het BROKER-pad).** `tool_broker/hitl_router.py::_refuse_self_approval`
is fail-open bij een ontbrekende `_requested_by`: daar kan een ticket zonder bekende aanvrager nog
wel worden goedgekeurd. Voor het gatekeeper-pad is die keuze nu omgedraaid (fail-closed op
approve, open op reject) omdat het "wachtrij loopt vast"-argument daar meetbaar niet opgaat.
Op het broker-pad is dat argument NIET nagemeten -- die tabel (`hitl_tickets`) heeft wel degelijk
live producenten, dus daar kunnen rijen zonder aanvrager echt bestaan en zou fail-closed een
bestaande wachtrij kunnen raken. Dat vraagt een eigen meting (hoeveel rijen hebben geen
`_requested_by`?) en een eigen besluit. Hier bewust NIET meegenomen: het is een ander oppervlak
met een andere risicoafweging.

### LOW

**L-1.** `alembic check` meldt 854 drift-operaties. Gemeten op de parent-staat: eveneens 854.
Pre-existent en schemabreed, geen enkele operatie over deze kolom. Buiten scope.

---

## 8. Checklist

| Eis | Status |
| --- | --- |
| Rode test in eigen commit VOOR de fix | JA -- `82e4f0e8`, roodheid bewezen via `git show` |
| Test loopt over de echte producent | JA -- Gatekeeper + repository + route |
| Mutatie-getest in beide richtingen | JA -- 4 mutaties, gemeten aantallen in par. 3 |
| Mutaties in de docstring vastgelegd | JA |
| Precies EEN alembic head | JA -- `adr036_op81_requested_by (head)` |
| `downgrade()` werkt echt, geen `pass` | JA -- gemeten op Postgres 15 |
| Geen `sa.inspect(op.get_bind())` | JA -- rauwe SQL |
| Model in `import_all_models.py` | JA -- `src.core.governance.models` stond er al |
| `tenant_id` uit context, nooit uit body | JA -- ongewijzigd, `get_tenant_id()` |
| Repository-methode met tenantfilter + isolatietest | JA -- `test_a_ticket_from_another_tenant_is_not_visible` |
| `datetime.now(timezone.utc)` | JA -- geen nieuwe datetime-aanroepen; bestaande waren al correct |
| ASCII-only, programmatisch gecontroleerd | JA -- byte-scan over alle geraakte bestanden |
| Regels <= 100 tekens | JA -- geen enkele TOEGEVOEGDE regel langer dan 100 |
| Geen formatter over een hele map | JA |
| Niet gemerged, geen tag, geen `--no-verify` | JA |

---

## Eindoordeel

**APPROVED.**

De grens is getrokken op de identiteit die de norm voorschrijft, met hergebruik van het patroon
dat op het broker-pad al bewezen is, en de guard is in beide richtingen mutatie-getest met
gemeten uitkomsten. Bij een ontbrekende aanvrager is goedkeuren fail-closed met een eigen
foutcode en afwijzen bewust open, zodat geen ticket kan vastlopen. De drie openstaande punten
(M-1, M-2, M-3) zijn expliciet gemeten en gerapporteerd in plaats van weggeschreven.

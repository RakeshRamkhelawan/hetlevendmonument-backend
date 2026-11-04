# BE-LLM-005 -- de failoverketen per tenant, en de sessie die dichtgaat

Datum:     2026-09-24
Fase:      Lokaal-eerst LLM-platform, fase 3 (na 2b = BE-LLM-004)
ADR:       ADR-026 par. 1.2.1 (failoverketen met circuit breaker)
Basis:     develop `54e4b1e7`

---

## 1. Waarom deze knip bestaat

Fase 2b liet een agent het eindpunt van zijn eigen klant gebruiken, maar nam bewust alleen de
EERSTE bruikbare rij. De tabel is per ontwerp geordend, dus er was een keten zonder failover:
viel het eindpunt van een klant uit, dan viel zijn agent uit.

ADR-026 par. 1.2.1 belooft precies die keten met een circuit breaker. Gemeten op `54e4b1e7`:

| Wat | Meting |
|---|---|
| Rijen die `for_tenant` gebruikte | EEN (`service.py:204`) |
| Failover in de nieuwe LLM-stapel | bestond niet |
| Failover elders | `learning/interfaces/failover_llm_provider.py` -- werkt, maar voor de twin en gevoed uit omgevingsvariabelen (`twin_service_factory.py:50,62`) |
| `tenant.llm_chain` uit ADR-026 | bestaat niet als kolom; fase 2a koos een TABEL |

## 2. Wat er nu gebeurt

`LLMService.for_tenant(tenant_id)` bouwt een `FailoverProvider` over ALLE bruikbare rijen, op
volgorde. Die probeert ze een voor een, met een circuit breaker per schakel: na drie fouten wordt
een schakel zestig seconden overgeslagen in plaats van opnieuw geprobeerd (de waarden uit
ADR-026).

**"Na drie fouten" en niet "na drie OPEENVOLGENDE fouten".** Die formulering stond in de eerste
versie van dit document, in de brief en in de code, en een Gate 2-reviewer wees erop. Zelf
nagemeten op `CircuitBreaker`: twee fouten, dan een succes, dan is de teller nog steeds 2 -- een
succes in de staat CLOSED zet hem niet terug. De drempel is dus CUMULATIEF over het leven van dat
proces. Een schakel die zelden faalt gaat daardoor na zijn derde fout OOIT zestig seconden dicht,
en herstelt daarna via HALF_OPEN. Dat is verdedigbaar; het onjuiste woord was het probleem.

**Waarom het een provider is en geen slimmigheid in `for_tenant`.** Failover is iets van de
AANROEP: een eindpunt faalt pas als je het gebruikt. Een functie die bij het opbouwen een rij
kiest, kan per constructie geen failover leveren -- hoe zorgvuldig hij ook kiest.

## 3. De breaker-id draagt de tenant, en dat is geen detail

De twin sleutelt zijn breakers op klassenaam plus index
(`learning/interfaces/failover_llm_provider.py:70`):

```python
breaker_key = f"{provider_name}#{idx}"
```

Voor een platformbrede keten klopt dat. Voor een KLANTketen is het een lek tussen tenants: twee
klanten met elk een eigen eindpunt zouden dan EEN breaker delen, en het uitvallen van klant A
zet de provider van klant B op open -- een storing bij de ene klant die de andere raakt, zonder
dat er ergens data overgaat en dus zonder dat een tenantisolatietest hem vindt.

De id is daarom `tenant:<id>|<host>|<volgorde>`. De host zit erbij omdat twee tenants dezelfde
volgorde hebben, en de volgorde omdat een tenant twee rijen naar dezelfde host kan hebben --
twee deployments op een Azure- of vLLM-eindpunt is een normale inrichting. Dat laatste deel
was in ronde 1 ongetest; een reviewer mat dat de mutatie `|{rij.volgorde}` weghalen groen
bleef, omdat de bestaande test twee verschillende hosts gebruikte.

**De registry is procesbreed, en dat MOET.** Een registry per exemplaar zou zijn tellers wissen
bij elke nieuwe agenttaak -- en agent-exemplaren worden per taak gebouwd. De breaker zou dan
alleen binnen een taak openen en nooit iets besparen. ADR-026 accepteert per-worker toestand
expliciet. Juist omdat hij procesbreed is, moet die id de tenant dragen.

Drie randvoorwaarden van die keuze staan in de moduledocstring van `failover.py`, alle drie
uit de Gate 2-ronde: de drempel is cumulatief, de registry groeit monotoon (met
worker-recycling als grens), en `asyncio`-sloten binden zich aan een event loop terwijl het
agentpad er een per bericht opent.

## 4. Wat er gebeurt als de HELE keten faalt -- een gedragswijziging

`LLMServiceError`, geen stille terugval op het platformmodel.

Bij een LEGE keten blijft terugvallen juist: die klant heeft niets ingericht en hoort gewoon te
werken. Maar als er rijen STAAN en ze falen allemaal, heeft de klant een verwerker gekozen. Zijn
gegevens dan alsnog naar onze standaardprovider sturen is een wissel van subverwerker die hij
niet heeft goedgekeurd (AVG art. 28 lid 2), en hij merkt er niets van. Een taak die faalt is
zichtbaar en herstelbaar; een taak die stil bij een andere verwerker landt niet.

**Een inhoudsweigering valt NIET door.** `LLMContentFilterError` betekent dat de leverancier de
INHOUD weigert, niet dat het eindpunt stuk is. Doorvallen zou dezelfde tekst bij de volgende
leverancier aanbieden tot er een ja zegt -- een filter omzeilen door het vaak genoeg te vragen.

**Streamen valt door tot het EERSTE stukje.** Daarna niet meer: een aanroeper die het begin van
het ene antwoord en het vervolg van het andere krijgt, aan elkaar geplakt zonder melding, is
slechter af dan een die een fout ziet.

**Ook fouten van ONSZELF vallen niet door** (`AttributeError`, `TypeError`, `KeyError`,
`NameError`, `ImportError`). Een bug hier is geen storing van het eindpunt; de prompt alsnog naar
leverancier 2 en 3 sturen zou een wissel van subverwerker op eigen falen zijn -- precies wat de
alinea hierboven verbiedt -- en die fout zou als storing tellen op de breaker van een gezond
eindpunt. `LLMAuthenticationError` valt WEL door: een ingetrokken sleutel op schakel 1 is juist
waarvoor een keten bestaat.

## 5. De uitgestelde bevinding uit BE-LLM-004 is opgelost

`for_tenant` opent nu zijn eigen databasesessie, kort, en sluit hem VOORDAT de adrescontrole
begint. Die controle doet per rij een naamsopzoeking van maximaal vijf seconden; met een keten
van vier rijen was dat twintig seconden verbindingsbezetting per agenttaak, op een database die
op 40 van de 50 verbindingen zit. `.claude/rules/database.md` verbiedt het met zoveel woorden.

De dienst is daarvoor in twee helften gesplitst: `opgeslagen_rijen()` (alleen database, met het
eerste slot) en `beproef()` (adrescontrole en ontsleuteling, raakt de database niet). `keten()`
blijft bestaan als de combinatie voor wie toch al een sessie openhoudt.

**Wat NIET verschuift is de volgorde.** De controle gebeurt nog steeds voor het eerste verzoek.
Dat is de hele reden dat hij bestaat (DNS-rebinding, BE-LLM-004); hem naar achteren schuiven zou
de verbindingspool redden en het doel weggooien. Er staat een test op die volgorde.

## 6. Wat dit kost, en wat het NIET is

**Koppeling.** `agent_runtime` Ce blijft op 240: de import van `get_db_session` verhuist van
`specialist_base.py` naar `service.py` (waar hij nu hoort, want die opent de sessie), en
`src/core/resilience` zit in de bak `shared` -- de circuit breaker kost dus niets. De plafonds
uit BE-LLM-004 hoefden niet omhoog.

**Wat dit NIET is.** Geen kostenplafond (ADR-026 par. 1.2.2): dat bestaat voor de twin met een
eigen tabel en zeven jaar bewaartermijn; dat aan het agentpad hangen is een eigen knip, en er is
geen klant en dus geen uitgave om te begrenzen. Geen latency hedging (ADR-026 stelt dat zelf
uit). Geen migratie van het chatpad.

## 7. Meting

Alles hieronder is na de Gate 2-ronde opnieuw gedraaid, niet overgenomen uit de eerste versie van
dit document (twee getallen daarin bleken niet na te maken -- zie de reviewnotitie).

```text
tests/unit/llm                                      104 passed
tests/unit/llm + {services,als,agents,security} + ssrf
                                                   1785 passed  (baseline 1724, 0 nieuwe failures)
tests/architecture (drie geraakte bewakers)           6 passed

ruff src/ tests/          All checks passed!
scripts/run_mypy_audit    Total errors: 0  (baseline 0)
python -m pyright         0 errors, 35 warnings
check_any_gate            7110 = 7110
validate_feature_docs     exit 0
agent_runtime             Ce 240, infra 105, auth 17 (gelijk aan BE-LLM-004)
```

### 7.1 Het mutatiebewijs -- 21 mutaties, alle 21 betrapt

Een regel per bewaakt element, zoals `quality-gates.md` eist, met de tegenrichting erbij. Gedraaid
via `scripts/mutation_harness.py` (dus met atomair herstel en een uniek-anker-eis); de werkboom was
achteraf aantoonbaar schoon.

| # | Mutatie | Betrapt door |
|---|---|---|
| K1 | de keten neemt alleen de eerste schakel | `test_valt_rij_1_om_dan_antwoordt_rij_2` |
| K2 | *tegen:* de keten stopt nooit bij de eerste die werkt | `test_bij_een_WERKENDE_eerste_rij_blijft_de_tweede_ongemoeid` |
| K3 | de drempel wordt onbereikbaar (10.000), dus de breaker opent nooit | `test_een_kapotte_rij_wordt_na_de_drempel_OVERGESLAGEN` + het streampad |
| K4 | de breaker-id is weer de klassenaam (de vorm van de twin) | `test_de_breaker_van_tenant_A_raakt_tenant_B_NIET` |
| K5 | een gefaalde keten geeft stil een leeg antwoord | `test_een_volledig_gefaalde_keten_geeft_een_FOUT_en_geen_ander_model` |
| K6 | `serves_mock` kijkt alleen naar de eerste schakel | `test_serves_mock_geldt_voor_de_HELE_keten` |
| ST1 | de breaker omhult weer een LEGE aanroep (de Gate 2-bevinding, letterlijk terug) | `test_de_breaker_werkt_OOK_op_het_streampad` + `test_een_mislukte_stroom_maakt_een_OPEN_breaker_niet_weer_gezond` |
| ST2 | de stroom valt WEL door nadat er al tekst is geleverd | `test_een_storing_NA_het_eerste_stuk_valt_niet_door` |
| ST3 | een lege stroom is weer een stil succes | `test_een_LEGE_stroom_is_een_storing_en_geen_stil_succes` |
| F1 | fouten van ONSZELF lopen weer de keten in | `test_een_fout_van_ONSZELF_gaat_omhoog_...` |
| F2 | *tegen:* alles gaat omhoog, dus de keten bestaat nergens meer voor | `test_een_verlopen_SLEUTEL_valt_wel_door` |
| F3 | een inhoudsweigering valt weer door naar de volgende leverancier | `test_een_inhoudsweigering_gaat_omhoog_...` |
| CF1 | de provider merkt een inhoudsweigering niet meer op | `test_een_geweigerde_inhoud_is_een_EIGEN_fout_en_geen_storing` |
| CF2 | *tegen:* ELKE reden met lege inhoud geldt als weigering | `test_een_ANDERE_reden_met_lege_inhoud_blijft_een_gewone_storing` |
| S1 | de breaker-id draagt de tenant niet | `test_de_breakersleutel_draagt_de_TENANT` |
| S2 | de breaker-id draagt de volgorde niet | `test_twee_rijen_op_DEZELFDE_host_krijgen_toch_hun_eigen_breaker` |
| S3 | `for_tenant` gebruikt weer alleen de eerste rij | idem |
| S4 | de adrescontrole gebeurt weer BINNEN de databasesessie | `test_de_sessie_is_DICHT_voordat_de_adrescontrole_begint` |
| S5 | *tegen:* een lege keten valt nog steeds terug op het platformmodel | `test_een_lege_keten_levert_de_platformstandaard` |
| G1 | `beproef` doet weer databasewerk | `test_beproef_raakt_de_repository_niet` |
| G2 | *tegen:* het databasedeel raakt de repository niet meer | `test_de_databasehelft_gebruikt_de_repository_WEL` |

**Wat G2 onderweg aantoonde.** De eerste versie van die tegenrichting haalde EEN van de drie
`self._repo`-aanroepen uit `opgeslagen_rijen` weg en bleef groen. Dat is juist -- de methode raakt
de repository dan nog steeds -- maar het betekent dat een tegenrichting op een
"gebruikt-hem-wel"-bewaker naar een methode moet met precies EEN aanroep, anders toont hij niets.
Hij staat nu op `toon`.

## 8. Wat de Gate 2-ronde heeft veranderd

Beide reviewers gaven CHANGES_REQUESTED en wezen onafhankelijk van elkaar het STREAMPAD aan. Dat
was de zwaarste bevinding en hij was erger dan gerapporteerd; zelf nagemeten:

```text
breaker OPEN  --2x een lege, altijd-slagende aanroep-->  HALF_OPEN  -->  CLOSED
```

De breaker omhulde op dat pad `await breaker.execute(_niets)` -- een lege aanroep die per
definitie slaagt. Gevolg: de breaker zag daar NOOIT een fout (een kapot eindpunt werd bij elk
verzoek opnieuw geprobeerd), en twee MISLUKTE stromen verklaarden een dood eindpunt weer gezond,
ook voor het gewone pad. Mijn eigen docstring noemde die constructie "de eerlijke tussenvorm".
Dat was onwaar. De breaker omhult nu het openen van de stroom PLUS het eerste stukje, en er staan
vijf stroomtests waar er nul waren.

Verder uit die ronde:

- **De inhoudsfilter-belofte was leeg.** `OpenAICompatibleProvider` -- het enige type dat een
  klantrij kan opleveren -- gooide nooit `LLMContentFilterError`; een weigering kwam als generieke
  fout binnen en ging dus als storing de keten in. Nu leest `_lees_antwoord` `finish_reason`
  VOORDAT hij over de lege inhoud valt.
- **Een lege stroom was een stil succes.** Nul stukjes zonder fout gaf een leeg antwoord en geen
  failover. Dat is nu een storing.
- **`sleutel` betekende twee dingen.** Het veld met de breaker-identificator heette `sleutel`, en
  in deze codebase betekent dat een GEHEIM -- de logbewaker werd er terecht rood van op zes
  onschuldige regels. Hernoemd naar `breaker_id`; dat is de "een woord, een betekenis"-regel uit
  CLAUDE.md toegepast op mijn eigen code.
- **`volgorde` in de breaker-id was ongetest.** De tenant-test gebruikte twee verschillende
  hosts, dus de id's verschilden toch al. Twee rijen op DEZELFDE host (normaal bij Azure of vLLM)
  zouden zonder dat deel een breaker delen -- en dan schakelt het uitvallen van rij 1 rij 2 uit.
- Plus: de nieuwe module in de logbewaker, een bewaker die eist dat `beproef` de repository niet
  raakt, een alleen-lezen venster op de breakertoestanden, en drie verouderde toelichtingen.

**Mutatiebewijs: 11 mutaties in ronde 1, alle betrapt**, tegenrichting groen. Vier daarvan moesten worden
herschreven: drie ankers kwamen tweemaal voor (`generate` en `stream` hadden dezelfde regels) en
een mutatie veranderde alleen een logregel. Dat eerste is opgelost door de breaker op EEN plek
op te halen -- twee identieke ankers betekent dat een mutatie de helft van het gedrag ongemoeid
laat en de test toch groen meldt.

## Trainingssamenvatting

- **Actor:** een agent die namens een tenant een taak uitvoert. Geen menselijke actor; dit pad
  draait in een worker.
- **Voorwaarde:** de tenant heeft een of meer providers laten inrichten en
  `externe_providers_toegestaan` staat op TRUE.
- **Actie:** de agent vraagt om een taalmodel en doet een aanroep.
- **Systeemreactie:** de keten wordt opgehaald (sessie kort open), daarna gecontroleerd en
  ontsleuteld (sessie dicht). De aanroep gaat naar de eerste schakel; faalt die, dan naar de
  volgende. Een schakel die drie keer achter elkaar faalde wordt zestig seconden overgeslagen.
- **Succes:** het antwoord komt van de eerste schakel die werkte; `provider_name` noemt WELKE.
- **Fout:** een schakel die faalt levert een waarschuwing met zijn sleutel, zonder de API-sleutel.
- **Uitzonderingen:** faalt de hele keten, dan komt er een `LLMServiceError` en GEEN terugval op
  het platformmodel -- de klant heeft een verwerker gekozen. Een inhoudsweigering van de
  leverancier valt niet door naar de volgende. Bij een LEGE keten (niets ingericht) geldt de
  platformstandaard wel, met een logregel.

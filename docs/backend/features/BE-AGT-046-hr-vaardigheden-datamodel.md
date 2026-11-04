# BE-AGT-046 -- HR-vaardighedenmodel en de kloofanalyse (ADR-036 OP-26)

Status: APPROVED
Datum: 2026-08-15
ADR: ADR-036 D10 (piloot skillsgaptraining), OP-26

---

## Waarom

De piloot van ADR-036 moest een vaardighedenkloof bepalen. Dat kon niet: er was geen tabel met
vaardigheden, functie-eisen of beoordelingen. De enige HR-tool (`query_hr_database`, BE-AGT-044)
telde koppen per functie uit de RBAC-tabellen. Daarmee kun je zeggen hoeveel mensen een rol
bekleden, niet wat ze missen. OP-26 stond daarom als productbeslissing open.

## Wat er is gebouwd

**Drie tabellen** (`20260815_hr_skills_tables`), alle met `tenant_id NOT NULL` en cascade op de
tenant (ADR-005):

| Tabel | Wat |
| --- | --- |
| `skills` | de catalogus per tenant, uniek op (tenant, naam) |
| `role_required_skills` | welk niveau een functie van een vaardigheid vraagt |
| `employee_skills` | het beoordeelde niveau van een medewerker, met beoordelaar en datum |

Niveaus lopen van 1 tot 5, afgedwongen met een CHECK-constraint. Nul bestaat niet: dat zou
"niet beoordeeld" en "kan het niet" op een hoop gooien, en dat verschil is nu juist waar een
kloofanalyse over gaat.

**Bewust GEEN `employees`-tabel.** Medewerkers zijn gebruikers en functies zijn rollen. Een
tweede waarheid over dezelfde mensen zou de AVG-wisroute moeten dupliceren, en een gemiste
kopie is precies hoe persoonsgegevens blijven staan nadat iemand om verwijdering heeft
gevraagd.

**Een tweede tool: `analyze_skill_gap`.** Per (functie, gevraagde vaardigheid) drie tellingen
die elkaar uitsluiten en optellen tot de bezetting: haalt het, haalt het niet, nooit
beoordeeld. Een eigen tool en geen extra parameter op de bestaande: die heeft een eigen
contract, een eigen risiconiveau en een eigen regel in `PAYLOAD_POLICY`, en een schakelaar die
het antwoordformaat omgooit maakt die drie meerduidig.

## Wat de tool bewust niet doet

Hij geeft geen personen terug. Alles wat een tool retourneert gaat de event bus op en wordt door
het leersubsysteem gepersisteerd; rij-data zou beoordelingen van individuele medewerkers in een
leeropslag zetten. Dat is dezelfde afweging als bij `query_hr_database` (OP-27) en hier
zwaarder: een oordeel over iemands vaardigheid is gevoeliger dan het feit dat hij een rol heeft.
`employee_id` blijft dan ook expliciet geweigerd.

## Wat dit NIET oplost

De tabellen zijn leeg. Waar de gegevens vandaan komen -- import uit een spreadsheet, koppeling
met een HR-systeem, onderhoud in de applicatie -- blijft een productbeslissing. Een lege tabel
geeft hier een eerlijke uitkomst: nul beoordeelden en dus een volledige kloof, geen verzonnen
getal.

**En een randvoorwaarde die vooraf gaat aan echte data.** Zodra hier beoordelingen van echte
medewerkers in staan, beoordeelt het systeem individuele werknemers en wijst het op grond
daarvan training toe. De drie andere HR-skills (`employeesentiment`, `internalmobility`,
`talentacquisition`) staan om die reden op `annex_iii` in hun manifest; `skillsgaptraining` staat
nog op `none`. Die classificatie en de AVG-grondslag moeten geregeld zijn voordat er echte
gegevens in gaan. Losse observatie daarbij: het veld `annex_iii_classification` wordt wel
ingelezen maar nergens in de code gebruikt -- ook niet bij de drie die op hoog risico staan.

## Tenantgrens

Op elke tabel afzonderlijk in de join-conditie, niet alleen in de WHERE. `user_roles` heeft geen
tenantkolom, dus een vervuilde associatierij zou anders gegevens van een andere tenant
binnenhalen. De ADR-004-hook filtert als tweede laag mee; dat de expliciete predicaten niet stil
kunnen verdwijnen wordt getoetst op de GECOMPILEERDE SQL, niet door de hook uit te zetten.
Gewiste gebruikers (AVG art. 17, soft delete) tellen niet mee -- anders houdt een ex-medewerker
een kloof open.

## Trainingssamenvatting

- Actor: de piloot-skill `skillsgaptraining`, namens een ingelogde gebruiker
- Voorwaarde: de tenant heeft vaardigheden, functie-eisen en beoordelingen vastgelegd; de skill
  mag `analyze_skill_gap` volgens zijn manifest en permissieprofiel
- Actie: de skill roept `analyze_skill_gap` aan, eventueel met een filter op functienaam
- Systeemreactie: per functie en gevraagde vaardigheid het gevraagde niveau, de bezetting, en
  hoeveel mensen het halen, niet halen of nooit beoordeeld zijn
- Succes: `success: true` met `gaps`, `gap_count` en de toegepaste paginering
- Fout: `success: false` met een leesbare reden -- een niet-ondersteund filter, een onleesbaar
  paginagetal, of een interne fout zonder SQL of parameters in de melding
- Uitzonderingen: een ontbrekende of onzinnige tenant is een harde fout en geen lege uitkomst;
  een functie zonder bezetting verdwijnt niet uit het antwoord maar rapporteert een volledige
  kloof

## Tests

`tests/unit/tool_broker/test_hr_skill_gap.py` -- 11 tests: de drie categorieen tellen op tot de
bezetting, niet-beoordeeld telt niet als gezakt, een onbezette functie blijft zichtbaar, het
functiefilter werkt, tenantisolatie in twee richtingen (ook via een payload die zijn eigen
tenant probeert te kiezen), gewiste gebruikers vallen weg, elke tabel draagt zijn eigen
tenantpredicaat in de gecompileerde SQL, en drie randgevallen op de argumenten.

Migratie heen en terug bewezen op een verse PostgreSQL: upgrade maakt drie tabellen, downgrade
verwijdert ze, opnieuw upgraden herstelt ze. Exitcode 0 in alle drie de richtingen.

## Gemeten

- 11 nieuwe tests groen; 1451 groen over `tests/architecture`, `tests/unit/tool_broker` en
  `tests/unit/als`
- pyright 0 errors, mypy 0 fouten, ruff schoon
- Any-teller onveranderd op 7891: geen nieuwe `Any`, de query is precies getypeerd
- alembic: precies 1 head

## Bijvangst

`tests/contracts/test_api_contracts.py` verwees nog naar een testklasse die met OP-138 is
verwijderd (F821). Opgeruimd.

De guard `test_tool_policy_matches_the_tools.py` had een hardgecodeerde toolnaam waar een lijst
hoorde: `_VOCABULARY_FROM_CONSTANTS` was decoratief en `_constant_vocabulary()` toetste
`if tool_name != "query_hr_database"`. De tweede tool met dezelfde weigerlijst liep daar
onmiddellijk op vast. De lijst draagt nu de logica en resolvet het pad echt; in beide
richtingen mutatie-getest.

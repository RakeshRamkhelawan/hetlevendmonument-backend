# BE-GOV-023 -- InputGuard: een inhoudswachter op twee van de deuren voor vrije tekst

Datum:  2026-09-22
Branch: develop
Basis:  016a836c

---

## 1. Waarom dit er is

Rakesh vroeg of we de inhoud van vrije tekst kunnen beoordelen voordat er iets mee gebeurt, en of
de Council dat niet zou kunnen. Het antwoord op die tweede vraag is nee, en het waarom is gemeten
in plaats van beredeneerd.

**De Council heeft de capaciteit wel.** De PrivacyOfficer gebruikt `GDPREnforcer.detect_pii`: zes
patronen met echte controlegetallen voor BSN, IBAN en creditcard. Gemeten 2026-09-21 op een vrije
prompt:

```text
"Schrijf een plan voor jan.jansen@klant.test, BSN 123456782, tel 0612345678"
   -> ['email', 'phone', 'bsn']
```

**Maar hij krijgt de inhoud nooit te zien.** Op het agentpad ontvangt hij de toolnaam en de NAMEN
van de argumenten, niet de waarden (BE-AGT-043, ADR-036 OP-25). Dezelfde detector op wat hij
werkelijk binnenkrijgt:

```text
{"tool": "local__llm_generate", "arg_keys": ["prompt"], "ai_disclosure": True}
   -> []
```

Dat is met opzet zo, en de reden is niet weg te nemen door er een officier bij te zetten: alles wat
de Council ziet belandt in `council_decisions` en wordt meegehasht in de ADR-019-keten, die per
ontwerp niet corrigeerbaar of wisbaar is. Vrije tekst daarin botst met AVG art. 16 en 17. Daar komt
bij dat de officieren hun bestuursvlaggen uit diezelfde dict lezen, dus modeltekst daarin laat een
prompt-injectie zijn eigen oordeel meesturen.

**Op het chatpad stond helemaal geen inhoudscontrole.** Gemeten: nul treffers op `detect_pii`,
`sanitize` of een guard in `src/core/copilot/service.py`.

Een wachter die VOOR de Council staat en niets bewaart, heeft geen van beide problemen -- en hij
staat op de betere plek: inhoud die er niet hoort te zijn bereikt de tool en het beslissingsregister
dan helemaal niet, in plaats van dat hij achteraf wordt geredigeerd.

## 2. De deuren: twee bewaakt, zes bekend en onbewaakt

| Deur | Waar | Wat erlangs komt |
|---|---|---|
| Chat | `copilot/service.py::handle_turn` (r. 214) | al het chatverkeer: `handle_turn_stream` delegeert hiernaartoe, en zowel de WebSocket (`api/chat_websocket.py:156`) als de REST-ingang (`api/turn_endpoint.py:86,109`) gaan via die twee. **Een deur, niet drie** |
| Agent | `als/agents/specialist_base.py::_reject_before_council` (r. 271) | de parameters van een tool-actie, vlak voor de Council |

Bewust NIET in deze knip: `submit_proactive_proposal` (r. 320). Die inhoud is systeemgegenereerd
uit waarnemingen, geen vrije invoer van een mens of een model.

**CORRECTIE NA GATE 2: het zijn niet "de twee deuren".** Een reviewer mat nog ZES andere
ingangen waar vrije tekst een taalmodel of de Council bereikt, en de scherpste heb ik zelf
nagemeten: `src/core/api/agentic_flow_endpoints.py:89` zet `request.prompt[:100]` in een
`context_snapshot` en daarmee in het Council-register -- precies het lek waar deze hele wachter
om is gebouwd. Mijn woord "elke" in de naam van de architectuurbewaker was dus onwaar, en dat is
het ergste soort onwaarheid: een bewaker die volledigheid belooft en er twee toetst, blijft voor
altijd groen terwijl de rest open staat.

Die bewaker heet nu `test_deuren_voor_vrije_tekst_hebben_een_wachter.py` en draagt twee lijsten:
de twee BEWAAKTE deuren, en zes BEKENDE ONBEWAAKTE ingangen met datum en reden per regel plus
een staleness-test. Drie van die zes heb ik zelf op regelniveau nagemeten, drie neem ik over van
de reviewer en dat staat er ook zo bij. De lijst is met de hand samengesteld en dus mogelijk
niet compleet -- dat staat er expliciet, want een lijst die volledigheid suggereert is erger dan
een lijst die het toegeeft.

## 3. Wat de wachter doet

Deterministisch, **geen I/O, geen database, geen taalmodel**. Hij hergebruikt
`GDPREnforcer.detect_pii` -- geen tweede patronenlijst, want twee kopieen van dezelfde lijst lopen
uit elkaar (dat kostte op 2026-09-21 al een blokkerende bevinding op `BROKER_INJECTED_KEYS`).

**De blokkeerlijst is na Gate 2 HERZIEN, en dat was de duurste bevinding van de dag.** De
eerste versie blokkeerde op vier categorieen. Gemeten met de echte detector:

```text
ts=1726937461123 duurde te lang              -> GEWEIGERD  (tijdstempel als creditcard)
Version 1.2.3 build 20260922145501           -> GEWEIGERD  (buildnummer)
order 9780306406157 ontbreekt                -> GEWEIGERD  (ISBN)
Open ticket 123456782 graag                  -> GEWEIGERD  (ticketnummer haalt de elfproef)
run_id 1726937461123 is vastgelopen          -> GEWEIGERD
Het factuurnummer is 2026-0000-1234-5678     -> GEWEIGERD
```

Zes van de zes. Twee oorzaken, allebei echt:

1. **`credit_card` had geen controlegetal.** Het patroon is elke reeks van 13-20 cijfers, en
   `_CHECKSUM_VALIDATORS` in `gdpr_enforcer.py` had wel `bsn` en `iban` maar niet
   `credit_card` -- terwijl die module twaalf regels hoger zelf opschrijft dat een kale
   patroontreffer voor dit soort types nooit volstaat. Dat was dus een defect volgens zijn
   eigen contract, niet een beleidskeuze. Er staat nu een Luhn-validator (`stdnum.luhn`, met
   een wrapper omdat `stdnum` niet strookt met streepjes en spaties).
2. **De elfproef alleen is te zwak om op te blokkeren.** Gemeten over 20.000 willekeurige
   negencijferige nummers: **1823 (9,12%)** halen hem. In een systeem vol ticket-, order- en
   runnummers is dat ongeveer een op de elf. `bsn` blokkeert daarom alleen nog MET een
   contextwoord ernaast (`bsn`, `burgerservicenummer`, `sofinummer`); zonder dat is het een
   melding.

| Categorie | Wat er gebeurt | Waarom |
|---|---|---|
| `iban` | GEBLOKKEERD | mod-97-controlegetal, vrijwel geen valse positieven |
| `credit_card` | GEBLOKKEERD | sinds 2026-09-22 met Luhn; zonder dat was het onbruikbaar |
| `bsn` | GEBLOKKEERD met contextwoord, anders GEMELD | de elfproef alleen laat 9,12% van willekeurige negencijferige nummers door |
| `ssn` | GEMELD | Amerikaans formaat zonder controlegetal; in een Nederlands HR-product vrijwel altijd ruis |
| `email`, `phone` | GEMELD | "stuur de uitnodiging naar jan@klant.test" is gewoon werk. Die weigeren maakt het product onbruikbaar, en een wachter die in de weg loopt wordt uitgezet -- dan heb je niets |

**Blokkeren mag alleen wat bewijsbaar is.** Dat is de regel die hieruit volgt en die nu in de
moduledocstring staat.

Het onderscheid tussen melden en blokkeren staat in `src/core/config/input_guard_rules.yml`:
bij een AI-verordening-audit moet je kunnen laten zien WAT je tegenhoudt en sinds wanneer. Een
regel in een bestand is te diffen, te dateren en aan een auditor te laten zien; "het model weet
het" is geen antwoord.

**Met EEN eerlijke beperking, gevonden in Gate 2.** De vloer (`iban`, `credit_card`) staat ook in
de code (`_VLOER`) en de code unieert hem onvoorwaardelijk -- het bestand kan hem dus alleen
VERBREDEN, niet versmallen. Een regel op `enabled: false` zetten heeft voor die twee geen effect;
gemeten. De reden dat de vloer in code staat is echt (een deploytypfout mag hem niet stil
wegnemen, en dat is de vorm waarin een bewaker verdwijnt), maar mijn eerste versie suggereerde
dat het onderscheid volledig in het bestand te wijzigen was, en dat was onwaar. Een
compliance-document dat gezaghebbend lijkt maar inert is, beeindigt een onderzoek in plaats van
er een te beginnen.

Gevolg dat een klant moet weten: wie IBAN's wel wil toestaan -- in een salarisproduct het meest
waarschijnlijke legitieme veld -- kan vandaag alleen de HELE wachter uitzetten. Dat is een echte
beperking en geen ontwerpkeuze om trots op te zijn.

## 3b. Wat deze wachter NIET is -- en dat hoort vooraan, niet in een voetnoot

Hij is een vloer onder IDENTIFICATOREN, geen filter op persoonsgegevens. Gemeten:

```text
Jan Jansen functioneert onder de maat en krijgt een verbetertraject   -> DOOR
Medewerker zit met een burn-out en is zes weken thuis                 -> DOOR
Salaris wordt verhoogd naar 82000 euro per jaar                       -> DOOR
Adres: Dorpsstraat 12, 1234 AB Amsterdam                              -> DOOR
Zij is zwanger en meldt zich in maart af                              -> DOOR
```

Vijf van de vijf, en het zijn precies de gegevens waar de AVG het strengst is (art. 9). Een
patroon vindt vormen, geen betekenis, en in een HR-product is de payload die telt proza over
mensen. Een Gate 2-reviewer vatte het scherp samen: de wachter blokkeert wat geen
persoonsgegeven is en laat door wat het wel is. Na de herziening hierboven blokkeert hij niet
langer het verkeerde, maar het tweede deel blijft staan.

Dat is geen tekortkoming die met een extra patroon te repareren is. Het is precies waarom de
redenerende laag de volgende knip is, en waarom die alleen mag ESCALEREN: wat een patroon niet
kan zien, kan alleen iets dat de betekenis begrijpt -- en dat iets mag nooit de poort openen.

**Nog een gemeten beperking**, die ik vond doordat een eigen test erop viel: een identificator
die met een liggend streepje aan een woord vastzit, matcht het patroon niet
(`iban_NL91ABNA0417164300` -> niets, `iban NL91...` en `iban:NL91...` -> wel). Dat komt van de
`\b` in het patroon; een `_` is een woordteken. Niet gerepareerd: het patroon aanpassen raakt
ook de PrivacyOfficer en `redact_pii`, en dat is een eigen wijziging met eigen bewijslast.

## 4. Wat hij NOOIT prijsgeeft

Het oordeel draagt een CATEGORIE en een verwijzing, nooit de gevonden tekst -- niet in het
antwoord en niet in het log. Anders lekt de wachter zelf precies wat hij tegenhield. Dat is geen
theoretisch bezwaar: op 2026-09-21 moest exact die fout in `hr_registry._schedule_training`
gerepareerd worden, waar een repository-melding de ontvangen naam meecitieerde.

De verwijzing is **willekeurig en niet uit de inhoud afgeleid**. Een hash van de tekst zou een
stabiele aanwijzing naar die persoon zijn en daarmee zelf een persoonsgegeven; dan lekt de
verwijzing alsnog, alleen trager. Vastgelegd met een test die twee keer dezelfde tekst beoordeelt
en eist dat de verwijzingen verschillen.

Het log krijgt: categorie, herkomst (welke deur), tenant, verwijzing. Dat is het snijpunt van
AI Act art. 12 (er moet een log zijn) en AVG art. 5 (minimaliseer): het bewijst dat de wachter
werkte zonder zelf een opslag te worden van wat hij tegenhield.

## 5. Wat het juridisch onderzoek opleverde, en waar het in de bouw landt

Vier open twijfels, twee ervan niet uit de code te beantwoorden. Opgezocht:

- **De wachter is zelf een verwerking.** Elk bericht lezen om het te beoordelen is het verwerken
  van gegevens van een medewerker. De EDPB stelt dat toestemming in een arbeidsverhouding in
  principe geen geldige grondslag is; het draait dus op gerechtvaardigd belang, en in Nederland is
  de ondernemingsraad in beeld bij monitoringtechnologie (AVG art. 88). Wij zijn bewerker, de klant
  is verantwoordelijke. **Landt als:** de wachter kan per tenant UIT, standaard AAN, en die
  uitzondering staat als expliciete regel met datum in het regelbestand in plaats van als stille
  vlag in een database. Een wachter die niet uit kan, maakt onze klant niet-compliant.
- **Een redenerende wachter is zelf een AI-systeem** en sleept als veiligheidscomponent van een
  hoog-risicosysteem die verplichtingen mee. **Landt als:** geen taalmodel in het beslispad, met
  een architectuurbewaker die de imports van de module op de AST toetst. Een redenerende laag mag
  er later bovenop met EEN richting -- alleen escaleren, nooit versoepelen -- zodat een injectie
  die die laag overtuigt de deur niet kan openen.
- **Een blokkade moet te overrulen zijn** (AI Act art. 14: mensen moeten kunnen ingrijpen; voor
  filtering met veel volume mag dat achteraf en op uitzonderingsbasis, maar de bevoegdheid moet
  echt bestaan). **Landt als:** de gebruiker krijgt de categorie te zien en kan het opnieuw stellen
  -- hij wordt niet van de dienst uitgesloten. Op het agentpad loopt de route via het bestaande
  HITL-ticket. Er is dus geen muur zonder deur. Een formele vrijgaveroute per geweigerde invoer is
  een eigen knip en is niet vooruit gebouwd.
- **Wat mag er gelogd worden** -- zie paragraaf 4.

**En een vondst die belangrijker is dan deze wachter:** het Hof heeft in de SCHUFA-zaak bevestigd
dat een stempel-review de keten van "uitsluitend geautomatiseerd" NIET verbreekt (AVG art. 22). Onze
HITL-poort rust op een mens die goedkeurt; kan die niet werkelijk beoordelen, dan blijft het besluit
juridisch geautomatiseerd. Dat maakt de dagteller en het overzicht voor de goedkeurder uit de brief
van 2026-09-21 geen verbetering meer maar de voorwaarde waaronder die poort betekenis heeft. Staat
apart, komt direct hierna.

**Wat het onderzoek NIET beslecht**, en dat hoort bij een jurist: valt het toewijzen van een
training onder "aanmerkelijk gevolg" in art. 22? De genoemde voorbeelden zijn een geweigerde
kredietaanvraag en e-recruitment zonder menselijke tussenkomst; een trainingstoewijzing ligt
daarbij in de buurt maar staat er niet, en ik vond geen rechtspraak die het beslecht. Ik bouw alsof
het eronder valt -- dat is de veilige kant en kost niets extra.

## 6. De prijs die ik expliciet neem: twee koppelingsplafonds omhoog

Twee nieuwe randen `agent_runtime -> governance` (de twee deuren, allebei
`from src.core.governance.input_guard import beoordeel`):

| Bewaker | Was | Nu | Gemeten |
|---|---|---|---|
| `test_dsm_008_reclassification.py` (Ce-ratel) | 234 | 236 | `I = 236/(236+201) = 0,5400` |
| `test_dsm006_ar_governance_fan_out.py` (deze rand) | 8 | 9 | het gemeten aantal, zonder buffer |

De ECHTE architectuurgrens is `I <= 0,55` en die breekt bij deze Ca pas op Ce=245 -- er blijft dus
ruimte. Beide ophogingen zijn een besluit met de reden in de docstring, geen bijvangst.

**Overwogen en niet gedaan:** de wachter in de `shared`-bak zetten, die niet meetelt in de
fan-out. Dan waren beide getallen gelijk gebleven, en precies daarom is het verkeerd: een wachter
die AVG-categorieen toetst is een governance-zorg en hoort naast `gdpr_enforcer.py`, wiens detector
hij hergebruikt. Hem elders parkeren om de meter te ontwijken is de optimalisatie waar de docstring
van `scan_module` zelf voor waarschuwt.

**Bijvangst bij het natrekken van die tweede bewaker, en het is een echte:** zijn opsomming telde
acht randen terwijl `scan_module` er negen mat -- die twee liepen dus al uiteen voordat de
InputGuard erbij kwam. Bij het nazoeken bleek waarom een eigen AST-telling dat niet kan
reproduceren: `SOURCE_DIRS['governance']` is een hardgecodeerde lijst van LOSSE BESTANDEN, dus een
nieuw bestand in `src/core/governance/` staat daar niet in en valt bij zo'n telling buiten de boot
(eigen telling 11 inclusief `TYPE_CHECKING`, `scan_module` 9). Dat staat nu in de docstring van
die bewaker; welke rand precies ontbreekt in de opsomming is NIET vastgesteld.

## 7. Meting

```text
python -m pytest tests/unit/governance/test_input_guard.py -q        13 passed
python -m pytest tests/unit/copilot/test_service.py -q               22 passed (20 + 2 nieuw)
tests/architecture/test_elke_deur_..._inhoudswachter.py               3 passed
gerichte regressie (als + copilot + governance + architecture, -n 4)  3054 passed, 0 failed

python -m ruff check src/ tests/ scripts/                             All checks passed!
python scripts/run_mypy_audit.py                                      Total errors: 0
python -m pyright                                                     0 errors, 35 warnings
python scripts/check_any_gate.py --mode acknowledged                  Baseline 7111; gemeten 7111
```

Handmatig gemeten gedrag, dat nu een permanente test is
(`TestInputGuardOpDeChatdeur`): een chatbericht met een geldig BSN wordt geweigerd VOORDAT het
taalmodel en de Council worden aangeraakt (`get_action` en `deliberate` zijn niet awaited), de
gebruiker hoort de categorie, en het BSN staat niet in het antwoord. Een gewone vraag bereikt het
taalmodel wel -- zonder die tegenrichting zou "weiger alles" een geldige oplossing zijn.

### Mutatiebewijs: 12 mutaties, alle betrapt

Met `scripts/mutation_harness.py`, tegenrichting groen. Elke mutatie in de productiecode of de
configuratie, nooit in een test.

| Mutatie | Betrapt door |
|---|---|
| de chatdeur roept de wachter niet meer aan | de deurenbewaker, met die deur in de melding |
| de agentdeur roept de wachter niet meer aan | idem -- twee APARTE mutaties, want een bewaker die beide deuren in een assertie propt kan groen blijven op de ene |
| de aanroep wordt een comment | idem (de AST ziet geen comment -- dit is de mutatie waarop een tekstzoekactie groen zou blijven) |
| de gevonden tekst als extra "categorie" in de melding | `test_de_reden_bevat_de_gevonden_tekst_niet` |
| de gevonden tekst in de logregel | `test_het_log_bevat_de_gevonden_tekst_niet` |
| de verwijzing als hash van de inhoud | `test_de_verwijzing_is_niet_uit_de_inhoud_afgeleid` |
| fail-open in plaats van fail-closed | `TestFailClosed` |
| de vloer weg bij een ontbrekend regelbestand | `test_de_vloer_geldt_ook_zonder_regelbestand` |
| de hoofdschakelaar standaard UIT | `test_standaard_staat_hij_aan` |
| de tenant-uitzondering genegeerd | `test_een_uitgezette_tenant_wordt_niet_beoordeeld` |
| weiger ALLES (tegenrichting) | `TestWatErDoorGaat` -- zonder deze is "weiger alles" geldig |
| een taalmodel-import in het beslispad | `TestGeenTaalmodelInHetBeslispad` |

**Twee mutaties moesten worden herschreven, en dat is leerzaam.** De eerste poging om de tekst in
de MELDING te lekken bleef groen -- terecht: `Oordeel` bewaart de tekst helemaal niet, dus `reden`
kan hem per constructie niet prijsgeven. De realistische regressie is dat iemand de waarde "voor
de duidelijkheid" meegeeft, en zo herschreven werd hij wel betrapt. De tweede was een anker dat
drie keer voorkwam (`enabled: true` staat ook per regel in de YAML) -- het harnas weigerde dat
zelf, wat precies zijn nut is.

## 8. Wat NIET in deze knip zit

- **De redenerende laag** voor wat een patroon niet kan zien ("medewerker X zit met een burn-out"
  is een gezondheidsgegeven in gewone taal, en geen patroon haalt dat eruit). Eerst de
  deterministische vloer; de laag erbovenop is een eigen besluit met een eigen bewaker op de
  richting.
- **De dagteller op HIGH-goedkeuringen** (het SCHUFA-punt). Komt direct hierna; hij heeft een
  scherm voor de goedkeurder nodig om waarde te hebben en dat is een tweede oppervlak.
- **`local__llm_generate` vrijgeven.** Dat was de aanleiding voor dit hele gesprek; nu de wachter
  er staat is die afweging opnieuw te maken, maar hij is nog NIET gemaakt.
- **Een lengtegrens op de beoordeelde tekst.** De detector loopt regexen over de hele string; bij
  een zeer lang chatbericht is dat werk dat niemand heeft begroot. Niet gemeten, dus niet geclaimd
  als probleem en ook niet als niet-probleem.
- **Geneste waarden op het agentpad.** De lus beoordeelt alleen `isinstance(waarde, str)`; een
  string in een geneste dict of lijst wordt vandaag niet gelezen. Dat is aan Gate 2 voorgelegd als
  expliciete vraag.

---

## 9. Trainingssamenvatting

**Flow 1 -- een gebruiker zet een BSN in de chat**

- Actor: een ingelogde gebruiker van een tenant waarvoor de wachter AAN staat (de standaard)
- Voorwaarde: geen; de wachter staat op de eerste regel van `handle_turn`
- Actie: `POST /api/v1/copilot/turn` met `{"message": "Plan een training voor BSN 123456782"}`
- Systeemverwerking: de wachter plat het bericht EN de context tot een doorzoekbare tekst
  (afgekapt op 20.000 tekens), vindt de categorie `bsn` MET een contextwoord ernaast, logt
  categorie + herkomst + tenant + een willekeurige verwijzing, en keert terug VOORDAT
  `_augment_context`, het taalmodel en de Council zijn aangeraakt
- Succesrespons: n.v.t. -- dit pad weigert
- Foutrespons: `verdict="blocked"`, `message` bevat de categorie en de verwijzing in de taal van
  de gebruiker (`nl` of `en`), en NIET het BSN. `decision_id` is gevuld, zodat het recht op
  uitleg blijft werken
- Uitzonderingen: hetzelfde getal ZONDER contextwoord gaat door met een melding (een
  ticketnummer mag geen chatbericht blokkeren); staat de wachter voor deze tenant uit, dan gaat
  alles door; faalt de wachter zelf, dan weigert hij met categorie `onbeoordeelbaar`

**Flow 2 -- een agent zet een IBAN in een geneste toolparameter**

- Actor: de piloot-skill `skillsgaptraining`, met een verantwoordelijke mens eraan gekoppeld
- Voorwaarde: de tool staat niet op de harde denylist en er IS een initiator (de eerste twee
  weigergronden van `_reject_before_council`)
- Actie: `TOOL_CALL: schedule_training {"employees": [{"iban": "NL91ABNA0417164300"}]}`
- Systeemverwerking: de HELE `params` gaat door de wachter, inclusief geneste dicts, lijsten en
  sleutelnamen; de categorie `iban` blokkeert op het mod-97-controlegetal
- Succesrespons: n.v.t.
- Foutrespons: `_reject_before_council` geeft een reden met de categorie en de verwijzing terug;
  `act()` zet de uitvoering op `GEBLOKKEERD`. De Council wordt NIET geraadpleegd en er komt geen
  HITL-ticket, dus de rauwe waarde bereikt `hitl_tickets.payload` niet
- Uitzonderingen: een gewone leestool-payload (`{"role": "Engineer", "limit": 50}`) gaat door;
  een getal dat de elfproef haalt zonder contextwoord ook

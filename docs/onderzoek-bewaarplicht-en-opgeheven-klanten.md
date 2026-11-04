# Onderzoek: wettelijke bewaarplicht en opgeheven klanten

Datum: 2026-10-12. Geen juridisch advies; een jurist moet de conclusie toetsen (zie "Wat onzeker is").

Labels:
- **A**: de tekst van de primaire bron is in dit onderzoek zelf gelezen.
- **B**: een secundaire bron (samenvatting, artikeltekst via een niet-officiële site, vakblad).
- **C**: niet gevonden, of het is mijn interpretatie.

## Kern in vijf zinnen

1. De wettelijke bewaarplichten (fiscaal 7 jaar, BW 2:24, HR-termijnen) liggen bij de **klant** als ondernemer en werkgever, **niet bij SanskritiSetu**. Wij zijn verwerker.
2. Als verwerker moeten wij na het einde van het contract alles **teruggeven of wissen, naar keuze van de klant** (AVG art. 28 lid 3 sub g). Wij mogen alleen langer bewaren als het recht ons dat **zelf** verplicht.
3. Na opheffing of faillissement verdwijnt de bewaarplicht van de klant niet. Ze gaat naar een **bewaarder** (BW 2:24) of naar de **curator** (Faillissementswet). Wissen vóór die is aangewezen en heeft kunnen ophalen is riskant.
4. Gegevens die echt geanonimiseerd zijn, vallen buiten de AVG (overweging 26). Maar een auditlog met namen, gebruikers-ID's of vrije tekst is zelden echt anoniem.
5. De bewaarplichten voor logs uit de AI-verordening (6 maanden en 10 jaar) gelden alleen voor **hoog-risico**-AI. Ze gaan pas in op **2 december 2027** (bijlage III). Of ons HR-pakket hoog-risico is, moet een jurist beoordelen.

---

## 1. Fiscale bewaarplicht, en wat er gebeurt na ontbinding

**AWR art. 52** (A). Bron: https://wetten.overheid.nl/BWBR0002320/2026-01-01
- Lid 1: de **administratieplichtige** (de ondernemer zelf) voert een administratie en bewaart de "boeken, bescheiden en andere gegevensdragers".
- Lid 4: de bewaartermijn is **zeven jaar**.
- Lid 5: de gegevens mogen naar een andere gegevensdrager. Ze moeten dan wel juist en volledig blijven en de hele bewaartijd binnen redelijke tijd leesbaar zijn.
- **Wie draagt de plicht:** de klant. De wet noemt geen leverancier en geen verwerker (A voor de tekst, C voor de toepassing op SaaS). Een SaaS-leverancier is een hulpmiddel waarmee de klant aan zijn plicht voldoet. Daaruit volgt: de klant moet bij vertrek een **leesbare export** kunnen krijgen (lid 5).
- Welke stukken bij ons: facturen en aanmaningen (debiteuren), bonnen en het btw-concept, loon- en HR-gegevens voor zover ze fiscaal van belang zijn. Of een concept (bijvoorbeeld een btw-concept) zelf onder de plicht valt, of alleen de vastgestelde aangifte: C.

**BW 2:24** (A). Bron: https://wetten.overheid.nl/jci1.3:c:BWBR0003045&boek=2&titeldeel=1&artikel=24
- De boeken, bescheiden en gegevensdragers van een ontbonden rechtspersoon worden **zeven jaar bewaard nadat hij heeft opgehouden te bestaan**.
- De **bewaarder** wordt aangewezen in deze volgorde: door de statuten, door de algemene vergadering, of (bij een stichting) door het bestuur. Ontbreekt een bewaarder en weigert de laatste vereffenaar, dan wijst de kantonrechter er een aan.
- De bewaarder meldt binnen acht dagen zijn naam en adres aan het handelsregister.
- **Mag de leverancier dan nog wissen?** De wet legt geen plicht bij de leverancier (C). In de praktijk wordt de bewaarder de partij die namens de klant de gegevens terugvraagt.
  - Wie de boeken van een opgeheven klant wist voordat de bewaarder ze heeft kunnen krijgen, maakt het de bewaarder onmogelijk zijn wettelijke plicht na te komen. Dat is een aansprakelijkheidsrisico (C).
  - Advies: eerst teruggeven of aanbieden, met een termijn. Pas daarna wissen.

## 2. Faillissement

**Faillissementswet art. 92, 105a en 105b** (B). Bronnen: zoekresultaat met de wetstekst, plus https://www.accountancyvanmorgen.nl/2024/03/27/belastingadvies-en-administratiekantoor-moet-alsnog-loonadministatie-aan-curator-overdragen/
- De curator neemt de administratie direct in bewaring (art. 92).
- De gefailleerde geeft de administratie volledig en ongeschonden af, met de middelen om haar leesbaar te maken (art. 105a).
- **Art. 105b:** een **derde** die de administratie van de gefailleerde in de uitoefening van zijn bedrijf onder zich heeft, moet die op verzoek volledig en ongeschonden aan de curator ter beschikking stellen, met de middelen om haar leesbaar te maken.
- Gevolg (C):
  - Een SaaS-leverancier valt zeer waarschijnlijk onder "derde" in art. 105b.
  - **Wissen na een faillissement zonder de curator te benaderen is riskant.** De curator treedt op voor de klant en is dus ook de partij die de keuze "teruggeven of wissen" uit AVG art. 28 maakt.
  - Of de leverancier zijn vordering (onbetaalde facturen) mag gebruiken om de gegevens achter te houden: niet onderzocht (C).

## 3. AVG

Bron (A): https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:32016R0679

- **Art. 5 lid 1 sub e (opslagbeperking):** persoonsgegevens worden "niet langer dan noodzakelijk" bewaard in een vorm waarin mensen te herkennen zijn.
- **Art. 17 lid 3:** het recht op wissen geldt niet voor zover verwerking nodig is:
  - sub b: om een wettelijke plicht na te komen "die op de verwerkingsverantwoordelijke rust";
  - sub e: voor het instellen, uitoefenen of onderbouwen van een rechtsvordering.
- **Art. 28 lid 3 sub g:** de verwerker moet "na afloop van de verwerkingsdiensten, naargelang de keuze van de verwerkingsverantwoordelijke, alle persoonsgegevens wist of deze aan hem terugbezorgt, en bestaande kopieën verwijdert, tenzij opslag van de persoonsgegevens Unierechtelijk of lidstaatrechtelijk is verplicht".
- **Art. 5 lid 2 en art. 30 (verantwoording):** de verantwoordelijke moet kunnen aantonen dat hij zich aan de AVG houdt. Art. 30 lid 2 eist van de verwerker een register van de verwerkingen. Dat register gaat over **soorten** verwerking, niet over het auditlog zelf (de tekst van art. 30 is niet apart nagelezen: B/C).
- **Overweging 26:** de AVG geldt niet voor anonieme gegevens. Bij de vraag of iemand te herkennen is, tellen alle middelen waarvan redelijkerwijs te verwachten is dat ze gebruikt worden.

**Mag een verwerker het auditlog na het einde van het contract bewaren?** (C)
- De uitzondering in art. 28 vraagt een wettelijke **bewaarplicht** van de verwerker zelf. Die is voor een klant-auditlog niet gevonden. Art. 17 lid 3 sub b gaat over plichten van de **verantwoordelijke**, niet van de verwerker.
- Bewaren "voor het geval er een geschil komt" maakt van SanskritiSetu op dat punt zelf een **verwerkingsverantwoordelijke**. Dan is een eigen grondslag nodig: gerechtvaardigd belang (art. 6 lid 1 sub f) met een belangenafweging, een korte termijn en alleen de gegevens die nodig zijn. Dat kan, maar het moet in de verwerkersovereenkomst staan en een jurist moet het toetsen.
- **Geanonimiseerd bewaren** (geen gebruikers-ID's, namen of vrije tekst; alleen tijdstip, soort handeling, uitkomst) valt buiten de AVG als het echt anoniem is. Bij een tenant met 1 tot 5 medewerkers is een handeling vaak alsnog tot een persoon te herleiden.
  - **Pseudonimiseren** (ID's hashen) is NIET anoniem. Gepseudonimiseerde gegevens blijven persoonsgegevens (overweging 26).
  - Een SHA-256-hashketen over de oude regels blijft na anonimiseren alleen controleerbaar als de keten op de geanonimiseerde inhoud opnieuw wordt opgebouwd (C, techniek).

## 4. HR-gegevens

Deze plichten liggen bij de **werkgever**, dus bij de klant.

| Gegeven | Termijn | Bron | Label |
|---|---|---|---|
| Loonadministratie | 7 jaar | AWR art. 52 lid 4 | A |
| Kopie identiteitsbewijs | 5 jaar na het einde van het jaar waarin het dienstverband eindigde | Wet op de loonbelasting / Wet arbeid vreemdelingen. Wetstekst niet zelf gelezen; via https://www.mkbservicedesk.nl/administratie/personeelsadministratie/bewaartermijn-personeelsdossier-dit-zijn-de-regels | B |
| Verzuimgegevens | geen wettelijke termijn. Gebruikelijk en door de AP aangeraden: max. 2 jaar na het einde van het dienstverband | idem; pagina van de AP niet zelf gelezen | B |
| Overig personeelsdossier (vaardigheden, opleidingen, beoordelingen) | geen vaste termijn; "niet langer dan nodig" (AVG art. 5 lid 1 sub e). Gebruikelijk: 2 jaar na uitdienst | AVG + praktijk | A/C |
| Sollicitanten | 4 weken na de procedure, of 1 jaar met toestemming | praktijk en AP-richtlijn, niet zelf gelezen | C |

## 5. AI-verordening (Verordening (EU) 2024/1689)

Artikelteksten gelezen via https://artificialintelligenceact.eu (B). Officiële tekst: https://eur-lex.europa.eu/legal-content/NL/TXT/?uri=CELEX:32024R1689 (deze pagina was te groot om de artikelen eruit te halen).

- **Art. 12:** een hoog-risico-systeem moet technisch automatisch logs vastleggen.
- **Art. 18:** de **aanbieder** bewaart de technische documentatie, de documentatie van het kwaliteitssysteem en de EU-conformiteitsverklaring **10 jaar** nadat het systeem op de markt is gebracht. De lidstaten regelen wat er gebeurt bij faillissement van de aanbieder. Het gaat om documentatie over het systeem, niet om klantgegevens.
- **Art. 19:** de **aanbieder** bewaart de automatische logs die onder zijn controle staan, passend bij het doel en **minstens 6 maanden**, tenzij ander recht iets anders bepaalt (met name het gegevensbeschermingsrecht).
- **Art. 26 lid 6:** de **gebruiksverantwoordelijke** (de klant) bewaart de logs onder zijn controle eveneens minstens 6 maanden.
- **Art. 73:** de aanbieder meldt ernstige incidenten aan de markttoezichthouder. De tekst is niet zelf gelezen (C voor de details).
- **Ingangsdatum:**
  - Volgens de geraadpleegde bronnen is de Digitale omnibus over AI op **24 juli 2026** in het Publicatieblad verschenen (B). Bron: https://www.aiactblog.nl/nl/posts/digital-omnibus-uitstel-high-risk-december-2027 en https://www.partena-professional.be/nl/node/22570
  - De plichten voor hoog-risico-systemen uit **bijlage III** gelden vanaf **2 december 2027**, die uit **bijlage I** vanaf **2 augustus 2028**.
  - Het nummer "2026/1744" heb ik niet kunnen bevestigen (C).
- **Geldt het voor ons?** (C)
  - SanskritiSetu brengt het systeem op de markt en is daarmee **aanbieder**. De klant is de **gebruiksverantwoordelijke**.
  - Debiteuren en btw lijken geen bijlage-III-gebruik.
  - **HR kan wel hoog-risico zijn.** Bijlage III punt 4 noemt AI voor beslissingen over werkrelaties, toewijzing van taken en het monitoren of evalueren van prestaties. Vaardigheden, opleidingen en reskilling komen daar dichtbij.
  - Is het HR-pakket hoog-risico, dan moet SanskritiSetu de logs ook na het vertrek van een klant **minstens 6 maanden** bewaren. Dat is dan precies een plicht uit "Unierecht" zoals bedoeld in AVG art. 28 lid 3 sub g.

## 6. Overige plichten

- **Wwft:** SanskritiSetu is geen meldingsplichtige instelling. Het platform doet geen dienstverlening als accountant, belastingadviseur of trustkantoor (C, niet onderzocht).
- **Eigen boekhouding van SanskritiSetu:** onze eigen facturen aan klanten, contracten en betalingen bewaren wij **7 jaar** (AWR art. 52, A). Dat is onze eigen plicht, als verantwoordelijke. Klantnaam en contactpersoon op die facturen blijven dus staan, ook na opheffing van de klant.
- **NIS2 / Cyberbeveiligingswet:** niet onderzocht. Of SanskritiSetu onder de reikwijdte valt (omvang, sector "digitale aanbieders"/"ICT-dienstbeheer") is open (C).

---

## Overzicht

| Gegevenssoort | Bewaarplicht | Termijn | Wie | Bron | Label |
|---|---|---|---|---|---|
| Administratie van de klant (facturen, aanmaningen, bonnen, btw) | ja | 7 jaar | klant (ondernemer) | AWR 52 lid 1 en 4 | A |
| Administratie van een ontbonden klant | ja | 7 jaar na ophouden te bestaan | aangewezen bewaarder | BW 2:24 | A |
| Administratie van een failliete klant | afgeven aan de curator | tijdens het faillissement | derde (wij) op verzoek van de curator | Fw 105b | B |
| Loonadministratie | ja | 7 jaar | klant (werkgever) | AWR 52 | A |
| Kopie identiteitsbewijs | ja | 5 jaar na het jaar van uitdienst | klant | Wet LB / Wav | B |
| Verzuim | nee (maximum) | max. ca. 2 jaar na uitdienst | klant | AP-richtlijn | B |
| Persoonsgegevens bij ons als verwerker, na het contract | wissen of teruggeven, naar keuze van de klant | einde dienst | SanskritiSetu | AVG 28 lid 3 sub g | A |
| AI-logs van een hoog-risico-systeem | ja | minstens 6 maanden | aanbieder (wij) en gebruiksverantwoordelijke (klant) | AI-verordening 19 en 26 lid 6 | B |
| Technische documentatie van een hoog-risico-systeem | ja | 10 jaar | aanbieder (wij) | AI-verordening 18 | B |
| Onze eigen facturen aan klanten | ja | 7 jaar | SanskritiSetu | AWR 52 | A |

## Conclusie en aanbeveling

**(a) Het auditlog van een opgeheven klant**

Aanbeveling, in deze volgorde:
1. **Teruggeven.** Bied een volledige export aan de bevoegde partij: de klant, de bewaarder (BW 2:24) of de curator (Fw 105b). Geef een redelijke termijn.
2. **Daarna verwijderen** van alle persoonsgegevens.
3. Bewaar alleen een **echt anoniem** restant: aantallen, soorten handelingen, tijdstippen, zonder gebruikers-ID's of vrije tekst. Of bewaar niets.

Juridische reden: wij zijn verwerker. Art. 28 lid 3 sub g laat ons alleen langer bewaren als het recht **ons** daartoe verplicht. Zo'n plicht is niet gevonden, behalve mogelijk de AI-verordening voor hoog-risico-logs (minstens 6 maanden, vanaf december 2027).

Bewaren **met** persoonsgegevens "voor het geval dat" vraagt een eigen grondslag, en dan worden wij op dat punt zelf verantwoordelijke. Doe dat alleen als het in de verwerkersovereenkomst staat en met een korte, vaste termijn.

**(b) Meldingen van AI-incidenten**

Dit zijn **onze eigen** gegevens als aanbieder, geen klantadministratie. Bewaar ze, zonder persoonsgegevens waar dat kan. Leg ze vast bij de documentatie uit art. 18 (10 jaar is een veilige bovengrens).

Of art. 73 voor ons geldt, hangt af van de vraag of er hoog-risico-AI in zit.

**(c) Facturen en boekhouding van de klant in ons systeem**

De bewaarplicht ligt bij de klant, of bij zijn bewaarder of curator. **Niet wissen voordat die de kans heeft gehad een leesbare export op te halen.** Daarna wissen.

Wij hoeven ze niet zelf 7 jaar te bewaren. Wel blijven onze **eigen** facturen aan die klant 7 jaar staan.

## Wat onzeker is, en wat een jurist moet toetsen

1. Is het HR-pakket (vaardigheden, opleidingen, termijnen, verzuim) hoog-risico volgens bijlage III punt 4? Dat bepaalt of art. 12, 19 en 73 voor ons gelden.
2. Mag SanskritiSetu na het contract een auditlog met persoonsgegevens bewaren op grond van gerechtvaardigd belang (rechtsvorderingen)? Hoe lang, en hoe leggen we dat vast in de verwerkersovereenkomst?
3. Hoe lang moeten wij wachten op een bewaarder of curator die niet reageert, en mogen we dan wissen? Er is geen wettelijke termijn gevonden.
4. Is ons "geanonimiseerde" auditlog bij heel kleine tenants echt anoniem (overweging 26)?
5. Valt SanskritiSetu onder NIS2 / de Cyberbeveiligingswet? Niet onderzocht.
6. Wat is het exacte nummer en de tekst van de omnibus-verordening? Gelezen via secundaire bronnen; de officiële publicatie is niet zelf ingezien.
7. Wat staan er voor termijnen op de AP-pagina's over het personeelsdossier en verzuim? Niet zelf gelezen; label B.

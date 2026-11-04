# Onderzoek: het HR-pakket als hoog-risico-AI onder de AI-verordening

Datum: 2026-10-12. Rol: vraag (onderzoek, geen code). Geen juridisch advies; punten voor een
jurist staan onderaan.

**Labels.** A = primaire wettekst zelf gelezen (EUR-Lex, volledige HTML opgehaald en per
artikel doorzocht). B = secundaire bron (kantoor, nieuwsbericht, samenvatting van een
richtsnoer). C = eigen interpretatie, of niet gevonden.

**Primaire bronnen die zijn gelezen**

- [P1] AI-verordening (EU) 2024/1689, NL, volledige tekst:
  https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:32024R1689
- [P2] Verordening (EU) 2026/1744 (Digital Omnibus on AI), EN, volledige tekst:
  https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32026R1744 en
  https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng
  Titel: "Regulation (EU) 2026/1744 ... of 8 July 2026 ... (Digital Omnibus on AI)",
  PB 24.7.2026, inwerkingtreding "on the third day following that of its publication" (A).
  **Het nummer 2026/1744 en de datum 24 juli 2026 zijn hiermee bevestigd.**
- [P3] AVG (EU) 2016/679, NL, art. 4 punt 4:
  https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:32016R0679

Let op: [P1] is de oorspronkelijke tekst. Waar [P2] een artikel wijzigt, staat dat erbij.

---

## De kern in vijf zinnen

1. Rakesh heeft in de uitkomst gelijk, maar het is niet "natuurlijk": het hangt af van wat
   wij zelf als doel van het systeem opschrijven. Het onderdeel dat per medewerker een
   opleiding voorstelt op basis van een beoordeling van zijn vaardigheden valt het meest
   waarschijnlijk onder bijlage III punt 4 b, en de uitzondering van art. 6 lid 3 vervalt
   omdat het systeem mensen profileert (C, gebouwd op A).
2. Wij zijn de **aanbieder**; de klant is **gebruiksverantwoordelijke** (A).
3. De hoog-risico-eisen gelden voor bijlage III pas vanaf **2 december 2027** (A, [P2]).
   De pilot van december 2026 is dus wettelijk nog niet aan die eisen gebonden. De AVG geldt
   wel al volledig.
4. Systemen die voor 2 december 2027 in de handel zijn, vallen er pas onder bij een
   "aanzienlijke wijziging in het ontwerp" (art. 111 lid 2 zoals gewijzigd, A). Daar moeten
   we niet op bouwen: wij veranderen het product voortdurend.
5. Advies: bouw nu al alsof het hoog-risico is (vrijwillig), en laat een jurist de
   classificatie en de pilotafspraken toetsen.

---

## 1. Classificatie

### Wat de wet zegt

- **Art. 6 lid 2** (A, [P1]): "Naast de in lid 1 bedoelde AI-systemen met een hoog risico
  worden ook AI-systemen zoals bedoeld in bijlage III als AI-systeem met een hoog risico
  beschouwd."
- **Bijlage III punt 4** (A, [P1]): "Werkgelegenheid, personeelsbeheer en toegang tot
  zelfstandige arbeid:
  a) AI-systemen die bedoeld zijn om te worden gebruikt voor het werven of selecteren van
  natuurlijke personen, met name voor het plaatsen van gerichte vacatures, het analyseren en
  filteren van sollicitaties, en het beoordelen van kandidaten;
  b) AI-systemen die bedoeld zijn om te worden gebruikt voor het nemen van besluiten die van
  invloed zijn op de voorwaarden van arbeidsgerelateerde betrekkingen, de bevordering of
  beeindiging van arbeidsgerelateerde contractuele betrekkingen, voor het toewijzen van taken
  op basis van individueel gedrag of persoonlijke eigenschappen of kenmerken, of voor het
  monitoren en evalueren van prestaties en gedrag van personen in dergelijke betrekkingen."
- **Art. 6 lid 3** (A, [P1]): een bijlage III-systeem is geen hoog risico "wanneer het geen
  significant risico op schade ... inhoudt, onder meer doordat het de uitkomst van de
  besluitvorming niet wezenlijk beinvloedt", als aan een van deze voorwaarden is voldaan:
  a) beperkte procedurele taak; b) het resultaat van een eerder voltooide menselijke
  activiteit verbeteren; c) besluitvormingspatronen of afwijkingen opsporen zonder de
  menselijke beoordeling te vervangen; d) een voorbereidende taak voor een beoordeling.
  Laatste alinea: "Niettegenstaande de eerste alinea wordt een in bijlage III bedoeld
  AI-systeem **altijd** als een AI-systeem met een hoog risico beschouwd indien het
  AI-systeem **profilering** van natuurlijke personen uitvoert."
- **Art. 6 lid 4** (A, [P1]): wie meent dat zijn bijlage III-systeem geen hoog risico is,
  "documenteert zijn beoordeling voordat dat systeem in de handel wordt gebracht" en valt
  onder de registratieplicht van **art. 49 lid 2**. Ook "geen hoog risico" kost dus papier en
  een registratie.
- **Art. 3 punt 52** (A, [P1]): "profilering" = profilering zoals gedefinieerd in art. 4
  punt 4 AVG.
- **AVG art. 4 punt 4** (A, [P3]): "elke vorm van geautomatiseerde verwerking van
  persoonsgegevens waarbij aan de hand van persoonsgegevens bepaalde persoonlijke aspecten van
  een natuurlijke persoon worden geevalueerd, met name met de bedoeling zijn
  **beroepsprestaties**, ... betrouwbaarheid, gedrag ... te analyseren of te voorspellen".
- **Art. 3 punt 12** (A, [P1]): het "beoogd doel" is het gebruik "waarvoor een AI-systeem
  door de aanbieder is bedoeld", zoals gespecificeerd in gebruiksinstructies, reclame- of
  verkoopmaterialen en technische documentatie. **Wat wij in de verkooptekst zetten, bepaalt
  dus mee of het hoog-risico is.**
- **Art. 3 punt 1** (A, [P1]): een AI-systeem "leidt uit de ontvangen input af hoe output te
  genereren zoals voorspellingen, inhoud, aanbevelingen of beslissingen". Een gewone
  berekening valt daar mogelijk buiten.

### Richtsnoeren van de Commissie

- **Classificatie hoog-risico (art. 6 lid 5):** de Commissie moest die uiterlijk 2 februari
  2026 geven (art. 6 lid 5, A). Gevonden is alleen een **ontwerp**, gepubliceerd 19 mei 2026,
  consultatie tot 23 juli 2026 (B):
  https://digital-strategy.ec.europa.eu/en/library/draft-commission-guidelines-classification-high-risk-ai-systems
  Een definitieve versie is niet gevonden (C).
  Uit samenvattingen (B):
  - een systeem kan hoog-risico zijn **ook als een mens formeel beslist**, als de uitkomst
    het besluit zwaar beinvloedt (DLA Piper / samenvatting zoekresultaat,
    https://knowledge.dlapiper.com/dlapiperknowledge/globalemploymentlatestdevelopments/2026/eu-commission-publishes-draft-guidelines-on-high-risk-ai-in-employment);
  - **buiten** punt 4 valt volgens het ontwerp o.a.: "AI systems to assess employees'
    progress in voluntary training modules by analysing quiz results, which only provides
    feedback and learning recommendations to the employee to support development, and is not
    used in performance assessment", en een onboarding-chatbot (McCann FitzGerald,
    https://www.mccannfitzgerald.com/knowledge/data-privacy-and-cyber-risk/employment-spotlight-eu-ai-act-draft-guidelines-on-high-risk-ai-classification).
    Ons voorstel gaat NIET alleen naar de medewerker zelf: het gaat naar HR, die toewijst.
    Dat is het verschil.
- **Definitie AI-systeem:** C(2025) 924, 6 februari 2025 (B). Systemen voor "basic data
  processing" vallen volgens de richtsnoeren buiten de definitie (B,
  https://www.insideprivacy.com/artificial-intelligence/european-commission-guidelines-on-the-definition-of-an-ai-system/).
  Niet zelf gelezen (C).

### Wat het product feitelijk doet (gelezen in de code)

- De kloof is een **aftreksom** in SQL: "wat de rol eist min wat de bezetters kunnen"
  (`src/core/models/hr_skills_models.py`, docstring regel 17-18).
- De docstring zegt zelf: `skillsgaptraining` staat in zijn manifest nog op risicoklasse
  `none`, terwijl drie andere HR-skills op `annex_iii` staan; "Die classificatie moet mee
  voordat er echte data in gaat" (zelfde bestand, regel 22-26).
- Opleidingsvoorstellen: `POST /training-proposals` maakt "per medewerker die onder de eis
  zit een voorstel"; goedkeuren of afwijzen door een gebruiker met `hr:approve`, vier ogen
  volgens tenantinstelling (`src/core/api/v1/hr/training_proposals_router.py`, regel 1-7 en
  162-165). In het stuk dat ik las wordt het voorstel regelgebaseerd gemaakt
  (`repo.create_from_gap`, regel 92); welk deel een taalmodel doet in de pilotketen
  (`hr.reskilling_engine` -> agent `skillsgaptraining`, `config/domain_packs.yaml` regel
  88-94) heb ik niet uitgezocht (C).

### Conclusie per functie

| Functie | Bijlage III 4? | Art. 6 lid 3 uitzondering? | Conclusie | Label |
|---|---|---|---|---|
| (1) Kloofanalyse per functie, per medewerker voldoet / voldoet niet | Kan onder 4 b "evalueren van prestaties" vallen, zeker als de verkooptekst "beoordelen" belooft. Is het een kale aftreksom, dan is het mogelijk geen AI-systeem (art. 3 punt 1) | Per medewerker vaststellen of zijn vaardigheden volstaan is een evaluatie van "beroepsprestaties" door geautomatiseerde verwerking = **profilering** (AVG 4 punt 4). Dan vervalt lid 3 | Losstaand twijfel; als **invoer voor de AI-agent** hoort het bij het hoog-risico-systeem | C |
| (2) AI-agent maakt opleidingsvoorstel per medewerker, HR keurt goed | Opleiding toewijzen raakt "voorwaarden van arbeidsgerelateerde betrekkingen" en mogelijk "toewijzen van taken op basis van ... kenmerken"; het voorstel rust op een evaluatie per persoon | "Voorbereidende taak" (d) zou kunnen, maar het systeem profileert -> uitzondering vervalt. Menselijke goedkeuring haalt het niet uit hoog-risico (B, ontwerprichtsnoer) | **Hoog-risico, meest waarschijnlijk** | C (op A) |
| (3) Termijnbewaking (contract, verzuim, certificaten), dagelijkse melding, beslist niets | Een datum vergelijken met vandaag is geen evaluatie van prestaties of gedrag | Zou anders onder (a) "beperkte procedurele taak" vallen; geen profilering zolang er alleen data worden vergeleken | **Waarschijnlijk geen AI-systeem en geen hoog-risico.** Let op: verzuimgegevens zijn gezondheidsgegevens onder de AVG | C |

**Antwoord op Rakesh zijn stelling:** voor functie 2 (en functie 1 zodra die de agent voedt)
klopt het, met de redenering "profilering sluit de uitzondering". Voor functie 3 klopt het
niet. "Natuurlijk" is het niet, omdat de grens loopt via "beoogd doel" en via de vraag of een
opleiding een "voorwaarde" van het werk is. Verstandig is het wel: het hele pakket als
hoog-risico behandelen (C).

---

## 2. Wie zijn wij

- **Art. 3 punt 3** (A, [P1]): aanbieder = wie "een AI-systeem ... ontwikkelt of laat
  ontwikkelen en dat systeem ... in de handel brengt of het AI-systeem in gebruik stelt onder
  de eigen naam of merk, **al dan niet tegen betaling**". -> SanskritiSetu is aanbieder, ook in
  een gratis pilot.
- **Art. 3 punt 4** (A): gebruiksverantwoordelijke = wie "een AI-systeem onder eigen
  verantwoordelijkheid gebruikt". -> de mkb-werkgever.
- **Art. 25 lid 1** (B via artificialintelligenceact.eu; de NL-tekst niet apart
  geciteerd): de klant wordt zelf aanbieder als hij (a) zijn naam of merk op het systeem
  zet, (b) een substantiele wijziging aanbrengt die niet in de oorspronkelijke
  conformiteitsbeoordeling was voorzien, of (c) het beoogde doel zo wijzigt dat het
  hoog-risico wordt.
- **Art. 25 lid 2, gewijzigd door [P2]** (A): de oorspronkelijke aanbieder blijft dan
  verplicht mee te werken (documentatie, bekende beperkingen, technische toegang), tenzij hij
  "clearly specified that its AI system is not to be changed into a high-risk AI system".
- **Art. 25 lid 4, gewijzigd door [P2]** (A): de aanbieder en een derde die "an AI system, AI
  model, tools, services, components" levert, leggen schriftelijk vast welke informatie en
  hulp nodig is. Dat raakt onze **taalmodelleverancier** (C: of dit voor een
  GPAI-model-API geldt, moet een jurist toetsen).
- Gevolg voor contracten (C): verbied in de voorwaarden white-labelen en eigen wijzigingen van
  het doel, of regel expliciet wat er dan gebeurt.

---

## 3. Verplichtingen van de aanbieder (wij)

Bron telkens [P1], gelezen (A), tenzij anders vermeld.

| Artikel | Wat er moet zijn |
|---|---|
| 16 | Overzichtsplicht: voldoen aan afdeling 2; naam en contactadres op het systeem; kwaliteitsbeheer (17); documentatie (18) en logs (19) bewaren; conformiteitsbeoordeling (43) voor in de handel brengen; EU-conformiteitsverklaring (47); CE-markering (48); registratie (49 lid 1); corrigerende maatregelen (20); toegankelijkheidseisen (16 sub l) |
| 9 | Risicobeheersysteem: "doorlopend en gepland iteratief proces" over de hele levensduur, met vaststellen, inschatten en beheersen van risico's voor gezondheid, veiligheid en grondrechten |
| 10 | Data en datagovernance. **[P2] wijzigt lid 6**: voor systemen die geen AI-model trainen gelden de leden 2-4 "only to the testing data sets" (A). Wij trainen niet zelf -> eisen gelden voor onze **testdata** (o.a. lid 2 f/g: onderzoek naar vooringenomenheid en maatregelen). [P2] voegt **art. 4a** toe: bijzondere persoonsgegevens mogen onder strikte voorwaarden voor biasdetectie (A) |
| 11 + bijlage IV | Technische documentatie, opgesteld **voor** het in de handel brengen. **[P2]**: kmo's en "SMC's" mogen een vereenvoudigd formulier van de Commissie gebruiken (A) |
| 12 | Logs: het systeem registreert "automatisch" gebeurtenissen gedurende de levenscyclus, o.a. voor monitoring na het in de handel brengen (art. 72) en voor de gebruiksverantwoordelijke (art. 26 lid 5) |
| 13 | Gebruiksinstructies met o.a. identiteit aanbieder, beoogd doel, nauwkeurigheid, bekende risico's, hulpmiddelen om de output te verklaren, prestaties voor specifieke groepen |
| 14 | Menselijk toezicht ingebouwd in het ontwerp; de toezichthouder moet beperkingen begrijpen, bedacht zijn op "automation bias", de output juist kunnen interpreteren en kunnen besluiten de output niet te gebruiken |
| 15 | Passende nauwkeurigheid, robuustheid en cyberbeveiliging, consistent over de levensduur |
| 17 | Kwaliteitsbeheersysteem, schriftelijk (strategie, ontwerpcontrole, testen, databeheer, risicobeheer, monitoring na in de handel brengen, incidentmelding, ...). **[P2] lid 2**: evenredig aan de omvang van de aanbieder, met name kmo's, maar met behoud van "the degree of rigour" (A) |
| 18 | **Tien jaar** na in de handel brengen: technische documentatie, documentatie kwaliteitsbeheer, EU-conformiteitsverklaring beschikbaar houden |
| 19 | Logs bewaren "voor zover dergelijke logs onder hun controle vallen", "ten minste zes maanden, tenzij anders is bepaald in het toepasselijke Unie- of nationaal recht, met name het Unierecht inzake de bescherming van persoonsgegevens" |
| 20 | Bij niet-naleving onmiddellijk corrigeren, uit de handel nemen of deactiveren, en gebruiksverantwoordelijken informeren |
| 43 lid 2 | Bijlage III punten 2 t/m 8: "conformiteitsbeoordelingsprocedure op basis van interne controle" (bijlage VI). Geen aangemelde instantie (de tekst die ik las brak af bij "waarvoor de betrokkenheid van e[en aangemelde instantie ...]"; de strekking is B) |
| Bijlage VI | Zelf nagaan: kwaliteitsbeheer voldoet aan 17; technische documentatie toont naleving afdeling 2; ontwerp en monitoring komen overeen met de documentatie |
| 47 | Schriftelijke EU-conformiteitsverklaring, **tien jaar** beschikbaar |
| 48 lid 2 | Digitaal systeem: digitale CE-markering, "gemakkelijk toegankelijk via de interface" |
| 49 lid 1 | Voor het in de handel brengen: aanbieder en systeem registreren in de EU-databank (art. 71) |
| 72 | Systeem en plan voor monitoring na het in de handel brengen. **[P2] lid 3**: de Commissie geeft uiterlijk 2 september 2027 een sjabloon (A) |
| 73 | Ernstige incidenten melden bij de markttoezichtautoriteit: uiterlijk **15 dagen**; bij wijdverbreide inbreuk **2 dagen**; bij overlijden **10 dagen** |

---

## 4. Verplichtingen van de klant (gebruiksverantwoordelijke) en wat wij moeten leveren

| Artikel | Plicht klant (A, [P1]) | Wat wij moeten leveren (C) |
|---|---|---|
| 26 lid 1 | gebruiken volgens de gebruiksaanwijzing | een gebruiksaanwijzing (art. 13) |
| 26 lid 2 | menselijk toezicht door mensen met "bekwaamheid, opleiding en autoriteit" | rol `hr:approve`, vier ogen, en uitleg wat de goedkeurder moet controleren |
| 26 lid 4 | invoerdata relevant en representatief | importcontrole en heldere eisen aan het vaardighedenbestand |
| 26 lid 5 | werking monitoren; bij risico gebruik onderbreken en aanbieder melden; ernstig incident eerst aan aanbieder | een meldkanaal en een "uitzetten"-knop per tenant |
| 26 lid 6 | logs "ten minste zes maanden" bewaren, voor zover onder hun controle | logs per tenant, exporteerbaar; bewaartermijn instelbaar |
| 26 lid 7 | **voordat** het systeem op de werkplek wordt gebruikt: werknemersvertegenwoordigers en betrokken werknemers informeren | een kant-en-klare informatietekst voor OR en medewerkers |
| 26 lid 9 | informatie uit art. 13 gebruiken voor de DPIA (AVG art. 35) | DPIA-bouwstenen |
| 26 lid 11 | betrokkenen informeren dat het systeem op hen wordt gebruikt bij besluiten | tekst voor de medewerker |
| 27 lid 1 | grondrechteneffectbeoordeling alleen voor "publiekrechtelijke organen", "particuliere entiteiten die openbare diensten verlenen" en bijlage III punt 5 b/c | **Geldt niet voor een gewone private mkb-werkgever** (A). [P2] laat de DPIA meetellen (lid 4) |
| 86 lid 1 | uitleg geven over "de rol van het AI-systeem in de besluitvormingsprocedure en de voornaamste elementen van het genomen besluit", bij een besluit met rechtsgevolg of vergelijkbare aanzienlijke invloed | per voorstel: welke eis, welke vaardigheid ontbrak, waarom deze opleiding, wie keurde goed |

---

## 5. AI-geletterdheid (art. 4) en transparantie (art. 50)

- **Art. 4 oorspronkelijk** (A, [P1]): aanbieders en gebruiksverantwoordelijken nemen
  maatregelen om "zoveel als mogelijk" te zorgen voor een "toereikend niveau van
  AI-geletterdheid" bij hun personeel. Geldt sinds 2 februari 2025 (art. 113 sub a, A).
- **Art. 4 vervangen door [P2]** (A): nu "shall take measures to support the development of
  AI literacy of their staff ... This obligation does not require providers or deployers to
  guarantee any specific level of AI literacy". Van kracht drie dagen na 24 juli 2026.
  -> Wij moeten ons eigen personeel en de mensen die namens ons werken ondersteunen; de klant
  moet zijn HR-goedkeurders ondersteunen. Wij kunnen trainingsmateriaal meeleveren (C).
- **Art. 50 lid 1** (A): wie een AI-systeem aanbiedt dat direct met mensen praat, zorgt dat
  ze weten dat het AI is, tenzij dat duidelijk is. Relevant voor de copilot/het
  interview-scherm (C). **Art. 50 lid 2** (A): synthetische tekst moet machineleesbaar
  gemarkeerd zijn; of een opleidingsvoorstel daaronder valt en welke uitzonderingen gelden,
  heb ik niet volledig gelezen (C). [P2] art. 111 lid 4: systemen die synthetische inhoud
  maken en voor 2 augustus 2026 in de handel waren, moeten uiterlijk 2 december 2026 aan art.
  50 lid 2 voldoen (A). Art. 50 valt onder de algemene toepassingsdatum 2 augustus 2026
  (art. 113, A).

---

## 6. Tijdlijn

- **Oorspronkelijk** (A, [P1] art. 113): algemeen van toepassing vanaf 2 augustus 2026;
  hoofdstukken I en II (incl. art. 4 en 5) vanaf 2 februari 2025.
- **Gewijzigd door [P2] art. 113 derde alinea punt c** (A): "Chapter III, Sections 1, 2,
  and 3, with the exception of Article 6(5), shall apply from: (i) **2 December 2027** as
  regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III; and (ii)
  2 August 2028 as regards ... Annex I". Afdelingen 1-3 bevatten art. 6-27 (classificatie,
  eisen, plichten aanbieder en gebruiksverantwoordelijke).
- **Overgangsregel art. 111 lid 2**: oorspronkelijk (A, [P1]) "die voor 2 augustus 2026 in
  de handel zijn gebracht of in gebruik zijn gesteld". **[P2] vervangt dit** (A): "placed on
  the market or put into service **before the date of application of Chapter III referred to
  in Article 113**, only if, as from that date, those systems are subject to significant
  changes in their designs." Overweging 39 van [P2] (A): het gaat om het "type and model";
  doorslaggevend is wanneer de eerste eenheid "lawfully placed on the market"; elke
  significante ontwerpwijziging daarna brengt de volledige plichten.
- **Gevolg voor de pilot in december 2026 (C):**
  - De hoog-risico-eisen gelden dan nog niet. De pilot mag draaien zonder
    conformiteitsbeoordeling, CE en registratie.
  - De AVG geldt wel: grondslag, DPIA, art. 22 (geen uitsluitend geautomatiseerd besluit),
    bewaartermijnen. Ook art. 4 (AI-geletterdheid) en art. 5 (verboden) gelden al.
  - Op art. 111 lid 2 rekenen is onverstandig: wij wijzigen het product wekelijks, dus na
    2 december 2027 is er vrijwel zeker een "significant change". Ook staat de vraag open
    of een pilot telt als "in de handel brengen" (art. 3 punt 9: "voor het eerst in de Unie
    op de markt aanbieden"; punt 11 "in gebruik stellen": "directe levering ... aan de
    gebruiksverantwoordelijke voor het eerste gebruik") -- dat moet een jurist zeggen.
  - Verstandig: nu al vrijwillig voldoen aan wat goedkoop is en in het ontwerp zit (logs,
    menselijk toezicht, uitleg, gebruiksaanwijzing), zodat er later niets omgebouwd hoeft.

---

## 7. Boetes en toezicht

- **Art. 99** (A, [P1]): verboden praktijken (art. 5) tot 35 miljoen of 7 % omzet (lid 3);
  plichten aanbieder (art. 16), gebruiksverantwoordelijke (art. 26) en transparantie (art. 50)
  tot 15 miljoen of 3 % (lid 4); onjuiste informatie aan toezichthouders tot 7,5 miljoen of
  1 % (lid 5). **Lid 6: voor kmo's geldt het laagste** van percentage en bedrag.
  [P2] (A): lidstaten houden rekening met kmo's en "SMC's" (lid 1), voor SMC's geldt ook het
  laagste bedrag (nieuw lid 6a), en lid 4 krijgt punt (da) voor art. 25 lid 2 en 4.
- **Toezicht in Nederland:**
  - Het wetsvoorstel Uitvoeringswet AI-verordening is op 20 april 2026 in internetconsultatie
    gegaan, open tot en met 1 juni 2026 (B, Rijksoverheid:
    https://www.rijksoverheid.nl/actueel/nieuws/2026/04/20/kabinet-zet-stap-met-toezicht-op-europese-ai-regels).
  - Volgens Stibbe wordt de **Autoriteit Persoonsgegevens** markttoezichthouder "voor
    verboden AI-praktijken, voor transparantie-verplichtingen, en voor een groot deel van de
    hoog-risico toepassingen, waaronder AI die wordt ingezet bij werving en selectie"; AP en
    RDI coordineren (B,
    https://www.stibbe.com/nl/publications-and-insights/nederlands-voorstel-voor-ai-toezicht-hybride-samenwerking-tussen).
  - Of de wet inmiddels is ingediend of aangenomen: niet gevonden (C).

---

## 8. Gevolgen voor eerdere besluiten

- **Tevredenheidsmeting (uitgesteld).** Art. 5 lid 1 sub f (A) verbiedt AI-systemen "om
  emoties van een natuurlijke persoon op de werkplek ... af te leiden, behalve ... uit
  medische of veiligheidsoverwegingen". Sinds 2 februari 2025 van kracht. Art. 3 punt 39 (A)
  definieert een emotieherkenningssysteem als bedoeld "op basis van hun biometrische
  gegevens". Volgens de richtsnoeren verboden praktijken C(2025) 884 (4 februari 2025, B)
  gaat het verbod over o.a. gezicht, stem, toetsaanslagen. Een enquete met vrije tekst valt
  daarmee waarschijnlijk niet onder het verbod (C), maar sentimentanalyse per medewerker is
  wel "monitoren en evalueren van ... gedrag" -> hoog-risico (C). Besluit "uitstellen" blijft
  juist; als het terugkomt: alleen anoniem en geaggregeerd, geen stem- of camerabeeld.
- **Interne mobiliteit (uitgesteld).** Medewerkers matchen aan functies raakt "bevordering"
  en "toewijzen van taken" (bijlage III 4 b) en lijkt op 4 a (selectie). Dat is de duidelijkste
  hoog-risico-toepassing in het pakket (C). Uitstel blijft juist.
- **Auditlog na vertrek klant.** Art. 19 lid 1 en art. 26 lid 6 (A) eisen logs van
  **ten minste zes maanden**, maar "tenzij anders is bepaald in ... het Unierecht inzake de
  bescherming van persoonsgegevens", en alleen "voor zover onder hun controle". Die plicht
  geldt pas vanaf 2 december 2027. Daarmee blijft de conclusie van
  `docs/onderzoek-bewaarplicht-en-opgeheven-klanten.md` staan: tot die datum is er geen
  AI-bewaarplicht die verwijderen na vertrek tegenhoudt; daarna wel voor de logs van het
  hoog-risico-deel, minimaal zes maanden (C). Advies: maak de logs zo arm mogelijk aan
  persoonsgegevens (verwijzing in plaats van naam en inhoud), zodat bewaren en AVG minder
  botsen. Dat sluit aan op de brief
  `docs/agent-briefs/generated/2026-10-12-sprint-dag-avg-auditlog-zonder-persoonsgegevens.md`.
- **Art. 18 (tien jaar)** gaat over documentatie van het systeem, niet over
  klantgegevens (A). Daar staan geen medewerkergegevens in, als we dat zo ontwerpen (C).

---

## CHECKLIST: wat moet er af zijn

"Hebben we" noemt alleen wat ik in de code heb aangewezen. Al het andere: niet gezien.

| Verplichting | Wat het is | Hebben we (aangewezen) | Ontbreekt |
|---|---|---|---|
| Classificatie (6 lid 4) | vastgelegde beoordeling hoog-risico ja/nee per functie | docstring `hr_skills_models.py` r. 22-26 erkent het probleem | `skillsgaptraining` staat op `none`; een vastgelegd besluit "hoog-risico" per functie |
| Beoogd doel (3 punt 12) | doel in gebruiksinstructie en verkooptekst | - | een doelomschrijving die zegt wat het wel en niet doet |
| Risicobeheer (9) | doorlopend risicoproces | - | risicoregister voor het HR-pakket |
| Data (10, 4a) | testdata, biasonderzoek | - | testset en biasmeting (bv. per leeftijd/geslacht als dat mag) |
| Technische documentatie (11, bijlage IV) | dossier voor in de handel brengen | ADR's, specs (niet getoetst tegen bijlage IV) | dossier volgens bijlage IV / kmo-formulier |
| Logs (12, 19, 26 lid 6) | automatische registratie, >= 6 maanden | auditgebeurtenissen `hr_training_proposal_approved` / `_rejected` (`training_proposals_router.py` r. 197, 227); hashketen volgens CLAUDE.md (niet zelf in code nagelezen) | bewaartermijn >= 6 maanden vastgelegd; export per tenant; logs zonder onnodige persoonsgegevens |
| Transparantie (13) | gebruiksaanwijzing | - | gebruiksaanwijzing met doel, beperkingen, nauwkeurigheid |
| Menselijk toezicht (14, 26 lid 2) | mens kan begrijpen, negeren, stoppen | goedkeuren/afwijzen met `hr:approve`, vier ogen per tenant (`training_proposals_router.py` r. 5-7, 162-165) | uitleg per voorstel voor de goedkeurder; waarschuwing tegen blind goedkeuren; noodstop per tenant |
| Nauwkeurigheid, robuustheid, beveiliging (15) | gemeten en gedocumenteerd | tenant-isolatie (CLAUDE.md, niet hier gemeten) | gemeten nauwkeurigheid van voorstellen |
| Kwaliteitsbeheer (17) | schriftelijk systeem | werkwijze in `.claude/rules/` en ADR's (niet als QMS opgezet) | QMS-document dat naar die bestaande regels verwijst |
| Conformiteit (43, bijlage VI), verklaring (47), CE (48), registratie (49) | eigen beoordeling, verklaring, digitale CE, EU-databank | - | alles; pas nodig voor de datum, maar plannen |
| Monitoring na in de handel brengen (72), incidenten (73) | plan en meldproces | - | plan; meldprocedure 15/2/10 dagen |
| Informatie aan klant voor 26 lid 7, 11 en 86 | teksten voor OR en medewerkers; uitleg per besluit | - | sjabloonteksten; uitleg per voorstel |
| AI-geletterdheid (4) | ondersteuning personeel | - | korte uitleg voor HR-goedkeurders; eigen vastlegging |
| AVG (nu al) | grondslag, DPIA, art. 22 | AVG-wisroute via `dsar_service` (genoemd in `hr_skills_models.py` r. 9-11, niet zelf gelezen) | DPIA voor het HR-pakket; verwerkersovereenkomst die dit dekt |

---

## Advies voor Rakesh (gewone taal)

**Wat het betekent.** Het deel dat per medewerker kijkt of iemand voldoet en daar een
opleiding bij voorstelt, is volgens de wet hoogstwaarschijnlijk "hoog-risico". Dat wij een
mens laten goedkeuren verandert dat niet. De termijnbewaking is dat waarschijnlijk niet.
Wij zijn de leverancier, en de leverancier draagt de meeste plichten.

**Voor de pilot (december 2026):**
1. Leg schriftelijk vast: "het HR-pakket behandelen we als hoog-risico". Zet
   `skillsgaptraining` op hoog-risico in plaats van `none`.
2. Doe een DPIA (AVG) voor het HR-pakket. Die is nu al nodig, los van de AI-wet.
3. Lever de pilotklant een korte tekst voor OR en medewerkers, en een korte
   gebruiksaanwijzing: wat het systeem doet, wat niet, en dat een mens beslist.
4. Laat bij elk voorstel zien waarom (welke eis, welke vaardigheid ontbreekt).
5. Houd interne mobiliteit en tevredenheidsmeting uit de pilot.

**Voor 2 december 2027 (de datum dat de eisen gelden):**
risicoregister, testset met biasmeting, technisch dossier (kmo-formulier mag), logs minimaal
zes maanden, kwaliteitsdocument, eigen conformiteitsbeoordeling, verklaring, digitale
CE-markering, registratie in de EU-databank, en een meldprocedure voor incidenten. Begin in
2027 Q1; het is papierwerk dat op ons bestaande werk kan leunen.

**Wat een jurist moet toetsen:**
1. Valt een opleidingsvoorstel onder "voorwaarden van arbeidsgerelateerde betrekkingen" of
   "toewijzen van taken" (bijlage III 4 b)? En is een regelgebaseerde kloofanalyse een
   AI-systeem?
2. Telt de pilot als "in de handel brengen" of "in gebruik stellen", en wat betekent dat
   voor art. 111 lid 2?
3. Art. 25 lid 4: wat moeten we met de taalmodelleverancier schriftelijk regelen?
4. Instemmingsrecht van de OR (Wet op de ondernemingsraden) bij de klant -- niet onderzocht.
5. De verhouding tussen zes maanden logs bewaren en AVG-wissing na vertrek van een klant.
6. De definitieve versie van de Commissierichtsnoeren classificatie (alleen het ontwerp van
   19 mei 2026 gevonden) en de stand van de Uitvoeringswet.

## Niet gemeten / niet gelezen

- Art. 25 lid 1, bijlage IV en art. 50 lid 2 zijn niet volledig in het Nederlands gelezen.
- De richtsnoeren (classificatie, definitie AI-systeem, verboden praktijken) alleen via
  samenvattingen (B).
- Of de pilotketen een taalmodel gebruikt voor de inhoud van het voorstel: niet nagegaan.
- Hashketen van het auditlog en `dsar_service`: niet in de code nagelezen.

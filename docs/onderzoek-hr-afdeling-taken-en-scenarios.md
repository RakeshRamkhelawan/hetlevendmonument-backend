# Onderzoek: wat een HR-afdeling doet, en welke gebruikersscenario's daaruit volgen

Datum: 2026-10-09. Soort: webonderzoek (vraag-rol), niets in de code gewijzigd.
Doel: het HR-pakket "Employee Reskilling & Mobility" in een pilot echt bruikbaar maken voor
het Nederlandse mkb (10-250 medewerkers).

**Leeswijzer.** Wettelijke punten zijn samengevat uit openbare bronnen en zijn GEEN juridisch
advies. Bronnummers [n] verwijzen naar de bronnenlijst onderaan. Bronnen gemarkeerd met (S)
zijn secundair (vakblad, leverancier, adviesbureau); die zijn bruikbaar als aanwijzing, niet
als bewijs. Waar een bewering op eigen redenering rust en niet op een bron, staat
"(redenering)".

---

## 1. De taakgebieden van HR

Kolommen: wat / hoe vaak / wie doet het / wat is in NL wettelijk verplicht.
HR = HR-adviseur of (in klein mkb) eigenaar/office manager; LG = leidinggevende; MW = medewerker.

| Gebied | Wat er gebeurt | Frequentie | Wie | Wettelijk (NL, mkb) |
|---|---|---|---|---|
| Werving en selectie | vacature opstellen, plaatsen, CV's selecteren, gesprekken, aanbod | doorlopend, piek bij groei/verloop | LG kiest, HR regelt | AVG: afgewezen sollicitanten uiterlijk 4 weken na procedure verwijderen, met toestemming max 1 jaar [12](S). AI-selectie is hoog-risico (AI Act Annex III 4a) [3] |
| Onboarding | contract, ID-controle, loonheffingsverklaring, account/spullen, inwerkplan | per nieuwe medewerker | HR + LG + IT | identificatieplicht; kopie ID bewaren tot 5 jaar na uitdiensttreding [12](S); informatieplicht arbeidsvoorwaarden (Wet transparante en voorspelbare arbeidsvoorwaarden, 2022) [11](S) |
| Contracten en personeelsdossier | contracten, wijzigingen, verlengingen, dossierbeheer | doorlopend; verlengingen maandelijks bewaken | HR, eigenaar tekent | aanzegplicht: bij tijdelijk contract van 6 maanden of langer uiterlijk 1 maand voor einde schriftelijk laten weten of en hoe er wordt verlengd; anders 1 maandsalaris vergoeding [5][6] |
| Salaris-/loonadministratie | loonstroken, loonaangifte, mutaties | maandelijks (of 4-wekelijks) | salarisadministratie/accountant, vaak uitbesteed | loonadministratie 7 jaar bewaren (fiscaal) [12](S) |
| Verzuim en re-integratie | ziekmelding, contact arbodienst, probleemanalyse, plan van aanpak, evaluaties, UWV-melding | bij elke ziekmelding; langlopend tot 104 weken | LG (eerste contact), HR (dossier), bedrijfsarts/arbodienst | **Gecorrigeerd na primaire bron:** de Regeling procesgang eerste en tweede ziektejaar (BWBR0013540) noemt GEEN vaste "week 8". Art. 2: oordeel/probleemanalyse bedrijfsarts binnen zes weken na eerste ziektedag; art. 4 lid 1: plan van aanpak binnen twee weken NA dat oordeel (dus meestal week 8, maar later als de analyse later komt); art. 4 lid 2 sub b: evaluatie in ieder geval aan het einde van het eerste ziektejaar [P1]. Het systeem moet de PvA-datum dus rekenen vanaf de datum van de probleemanalyse, niet vast op week 8. Oorspronkelijke tekst: probleemanalyse uiterlijk week 6, plan van aanpak uiterlijk week 8, melding UWV week 42, eerstejaarsevaluatie rond week 52, re-integratieverslag/WIA-aanvraag rond week 88-93; loondoorbetaling max 104 weken; loonsanctie tot 52 weken bij tekortkoming [4](S)[7](S). Werkgever mag aard/oorzaak van ziekte NIET registreren [9](S)(AP-lijn) |
| Verlof | aanvragen, goedkeuren, saldo, bijzonder verlof (ouderschap, zorg) | dagelijks/wekelijks | MW vraagt, LG keurt | wettelijk minimum 4x arbeidsduur per week vakantie (BW 7:634; niet apart gemeten in dit onderzoek) |
| Functioneren/beoordelen | gesprekscyclus: plannings-, voortgangs-, beoordelingsgesprek | 1-3x per jaar per MW | LG voert, HR faciliteert | gesprek zelf niet wettelijk verplicht; WEL relevant: een beoordelingsregeling valt onder OR-instemming (WOR 27), en een ontslag wegens disfunctioneren vergt dossier (niet in detail gemeten) [8](S)[11](S) |
| Opleiding en ontwikkeling | scholingsbehoefte, budget, aanbod, registratie certificaten | jaarlijks plan, doorlopend | MW + LG, HR budget | scholingsplicht werkgever (BW 7:611a): scholing nodig voor de functie, en bij vervallen functie voor zover redelijk; verplichte scholing kosteloos en in werktijd sinds 2022 [11](S); opleidingsregeling onder OR-instemming (WOR 27) |
| Loopbaan/interne mobiliteit | loopbaangesprek, interne vacatures, doorgroei, herplaatsing | ad hoc, vaak jaarlijks gesprek | MW + LG, HR | geen algemene plicht; bij re-integratie en herplaatsing (ontslag) wel zoekplicht naar passende functie (niet in detail gemeten) |
| Beloning | salarisschalen, verhogingen, bonussen, cao-toepassing | jaarlijks + bij promotie | eigenaar/directie, HR | cao waar van toepassing; EU-loontransparantierichtlijn (implementatie juni 2026) - stand NL-implementatie niet vastgesteld |
| Arbo en welzijn | RI&E + plan van aanpak, preventiemedewerker, basiscontract arbodienst, PMO, psychosociale arbeidsbelasting | RI&E periodiek; doorlopend | eigenaar, preventiemedewerker, arbodienst | RI&E verplicht en (boven drempel) laten toetsen; basiscontract met arbodienst/bedrijfsarts verplicht; preventiemedewerker verplicht [10](S) |
| Tevredenheid/engagement | MTO/pulspeiling, actieplan per team | jaarlijks of per kwartaal | HR organiseert, LG volgt op | niet verplicht; RI&E moet wel psychosociale arbeidsbelasting meenemen (redenering op basis van Arbowet) |
| Offboarding/exit | ontslag of opzegging verwerken, eindafrekening, spullen/accounts terug, exitgesprek, getuigschrift | per vertrek | HR + LG | opzegtermijnen BW; bewaartermijnen dossier na uitdiensttreding [12](S) |
| Personeelsplanning | bezetting, roosters, formatie, vervanging | wekelijks (rooster) tot jaarlijks (formatie) | LG, directie | Arbeidstijdenwet (rust en maximale arbeidstijd) |
| HR-analytics | verzuim%, verloop, opleidingsuren, kosten | maandelijks/jaarlijks | HR, directie | geen plicht; WEL AVG-doelbinding |
| Compliance | AVG (verwerkingsregister, bewaartermijnen), WOR, Arbeidstijdenwet, Wet arbeidsmarkt in balans | doorlopend | eigenaar/HR, soms jurist | AVG; AP beboet foute registratie gezondheidsgegevens (voorbeeld: 15.000 euro boete onderhoudsbedrijf) [9](S) |
| Ondernemingsraad | overleg, advies- en instemmingsaanvragen | OR: min. 2x per jaar overleg (niet gemeten); PVT/personeelsvergadering | directie, HR bereidt voor | OR verplicht vanaf 50 personen; 10-50: PVT op verzoek van meerderheid, anders min. 2 personeelsvergaderingen per jaar [13](S). Instemming nodig voor o.a. beoordelings-, opleidings-, verzuim-, privacy- en personeelsvolgregelingen (WOR 27 lid 1, o.a. sub k en l) [8](S) |

---

## 2. Klein mkb tegenover middelgroot

**Klein (10-~50).** Geen HR-afdeling. De eigenaar, een office manager of de boekhouder doet HR
erbij. Salaris is bijna altijd uitbesteed (accountant/salarisbureau, Nmbrs/Loket.nl).
Gegevens staan verspreid: salarissysteem, Excel, mail, papieren map, WhatsApp. Ondernemers met
minder dan 25 medewerkers besteden gemiddeld ca. 2 uur per week aan personeelszaken en
onderschatten dat volgens Mercer Direct [14](S). Geen OR; hooguit een PVT. Verzuim is hier laag
(2,4% bij <10 werknemers in 2025) maar een langdurig zieke weegt zwaar [15].

**Middelgroot (~50-250).** Er is een HR-adviseur of kleine HR-afdeling, vaak een HR-pakket
(AFAS, Visma|Raet/Youforce, Personio, HiBob). OR is verplicht vanaf 50, dus elke nieuwe
regeling rond beoordelen, opleiden of persoonsgegevens gaat langs de OR. Verzuim hoger
(middelgroot 4,5%, 100+ 6,0%) [15]. Hier ontstaat pas echt vraag naar gesprekscyclus,
vaardighedenoverzicht, opleidingsbudgetten en interne mobiliteit.

**Gevolg voor SanskritiSetu (redenering).** Voor klein mkb moet het pakket werken zonder
HR-kennis bij de gebruiker en de wettelijke termijnen zelf bewaken. Voor middelgroot is
"Reskilling & Mobility" logischer, maar komt de OR-instemming direct in beeld.

---

## 3. Pijnpunten en tijdvreters (met bron)

1. **Administratieve last.** 41% van de mkb-ondernemers vindt dat ze te veel tijd kwijt zijn aan
   administratie (Van Spaendonck) [14](S). Let op: dit is administratie in het algemeen, niet
   alleen HR, en het komt uit een persbericht van een leverancier (Loket.nl, 2026-02-10) zonder
   gepubliceerde steekproef; zie `docs/onderzoek-hr-administratie-tijdsbesteding.md`.
2. **Versnipperde gegevens.** HR en salaris in het mkb zijn versnipperd en afhankelijk van enkele
   personen; vakpers spreekt van "HR via WhatsApp en Excel" [14](S)[16](S).
3. **Verzuim en poortwachter.** Veel termijnen, hoge boete (loonsanctie tot 52 weken extra) en
   de AVG-valkuil van gezondheidsgegevens registreren [4](S)[9](S).
4. **Termijnen missen.** Aanzegtermijn (1 maandsalaris), proeftijd, contractketens [5][6].
5. **Kennisgebrek.** 31% ziet kansen in digitalisering/AI maar weet niet hoe [14](S).

**Waar automatisering aantoonbaar helpt (redenering, met lage bewijslast).** Termijnbewaking
(aanzeg, poortwachter) is regelgebaseerd en hoeft geen AI; leveranciers bieden het al
(AFAS-help over poortwachter [7](S), Loket.nl verzuim [17](S)). AI voegt waarde toe bij tekst en
samenvatten: vacature- en gespreksvoorbereiding, vaardigheden uit functieomschrijvingen halen,
open antwoorden van een peiling clusteren. Harde, onafhankelijke metingen van tijdwinst door AI
in NL-mkb-HR zijn NIET gevonden.

---

## 4. Gebruikersscenario's

Vaste vorm per scenario. Afkortingen in "Gevoeligheid":
**AI Act** = Annex III punt 4 (4a werving/selectie; 4b beslissingen over arbeidsvoorwaarden,
promotie, ontslag, taakverdeling op basis van gedrag/kenmerken, en monitoren/beoordelen van
prestaties) [3]. **AVG-bijz.** = bijzondere persoonsgegevens (art. 9, o.a. gezondheid).
**WOR27** = waarschijnlijk OR-instemmingsplichtig (alleen bij OR/PVT; vanaf 50 personen).
"Voorstellen/beslissen" = wat de AI-agent mag.

### S1. Vaardigheden van een team in kaart brengen
- **Actor:** HR-adviseur of eigenaar; medewerkers vullen aan.
- **Aanleiding:** jaarplan, nieuwe klantvraag, of vertrek van een sleutelpersoon.
- **Gebruiker:** kiest team, laat medewerkers hun vaardigheden bevestigen/aanvullen.
- **Systeem:** stelt vaardighedenlijst voor uit functieomschrijvingen en certificaten; toont
  matrix en enkelvoudige afhankelijkheden ("alleen Piet kan X").
- **Resultaat:** vaardighedenmatrix per team, gaten zichtbaar.
- **Goedkeuring:** medewerker bevestigt eigen profiel; LG valideert niveau.
- **Gevoeligheid:** AI Act: laag zolang het een overzicht is; wordt 4b zodra het gebruikt wordt
  voor beoordelen/promotie. AVG: gewone gegevens. WOR27: ja (personeelsvolgsysteem/persoonsgegevens, sub k/l).
- **Gegevens:** functies, certificaten, opleidingshistorie. **Waar:** Excel, HR-pakket, papier.
- **AI:** voorstellen. Niveau van een persoon wordt door mens vastgesteld.

### S2. Opleidingsvoorstel
- **Actor:** LG + medewerker.
- **Aanleiding:** gat uit S1, verplicht certificaat verloopt, of wens medewerker.
- **Gebruiker:** opent profiel, vraagt voorstel.
- **Systeem:** zoekt passende opleidingen, kosten, duur; markeert of het verplichte scholing is
  (dan kosteloos en in werktijd, BW 7:611a) [11](S).
- **Resultaat:** opleidingsaanvraag met onderbouwing.
- **Goedkeuring:** LG en budgethouder.
- **Gevoeligheid:** AI Act: laag tot 4b als toewijzing ongelijk uitpakt. WOR27: opleidingsregeling.
- **Gegevens:** S1, budget, opleidingsaanbod. **Waar:** Excel/boekhouding, leveranciers.
- **AI:** voorstellen.

### S3. Interne vacature matchen
- **Actor:** HR/LG met openstaande functie.
- **Aanleiding:** vacature ontstaat.
- **Gebruiker:** zet vacature intern open.
- **Systeem:** toont interne kandidaten met passende vaardigheden, en uitleg waarom.
- **Resultaat:** shortlist ter overweging; medewerkers kunnen zelf reageren.
- **Goedkeuring:** LG beslist over gesprekken en benoeming.
- **Gevoeligheid:** AI Act 4a/4b: HOOG (selectie/promotie). AVG art. 22: geen uitsluitend
  geautomatiseerd besluit. WOR27: ja.
- **Gegevens:** vacature, S1-profielen, interesse medewerker. **Waar:** HR-pakket/Excel.
- **AI:** alleen voorstellen, met uitleg; nooit automatisch uitsluiten.

### S4. Loopbaangesprek voorbereiden
- **Actor:** LG en medewerker.
- **Aanleiding:** jaarlijks gesprek of vraag medewerker.
- **Gebruiker:** opent voorbereiding.
- **Systeem:** vat profiel, opleidingen, interessegebieden samen; stelt gespreksvragen voor.
- **Resultaat:** agenda en notitiesjabloon; afspraken vastgelegd na gesprek.
- **Goedkeuring:** beide partijen tekenen verslag.
- **Gevoeligheid:** AI Act: 4b als het meeweegt in beoordeling. WOR27: mogelijk.
- **Gegevens:** profiel, eerdere verslagen. **Waar:** Word/papier, HR-pakket.
- **AI:** voorstellen.

### S5. Tevredenheidspeiling anoniem per team
- **Actor:** HR; medewerkers antwoorden.
- **Aanleiding:** jaarlijkse MTO of pulspeiling.
- **Gebruiker:** kiest vragen, teams, periode.
- **Systeem:** verstuurt, toont resultaten alleen als een team een minimumaantal respondenten
  heeft (gangbaar bij leveranciers; exacte drempel niet uit primaire bron vastgesteld), clustert
  open antwoorden.
- **Resultaat:** rapport per team + actiepunten.
- **Goedkeuring:** HR/directie over publicatie en acties.
- **Gevoeligheid:** AVG: anonimiteit in kleine teams is breekbaar (heridentificatie).
  AI Act: laag zolang het niet per persoon gaat. WOR27: waarschijnlijk.
- **Gegevens:** teamindeling, antwoorden. **Waar:** losse tools (Forms), HR-pakket.
- **AI:** samenvatten; nooit herleiden tot persoon.

### S6. Verzuimmelding en poortwachter-termijnen
- **Actor:** LG of medewerker meldt; HR beheert dossier; bedrijfsarts.
- **Aanleiding:** ziekmelding.
- **Gebruiker:** registreert melding (zonder diagnose).
- **Systeem:** meldt aan arbodienst, plant termijnen (week 6, 8, 42, 52, 88-93), herinnert, bouwt
  re-integratiedossier op; weigert velden voor aard/oorzaak ziekte [4](S)[9](S).
- **Resultaat:** volledig dossier, geen gemiste termijn.
- **Goedkeuring:** plan van aanpak door werkgever en werknemer samen; bedrijfsarts adviseert.
- **Gevoeligheid:** AVG-bijz.: HOOG (gezondheid; werkgever mag diagnose niet verwerken).
  WOR27: verzuimregeling. AI Act: 4b als het prestaties/gedrag gaat "monitoren".
- **Gegevens:** meldingsdatum, verwachte duur, bereikbaarheid. **Waar:** salaris-/HR-pakket, arbodienstportaal.
- **AI:** termijnen en herinneringen (regels); geen inhoudelijke oordelen over de zieke.

### S7. Onboarding nieuwe medewerker
- **Actor:** HR/office manager, LG, nieuwe medewerker.
- **Aanleiding:** contract getekend.
- **Systeem:** maakt checklist (ID-controle, loonheffingsverklaring, accounts, inwerkplan,
  buddy), stuurt taken, verzamelt documenten.
- **Resultaat:** medewerker is dag 1 productief; dossier compleet.
- **Goedkeuring:** HR controleert documenten.
- **Gevoeligheid:** AVG: BSN/ID-kopie met bewaartermijn [12](S). AI Act: laag.
- **Gegevens:** contract, persoonsgegevens. **Waar:** salarissysteem, mail.
- **AI:** voorstellen en uitvoeren van niet-persoonsrakende taken (checklist).

### S8. Contractverlenging en aanzegtermijn
- **Actor:** HR/eigenaar, LG.
- **Aanleiding:** tijdelijk contract loopt af.
- **Systeem:** signaleert ruim voor de aanzegdatum (1 maand voor einde, bij contract van 6
  maanden of langer), toont ketenstand, maakt conceptbrief [5][6].
- **Resultaat:** tijdige schriftelijke aanzegging.
- **Goedkeuring:** eigenaar/LG beslist verlengen ja/nee en tekent.
- **Gevoeligheid:** AI Act 4b: HOOG als AI adviseert over wel/niet verlengen op prestatie.
  AVG art. 22.
- **Gegevens:** contractdata. **Waar:** salarissysteem/Excel.
- **AI:** signaleren en conceptbrief; de keuze is van de mens.

### S9. Functioneringsgesprek plannen
- **Actor:** HR plant cyclus; LG voert.
- **Systeem:** plant per medewerker, stuurt voorbereidingsformulier, bewaakt dat verslagen
  getekend worden.
- **Resultaat:** volledige gesprekscyclus.
- **Gevoeligheid:** WOR27: beoordelingsregeling. AI Act 4b als AI beoordeelt.
- **Gegevens:** medewerkerslijst, LG, vorige verslagen. **Waar:** agenda, Word.
- **AI:** plannen en samenvatten; geen score toekennen.

### S10. Exitgesprek
- **Actor:** HR met vertrekkende medewerker.
- **Systeem:** stelt vragen voor, verzamelt antwoorden, aggregeert redenen over tijd.
- **Resultaat:** inzicht in verloopredenen; offboarding-checklist (spullen, accounts, getuigschrift).
- **Gevoeligheid:** AVG: bewaartermijn; anonimiseren bij rapportage. AI Act: laag.
- **AI:** samenvatten en aggregeren.

### S11. Verlofaanvraag en saldo
- **Actor:** MW vraagt, LG keurt.
- **Systeem:** toont saldo, botsingen met planning.
- **Gevoeligheid:** laag (zorgverlof kan gezondheid raken).
- **Gegevens/waar:** salaris-/HR-pakket. **AI:** voorstellen; LG keurt.

### S12. Verplichte certificaten bewaken
- **Actor:** HR/preventiemedewerker.
- **Aanleiding:** VCA, BHV, rijbewijs e.d. verlopen.
- **Systeem:** lijst met vervaldata, herinnering, koppeling aan S2.
- **Gevoeligheid:** laag; Arbo-relevant [10](S).
- **AI:** uitvoeren van herinneringen.

### S13. Vacaturetekst opstellen en sollicitanten afhandelen
- **Actor:** LG/HR.
- **Systeem:** concept vacature; registreert sollicitanten; verwijdert afgewezenen na 4 weken.
- **Gevoeligheid:** AI Act 4a: HOOG bij filteren/rangschikken van kandidaten [3].
- **AI:** tekst voorstellen; geen CV-ranking zonder volledige hoog-risico-maatregelen.

### S14. Personeelsplanning/ vervanging bij uitval
- **Actor:** LG.
- **Systeem:** stelt vervangers voor op basis van S1.
- **Gevoeligheid:** AI Act 4b ("taken toewijzen op basis van kenmerken"); Arbeidstijdenwet.
- **AI:** voorstellen.

### S15. HR-overzicht voor directie
- **Actor:** eigenaar/directie.
- **Systeem:** verzuim%, verloop, opleidingsuren, open termijnen, geaggregeerd.
- **Gevoeligheid:** AVG: aggregatie, geen herleidbare gezondheidsdata.
- **AI:** samenvatten.

### S16. Instemmingsaanvraag aan de OR voorbereiden
- **Actor:** directie/HR.
- **Aanleiding:** invoeren van dit HR-pakket zelf.
- **Systeem:** genereert beschrijving welke gegevens worden verwerkt, doelen, bewaartermijnen,
  wat AI wel/niet doet.
- **Gevoeligheid:** WOR27 sub k/l [8](S). DPIA waarschijnlijk nodig (niet vastgesteld).
- **AI:** concepttekst; directie dient in.

---

## 5. Overzicht gegevens, vindplaats, voorstellen/beslissen

| Scenario | Belangrijkste gegevens | Waar meestal (mkb) | AI mag |
|---|---|---|---|
| S1 vaardigheden | functies, certificaten | Excel, papier, HR-pakket | voorstellen |
| S2 opleiding | profiel, budget | Excel, boekhouding | voorstellen |
| S3 interne match | profielen, vacature | HR-pakket/Excel | voorstellen met uitleg |
| S4 loopbaan | eerdere verslagen | Word, HR-pakket | voorstellen |
| S5 peiling | antwoorden, teams | Forms, HR-pakket | samenvatten |
| S6 verzuim | meldingsdata (geen diagnose) | salarispakket, arbodienst | termijnen bewaken (regels) |
| S7 onboarding | contract, ID | salarissysteem, mail | checklist uitvoeren |
| S8 aanzeg | contractdata | salarissysteem, Excel | signaleren + concept |
| S9 functioneren | lijst, verslagen | agenda, Word | plannen |
| S10 exit | antwoorden | Word | samenvatten |
| S11 verlof | saldi | salarispakket | voorstellen |
| S12 certificaten | vervaldata | Excel | herinneren |
| S13 werving | CV's | mail, vacaturesite | tekst voorstellen |
| S14 planning | S1, rooster | roosterpakket | voorstellen |
| S15 dashboard | aggregaten | diverse | samenvatten |
| S16 OR | systeembeschrijving | - | concept |

Regel over alles heen: alles wat een persoon raakt (aannemen, verlengen, beoordelen,
promoveren, opleiding toewijzen, ontslag) beslist een mens. Dat volgt uit AVG art. 22
(geen uitsluitend geautomatiseerd besluit met rechtsgevolg) en uit de menselijke-toezichtplicht
voor hoog-risico-AI [3]. Let op: de hoog-risicoplichten van Annex III gaan volgens een
voorlopig politiek akkoord (7 mei 2026) pas op 2 december 2027 in, in plaats van 2 augustus 2026;
dat is nog geen gepubliceerde wet bij de bronnen [18](S).

**Gecorrigeerd na primaire bron:** het uitstel IS inmiddels wet. Verordening (EU) 2026/1744
(Digital Omnibus on AI), vastgesteld 8 juli 2026, gepubliceerd in PB L op 24 juli 2026, wijzigt
art. 113 AI Act: hoog-risicoplichten (hoofdstuk III) voor bijlage III-systemen gelden vanaf
2 december 2027, voor bijlage I-systemen vanaf 2 augustus 2028 [P4]. De tijdlijn van de
AI Act Service Desk van de Commissie noemt dezelfde data [P5]. Art. 26 lid 7 (werkgever informeert
werknemersvertegenwoordigers en betrokken werknemers VOORDAT een hoog-risico-AI-systeem op de
werkplek wordt gebruikt) is in de oorspronkelijke tekst gelezen [P3]; of 2026/1744 art. 26 wijzigt
is niet vastgesteld (tekst afgekapt bij ophalen).

---

## 6. Waarde voor de klant tegenover juridisch risico

**Meeste waarde om een mkb-klant over te halen (redenering, onderbouwd met pijnpunten in 3):**
1. **S8 aanzegtermijn + S6 poortwachter-termijnen** - direct geld (1 maandsalaris; loonsanctie
   tot 52 weken) en precies de termijnen die een eigenaar zonder HR mist [4](S)[5][6].
   Kanttekening: S6 raakt gezondheid; het moet zonder diagnose werken.
2. **S7 onboarding** en **S12 certificaten** - laag risico, zichtbaar tijdwinst, veel voorkomend.
3. **S1 + S2 vaardigheden en opleiding** - kern van het pakket, sluit aan op scholingsplicht
   [11](S); waarde vooral voor middelgroot.
4. **S5 peiling** - waardevol, maar anonimiteit in kleine teams is lastig.

**Hoogste juridisch risico:**
1. **S3 interne match en S13 kandidaatselectie** - kern-hoog-risico in AI Act 4a/4b [3].
2. **S8 als AI adviseert wel/niet verlengen**, en elke "prestatiescore" (S4/S9) - 4b + AVG art. 22.
3. **S6 verzuim** - AVG bijzondere gegevens; AP heeft al beboet [9](S).
4. **S14 taaktoewijzing op kenmerken** - expliciet in 4b [3].
5. Alles wat medewerkers volgt, bij een bedrijf met OR: zonder instemming nietig te maken
   (WOR27; consequentie niet in detail gemeten) [8](S).

Advies voor de pilot (redenering): begin met termijnbewaking (S6 zonder diagnose, S8, S12, S7)
en S1/S2 als "voorstellen"; houd S3/S13 als voorstel-met-uitleg zonder rangschikking tot de
hoog-risicomaatregelen staan.

---

## Bronnen

Primair/gezaghebbend:
- [3] EU AI Act, Annex III punt 4 (tekstweergave) - https://artificialintelligenceact.eu/annex/3/
- [5] Rijksoverheid, Wat is een aanzegtermijn - https://www.rijksoverheid.nl/onderwerpen/arbeidsovereenkomst-en-cao/vraag-en-antwoord/wat-is-een-aanzegtermijn
- [6] Ondernemersplein (KVK/overheid), aanzegtermijn en vergoeding - https://ondernemersplein.overheid.nl/wetten-en-regels/aanzegtermijn-voor-tijdelijke-werknemers/ en https://ondernemersplein.overheid.nl/wetten-en-regels/vergoeding-betalen-voor-het-missen-van-de-aanzegtermijn/
- [15] CBS, ziekteverzuim naar bedrijfsgrootte - https://www.cbs.nl/nl-nl/cijfers/detail/80072ned en https://www.cbs.nl/nl-nl/nieuws/2026/23/ziekteverzuim-in-eerste-kwartaal-hoger-dan-gemiddeld-in-afgelopen-30-jaar

Secundair (S):
- [4] Grant Thornton, langdurige ziekte verplichtingen - https://www.grantthornton.nl/insights/legal-services/langdurige-ziekte-werknemer-jouw-verplichtingen-op-een-rij/ ; Salaris van Morgen stappenplan - https://www.salarisvanmorgen.nl/2024/11/21/stappenplan-zieke-werknemer-zet-stappen-en-datums-in-jouw-agenda/
- [7] AFAS help, Wet verbetering poortwachter - https://help.afas.nl/help/nl/se/Hrm_Sick_PW.htm
- [8] OR-instemming en privacy (WOR 27 k/l) - https://www.rendement.nl/or-en-digitale-veiligheid/nieuws/welke-invloed-heeft-or-op-de-privacy-van-werknemers.html ; https://www.aiactblog.nl/nl/posts/or-instemmingsrecht-ai-op-de-werkvloer
- [9] Gezondheidsgegevens zieke werknemers (AP-lijn, boete) - https://www.taxlive.nl/nl/documenten/nieuws/onderhoudsbedrijf-krijgt-boete-om-privacyschending-zieke-werknemers/ ; https://www.salarisvanmorgen.nl/2019/10/08/persoonsgegevens-zieke-werknemers-verwerken-wat-mag-niet/
- [10] RI&E, basiscontract, preventiemedewerker - https://www.moore-drv.nl/wat-is-een-ri-e-en-hoe-stelt-u-deze-op/ ; Arboportaal basiscontract (genoemd, niet zelf geopend)
- [11] Scholingsplicht 7:611a - https://www.awvn.nl/arbeidsovereenkomst/hr-van-a-tot-z/scholingsplicht-studiekosten/ ; https://www.hrpraktijk.nl/juridisch/wet-en-regelgeving/belang-scholing-onder-de-wwz/
- [12] Bewaartermijnen - https://www.ondernemenmetpersoneel.nl/administreren/privacywet-avg/bewaartermijnen-personeelsdossier-werknemersgegevens
- [13] OR/PVT drempels - https://www.awvn.nl/medezeggenschap/hr-van-a-tot-z/medezeggenschap-de-ondernemingsraad/ ; https://ondernemenmetpersoneel.nl/orienteren/ondernemingsraad/een-ondernemingsraad-verplicht
- [14] Mkb-tijdsbesteding (Van Spaendonck, Mercer Direct) - https://www.accountant.nl/nieuws/2026/2/digitale-hr-buddy-moet-mkb-ondernemer-helpen-bij-uitvoeren-hr-beleid/ ; https://files.exact.com/static/web/downloads/NL-HR-Whitepaper-HR-in-het-mkb.pdf
- [16] "Het mkb runt HR nog via WhatsApp en Excel" - https://mtsprout.nl/partners/het-mkb-runt-hr-nog-via-whatsapp-en-excel (403 bij ophalen; alleen titel gezien)
- [17] Leveranciersoverzichten (Loket.nl, Nmbrs, Factorial) - https://www.ordio.com/nl/insights/ratgeber/hrm-software ; https://peoplemanagingpeople.com/nl/tools/factorial-beoordeling/
- [18] AI Act-uitstel Digital Omnibus - https://www.aiactblog.nl/nl/posts/digital-omnibus-uitstel-high-risk-december-2027 ; https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/
- CIPD over interne mobiliteit - https://www.cipd.org/en/knowledge/podcasts/internal-mobility

---

## Wat niet vastgesteld kon worden

- Wetteksten zelf (wetten.overheid.nl WOR, BW) gaven 404 bij ophalen; WOR 27 en BW 7:611a/7:634
  zijn via secundaire bronnen weergegeven.
- Rijksoverheid-pagina over werkgeversplichten bij ziekte gaf 404; poortwachter-termijnen komen
  uit secundaire bronnen (onderling consistent).
- Geen NVP-, SHRM- of UWV-primaire bron daadwerkelijk geopend; CIPD alleen globaal.
- Geen onafhankelijke meting van tijdwinst door AI in NL-mkb-HR gevonden.
- Exacte anonimiteitsdrempel per leverancier (Personio, HiBob, AFAS) niet gevonden.
- Of de AI Act-uitsteldatum (2 dec 2027) inmiddels formeel gepubliceerd is: niet vastgesteld.
  **Gecorrigeerd na primaire bron:** ja, Verordening (EU) 2026/1744, PB 24 juli 2026 [P4].
- Stand NL-implementatie EU-loontransparantierichtlijn: niet onderzocht.
- Of een DPIA verplicht is voor dit pakket: waarschijnlijk, niet vastgesteld.
- Functieoverzichten van Visma|Raet/Youforce, Personio, HiBob, BambooHR niet per leverancier geopend.
  (Tweede ronde: Personio en HiBob wel bekeken, zie hieronder.)

---

## Tweede ronde: primaire bronnen (2026-10-09)

Alle bronnen geraadpleegd op 2026-10-09 met WebFetch/WebSearch. "Niet gevonden" = de bron kon
niet worden geopend of de bewering stond er niet in; reden erbij.

| Bewering | Bron-URL | Uitslag |
|---|---|---|
| Probleemanalyse binnen 6 weken na eerste ziektedag (Regeling art. 2) | https://wetten.overheid.nl/BWBR0013540 [P1] | bevestigd |
| Plan van aanpak "uiterlijk week 8" | idem, art. 4 lid 1; https://www.uwv.nl/nl/ziek/loondoorbetaling/plan-van-aanpak [P2] | **gecorrigeerd**: binnen 2 weken NA de probleemanalyse, geen vaste week; UWV zegt hetzelfde en noemt ook minstens 1x per 6 weken voortgangsgesprek |
| Eerstejaarsevaluatie rond week 52 | BWBR0013540 art. 4 lid 2 sub b; art. 6 lid 1 sub h (onderdeel re-integratieverslag) | bevestigd ("aan het einde van het eerste ziektejaar") |
| Ziekmelding UWV na week 42 | UWV-zoekresultaat (uwv.nl, "uiterlijk de eerste werkdag na de 42e ziekteweek") | bevestigd via UWV-zoekfragment; pagina en Ziektewet-artikel niet zelf geopend |
| Re-integratieverslag/WIA rond week 88-93 (eindevaluatie week 91) | https://www.uwv.nl/nl/ziek/re-integratie/verslag ; UWV-zoekfragment | deels: "eindevaluatie in week 91" alleen in zoekfragment; week 93 WIA-aanvraag niet gevonden in primaire tekst |
| Loonsanctie tot 52 weken | UWV-zoekfragment ("loonsanctie van maximaal een jaar") | bevestigd via zoekfragment; WIA-artikel niet geopend |
| Werkgever mag aard/oorzaak ziekte niet vragen/registreren | AP, https://www.autoriteitpersoonsgegevens.nl/en/themes/employment-and-benefits/sick-employees en .../registration-in-an-absenteeism-system [P6] | bevestigd via AP-zoekfragmenten (AP-pagina's gaven 403 bij direct openen); alleen bedrijfsarts mag medische gegevens verwerken; werkgever mag o.a. verwachte duur en lopende afspraken vragen |
| AP-boete zieke werknemers (bedrag 15.000 euro) | https://autoriteitpersoonsgegevens.nl/nl/nieuws/boete-voor-cpa-om-privacyschending-zieke-werknemers | niet gevonden: 403. Het bedrag blijft secundair [9](S) |
| AP over monitoring: gerechtvaardigd belang, informeren, OR-instemming vooraf, DPIA bij systematische monitoring | https://autoriteitpersoonsgegevens.nl/en/themes/employment-and-benefits/monitoring-employees/conditions-for-monitoring-employees [P7] | bevestigd via AP-zoekfragmenten; bevestigt ook dat DPIA nodig is bij grootschalige/systematische monitoring (raakt S5/S9/S14) |
| Sollicitanten uiterlijk 4 weken na procedure verwijderen, met toestemming max 1 jaar | NVP Sollicitatiecode https://www.nvp-hrnetwerk.nl/l/library/download/urn:uuid:c902b6f9-dcac-4c26-9a13-8b90f4d2fe5f/mos25068+brochure+sollicitatiecode+online.pdf ; AP https://autoriteitpersoonsgegevens.nl/nl/onderwerpen/werk-uitkering/sollicitaties [P8] | bevestigd (via zoekfragmenten van NVP en AP) |
| AI Act bijlage III punt 4 a/b | https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:32024R1689 | niet gevonden: EUR-Lex-pagina (561k tekens) werd afgekapt voor de bijlagen; blijft [3] (tekstweergave) |
| AI Act art. 26 lid 7: werknemers en hun vertegenwoordigers vooraf informeren | idem [P3] | bevestigd, letterlijk gelezen |
| Hoog-risicodatum verschoven naar 2 dec 2027, "nog geen wet" | https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng [P4]; https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act [P5] | **gecorrigeerd**: wel wet, Verordening (EU) 2026/1744, PB 24 juli 2026 |
| Aanzegtermijn/-vergoeding BW 7:668 | wetten.overheid.nl BWBR0005290 (diverse URL-varianten) | niet gevonden: pagina laadt heel boek 7 en werd afgekapt voor titel 10; blijft Rijksoverheid/Ondernemersplein [5][6] |
| BW 7:629 (104 weken), 7:658a, 7:653, 7:673 | idem | niet gevonden (zelfde reden) |
| Arbowet (RI&E), AVG art. 9/88, UAVG, WOR 27 lid 1 sub l, AWR art. 52 (7 jaar), Wet arbeid vreemdelingen (ID-kopie 5 jaar) | - | niet opgehaald in deze ronde; blijven secundair [8][10][12] |
| Kern-HR-taken (bevestiging 17 taakgebieden) | Personio https://www.personio.nl/hr-woordenboek/hrm-systeem/ ; HiBob https://www.hibob.com/nl/ ; NVP https://www.nvp-hrnetwerk.nl/en/ | bevestigd op hoofdlijnen: Personio noemt personeelsadministratie, documenten, verlof, verzuim, onboarding, werving, performance, rapportage; HiBob daarnaast learning, enquetes, beloning/compensatie, personeelsplanning, payroll-koppeling; NVP noemt HR-strategie, arbeidsrelaties, werving en selectie, beloning, arbeidsvoorwaarden, opleiding. Geen van drieen noemt OR/medezeggenschap of compliance als module (bij ons wel apart; dat is een wettelijk, geen softwaregebied) |

Primaire bronnen tweede ronde:
- [P1] Regeling procesgang eerste en tweede ziektejaar - https://wetten.overheid.nl/BWBR0013540
- [P2] UWV, Plan van aanpak - https://www.uwv.nl/nl/ziek/loondoorbetaling/plan-van-aanpak
- [P3] Verordening (EU) 2024/1689, NL - https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:32024R1689
- [P4] Verordening (EU) 2026/1744 (Digital Omnibus on AI) - https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng
- [P5] AI Act Service Desk, tijdlijn - https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act
- [P6] AP, zieke werknemers - https://www.autoriteitpersoonsgegevens.nl/en/themes/employment-and-benefits/sick-employees
- [P7] AP, monitoring - https://autoriteitpersoonsgegevens.nl/en/themes/employment-and-benefits/monitoring-employees/conditions-for-monitoring-employees
- [P8] AP, sollicitaties - https://autoriteitpersoonsgegevens.nl/nl/onderwerpen/werk-uitkering/sollicitaties

Nog open na ronde 2: wetteksten BW boek 7 (technisch niet op te halen), Arbowet, UAVG, AWR,
Wet arbeid vreemdelingen, WOR art. 27; UWV-weekschema (stappenplan-pagina is een invultool zonder
tekst; Werkwijzer-PDF niet leesbaar te maken zonder extra pakket).

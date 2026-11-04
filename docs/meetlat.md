# De meetlat: wanneer zeggen we "het werkt"?

> **Auteur: Rakesh. Vastgelegd 2026-09-27.** Dit document is van de opdrachtgever en is de
> maatstaf voor "productieklaar". Een agent past het niet aan zonder zijn woord; een agent
> voegt hooguit gemeten stand toe in een aparte sectie onderaan.
>
> Alleen de opmaak is aangepast aan de ASCII-regel van het project (pijlen als `->`,
> letters zonder puntjes). De inhoud is ongewijzigd.

Regel: een feature "werkt" pas als een klant het hele pad zelfstandig kan doorlopen,
van inloggen tot bruikbaar eindresultaat. Niet "de code staat er", niet "de test is groen".
Elke feature hieronder eindigt met een **klaar-als** die Rakesh zelf kan toetsen
(klikken in de app), zonder technische hulp.

## 0. De harde poort (moet dicht voor elke klant)

Dit staat zo ook in `docs/prod-readiness.md` (PHASE 0) en het ADR-036-register:

1. De vijf P0-autorisatielekken (OP-182 t/m OP-186) zijn gesloten met machineleesbaar bewijs.
2. De acceptatieketen (`python scripts/acceptance_thread.py`) staat op 7 van 7.
3. Uitloggen maakt een toegangstoken echt ongeldig (OP-188).
4. De volledige testpoort is groen (laatste meting: 16.985 tests geslaagd).
5. De auditketencontrole draait dagelijks en is groen.
6. Een hersteltest vanaf een backup is minstens een keer echt uitgevoerd.

Zolang punt 1 en 2 open staan, mag geen enkele externe klant op welke omgeving dan ook.
Dat is geen meningsverschil maar een poortregel die al vastligt.

## 1. Vier klanttypen (persona's)

| Persoon | Wie | Wat wil die |
|---|---|---|
| **Fatima** | ZZP'er (freelancer) | Bonnen en facturen zelf regelen, weten wat ze aan belasting moet denken |
| **Jeroen** | MKB-eigenaar | Debiteuren, webshop en administratie deels automatiseren |
| **Sanne** | Bedrijfsbeheerder | Medewerkers uitnodigen, rollen geven, bijhouden wat de agents doen |
| **Mark** | Compliance-verantwoordelijke | Bewijs leveren: wie deed wat, wanneer, en waarom die agent dat deed |

Elke feature hieronder wordt getoetst vanuit minstens een van deze vier.

---

## 2. Basispad: van niets naar eerste resultaat

### Scenario 1 -- Registreren, inloggen, uitloggen

1. Fatima opent de site en maakt een account aan.
2. Haar eigen klantomgeving (tenant) wordt automatisch aangemaakt en netjes ingericht.
3. Ze logt in, krijgt een duidelijk beginscherm en snapt waar ze moet zijn.
4. Ze logt uit op een gedeelde computer en logt opnieuw in op haar telefoon.
5. Ze gebruikt "wachtwoord vergeten" en komt weer binnen zonder ons te mailen.

**Klaar als:** een nieuwe klant binnen tien minuten, zonder hulp, ingelogd is en
haar eerste taak heeft ingetikt. Uitloggen op de ene plek sluit de andere plek
niet onverwacht uit, en een verloren sessie kan geen kwaad meer.

### Scenario 2 -- De kernbelofte: een taak in gewone taal

1. Fatima typt: "Maak een factuur voor 8 uur werk aan Van den Berg tegen 85 euro per uur."
2. Het platform kiest zelf de juiste agent (factuuragent).
3. Ze krijgt binnen redelijke tijd een bruikbaar resultaat: een conceptfactuur met
   naam, bedrag, btw en uitleg waarom het er zo uitziet.
4. Ze vraagt: "waarom heb je 21% btw gerekend?" en krijgt een begrijpelijk antwoord.
5. Ze typt onzin of iets onmogelijks en krijgt een nette, begrijpelijke melding --
   geen technische foutpagina.

**Klaar als:** tien voorbeeldtaken uit minstens drie pakketten (zzp, mkb, enterprise)
eindigen met een bruikbaar resultaat, en elke agentuitslag terug te vragen is met "waarom".

### Scenario 3 -- Eigen kennis toevoegen (de agent leest je documenten)

1. Jeroen uploadt zijn algemene voorwaarden en prijslijst.
2. Hij vraagt: "Welke betalingstermijn geldt voor bestellingen boven 1000 euro?"
3. De agent antwoordt uit zijn eigen document en **toont het stukje bron** waarop het antwoord staat.

**Klaar als:** het antwoord aantoonbaar uit het geuploade document komt, met verwijzing
naar de plek in dat document. Antwoorden zonder bron mag de agent niet geven op dit onderwerp.

### Scenario 4 -- Automatisering bouwen (meerdere stappen aan elkaar)

1. Jeroen bouwt in de workflowbouwer: "Elke maandag: haal openstaande facturen op,
   stel een herinnering op, en stuur die naar de klant."
2. Hij draait de workflow met de hand om te testen en ziet per stap of die gelukt is.
3. Hij laat de workflow 's nachts draaien. Een stap faalt.
4. 's Ochtends ziet hij precies welke stap faalde, waarom, en kan die ene stap opnieuw draaien.

**Klaar als:** een meerdere-stappen-workflow 24 uur onbeheerd draait, de klant achteraf
kan zien wat er is gebeurd, en een mislukte stap opnieuw kan zonder de hele workflow te hertellen.

### Scenario 5 -- Mensen-goedkeuring bij riskante acties

1. De debiteurenagent wil een dreigbrief sturen (riskant).
2. Jeroen krijgt een goedkeurverzoek met duidelijke tekst: wat er gebeurt, aan wie, met welke inhoud.
3a. Hij keurt goed: de actie wordt exact zo uitgevoerd, niets meer.
3b. Hij keurt af: de actie wordt echt niet uitgevoerd en de agent meldt netjes dat hij wacht.
4. Elke goed- of afkeuring staat met tijdstip in het log.

**Klaar als:** afkeuren de actie echt stopt en goedkeuren exact de getoonde actie uitvoert.

### Scenario 6 -- Medewerkers en rechten beheren

1. Sanne nodigt een medewerker uit per e-mail.
2. Ze geeft hem de rol "administratie": die mag facturen zien en bonnen inboeken, maar
   geen workflows bouwen en geen andere medewerkers beheren.
3. De medewerker logt in en ziet alleen wat zijn rol toelaat.
4. Sanne trekt een recht in. De medewerker merkt dat direct bij zijn volgende klik --
   niet pas na een uur, niet na opnieuw inloggen.

**Klaar als:** rechten aansluiten bij wat de klant verwacht, intrekken direct werkt, en
een medewerker van het ene bedrijf nooit iets van een ander bedrijf kan inzien --
ook niet via een omweg (andere pagina, directe link, export).

### Scenario 7 -- Inzage, export en verwijderen (privacy)

1. Mark opent het logboek en ziet per gebeurtenis: wie, wat, wanneer, met welk resultaat.
2. Hij filtert op een agent en op een datum en exporteert dat overzicht.
3. Een klant vraagt om een export van al zijn data (recht op dataportabiliteit) en krijgt
   binnen redelijke tijd een compleet bestand.
4. Een klant vraagt om verwijdering van zijn data (recht op vergetelheid) en die is daarna
   echt weg, ook uit de logs waar het mag, met bewijs van verwijdering in het logboek.

**Klaar als:** inzage, export en verwijderen zonder onze tussenkomst werken, en het
logboek zelf dagelijks automatisch wordt gecontroleerd op geldigheid (groen).

### Scenario 8 -- Controle over de agents (governance)

1. Sanne opent het overzicht: welke agents staan aan, en welke gereedschappen mag elke agent gebruiken.
2. Ze haalt bij de webshopagent het recht weg om e-mails te versturen.
3. Een "raad" van agents keurt iets goed dat Sanne niet zint; het systeem legt vast
   waarom dat besluit viel zoals het viel, en Sanne kan het overrulen.

**Klaar als:** de klant begrijpt welke bevoegdheden elke agent heeft, die kan begrenzen,
en elk automatisch besluit van betekenis een naleesbare reden heeft plus een menselijke
rem.

### Scenario 9 -- Geld en verbruik

1. Fatima ziet op haar beginscherm hoeveel ze heeft verbruikt en wat haar dat kost.
2. Ze ziet per taak of per dag wat er is gedraaid en wat dat kostte.
3. Ze stelt een limiet in ("stopt erboven") en het platform stopt dan ook echt.

**Klaar als:** het overzicht van verbruik klopt met de werkelijkheid en de limiet echt afdwingt.

### Scenario 10 -- Als het fout gaat

1. De dienst valt even weg terwijl een taak draait.
2. Fatima krijgt een nette melding, geen kale technische fout.
3. Na herstart is haar data er nog; de taak wordt netjes opnieuw opgepakt of netjes
   als mislukt gemeld met de mogelijkheid om opnieuw te starten.

**Klaar als:** uitval en herstart geen dataverlies geven en de klant altijd weet
wat de stand van zaken is.

---

## 2b. De copilot als werktafel (de voordeur van het product)

De copilot is geen bijzaak: het is hoe de klant het platform gebruikt. Alles hierboven
moet ook via de copilot kunnen. Vandaag bestaat hij in de bouw als een gereguleerd
ingangspunt (elke actie langs de raad van agents, met uitleg, met menselijke rem).

### Scenario 11 -- Praten met de copilot als in een gewoon gesprek

1. Fatima opent de chat en vraagt in gewone taal iets over haar zaak. Het antwoord is
   een gesprek, geen handleiding: kort, in haar taal, met uitleg waar nodig.
2. Ze vraagt door ("en voor november?") -- het gesprek onthoudt waar ze was.
3. De copilot doet voorstellen ("zullen we deze drie facturen opstellen?") en wacht
   op haar ja of nee. Gevoelige acties vragen altijd eerst toestemming (scenario 5).
4. Ze kan elk antwoord terugvragen ("waarom stel je dit voor?") en krijgt een
   begrijpelijke reden. De copilot legt zichzelf open als AI.

**Klaar als:** een klant zijn dagelijkse werk via de chat doet zonder handleiding,
de voorstellen vaker kloppen dan niet, en elk antwoord een "waarom"-knop heeft.

### Scenario 12 -- Zelfstandig workflows bouwen, afdelingsbreed en bedrijfsbreed

1. Jeroen beschrijft in gewone taal wat hij wil: "Elke vrijdag: verkoopcijfers
   verzamelen, debiteuren bellen die te laat zijn, en mij een samenvatting sturen."
2. De copilot stelt een workflow voor met zichtbare stappen en de agents die erbij
   horen (binnen een afdeling: verkoop). Jeroen leest de stappen in gewone taal.
3. Hij past aan ("maandag in plaats van vrijdag"), keurt goed, de workflow draait.
4. Later maakt Sanne een bedrijfsbrede: inkoop -> voorraad -> verkoop -> facturatie,
   over meerdere afdelingen heen, met een overzicht en een aan/uit-knop.
5. Wie zo'n workflow mag aanpassen, bepaalt het rechtenstelsel (scenario 6) --
   een afdelingshoofd mag binnen zijn afdeling, niet daarbuiten.

**Klaar als:** een niet-technische klant vanuit een beschrijving een werkende
workflow krijgt die over afdelingen heen loopt, per stap zichtbaar is, en op de
gevoelige stappen menselijke goedkeuring vraagt.

### Scenario 13 -- Procesbewaking en agenda zonder handwerk

1. Een proces loopt vast (wachtrij groeit, agent valt uit, afwijking in het logboek):
   de copilot merkt het zelf op en waarschuwt Jeroen met een concrete suggestie
   ("stap drie opnieuw starten?") -- voordat het werk stilstaat.
2. Een toestemming van een klant loopt bijna af: het systeem stelt voor die te
   vernieuwen en wacht op bevestiging.
3. De agenda-agent beschermt focusblokken, maakt notulen van vergaderingen en
   zet vervolgacties klaar als taken.

**Klaar als:** de klant problemen bijna altijd van het platform zelf hoort, met een
bruikbare suggestie erbij, en de agenda-ondersteuning werkt zonder handwerk.

---

## 2c. Uit de ADR's: pagina's, budget en afspraken tussen agents

ADR-032 is de alleenheersende lijst van wat de applicatie bevat. Daar zitten
functies bij die een klant rechtstreeks raken en die hier hun eigen scenario krijgen.

### Scenario 14 -- Proberen zonder account, en binnenkomen zonder verwarring

1. Een bezoeker opent de demo en probeert het product zonder account (beperkt,
   beveiligd tegen misbruik).
2. Fatima maakt een account; na haar eerste login voert de onboarding haar in
   stappen naar haar eerste resultaat: taal kiezen, pakket kiezen, eerste taak doen.

**Klaar als:** een bezoeker na de demo snapt wat het product voor hem kan doen,
en een nieuwe klant na de eerste login zonder verdwaald te raken bij haar eerste
werkende taak komt.

### Scenario 15 -- Kennis, planning en zandbak

1. Kennis: Jeroen vindt de antwoorden en documenten van zijn bedrijf terug op de
   kennispagina; zoeken levert het juiste stuk, met de bron erbij.
2. Planning: wat er gepland staat (taken, agent-runs, agenda) is zichtbaar -- en
   wat er staat, gebeurt ook.
3. Zandbak: Sanne bouwt en test een automatisering in een oefenomgeving waar niets
   echt gebeurt (geen echte e-mails, geen echte betalingen); pas na haar keuring
   zet ze hem over naar echt.

**Klaar als:** deze drie pagina's bruikbaar zijn voor niet-technici, en de zandbak
echt niets kan breken.

### Scenario 16 -- Zelf pakketten en persona's regelen

1. Jeroen opent de domain packs en activeert zelf het MKB-pakket; de bijbehorende
   agents verschijnen bruikbaar in zijn omgeving, zonder tussenkomst van ons.
2. Hij stelt de persoonlijkheid van de copilot in (toon, stijl, taal) zodat die
   past bij zijn bedrijf; medewerkers merken dat in alle gesprekken.

**Klaar als:** een beheerder zelf pakketten aan- en uitzet en de copilot zonder
technische hulp naar de hand van het bedrijf zet.

### Scenario 17 -- Budget per afdeling

1. Sanne ziet per afdeling de dagelijkse begroting, het verbruik en wat welke
   taken kosten.
2. Loopt een afdeling bijna leeg? Ze krijgt vooraf een seintje. Is hij leeg?
   Die afdeling stopt eerlijk, zonder andere afdelingen te raken; de beheerder
   kan bijsturen.
3. Elk stukje verbruik is herleidbaar: welke taak kostte wat.

**Klaar als:** de begroting klopt, de waarschuwing komt voor de stop, en bijsturen
direct werkt.

### Scenario 18 -- Agents die afspraken met elkaar maken

1. Twee agents maken een afspraak over wie wat levert en wanneer (bijvoorbeeld
   offerte-agent en factuur-agent); Jeroen ziet dat contract met stappen, deadline
   en onderpand.
2. De afspraak verloopt: opgeleverd wordt afgerekend; mislukt wordt opnieuw geprobeerd,
   en na drie keer netjes mislukt, met terugbetaling van het onderpand.

**Klaar als:** de klant elk lopend contract kan zien en begrijpen wat er staat te
gebeuren, en geen contract voor altijd "hangend" blijft staan.

### Scenario 19 -- Persoonlijke leer-twin met toestemming

1. Fatima geeft toestemming (of juist niet) voor persoonlijke voorkeuren; het
   platform past daardoor voorstellen aan ("vorige keer koos je dit").
2. Ze ziet wat het platform over haar weet, kan het pauzeren en kan het laten wissen;
   na wissen is het ook echt weg.

**Klaar als:** de personalisatie voordelig is, uitschakelen direct werkt, en inzage
en wissen zonder hulp kunnen.

---

## 3. Gecombineerde scenario's (de echte meetlat)

Een feature los werken is nodig maar niet genoeg. De belofte is de keten.

### Keten A -- Fatima's maandafsluiting, zonder handen

Foto van een bon uploaden -> de bonnenagent leest hem uit -> de boekingsagent
deelt hem in -> de factuuragent maakt de maandfacturen -> de belastingagent schat
de te reserveren belasting -> alles landt overzichtelijk in haar dashboard.
Elke stap is terug te kijken; elke twijfel is met "waarom" te verklaren.

**Klaar als:** deze hele keten bij een echte, ongeoefende ZZP'er zonder hulp draait
en elk tussenresultaat klopt.

### Keten B -- Jeroen's debiteuren, met rem erop

De debiteurenagent stelt een betaalherinnering op -> de herinnering is riskant dus
Jeroen krijgt hem te zien voor verzending -> hij keurt goed -> de brief gaat -> de
workflow controleert later of er is betaald -> bij betaling sluit de zaak zichzelf,
bij niet-betaling escaleert het netjes. Alles staat in het logboek, Mark kan het
in een overzicht volgen.

**Klaar als:** geld-rakende acties nooit zonder menselijke rem gaan, en de opvolging
tot aan betaling of escalatie vanzelf loopt.

### Keten C -- Sanne en Mark samen: nieuwe medewerker, beheerlijk en aantoonbaar

Sanne maakt een account voor een nieuwe administratief medewerker met minimale rechten ->
de medewerker laat een agent bonnen inboeken -> Mark toetst later: welke agent, welke
documenten, welke uitslagen, welke goedkeuringen, wat kostte het. Hij exporteert dat
als bewijs.

**Klaar als:** een klant aantoonbaar kan verantwoorden wie wat heeft laten doen,
wat het kostte, en welke menselijke beslissingen er lagen.

### Keten D -- Twee bedrijven door elkaar (isolatie onder druk)

Twee klanten werken tegelijk, opdrachten kruisen elkaar, de ene klant probeert expres
(bij de test: wijzelf, als aanvalstest) bij de ander te komen via alle denkbare omwegen.

**Klaar als:** geen enkel pad -- normaal, per ongeluk of met opzet -- data van de ene
klant bij de andere toont. Dit is het scherpste punt van de hele meetlat en precies
waar de open P0-cluster om draait.

### Keten E -- Jeroen's week, met de copilot als regisseur

Maandagochtend: de copilot geeft een samenvatting van het weekend (wat heeft gedraaid,
wat is er misgegaan). Woensdag: een signaal dat de verkoopworkflow vastloopt, met
een klik hersteld en keuring vastgelegd. Vrijdag: de bedrijfsbrede workflow maakt
de weekrapportage; Jeroen hoeft alleen goed te keuren wat geld of klanten raakt.
Alles is in het logboek terug te kijken, ook door Mark.

**Klaar als:** de copilot het overzicht houdt, Jeroen alleen keurt wat er toe doet,
en niemand meer "even in het systeem kijken hoe het gaat" hoeft te doen.

### Keten F -- Jeroen's crediteuren, betalen met rem erop

*Toegevoegd 2026-10-23 door de regie, in opdracht van Rakesh ("beide ja", daarna "ik geef je opdracht om het te doen").*

Een inkoopfactuur komt binnen (Jeroen uploadt hem of stuurt hem door per mail) -> het
platform leest leverancier, bedrag en vervaldatum -> een medewerker controleert het ->
een goedkeurder keurt de betaling goed; boven een ingesteld bedrag zijn twee mensen nodig
-> het platform maakt een betaalbestand dat Jeroen bij zijn bank inleest (SEPA) -> na het
bankafschrift staat de factuur vanzelf op "betaald". Alles staat in het logboek.

**Klaar als:** geen betaling zonder menselijke goedkeuring (en vier ogen boven het
ingestelde bedrag) het betaalbestand in komt, het betaalbestand door de bank wordt
geaccepteerd, en een betaalde factuur na het bankafschrift zonder handwerk sluit.

### Keten G -- Een eigen workflow met een AI-agent als stap

*Toegevoegd 2026-10-23 door de regie, in opdracht van Rakesh (zie Keten F).*

Een medewerker bouwt in het workflowscherm zelf een workflow en kiest daarin een AI-agent
als stap (bijvoorbeeld "vat deze klantvraag samen en maak er een taak van") -> hij start
de workflow -> de gekozen agent voert de stap echt uit, met alleen de rechten van de
medewerker die hem startte -> de uitkomst en elke stap zijn terug te kijken.

**Klaar als:** de gekozen agent (niet een andere) de stap uitvoert, nooit meer mag dan de
starter, een geweigerde of mislukte stap een begrijpelijke Nederlandse reden geeft, en dit
bij een ongeoefende medewerker zonder hulp werkt.

### Keten H -- Koppelingen inrichten

*Toegevoegd 2026-10-24 door de regie, in opdracht van Rakesh ("ja" op de voorgelegde tekst).*

Een beheerder van een nieuwe klant richt bij de start een koppeling in met een programma
dat de klant al gebruikt (bijvoorbeeld mail of boekhouding): hij kiest het programma, logt
in, test en ziet "werkt". Een medewerker kan een koppeling niet wijzigen of weghalen.
Gebruikt een agent de koppeling om iets naar buiten te sturen, dan wacht dat eerst op
goedkeuring, en daarna staat het in het logboek.

**Klaar als:** met beeld van de draaiende applicatie: de beheerder richt een koppeling in en
de test is groen; een medewerker krijgt een weigering als hij de koppeling wil weghalen; een
agentactie via de koppeling staat eerst in de goedkeurwachtrij en daarna in het logboek.

---

## 4. Onder de waterlijn (klant ziet het niet, meetlat wel)

- De vijf P0-lekken dicht, in die volgorde, met meetbare bewijsstukken (zie prod-readiness).
- Alle rechtenbeslissingen gaan door een deur; de snelle permissiecache blijft weg.
- De auditketen klopt van begin tot eind en wordt dagelijks gecontroleerd.
- Backups draaien en een herstel is minstens een keer echt getest, niet alleen gepland.
- Er staat een handleiding voor de klant in gewone taal (geen technisch Nederlands).
- Er staat een "wat doet de klant als..."-boekje: wachtwoord kwijt, agent geeft raar antwoord,
  rekening klopt niet, dienst is eruit.
- **On-premise variant** (ADR-035): een klant, eigen installatie, klant beheert zelf.
  Er is een installatiehandleiding in gewone taal; een klant met een eigen ICT'er kan
  het draaiend krijgen zonder dat wij meekijken. De eerste vraag daarnaar bestaat al.
- **Ons eigen portaal** (`/admin`): wij kunnen klanten, pakketten en gebruikers beheren
  vanuit een scherm, niet door in de database te kijken.

---

## 5. Samengevat: wanneer zeggen we "het werkt"

We zeggen "het werkt" pas als alle zes hieronder waar zijn:

1. **De poort is dicht** -- de zes punten uit paragraaf 0.
2. **Elke feature hierboven heeft zijn klaar-als gehaald**, getest door iemand die
   de app alleen met de muis bedient.
3. **De vijf ketens (A t/m E) draaien van begin tot eind** bij echte proefklanten
   (vrienden/kennissen van Rakesh, geen technici) -- waarvan keten E (copilot als
   regisseur) de belangrijkste is, want die voert de rest aan.
4. **Een proefklant komt binnen, doet zijn werk, en vertrekt zonder ons te bellen.**
5. **Als er iets misgaat, ziet de klant het zelf en kan hij zelf herstellen of netjes stoppen.**
6. **Niemand van buitenaf kan bij een andere klant** -- bewezen met een echte aanvalstest.

De eenvoudigste versie van de meetlat, in een zin:

> **Het werkt als een klant die ons niet kent, via de copilot zijn echte werk doet,
> de voorstellen vertrouwt omdat elke stap te verklaren is, en er achteraf aan kan
> tonen wat er is gebeurd.**

---

## 6. Gemeten stand op de harde poort -- 2026-09-27

> Deze sectie is toegevoegd door de agent en bevat metingen, geen meningen. Elk getal
> komt uit een commando dat genoemd staat. De rest van dit document is van Rakesh.

| # | Eis uit paragraaf 0 | Gemeten stand |
|---|---|---|
| 1 | De vijf P0-lekken dicht | Het register meldt alle vijf GESLOTEN: OP-182 en OP-183 op 2026-09-12, OP-184 en OP-185 op 2026-09-11, OP-186 op 2026-09-15. **Niet nagetoetst** -- "het register zegt gesloten" is geen bewijs dat het dicht is. |

**Belangrijk bij eis 1: het cluster is groter dan de vijf.** `.claude/WORKING-CONTEXT.md`
noemt het omheinde P0-autorisatiecluster als **OP-182 t/m OP-193** -- twaalf punten. Stand
gemeten 2026-09-27: **negen gesloten, drie open.**

| Open gebleven | Onderwerp |
|---|---|
| **OP-190** | `roles` en `user_roles` vallen buiten de tenant-afscherming |
| **OP-192** | eenentwintig plekken beslissen los van elkaar over adminschap |
| **OP-193** | drie frontend-bevindingen op hetzelfde rechtenprobleem |

De vijf uit eis 1 zijn dicht; het cluster als geheel is dat niet. OP-190 raakt keten D
(isolatie onder druk) rechtstreeks. Meet de stand met
`python scripts/list_adr036_open_items.py` in plaats van deze tabel te vertrouwen --
nummers in een document verouderen, het register niet.

| 2 | Acceptatieketen 7 van 7 | **4 van 7** -- maar dit is GEEN geldige meting: er draaide alleen `sanskritisetu_traefik`, geen database. Stap 5 meldt "geen testdatabase bereikbaar". Opnieuw meten met een draaiende stack. |
| 3 | Uitloggen maakt token ongeldig | register zegt gesloten 2026-09-16, niet nagetoetst |
| 4 | Volledige testpoort groen | niet gemeten op 2026-09-27 |
| 5 | Auditketencontrole dagelijks groen | niet gemeten |
| 6 | Hersteltest vanaf backup uitgevoerd | niet gemeten |

**Wat goed is en het vermelden waard:** stap 7 van de acceptatieketen weigert uit zichzelf
vals bewijs. De letterlijke uitvoer:

> "provider is 'mock' -- een besluit uit een namaakmodel telt niet als bewijs"

### Hoe deze meetlat getoetst gaat worden

Bron van het gereedschap: `@playwright/test` (frontend), `playwright==1.42.0` (Python),
`docker-compose.e2e.yml`.

| Wat | Stand 2026-09-27 |
|---|---|
| e2e-tests aanwezig | **138** in 28 bestanden, echt (niet leeg, niet uitgezet) |
| e2e-tests die CI draait | **22** -- alleen `workflows.spec.ts` en `focus-builder-canvas.spec.ts` |
| e2e-tests die nergens draaien | **116**, waaronder `auth.spec.ts`, `complete-user-journey.spec.ts`, `critical-paths.spec.ts` |

Precies de tests die scenario 1 en 2 zouden bewijzen, draaien nergens. Het is geen
bedrog, het is ongebruikt -- en dat is een kleiner probleem, want het staat er al.

**De drie regels die maken dat Rakesh dit zonder technische kennis kan controleren:**

1. Hij kijkt naar beeld, niet naar code. Playwright maakt schermopnames tijdens het
   bedienen van de applicatie. Een foutmelding op een scherm herkent iedereen.
2. De agent kan die opname niet verzinnen. Het beeld komt van het gereedschap dat de
   browser aanstuurt. Draait de applicatie niet, dan is er geen beeld.
3. **Geen bewijs is AFGEKEURD.** Nu geldt "ik kon het niet testen" in de praktijk als
   "het werkt". Dat draait om.

---

## 6e. Gemeten stand op de harde poort -- 2026-10-14 (op a9115987)

> Toegevoegd door de regie op verzoek van Rakesh (2026-10-14, "prima"). Metingen op `origin/develop` a9115987, lokaal op de ontwikkelmachine, door de verkenner. Dit
> vervangt 6b/6c/6d niet: die staan op tak `wip/onbekende-sessie-2026-10-13` (commit 813b72a0)
> en zijn NIET naar develop gekomen. Wat daar als gebouwd staat (stap 7, uitlogtest,
> herstelscripts, herstelproef) is op develop niet aanwezig; hieronder is dat opnieuw gemeten.
> Staging en productie zijn niet gemeten.

**Uitkomst: nog steeds geen van de zes eisen is aantoonbaar gehaald.** Eis 2, 3 en 6 zijn op
develop rood of zonder bewijs; het bouwwerk van de wip-tak ligt er nog niet in.

| # | Eis | Stand op a9115987 | Bewijs |
|---|---|---|---|
| 1 | De vijf P0-lekken dicht | **Register: van OP-182 t/m OP-193 is alleen OP-192 (P2) open**; de overige elf staan gesloten (zelfde beeld als 6b). In totaal 74 open OP's. | `python scripts/list_adr036_open_items.py` -> "Totaal open: 74", `--count` -> 74; gefilterd op OP-182..193 -> alleen `OP-192` (controle: 74 OP-regels in de lijst). Bewijstests OP-182 t/m 186 en OP-190 niet opnieuw gedraaid. |
| 2 | Acceptatieketen 7 van 7 | **6 van 7.** Stap 7 faalt: provider is `mock`, en op develop faalt stap 7 sowieso zonder voorwaarde ("nog geen goedgekeurd besluit...") -- de bouw uit 6d staat alleen op de wip-tak. Stap 5 slaagt nu met echte database. | `python scripts/acceptance_thread.py` op een EIGEN wegwerpdatabase `harde_poort_test` (poort 5455, schema door de integratietest aangemaakt): "Keten komt tot stap 6 van 7". Alleen stap 5 schrijft (eigen gemarkeerde rij, wordt afgeruimd); stap 7 schrijft niets. |
| 3 | Uitloggen maakt token ongeldig (OP-188) | **Niet bewezen; het bestaande bewijs is stuk.** De test faalt voor het uitloggen: `AttributeError: ... router_token does not have the attribute 'get_redis_client'`. De nieuwe test `tests/integration/security/test_een_uitgelogd_token_wordt_geweigerd.py` bestaat niet op develop. | `SANSKRITISETU_TEST_DATABASE_URL=...harde_poort_test`, `REDIS_URL=redis://localhost:6380/1`, `python -m pytest tests/integration/test_auth_cookie_session.py::test_cookie_auth_fails_after_logout` -> 1 failed (twee keer, 87 s en 53 s). |
| 4 | Volledige testpoort groen | **Niet door de verkenner gemeten** (andere sessies draaien; de regie draait hem bij de push). Uit het regielog: pre-push 2026-10-14 op a9115987 was groen, 18.871 tests. Niet zelf nagemeten. | Regielog (mededeling van de opdrachtgever). De eerdere meting van 2026-10-12 (18.815 geslaagd, 1 gefaald `test_initialize`) is hiermee niet bevestigd of weerlegd voor de nu bekende stand. |
| 5 | Auditketencontrole dagelijks groen | **Opzet aanwezig, geen bewijs van een run.** De job staat in de scheduler (dagelijks 03:00), de container staat uit. | `src/workers/scheduler.py:276-284` (`run_audit_verification`, CronTrigger hour=3); `docker ps -a`: `sanskritisetu_scheduler` Exited (255) 31 uur geleden. Job niet gedraaid: `AuditTrailVerificationJob.store_result` en de ankercontrole schrijven (`src/core/jobs/audit_verification.py:277`). |
| 6 | Hersteltest vanaf back-up | **Geen bewijs op develop.** `docs/evidence/` bevat alleen `adr036-fase-a`; de herstelproef van 2026-10-12 en de herschreven herstelscripts staan alleen op de wip-tak. Op develop staat alleen het runbook `docs/runbooks/foundation-portal/backup-restore.md`. | `ls docs/evidence` -> `adr036-fase-a`; `git ls-files` op "herstelproef" -> geen treffer (controle: "restore" geeft wel 5 treffers). |

**Niet gemeten**
- Of de bewijstests van OP-182 t/m OP-191 en OP-193 nog slagen (alleen het register is gelezen).
- Stap 7 met een echte provider (Ollama stond uit); op develop kan hij toch niet slagen.
- De integratietest van OP-190 en de volledige testpoort.
- `run_audit_verification` zelf, en elke run in CI of productie (`gh` niet gebruikt).
- Staging, productie, een draaiende applicatie met beeld.

## 6f. Gemeten stand op de harde poort -- 2026-10-25 (op 69f433cc)

> Toegevoegd door de regie (sessie sanskritisetu-org-4f). Gemeten op `origin/develop` 69f433cc in een eigen werkmap,
> met een eigen wegwerpdatabase op netwerkpoort 5455 en Redis db 14; daarna opgeruimd. Staging en productie niet gemeten.

**Uitkomst: vier van de zes eisen zijn gehaald (1, 2, 3, 4); eis 5 en 6 zijn niet aantoonbaar.**

| # | Eis | Stand | Bewijs |
|---|---|---|---|
| 1 | P0-lekken OP-182 t/m OP-186 | **Gehaald** | register: gesloten 2026-09-11/12/15; de bewijstests plus die van OP-188: 7 bestanden, 58 passed |
| 2 | Acceptatieketen 7 van 7 | **Gehaald** | `python scripts/acceptance_thread.py` met Redis en `LLM_PROVIDER=ollama`: "Keten komt tot stap 7 van 7", rc=0. Let op: stap 7 roept geen taalmodel aan (weigert alleen `mock`); 7/7 zegt iets over database en goedkeuren, niet over een taalmodel |
| 3 | Uitloggen maakt het token ongeldig (OP-188) | **Gehaald** | `tests/integration/security/test_een_uitgelogd_token_wordt_geweigerd.py`: 6 passed |
| 4 | Volledige testpoort groen | **Gehaald** (niet opnieuw gemeten) | pre-push van 69f433cc: 27303 passed |
| 5 | Auditketencontrole draait dagelijks en is groen | **Niet aantoonbaar** | gepland in `src/workers/scheduler.py` (dagelijks 03:00), alarmregels in `infra/prometheus/alerts/audit-chain.yml`; geen enkel bewijs dat hij ooit draaide (lokale scheduler "Exited (255) 12 days ago", geen auditrun in `docs/evidence/`) |
| 6 | Hersteltest vanaf een backup | **Niet aantoonbaar** | `bash scripts/herstelproef.sh`: 26 PASS, rc=0 -- maar op een wegwerpcontainer met 500 nagemaakte rijen, zonder het schema van de applicatie. Een herstel van een echte backup van de applicatiedatabase en een controle van de app daarop ontbreken (het bewijsdocument zegt dat zelf) |

De tak `wip/onbekende-sessie-2026-10-13` is voor eis 2 en 3 niet meer nodig: wat erop stond, staat op develop in
gelijke of nieuwere vorm. Er staan alleen nog documenten op (onder meer ADR-041 en workflowbuilder-documenten).

**Niet gemeten**
- De volledige testpoort opnieuw; `tests/security/test_owasp_a01_access_control.py`.
- Stap 7 met een draaiend taalmodel (stap 7 kan dat ook niet aantonen).
- `run_audit_verification` zelf, en elke run op staging of productie.
- Herstel van een echte (Azure-)backup; staging, productie, een draaiende applicatie met beeld.


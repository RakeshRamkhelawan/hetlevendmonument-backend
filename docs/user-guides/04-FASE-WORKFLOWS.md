# Fase 4: Workflows & Focus Builder

> **Handleiding voor:** Eindgebruikers, Workflow Designers, Process Engineers, Team Leads
> **Laatst bijgewerkt:** 26 Maart 2026

---

## 1. Doel van deze handleiding

Deze handleiding beschrijft de huidige, canonieke workflow-ervaring in SanskritiSetu. Het doel is dat je zonder technische voorkennis workflows kunt:

- vinden en beheren
- nieuw opzetten
- starten vanuit een template
- opslaan en heropenen
- uitvoeren en verbeteren

Deze gids is geschreven op basis van de actuele productroutes en UI-componenten. Oudere builderroutes zijn niet langer de primaire ingang.

---

## 2. Snelle samenvatting

SanskritiSetu gebruikt nu twee vaste workflow-oppervlakken:

| Doel | Route | Gebruik wanneer |
| ---- | ----- | ---------------- |
| Workflows beheren | `/workflows` | Je wilt zoeken, filteren, openen of verwijderen |
| Workflows maken of bewerken | `/focus-builder` | Je wilt een workflow bouwen, aanpassen of opslaan |
| Starten vanuit template | `/focus-builder?mode=templates` | Je wilt beginnen met een bestaand patroon |

Belangrijk:

- `/workflows` is de beheerpagina
- `/focus-builder` is de enige authoring-omgeving
- templates zijn onderdeel van Focus Builder, geen apart productvlak meer
- oude routes zoals `/workflow-builder`, `/workflow-templates` en `/templates` worden doorgestuurd

---

## 3. Wanneer gebruik je welke pagina?

### 3.1 Gebruik `/workflows` als je wilt

- een bestaande workflow terugvinden
- filteren op status
- een workflow openen om verder te bewerken
- een workflow verwijderen
- snel een nieuwe workflow starten
- templates ontdekken vanaf de beheerpagina

### 3.2 Gebruik `/focus-builder` als je wilt

- een workflow vanaf nul bouwen
- AI een workflow laten genereren vanuit een prompt
- een bestaande workflow bewerken
- nodes handmatig toevoegen
- een workflow opslaan
- een opgeslagen workflow laden in de builder

### 3.3 Gebruik `/focus-builder?mode=templates` als je wilt

- beschikbare templates bekijken
- een template instantiëren naar het canvas
- een template aanpassen aan je eigen use case
- direct na instantiatie verder ontwerpen

---

## 4. Voor je begint

Controleer dit voordat je workflows maakt:

- Je bent ingelogd op SanskritiSetu
- Je hebt rechten om workflows te bekijken of bewerken
- Je weet of je vanaf nul wilt starten of liever een template gebruikt
- Je hebt een duidelijk doel voor de workflow, bijvoorbeeld goedkeuring, rapportage of notificatie

Praktische vuistregel:

- Gebruik een lege workflow als je proces nog open is
- Gebruik een template als je een bekend proces versneld wilt opzetten

---

## 5. Workflows beheren op `/workflows`

### 5.1 De pagina openen

1. Log in op SanskritiSetu.
2. Open in de navigatie `Workflows`.
3. Je komt op `/workflows`.

### 5.2 Wat je op de pagina ziet

De Workflows-pagina bevat:

- een overzicht van beschikbare workflows
- een zoekveld
- een statusfilter
- knoppen voor `Browse Templates`, `Refresh` en `New Workflow`
- per workflow een kaart met naam, beschrijving, status en datums

### 5.3 Een workflow zoeken

Gebruik het zoekveld om te zoeken op:

- workflownaam
- beschrijving

Zoeken werkt direct terwijl je typt.

### 5.4 Filteren op status

Je kunt filteren op:

- `All Status`
- `Active`
- `Inactive`

Gebruik dit wanneer je alleen live workflows of juist concepten wilt bekijken.

### 5.5 Een workflow openen om te bewerken

1. Klik op een workflowkaart.
2. Of klik op het potlood-icoon.
3. SanskritiSetu opent de workflow in `/focus-builder?id=<workflow-id>`.

### 5.6 Een workflow verwijderen

1. Hover over een workflowkaart.
2. Klik op het prullenbak-icoon.
3. Bevestig de waarschuwing.

Let op:

- verwijderen is permanent
- gebruik dit alleen als de workflow niet meer nodig is

### 5.7 Een nieuwe workflow starten

Klik op `New Workflow` om direct naar een lege builder te gaan.

### 5.8 Vanuit Workflows naar templates gaan

Klik op `Browse Templates` om naar template mode te gaan binnen Focus Builder.

---

## 6. Focus Builder begrijpen

Focus Builder is de centrale omgeving voor ontwerp en bewerking. Je kunt hier zowel AI-assisted als handmatig werken.

### 6.1 Hoofdonderdelen van Focus Builder

Afhankelijk van je situatie zie je:

- een landingsscherm met prompt-invoer
- een template-ervaring in template mode
- een canvas met nodes en verbindingen
- een chatpaneel voor generatie en verfijning
- eigenschappenpanelen voor node-instellingen
- een bovenste toolbar met acties zoals `New`, `Workflows`, `Delete`, `+ Node`, `Execute`, `Save`

### 6.2 Twee manieren om te starten

Je kunt op twee manieren binnenkomen:

1. Lege builder
2. Template mode

#### Lege builder

Dit is geschikt als je zelf een proces wilt beschrijven of opbouwen.

#### Template mode

Dit is geschikt als je wilt starten vanuit een bewezen patroon en daarna verder wilt verfijnen.

---

## 7. Een workflow vanaf nul maken

### 7.1 Start via prompt

1. Open `/focus-builder`.
2. Je ziet een invoerveld met de vraag wat je wilt bouwen.
3. Beschrijf je proces in gewone taal.

Voorbeelden:

- `Stuur elke ochtend een statusupdate naar Slack`
- `Maak een dagelijkse finance reconciliation workflow`
- `Controleer supporttickets en escaleer urgente meldingen`

1. Klik op `Generate` of druk op `Enter`.
2. SanskritiSetu genereert een eerste workflowstructuur.

### 7.2 Start handmatig

1. Open `/focus-builder`.
2. Gebruik `+ Node` zodra de builder actief is.
3. Voeg stap voor stap nodes toe.
4. Configureer per node de gewenste logica.

### 7.3 Wanneer kies je prompt versus handmatig?

Gebruik prompt-first als:

- je snel een concept wilt
- je nog zoekt naar de beste opbouw
- je AI wilt laten voorstellen welke stappen logisch zijn

Gebruik handmatig bouwen als:

- je proces al vastligt
- je heel precies wilt modelleren
- je slechts kleine wijzigingen maakt in een bestaand ontwerp

---

## 8. Starten vanuit een template

### 8.1 Template mode openen

Open een van deze paden:

1. Vanaf `/workflows` via `Browse Templates`
2. Direct via `/focus-builder?mode=templates`

### 8.2 Wat je in template mode ziet

Template mode toont:

- een introductieblok links
- een promptveld om alsnog AI-generatie te gebruiken
- voorbeeldprompts
- rechts een templates-paneel

In het templates-paneel kun je:

- templates bekijken
- details openen
- een template selecteren
- een template instantiëren

### 8.3 Een template instantiëren

1. Kies een template.
2. Open de template of bekijk de details.
3. Start de instantiatie.
4. Na een succesvolle instantiatie wordt het canvas automatisch gevuld.

Wat SanskritiSetu daarna doet:

- de workflownaam wordt ingevuld
- nodes worden op het canvas geplaatst
- verbindingen worden geladen
- je kunt direct verder bewerken

### 8.4 Belangrijk na instantiatie

Een template is pas echt van jou nadat je hem opslaat als workflow.

Aanbevolen volgorde:

1. Template laden
2. Naam en logica controleren
3. Wijzigingen doorvoeren
4. `Save` gebruiken

---

## 9. Werken met het canvas

### 9.1 Wat is het canvas?

Het canvas is het visuele werkvlak waarop je workflowstappen ziet en ordent.

### 9.2 Wat zijn nodes?

Nodes vertegenwoordigen stappen in je workflow, zoals:

- input
- processtappen
- beslismomenten
- outputs
- AI- of agentacties

De exacte node-typen kunnen variëren per workflow en per gegenereerde structuur.

### 9.3 Nodes toevoegen

1. Klik op `+ Node`.
2. Kies of configureer het type.
3. Geef de node een duidelijke naam.

### 9.4 Nodes aanpassen

Klik op een node om details te bewerken via de beschikbare panelen. Gebruik duidelijke namen zodat anderen je workflow later ook begrijpen.

### 9.5 Verbindingen en flowlogica

Verbindingen bepalen de volgorde en overdracht van je workflow. Controleer na elke grotere wijziging of de logische volgorde nog klopt.

### 9.6 Ghost suggestions en voorstellen

Tijdens AI-assisted bouwen kan SanskritiSetu voorstellen doen voor extra nodes of verbeteringen.

Je kunt dan:

- afzonderlijke voorstellen accepteren
- voorstellen afwijzen
- `Accept All` gebruiken als de voorgestelde set klopt

Gebruik `Accept All` alleen als je het hele voorstel inhoudelijk hebt gecontroleerd.

---

## 10. Workflow opslaan

### 10.1 Handmatig opslaan

1. Klik op `Save` in de toolbar.
2. SanskritiSetu slaat de workflow op.
3. Bij een nieuwe workflow wordt de URL bijgewerkt naar `/focus-builder?id=<workflow-id>`.

### 10.2 Autosave

Focus Builder gebruikt ook autosave voor werk-in-uitvoering.

Belangrijk om te weten:

- autosave helpt tegen dataverlies tijdens het werken
- autosave vervangt niet je expliciete eindopslag
- gebruik `Save` altijd na belangrijke wijzigingen of na template-instantiatie

### 10.3 Waaraan herken je dat een workflow echt opgeslagen is?

Na succesvol opslaan:

- krijg je een bevestiging in de builderchat
- heeft de workflow een vaste workflow-id
- kun je hem terugvinden via `/workflows` of via de knop `Workflows` in de builder

---

## 11. Opgeslagen workflows openen en beheren in de builder

### 11.1 De Saved Workflows-lade openen

1. Klik in Focus Builder op `Workflows`.
2. Rechts opent een lade met opgeslagen workflows.

### 11.2 Wat je in de lade kunt doen

Je kunt daar:

- zoeken op naam of beschrijving
- zien welke workflow momenteel geopend is
- zien of een workflow gepubliceerd is
- een andere workflow laden
- een workflow verwijderen

### 11.3 Een workflow laden

1. Open de lade.
2. Klik op de gewenste workflow.
3. De builder laadt de workflow direct in.

### 11.4 Een workflow verwijderen vanuit de lade

1. Hover over de workflow in de lade.
2. Klik op het prullenbak-icoon.
3. Bevestig de melding.

Deze actie is permanent.

---

## 12. Een bestaande workflow aanpassen

Er zijn twee gebruikelijke manieren:

### 12.1 Via `/workflows`

1. Zoek de workflow.
2. Open deze.
3. Bewerk de inhoud in Focus Builder.
4. Sla opnieuw op.

### 12.2 Via directe link

Als je al een workflow-id hebt, kom je binnen via:

- `/focus-builder?id=<workflow-id>`

Dit is handig voor bookmarks, teamlinks en terugkeer naar lopend werk.

---

## 13. Uitvoeren en testen

### 13.1 `Execute`

Gebruik `Execute` als je de workflow vanuit de builder wilt starten.

Dit is nuttig als je:

- snel wilt controleren of de flow logisch werkt
- een eerste validatie wilt doen
- iteratief wilt testen tijdens ontwerp

### 13.2 `Run Flow`

Als de workflow een geldige opgeslagen workflow-id heeft, kun je ook `Run Flow` gebruiken.

Praktisch verschil:

- `Execute` is gericht op directe uitvoering vanuit de buildercontext
- `Run Flow` gebruikt de gekoppelde flow-uitvoering wanneer de workflow al als persistente flow beschikbaar is

### 13.3 Wanneer eerst opslaan?

Sla eerst op als:

- je vanaf een template bent gestart
- je een bestaande workflow sterk hebt aangepast
- je wilt zeker weten dat anderen dezelfde versie kunnen openen

---

## 14. Handige toolbar-acties

| Actie | Betekenis | Wanneer gebruiken |
| ----- | --------- | ------------------ |
| `New` | Start opnieuw met een lege workflow | Voor een nieuw ontwerp |
| `Workflows` | Open opgeslagen workflows | Om te wisselen of te laden |
| `Delete` | Verwijder huidige workflow permanent | Alleen als je zeker bent |
| `+ Node` | Voeg handmatig een node toe | Voor precieze opbouw |
| `Execute` | Start de huidige workflow | Tijdens testen of valideren |
| `Run Flow` | Voer de gekoppelde flow uit | Bij opgeslagen flow-uitvoering |
| `Save` | Bewaar huidige wijzigingen | Altijd na belangrijke stappen |
| `Accept All` | Accepteer alle AI-voorstellen | Alleen na inhoudelijke controle |

---

## 15. Sneltoetsen

De builder ondersteunt in ieder geval deze acties via toetsenbord:

| Sneltoets | Actie |
| --------- | ----- |
| `Ctrl/Cmd + S` | Opslaan |
| `Ctrl/Cmd + Z` | Undo |
| `Ctrl/Cmd + Y` | Redo |
| `Ctrl/Cmd + Enter` | Execute |

Niet elke actie heeft een zichtbare sneltoets in de UI. Gebruik daarom vooral de toolbar als je twijfelt.

---

## 16. Aanbevolen werkwijze

### 16.1 Voor nieuwe gebruikers

Gebruik deze volgorde:

1. Open `/workflows`
2. Kies `Browse Templates` als je een bekend proces hebt
3. Kies `New Workflow` als je iets nieuws ontwerpt
4. Werk in Focus Builder
5. Sla op zodra de eerste goede versie staat

### 16.2 Voor teams

Werk op deze manier consistenter:

- geef workflows duidelijke namen
- beschrijf het doel in de workflowbeschrijving
- start bij terugkerende processen met templates
- verwijder verouderde concepten uit `/workflows`
- test steeds na grotere wijzigingen

### 16.3 Voor procesverbetering

Gebruik AI niet alleen om te genereren, maar ook om te verfijnen:

- begin met een eenvoudige prompt
- beoordeel de voorgestelde structuur
- voeg handmatig nodes toe waar controle nodig is
- herhaal totdat het proces duidelijk en uitvoerbaar is

---

## 17. Veelvoorkomende taken

### 17.1 Ik wil snel een eerste workflow maken

1. Open `/focus-builder`
2. Beschrijf het proces in een zin
3. Klik `Generate`
4. Controleer de gegenereerde stappen
5. Klik `Save`

### 17.2 Ik wil een bestaand proces standaardiseren met een template

1. Open `/focus-builder?mode=templates`
2. Kies een passend template
3. Instantieer het template
4. Pas namen, stappen en logica aan
5. Sla het resultaat op

### 17.3 Ik wil een bestaande workflow aanpassen

1. Open `/workflows`
2. Zoek de workflow
3. Open hem
4. Pas hem aan in Focus Builder
5. Sla opnieuw op

### 17.4 Ik wil een foutieve workflow verwijderen

1. Verwijder hem via `/workflows`
2. Of verwijder hem vanuit de builder via `Delete`
3. Bevestig de waarschuwing

---

## 18. Troubleshooting

### 18.1 Mijn workflow verschijnt niet in `/workflows`

Controleer dit:

- heb je echt op `Save` geklikt
- kreeg je een succesmelding in de builder
- is de URL veranderd naar een versie met `?id=`
- probeer `Refresh` op `/workflows`

### 18.2 Ik heb een template geladen maar zie niets op het canvas

Mogelijke oorzaak:

- de template bevatte geen bruikbare canvasnodes

Oplossing:

- kies een ander template
- probeer opnieuw te instantiëren
- start desnoods vanuit een prompt

### 18.3 Ik ben onopgeslagen werk kwijtgeraakt

Mogelijke oorzaak:

- de workflow was alleen in tijdelijke autosave aanwezig
- de browser of sessie werd onderbroken

Oplossing:

- open Focus Builder opnieuw
- controleer of automatisch herstel wordt aangeboden
- sla daarna direct handmatig op

### 18.4 `Run Flow` is niet beschikbaar

Mogelijke oorzaak:

- de workflow heeft nog geen geldige opgeslagen flow-id

Oplossing:

- sla de workflow eerst op
- probeer daarna opnieuw

### 18.5 Verwijderen lukt niet

Controleer dit:

- heb je voldoende rechten
- is de backend bereikbaar
- probeer de workflowlijst te verversen en opnieuw te verwijderen

---

## 19. Best practices

Gebruik deze richtlijnen voor betere workflows:

- houd elke workflow gericht op een duidelijk procesdoel
- werk met duidelijke namen voor workflow en nodes
- begin eenvoudig en breid daarna uit
- gebruik templates voor herhaalbare processen
- sla vaak op
- verwijder oude concepten om ruis te voorkomen
- controleer AI-voorstellen inhoudelijk voordat je ze accepteert

---

## 20. FAQ

**Moet ik nog `/workflow-builder` gebruiken?**

Nee. Gebruik `/focus-builder`.

**Waar vind ik templates?**

In Focus Builder template mode via `/focus-builder?mode=templates` of via `Browse Templates` op `/workflows`.

**Waar beheer ik mijn workflows?**

Op `/workflows`.

**Kan ik vanuit de builder opgeslagen workflows openen?**

Ja. Gebruik de knop `Workflows` in de toolbar.

**Wordt mijn werk automatisch bewaard?**

De builder gebruikt autosave, maar je moet nog steeds handmatig opslaan om je workflow definitief te bewaren.

**Kan ik een template direct aanpassen?**

Ja. Na instantiatie staat de template direct op het canvas en kun je verder bewerken.

---

## 21. Snelle referentie

| Actie | Route | Opmerking |
| ----- | ----- | --------- |
| Workflows bekijken | `/workflows` | Beheer, zoeken, filteren, openen |
| Nieuwe workflow maken | `/focus-builder` | Leeg of via prompt |
| Template starten | `/focus-builder?mode=templates` | Templates binnen Focus Builder |
| Bestaande workflow openen | `/focus-builder?id=<workflow-id>` | Directe edit-link |

---

## 22. Samenvatting

Als je maar drie dingen onthoudt, laat het deze zijn:

1. Beheer workflows altijd via `/workflows`
2. Bouw en bewerk workflows altijd via `/focus-builder`
3. Gebruik templates als startpunt binnen Focus Builder, niet als aparte builderwereld

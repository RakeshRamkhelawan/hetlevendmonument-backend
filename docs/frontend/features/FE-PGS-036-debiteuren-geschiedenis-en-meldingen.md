# FE-PGS-036 -- Debiteuren: geschiedenis in gewone taal en een duidelijke melding bij een ongeldig veld

**Sprint:** Debiteuren van goedkeuring tot mail (2026-10-22), backend BE-DEB-006
**Status:** Geimplementeerd (zelfreview door de bouwer, zie review-FE-PGS-036; de backend en de schermlogica zijn door de security-reviewer gelezen)
**Datum:** 2026-10-22
**Bestanden:** `frontend/src/components/hitl/HITLHistory.tsx`, `frontend/src/lib/hitl/actie-omschrijving.ts`,
`frontend/src/lib/api/error-handler.ts`, `frontend/src/pages/ReceivablesPage.tsx`
**Handleiding:** `docs/user-guide/frontend/debiteuren-geschiedenis-en-meldingen.md`

---

## Beschrijving

- `/hitl`, Geschiedenis: de actie staat in gewone taal ("Een herinnering of aanmaning versturen") in plaats van de systeemnaam
  `send_payment_reminder`. Een actie die het scherm niet kent heet "Een actie van de assistent"; een klant ziet nooit een
  systeemnaam. De teksten spiegelen `FOUR_EYES_ACTIONS` in de backend; de architectuurtest
  `test_actie_omschrijving_spiegelt_four_eyes.py` bewaakt dat ze gelijk blijven.
- Het ticketnummer staat niet meer in de samenvattingsregel maar bij uitklappen, onder "Ticketnummer:". In de regel staat, als
  het adres bekend is, "Aangevraagd door <e-mailadres>".
- De kolom Datum toont dag, maand, jaar en tijdstip van het BESLUIT (goedgekeurd of afgekeurd); voor een ticket zonder besluit
  het tijdstip van de aanvraag.
- `/debiteuren`, Toevoegen: bij een 422 met een foutlijst zegt de melding welk veld en waarom, met de veldnamen van het
  formulier (Naam klant, E-mailadres, Factuurnummer, Bedrag, Valuta, Vervaldatum). Bij een ongeldig e-mailadres staat de
  Nederlandse tekst van de backend; voor de andere velden kiest het scherm een Nederlandse reden per soort fout, en de Engelse
  tekst van de backend wordt nooit getoond. Een veld of soort die het scherm niet kent geeft de oude melding "Controleer de
  velden." Alleen eigen sleutels tellen: `constructor` of `toString` als veld of soort geeft geen programmatekst.
- `/debiteuren`: de meldingen staan in een blok boven de lijst, het formulier eronder. Zodra er een melding komt (fout,
  bevestiging of "staat klaar bij Goedkeuringen") scrolt de pagina naar dat blok; anders zag de klant bij het formulier niets
  gebeuren (acceptatie 2026-10-22).
- `/hitl`, wachtende kaart: dezelfde gewone taal als in de geschiedenis. De titel is de omschrijving van een BEKENDE actie; een
  onbekende actie houdt zijn naam zoals hij is, omdat de goedkeurder moet kunnen zien wat hij beslist (bijvoorbeeld een
  opdrachtregel). De titel wordt niet afgekapt maar breekt af, met de volledige naam als hover-tekst. De agent heet
  "Debiteurenagent" (voor `dunning`); bij `unknown` of leeg staat er geen regel, een andere agentnaam blijft zoals hij is. Het
  ticketnummer staat alleen nog voor schermlezers en ondersteuning in de pagina (`sr-only`).
- `/hitl`, geschiedenis uitgeklapt: de regel Agent alleen met een naam; "Aangevraagd door" met het e-mailadres, anders een naam
  (een agent), nooit een kaal gebruikersnummer. De kolom Actie breekt af in plaats van afgekapt te worden.
- `/debiteuren`: een factuur met status `herinnerd` heeft geen voorstelknop meer. Na een verzonden herinnering is de opvolging de
  automatische escalatie na 14 dagen (met een aanmaning); een tweede herinnering zet die klok niet opnieuw
  (`_markeer_herinnerd` zet alleen `open` op `herinnerd`) en de backend weigert hem niet. Een factuur waarvan de brief mislukte
  blijft `open` en houdt zijn knop; een geescaleerde factuur houdt "Aanmaning voorstellen".
- Zakelijk dashboard: bij een 404 van het KPI-eindpunt (dat in de backend nog niet bestaat) verbergt het KPI-blok zich (geen rode
  melding en geen kaarten met streepjes); de proactieve meldingen eronder blijven. Een andere fout blijft een melding. Het
  dashboard zelf toont bij een 403 op de agent- en workflowcijfers (een medewerker debiteuren heeft daar geen recht op) geen rode
  kaart meer, en een andere fout heet "Het dashboard kon niet worden geladen." in plaats van het Engelse "Error loading dashboard
  data."
- `createApiError` bewaart de foutlijst van een 422 als `error.validation` (veld, soort, tekst). Alleen een LIJST krijgt een
  eigen plek; een tekst of een object in `detail` blijft zoals voorheen (de pakkettenpagina leest er een `code` uit), en bij een
  lijst wordt de foutboodschap niet meer "[object Object]".

## Trainingssamenvatting

### De geschiedenis van goedkeuringen lezen

- Actor: goedkeurder of beheerder
- Voorwaarde: ingelogd
- Actie: opent Goedkeuringen en kiest Geschiedenis
- Systeemreactie: per besluit een omschrijving van de actie, wie besloot, en dag en tijdstip van het besluit
- Succes: "Een herinnering of aanmaning versturen", status Goedgekeurd of Afgekeurd, dag en tijd
- Fout: geen; een lege geschiedenis zegt "Nog geen geschiedenis"
- Uitzonderingen: het ticketnummer staat pas na uitklappen; een onbekende actie heet "Een actie van de assistent"

### Een debiteur toevoegen met een fout veld

- Actor: medewerker debiteuren
- Voorwaarde: ingelogd met schrijfrecht
- Actie: vult het formulier in met een ongeldig veld en drukt op Toevoegen
- Systeemreactie: er wordt niets aangemaakt
- Succes: niet van toepassing
- Fout: "Toevoegen is niet gelukt. Het e-mailadres is niet geldig: ..." of "Toevoegen is niet gelukt. Bedrag mag niet negatief zijn."
- Uitzonderingen: kent het scherm de fout niet, dan staat er "Toevoegen is niet gelukt. Controleer de velden."

### De wachtende kaart lezen

- Actor: goedkeurder
- Voorwaarde: er staat een voorstel klaar
- Actie: opent Goedkeuringen
- Systeemreactie: de kaart toont de actie in gewone taal, aan wie de brief gaat en de agent als "Debiteurenagent"
- Succes: de goedkeurder ziet wat hij beslist, zonder systeemnamen of ticketnummer
- Fout: een onbekende actie toont zijn naam zoals hij is, zodat de goedkeurder weet wat er wordt voorgesteld
- Uitzonderingen: een voorstel van een onbekende agent toont die agentnaam; bij `unknown` ontbreekt de regel

## Regressierisico's

- Vier bestaande testbestanden zochten de rij van de geschiedenis op de ruwe actienaam of het ticketnummer; ze vinden de rij
  nu via een testkenmerk op de datumcel (`hitl-history-datum-<ticketnummer>`) en toetsen hetzelfde als voorheen.
- De opmaak van de datum kreeg het jaartal erbij (ook in de uitgeklapte regels), omdat dezelfde functie wordt gebruikt.
- De test van de pakkettenpagina en de volledige vitest-run ving een regressie in `createApiError` (een object in `detail` ging
  verloren); hersteld en met een eigen test vastgelegd.
- De test `ReceivablesPageBetaald` gebruikte de voorstelknop op een herinnerde rij als bewijs dat de rij ongewijzigd bleef; dat
  bewijs is nu de knop "Markeer ... als betaald".

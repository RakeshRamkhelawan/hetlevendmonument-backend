# FE-PGS-033 -- Uitleg vier ogen bij het inrichten

**Sprint:** SP-KLANT-02 (vervolg dag 3), ADR-039 "Bestaande ondernemingen"
**Status:** APPROVED
**Datum:** 2026-10-05
**Bestanden:** `frontend/src/components/settings/FourEyesExplanation.tsx`,
`frontend/src/components/settings/FourEyesExplanationRedirect.tsx`,
`frontend/src/pages/FourEyesExplanationPage.tsx`, `frontend/src/lib/api/receivables.ts`,
`frontend/src/App.tsx`

---

## Beschrijving

- `/instellingen/vier-ogen/uitleg`: per actie in gewone taal wat vier ogen betekent, de
  standaard (aan voor HR, betalen, IBAN, afboeken, incasso; uit voor herinneringen), dat een
  zzp'er zonder collega het zelf kan uitzetten, met vinkjes om direct aan te passen.
  "Bevestigen en doorgaan" bewaart (PUT) en bevestigt (POST), daarna naar `/dashboard`.
- Op `/dashboard` stuurt `FourEyesExplanationRedirect` een beheerder met openstaande uitleg
  naar die pagina. Geldt voor een nieuwe onderneming na registratie en eerste inlog, en voor
  een bestaande na de migratie.

## Trainingssamenvatting

### Uitleg bij eerste inlog

- Actor: beheerder van de onderneming
- Voorwaarde: de onderneming heeft de markering (nieuw, of gemigreerd)
- Actie: logt in, leest de uitleg, past eventueel vinkjes aan, drukt "Bevestigen en doorgaan"
- Systeemreactie: keuze opgeslagen, markering weg, door naar het dashboard
- Succes: bij de volgende inlog geen uitleg meer
- Fout: "Opslaan is niet gelukt" en de pagina blijft staan
- Uitzonderingen: een gebruiker zonder beheerrecht wordt niet doorgestuurd

## Nazorg scenario 5 (2026-10-05, tak fix/na-scenario5)

- **Doorsturing na inloggen.** De doorsturing vraagt de stand nu op via een react-query met
  vaste sleutel (per gebruiker). Oorzaak van het gemiste doorsturen: onder React.StrictMode
  draaide het oude effect twee keer; het eerste antwoord werd weggegooid en het tweede stond
  achter vijf dashboardverzoeken (gemeten met Playwright: 2,8 s en 9,8 s). De uitlegpagina zet
  na bevestigen de stand op false.
- **Publieke pagina's.** `/register`, `/forgot-password`, `/auth/reset-password` en `/demo`
  sturen bij een 401 niet meer naar `/login` (`PUBLIC_PAGES`). Geen sessie bij het opstarten
  wordt als info gelogd, niet als fout.
- **Een klik, een verzoek.** Schrijfverzoeken worden niet meer automatisch herhaald. Bij 429
  zegt de uitleg: "Wacht een minuut en klik dan opnieuw."

### Trainingssamenvatting -- te vaak geprobeerd

- Actor: beheerder van de onderneming
- Voorwaarde: de limiet van tien wijzigingen per minuut is bereikt
- Actie: drukt "Bevestigen en doorgaan"
- Systeemreactie: een verzoek, antwoord 429
- Succes: na een minuut lukt het met een nieuwe klik
- Fout: "U heeft dit te vaak achter elkaar geprobeerd. Wacht een minuut en klik dan opnieuw."
- Uitzonderingen: geen

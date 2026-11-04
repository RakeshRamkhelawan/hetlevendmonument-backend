# FE-PGS-034 -- Debiteuren vanzelf afronden: bankafschrift, verloop per factuur, escalatietermijn

**Sprint:** Debiteuren vanzelf afronden (2026-10-20), backend BE-DEB-004
**Status:** Geimplementeerd (zelfreview, zie review-FE-PGS-034)
**Datum:** 2026-10-20
**Bestanden:** `frontend/src/pages/ReceivablesPage.tsx`, `frontend/src/pages/DebiteurenInstellingenPage.tsx`,
`frontend/src/components/hitl/HITLActionCard.tsx`, `frontend/src/lib/api/receivables.ts`,
`frontend/src/lib/api/client.ts`, `frontend/src/types/hitl.ts`, `frontend/src/App.tsx`,
`frontend/src/components/layout/BusinessSidebar.tsx`
**Handleiding:** `docs/user-guide/frontend/debiteuren-vanzelf-afronden.md`

---

## Beschrijving

- `/debiteuren`: wie schrijfrecht heeft ziet "Bankafschrift inlezen (CAMT.053, XML)". Het gekozen bestand gaat als ruwe
  inhoud naar `POST /api/v1/receivables/bankafschrift`; de uitslag zegt hoeveel facturen als betaald zijn afgevinkt, hoeveel
  al afgevinkt waren en welke bijschrijvingen niet gekoppeld zijn (datum, bedrag, omschrijving). De lijst wordt opnieuw
  geladen. Van het afschrift wordt niets bewaard; de uitslag staat alleen in het geheugen van de pagina.
- `/debiteuren`: per factuur de knop "Verloop" (ook voor wie alleen mag lezen). Hij klapt de tijdlijn open met datum en
  naam per gebeurtenis; een onbekende datum staat als "datum onbekend".
- `/instellingen/debiteuren` (zijbalk, alleen beheerder zichtbaar): de escalatietermijn in dagen, 1 tot en met 120. Een
  onmogelijke waarde wordt geweigerd voordat er een verzoek uitgaat.
- HITL-kaart: de aanvrager staat met e-mailadres (`requested_by_email`), nooit als kaal nummer ("onbekende aanvrager" als
  het adres ontbreekt). Bij een besloten kaart heet de raadstekst "Advies van de Co-Pilot" in plaats van "Reden".
- `apiClient` stuurt een `Blob` of `File` ongewijzigd met zijn eigen inhoudstype (een formulier laat de server de inhoud
  tijdelijk op schijf zetten; dat is voor een bankafschrift ongewenst).

## Trainingssamenvatting

### Een bankafschrift inlezen

- Actor: medewerker debiteuren
- Voorwaarde: ingelogd met schrijfrecht; het afschrift is bij de bank gedownload als CAMT.053 (XML)
- Actie: kiest het bestand bij "Bankafschrift inlezen"
- Systeemreactie: de facturen die precies passen staan op betaald; de rest staat onder "niet gekoppeld"
- Succes: "N facturen afgevinkt als betaald", met de lijst en eventueel "M was al afgevinkt"
- Fout: "Het bankafschrift kon niet worden ingelezen. Download het opnieuw bij uw bank als CAMT.053 (XML)."
- Uitzonderingen: een bijschrijving zonder factuurnummer of met een ander bedrag wordt nooit afgevinkt; de medewerker zet
  die factuur zelf op betaald

### Het verloop van een factuur bekijken

- Actor: medewerker met leesrecht
- Voorwaarde: de factuur staat in de lijst
- Actie: drukt op "Verloop"
- Systeemreactie: de gebeurtenissen verschijnen onder de factuur, oudste eerst
- Succes: elke regel heeft datum en tekst, met de naam van de medewerker waar die er is
- Fout: "Het verloop kon niet worden geladen."
- Uitzonderingen: nog een klik klapt de lijst dicht

### De escalatietermijn instellen

- Actor: beheerder
- Voorwaarde: ingelogd als beheerder
- Actie: vult het aantal dagen in en drukt "Opslaan"
- Systeemreactie: termijn bewaard
- Succes: "Opgeslagen: een dossier escaleert na N dagen zonder betaling."
- Fout: buiten 1 tot en met 120: "Kies een aantal dagen van 1 tot en met 120." Geen beheerder: "Opslaan is niet gelukt. Alleen
  een beheerder mag dit wijzigen."
- Uitzonderingen: de pagina laadt de huidige termijn; lukt dat niet, dan "De instelling kon niet worden geladen."

## Regressierisico's

- De test `ReceivablesPageRol` eiste "geen enkele knop" zonder gebruiker; hij eist nu "geen schrijfknop", want "Verloop" is
  een leesknop. De rolgrens zelf (geen schrijfknoppen) is niet versoepeld.
- `ReceivablesPage.tsx` is door de nieuwe tabelstructuur (een fragment per rij) opnieuw ingesprongen: de diff is groter
  dan de werkelijke wijziging.

# FE-PGS-037 -- Crediteuren: lijst en invoer van leveranciers en inkoopfacturen

**Sprint:** Keten F, crediteuren dag 1 (2026-10-24), backend BE-CRD-001
**Status:** Geimplementeerd en onafhankelijk geaccepteerd met beeld (2026-10-24, acceptant: GOEDGEKEURD MET OPMERKINGEN, tien punten WERKT; beelden in `D:/tmp/crd-acceptatie\`, buiten de repo). Gate 2: twee reviewers lazen ook het scherm; bevindingen verwerkt, zie review-FE-PGS-037.
**Datum:** 2026-10-24
**Bestanden:** `frontend/src/pages/PayablesPage.tsx`, `frontend/src/lib/api/payables.ts`, `frontend/src/lib/api/payables-grens.ts`, `frontend/src/lib/bedrag.ts`, `frontend/src/lib/rechten.ts`, `frontend/src/App.tsx`, `frontend/src/components/layout/BusinessSidebar.tsx`, `frontend/src/components/layout/LegacyLayout.tsx`, `frontend/src/pages/UserManagement.tsx`
**Handleiding:** `docs/user-guide/frontend/crediteuren-lijst-en-invoer.md`

---

## Beschrijving

- Nieuwe pagina `/crediteuren` ("Crediteuren"): een lijst met inkoopfacturen (leverancier, factuur, bedrag, factuurdatum, vervaldatum, status), een formulier "Leverancier toevoegen" (naam, IBAN en e-mail niet verplicht) en een formulier "Inkoopfactuur toevoegen" (leverancier uit een lijst, factuurnummer, bedrag, factuurdatum, vervaldatum), en bij een factuur op "Ontvangen" de knop "Markeer als gecontroleerd" (acceptatie: "Gecontroleerd" naast de status "Ontvangen" verwarde).
- Het bedrag wordt als geheel aantal centen verstuurd (`amount_cents`): `euroNaarCenten` leest "1.250,50" als 125050 met de cijfers van de tekst, nooit met een komma-getal. Een bedrag dat niet klopt, een bedrag van nul of een vervaldatum voor de factuurdatum geeft een melding in het scherm voordat er iets wordt verstuurd.
- Meldingen staan boven de lijst (`aria-live`, een fout met `role="alert"`); de pagina scrolt ernaartoe. Bij een weigering door de backend (409) staat de Nederlandse tekst van de backend in de melding ("Deze factuur van deze leverancier is al vastgelegd."); de Engelse terugvaltekst "Conflict." gaat nooit naar de klant. Bij een 400 of 422 staat "Controleer de velden." zonder de Engelse tekst van de bibliotheek.
- De schrijfknoppen en formulieren staan er alleen voor wie `payables:write` heeft; lezen vraagt `payables:read`. Dit is een UI-aanwijzing, geen autorisatie: de backend toetst per route.
- Een dubbelklik stuurt een verzoek: tijdens het verzoek zijn de knoppen uitgeschakeld en een slot (ref) laat een tweede klik niet door. Mislukt "Gecontroleerd" (bijvoorbeeld omdat een collega de factuur al controleerde), dan wordt de lijst opnieuw geladen, zodat de huidige stand zichtbaar wordt.
- De lijsten vragen het maximum van de API (1000 rijen, `payables-grens.ts`) in plaats van de standaard van 50; bij 1000 zegt de pagina dat alleen de eerste 1000 facturen of leveranciers worden getoond.
- De tabel heeft een naam ("Inkoopfacturen") en kolomkoppen met `scope="col"`.
- Menu: "Crediteuren" in beide indelingen (klassiek en zakelijk) voor wie `payables:read` heeft. `payables` is, net als `hr`, een eigen resource voor het scherm: een jokerrecht `*:read` telt niet (spiegel van `EXPLICIT_RESOURCES`); alleen een recht op `payables` of het beheerdersrecht `*:*`.
- Beheerscherm: de rol `crediteuren` heet "Crediteuren" en staat in de standaardlijst van rollen.

## Trainingssamenvatting

### Een leverancier en een inkoopfactuur vastleggen

- Actor: crediteurenadministrateur of beheerder
- Voorwaarde: de gebruiker heeft de rol `crediteuren` (of is beheerder) en opent Crediteuren in het menu
- Actie: vult "Leverancier toevoegen" in en kiest "Leverancier toevoegen"; daarna "Inkoopfactuur toevoegen" met die leverancier
- Systeemreactie: "Leverancier <naam> toegevoegd." en "Inkoopfactuur <nummer> vastgelegd."; de factuur staat op "Ontvangen" in de lijst
- Succes: de factuur staat in de lijst met het bedrag in euro's met twee cijfers achter de komma
- Fout: een bedrag dat niet klopt ("Bedrag klopt niet..."), een bedrag van nul, een vervaldatum voor de factuurdatum, een dubbele factuur of dubbele leverancier ("... is al vastgelegd" / "Er bestaat al een leverancier met deze naam."), een ongeldig IBAN
- Uitzonderingen: wie alleen mag lezen ziet de lijst maar geen formulieren; wie geen recht heeft ziet Crediteuren niet in het menu

### Een factuur als gecontroleerd markeren

- Actor: crediteurenadministrateur
- Voorwaarde: de factuur staat op "Ontvangen"
- Actie: kiest "Markeer als gecontroleerd" bij de factuur
- Systeemreactie: "Factuur <nummer> staat op gecontroleerd."; de knop verdwijnt
- Succes: de status is "Gecontroleerd"
- Fout: "Wijzigen is niet gelukt." met de Nederlandse reden; de lijst wordt opnieuw geladen
- Uitzonderingen: goedkeuren en betalen zijn er nog niet (volgende stappen van Keten F)

## Bewust laten liggen

| Punt                                                                                                | Reden                                                                                                                                   |
| --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Geen bewerken of verwijderen van een leverancier of factuur                                         | niet gevraagd voor dag 1                                                                                                                |
| Geen paginering of "meer laden" in het scherm; wel een waarschuwing bij 1000                        | het pilotvolume zit ver daaronder; een echte paginering volgt als een klant er tegenaan loopt                                           |
| Alleen de valuta EUR in het formulier; de tabel toont de valuta van de rij                          | de pilotklant werkt in euro's; dag 4 filtert op EUR en SEPA                                                                             |
| De Nederlandse tekst van een 409 wordt getoond met een uitzondering voor "Conflict." (zwarte lijst) | de backend stuurt op deze routes alleen vaste Nederlandse teksten of "Conflict."; een witte lijst zou een nieuwe backendtekst blokkeren |
| De pagina probeert bij een mislukt laden niet opnieuw                                               | de klant ververst; "opnieuw proberen" is geen onderdeel van dag 1                                                                       |

## Niet gemeten

- Een smal (telefoon)scherm, de optionele e-mail van een leverancier, andere rollen in de browser (de rolscheiding is met API-tests gemeten) en wat er na "gecontroleerd" gebeurt (volgt op latere dagen).
- Toegankelijkheid met een echte schermlezer; alleen labels, rollen en `scope` zijn met tests gemeten.

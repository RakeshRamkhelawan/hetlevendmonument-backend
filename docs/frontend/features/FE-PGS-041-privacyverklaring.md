# FE-PGS-041 Privacyverklaring

**ID:** `FE-PGS-041` | **Datum:** 2026-11-01 | **Bron:** markt-review 2026-09-24 blokkade 7 (geen privacyverklaring)

## Wat

Nieuwe pagina `portal/src/pages/Privacy.tsx` op `/privacy`, link in de voettekst naast de
toegankelijkheidsverklaring. Inhoud getoetst tegen de code: verwerkte gegevens per functie,
grondslag, verwerkers (Azure Ierland, Brevo, Stripe, hCaptcha, Mistral AI, OpenStreetMap),
archivering, bewaartermijnen, rechten, lokale opslag.

**Concept:** de tekst moet nog worden nagekeken door iemand met juridische kennis, en de juridische
naam van de stichting en het contactadres moeten worden bevestigd.

## Trainingssamenvatting

- **Actor:** bezoeker, inzender, donateur, docent.
- **Voorwaarde:** geen.
- **Actie:** klikt in de voettekst op "Privacyverklaring".
- **Systeemreactie:** toont de verklaring.
- **Succes:** de bezoeker weet welke gegevens worden verwerkt, waarom, door wie, en hoe hij zijn rechten uitoefent.
- **Fout:** geen.
- **Uitzonderingen:** verzoeken om inzage of verwijdering lopen via e-mail; een gepubliceerde inzending via het meldformulier.

## Gemeten

`portal/src/__tests__/Privacy.test.tsx` (kop, links, geen axe-schendingen). Gate 2 ronde 1 vond
drie onjuiste beweringen (link "Mijn gegevens" naar de open-datapagina, bewaartermijn nieuwsbrief,
openbare donateursnamen); alle drie gecorrigeerd en een test vangt de foute link.

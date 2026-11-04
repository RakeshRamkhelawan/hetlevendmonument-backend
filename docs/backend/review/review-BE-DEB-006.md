# Backend Feature Review -- BE-DEB-006

## Metadata

- **Review ID:** review-BE-DEB-006
- **Feature ID:** BE-DEB-006
- **Feature naam:** Debiteuren van goedkeuring tot mail -- gemeten met werker en planner, duidelijke melding bij een ongeldig e-mailadres
- **Reviewer:** security-reviewer (subagent, Gate 2, een ronde). De code-reviewer is voor deze dag NIET ingezet: de brief vroeg de security-reviewer.
- **Datum:** 2026-10-22
- **Spec versie:** 1.0

---

## A. Eindoordeel

STATUS: APPROVED

Ronde 1 (sha 765f47a8, bereik 8d687ea4..765f47a8): GO. Geen CRITICAL, HIGH of MEDIUM; twee LOW-punten en een onbewezen punt.
Alles is verwerkt in 0c120873, elk punt eerst aan de code getoetst en met een rode test. De reparaties zelf zijn niet opnieuw
door een reviewer nagelopen (zie sectie E).

Ronde 2 (sha 73ef6c43, bereik 0c120873..73ef6c43, alleen frontend): GO, drie LOW-punten (zie review-FE-PGS-036). Er is geen
backendwijziging na ronde 1. Een derde ronde is niet gedaan (grens: twee rondes).

## B. Bevindingen en wat ermee is gedaan

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| `KlantEmail = Annotated[str, ...]` liet `format: email` uit het OpenAPI-schema verdwijnen | LOW | Eerst rood gemeten (2 tests), opgelost met `Field(json_schema_extra={"format": "email"})`; `WithJsonSchema` is bewust niet gebruikt omdat het `maxLength` zou vervangen |
| `VELDNAAM[fout.field]` en `REDEN_PER_SOORT[fout.type]` in `ReceivablesPage.tsx` zijn gewone objectopzoekingen: een veld of soort als `constructor` of `toString` geeft programmatekst in de melding | LOW | Eerst rood gemeten (2 tests), opgelost met een controle op eigen sleutels |
| Onbewezen: dwingt `Field(max_length=320)` na `Annotated[str, AfterValidator]` nog af? | n.v.t. | Gemeten: een adres van 321 tekens geeft de soort `string_too_long` (geen serverfout), en `maxLength` 320 staat in het schema; beide met een test |

De reviewer controleerde onder meer: dat `validate_email` dezelfde functie is die `EmailStr` zelf gebruikt (dus dezelfde
controle en dezelfde genormaliseerde uitkomst), dat de Nederlandse teksten vast zijn en het adres niet herhalen, dat
regeleinden in het adres niet door de validatie komen, en dat er geen XSS-pad is in de melding op het scherm.

## C. Bewust gelaten

- Een regel in `ReceivableCreate` en `ReceivableUpdate`: "Naam <adres>"-vormen worden geaccepteerd en alleen het adres wordt
  bewaard. Dat was al zo bij `EmailStr` en valt buiten dit bereik.
- Het KPI-eindpunt dat niet bestaat (zie de spec): geen fout in deze wijziging, een nieuwe functie.

## D. Mutatiebewijs

In een wegwerp-worktree (detached op 0c120873), een mutatie per element, steeds de bewakende test draaien en daarna
`git checkout --` in die worktree. Backend, alle vijf gevangen (ROOD):

- B1 geen e-mailcontrole en geen normalisatie; B2 altijd de algemene tekst (geen reden voor een gereserveerd domein);
  B3 soort weer `value_error`; B4 `format: email` uit het OpenAPI-schema; B5 geen lengtegrens op het veld (aanmaken).
- Frontend (F1 t/m F10): zie review-FE-PGS-036.

Niet gemuteerd: het wijzigpad `ReceivableUpdate` (alleen het schema is getoetst, niet een PATCH-verzoek), en de tweede
Nederlandse tekst afzonderlijk (de algemene tekst wordt wel getoetst via een adres zonder apenstaart).

## E. Niet getoetst

- Of NFC- of IDN-normalisatie een adres langer dan 320 tekens kan maken (de reviewer meldde het; niet uitgezocht).
- Het gedrag van `email-validator` bij stuurtekens is door de reviewer aangenomen en niet nagelezen.
- Wie de HITL-geschiedenis mag lezen (tenantfilter) en of de 422-antwoorden het adres loggen: niet door de reviewer bekeken.
- De reparaties van de twee LOW-punten zijn niet opnieuw door een reviewer nagelopen.

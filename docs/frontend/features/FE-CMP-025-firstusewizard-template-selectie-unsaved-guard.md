# FE-CMP-025: FirstUseWizard template-selectie unsaved guard

**Sprint:** Studio UI Fix Dag 3
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

DATA-001 rest: Verificatie of `StudioPage.tsx` de `onSelectTemplate`-callback van
`FirstUseWizard` correct beveiligt met de unsaved-changes guard. Geen code-wijziging
verwacht -- TDD-verify.

## Bevinding

`StudioPage.tsx` wikkelt de `onSelectTemplate`-callback al in `withUnsavedGuard`.
Wanneer `hasUnsavedChanges: true`, toont de guard een confirmatie-dialog voordat
de template-selectie doorgaat. Het gedrag was al correct geimplementeerd.

## Tests

- `StudioPage.test.tsx` -- DATA-001 rest: 15/15 GROEN (onmiddellijk)
  - Wizard toont dialog bij selectie als hasUnsavedChanges true
  - Wizard gaat direct door bij selectie als hasUnsavedChanges false
  - Dialog-knop "Ja, verder" navigeert door na bevestiging

Rode tests werden groen op het moment van schrijven: bevestigt dat het gedrag
al correct was zonder code-aanpassing.

## Trainingssamenvatting

### Flow 1: Template selecteren met unsaved changes -- dialog getoond

- Actor: Gebruiker in StudioPage met onopgeslagen wijzigingen
- Voorwaarde: hasUnsavedChanges: true; FirstUseWizard is zichtbaar
- Actie: Gebruiker klikt op een template in de wizard
- Systeemreactie: withUnsavedGuard onderschept; confirmatie-dialog verschijnt
- Succesrespons: Gebruiker bevestigt -> onSelectTemplate uitgevoerd
- Foutrespons: Gebruiker annuleert -> dialog sluit; geen navigatie
- Uitzonderingen: Geen

### Flow 2: Template selecteren zonder unsaved changes -- direct door

- Actor: Gebruiker in StudioPage zonder onopgeslagen wijzigingen
- Voorwaarde: hasUnsavedChanges: false; FirstUseWizard is zichtbaar
- Actie: Gebruiker klikt op een template
- Systeemreactie: withUnsavedGuard laat door; onSelectTemplate direct uitgevoerd
- Succesrespons: Template-selectie verwerkt zonder dialog
- Foutrespons: n.v.t.
- Uitzonderingen: Geen

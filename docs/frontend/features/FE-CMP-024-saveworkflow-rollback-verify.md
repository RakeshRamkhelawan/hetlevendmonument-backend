# FE-CMP-024: saveWorkflow rollback gedrag geverifieerd

**Sprint:** Studio UI Fix Dag 3
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

ERR-005: Verificatie of `useWorkflowBuilderStore.saveWorkflow` de `hasUnsavedChanges`-vlag
correct behoudt bij een mislukte opslag. Geen code-wijziging verwacht -- TDD-verify.

## Bevinding

`saveWorkflow` in `useWorkflowBuilderStore.ts` zet `hasUnsavedChanges: false` al ALLEEN
na een succesvolle `await`. Bij een fout in het `catch`-blok wordt de vlag
niet gereset en blijft `hasUnsavedChanges: true`. Het rollback-gedrag was al correct
geimplementeerd.

## Tests

- `useWorkflowBuilderStore.dag3.test.ts` -- ERR-005 TDD-verify: 4/4 GROEN (onmiddellijk)
  - hasUnsavedChanges blijft true na mislukte saveWorkflow
  - hasUnsavedChanges wordt false na succesvolle saveWorkflow
  - isLoading false na fout
  - error-state gevuld na fout

Rode tests werden groen op het moment van schrijven: bevestigt dat het gedrag
al correct was zonder code-aanpassing.

## Trainingssamenvatting

### Flow 1: Opslaan mislukt -- vlag bewaard

- Actor: Gebruiker in de workflow-builder
- Voorwaarde: hasUnsavedChanges is true; gebruiker klikt op opslaan; API geeft fout terug
- Actie: saveWorkflow wordt aangeroepen
- Systeemreactie: API-aanroep faalt; catch-blok loopt; hasUnsavedChanges blijft true
- Succesrespons: n.v.t. (dit is de fout-flow)
- Foutrespons: hasUnsavedChanges: true bewaard -- gebruiker verliest geen gewijzigde status
- Uitzonderingen: Geen

### Flow 2: Opslaan geslaagd -- vlag gereset

- Actor: Gebruiker in de workflow-builder
- Voorwaarde: hasUnsavedChanges is true; API geeft 200 terug
- Actie: saveWorkflow wordt aangeroepen
- Systeemreactie: await slaagt; hasUnsavedChanges: false gezet na await
- Succesrespons: hasUnsavedChanges: false -- opgeslagen indicator verdwijnt
- Foutrespons: n.v.t.
- Uitzonderingen: Geen

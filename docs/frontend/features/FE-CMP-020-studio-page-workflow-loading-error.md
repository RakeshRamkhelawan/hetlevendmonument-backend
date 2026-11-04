# FE-CMP-020: StudioPage workflow-lijst loading en error state

**Sprint:** Studio UI Fix Dag 2
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

`StudioPage` destruktureerde `isLoading` en `error` NIET uit `useWorkflowStore()`. Bij een
mislukte `fetchWorkflows`-aanroep was er geen visuele feedback -- de library-panel bleef leeg
zonder dat de gebruiker kon zien of de lijst nog werd opgehaald of al gefaald had (ERR-001).

## Implementatie

### `frontend/src/pages/StudioPage.tsx`

Destructuring uitgebreid op regel 24:

```typescript
const {
  workflows: rawWorkflows,
  isLoading: workflowsLoading,
  error: workflowsError,
  fetchWorkflows,
  deleteWorkflow: storeDeleteWorkflow,
} = useWorkflowStore();
```

In de library-panel JSX, binnen `{showLibrary && (...)}`, voor `<LibraryPanel>` toegevoegd:

- Laad-indicator (`role="status"`, `aria-live="polite"`, `data-testid="workflow-list-loading"`)
  getoond wanneer `workflowsLoading === true`.
- Foutbanner (`role="alert"`, `data-testid="workflow-list-error"`) getoond wanneer
  `!workflowsLoading && workflowsError !== null`.

Beide elementen zitten binnen `{showLibrary && ...}` zodat ze alleen zichtbaar zijn
wanneer de library-panel open is.

## Tests

- `StudioPage.test.tsx` -- ERR-001 describe-blok: 2 nieuwe tests (loading + error) GREEN
- Bestaande 11 tests volledig GROEN (13/13 totaal)

## Trainingssamenvatting

### Flow 1: Workflow lijst ophalen -- laden

- Actor: Ingelogde gebruiker die de Studio opent
- Voorwaarde: Bibliotheekpaneel is zichtbaar (libraryCollapsed: false); fetchWorkflows loopt
- Actie: Gebruiker opent de Studio-pagina
- Systeemreactie: `data-testid="workflow-list-loading"` zichtbaar boven LibraryPanel; `role="status"` + `aria-live="polite"` actief
- Succesrespons: Laad-indicator verdwijnt zodra `isLoading` false wordt; workflow-lijst verschijnt
- Foutrespons: Zie Flow 2
- Uitzonderingen: Bibliotheek ingeklapt -- laad-indicator niet zichtbaar (zit binnen showLibrary-guard)

### Flow 2: Workflow lijst ophalen -- fout

- Actor: Ingelogde gebruiker die de Studio opent
- Voorwaarde: fetchWorkflows mislukt; bibliotheekpaneel is zichtbaar
- Actie: fetchWorkflows retourneert fout -- useWorkflowStore.error wordt gevuld
- Systeemreactie: `data-testid="workflow-list-error"` zichtbaar; `role="alert"`; tekst is de foutmelding uit de store
- Succesrespons: n.v.t.
- Foutrespons: Foutbanner zichtbaar zolang `!workflowsLoading && workflowsError !== null`
- Uitzonderingen: deleteWorkflow-fouten worden NIET getoond via deze banner (pre-existing backlog: deleteWorkflow hergooit niet)

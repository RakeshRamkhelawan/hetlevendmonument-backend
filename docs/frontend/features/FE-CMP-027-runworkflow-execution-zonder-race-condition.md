# FE-CMP-027: runWorkflow execution zonder race condition

**Sprint:** Studio UI Fix Dag 3
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

API-004: `useWorkflowStore.runWorkflow` riep direct na `executeWorkflow` een
`getExecution`-aanroep aan. De backend verwerkt workflows asynchroon, zodat
het execution-record nog niet bestaat wanneer `getExecution` wordt aangeroepen.
Dit leidde tot 404-fouten of verouderde statuswaarden.

## Implementatie

### `frontend/src/lib/stores/useWorkflowStore.ts`

`runWorkflow` herschreven: de `getExecution`-aanroep verwijderd en vervangen door
een optimistisch execution-object dat direct uit de trigger-response wordt gebouwd:

```typescript
runWorkflow: async (id, input) => {
  set({ isLoading: true, error: null });
  try {
    const executionId = await WorkflowService.executeWorkflow(id, input);
    // Build optimistic execution object -- no getExecution call because
    // the backend processes async and the record may not exist yet.
    set({
      currentExecution: {
        id: executionId,
        workflowId: id,
        status: 'running',
        startedAt: new Date().toISOString(),
        logs: [],
        steps: [],
      },
      isLoading: false,
    });
  } catch (err: any) {
    set({ error: err.message, isLoading: false });
  }
},
```

`completedAt`, `output` en `error` zijn weggelaten omdat die velden optioneel
zijn in de `WorkflowExecution`-interface en `null` niet accepteren.

## Tests

- `useWorkflowStore.dag3.test.ts`: 4/4 GROEN
  - getExecution NIET aangeroepen na executeWorkflow
  - currentExecution.status === 'running' gezet
  - isLoading false na succes
  - error-state gevuld bij mislukte trigger
- `useWorkflowStore.extra.test.ts` en `branches.test.ts`: bijgewerkt naar nieuw gedrag

## Trainingssamenvatting

### Flow 1: Workflow starten -- optimistisch

- Actor: Gebruiker of geautomatiseerde trigger
- Voorwaarde: Workflow bestaat; runWorkflow aangeroepen
- Actie: executeWorkflow API-call verstuurd
- Systeemreactie: executionId ontvangen; currentExecution optimistisch gevuld
  met status 'running'; geen tweede API-call naar getExecution
- Succesrespons: currentExecution zichtbaar in UI als 'running'; isLoading false
- Foutrespons: executeWorkflow mislukt -> error gevuld; isLoading false; geen currentExecution
- Uitzonderingen: Status-updates komen daarna via polling of WebSocket -- niet via directe getExecution

### Flow 2: Workflow starten -- executeWorkflow mislukt

- Actor: Gebruiker of geautomatiseerde trigger
- Voorwaarde: executeWorkflow geeft fout terug (bijv. 500, 403)
- Actie: catch-blok loopt
- Systeemreactie: error gezet naar err.message; isLoading false; currentExecution ongewijzigd
- Succesrespons: n.v.t.
- Foutrespons: Fout zichtbaar in store.error; geen optimistisch execution-object aangemaakt
- Uitzonderingen: Geen

# FE-CMP-021: FocusModeBuilderEnhanced handleNewWorkflow dirty-check uitgebreid

**Sprint:** Studio UI Fix Dag 2
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

`handleNewWorkflow` in `FocusModeBuilderEnhanced` controleerde alleen `nodes.length > 0`
voordat het reset-confirmation-banner toonde. Wanneer een gebruiker verbindingen (`connections`)
of ghost-nodes (`ghostNodes`) had aangemaakt zonder nodes, werd de confirmation niet getoond
en werd het werk zonder waarschuwing verwijderd (DATA-005).

## Implementatie

### `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx`

Dirty-check uitgebreid:

```typescript
// VOOR
if (nodes.length > 0) {

// NA
if (nodes.length > 0 || connections.length > 0 || ghostNodes.length > 0) {
```

`useCallback` dependency array bijgewerkt:

```typescript
[
  nodes.length,
  connections.length,
  ghostNodes.length,
  workflowId,
  clearVibeMessages,
  clearChatMessages,
  clearRefinement,
  resetWorkflow,
  addMessage,
  onNavigate,
];
```

`addMessage`-aanroep in `doReset` gecorrigeerd naar ASCII-only content
(emoji verwijderd per CLAUDE.md NOOIT-lijst).

## Tests

- `FocusModeBuilderEnhanced.dag2.test.tsx` -- DATA-005: 2 nieuwe tests GREEN
  - connections aanwezig zonder nodes -> confirmation zichtbaar
  - ghostNodes aanwezig zonder nodes -> confirmation zichtbaar

## Trainingssamenvatting

### Flow 1: Nieuw workflow starten met onopgeslagen verbindingen of ghost-nodes

- Actor: Gebruiker die werkt in de Focus Mode Builder
- Voorwaarde: Builder heeft 1+ verbindingen OF 1+ ghost-nodes (nodes mag leeg zijn); workflow is niet opgeslagen
- Actie: Gebruiker klikt op de "New Workflow"-knop
- Systeemreactie: `pendingConfirm`-banner verschijnt met tekst "You have unsaved work. Start a new workflow anyway?"
- Succesrespons: Gebruiker bevestigt -> workflow gereset, navigatie naar /focus-builder
- Foutrespons: n.v.t.
- Uitzonderingen: nodes.length === 0 EN connections.length === 0 EN ghostNodes.length === 0 -> directe reset zonder banner

# FE-CMP-022: FocusModeBuilderEnhanced handleExit unsaved-changes guard

**Sprint:** Studio UI Fix Dag 2
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

`handleExit` in `FocusModeBuilderEnhanced` riep direct `resetWorkflow()` en `onExit()` aan
zonder te controleren of er onopgeslagen wijzigingen waren. Gebruikers verloren werk zonder
waarschuwing wanneer ze op de Exit-knop klikten (DATA-006).

## Implementatie

### `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx`

`hasUnsavedChanges` toegevoegd aan de store-destructuring (regel 82-116).

`handleExit` uitgebreid met guard:

```typescript
const handleExit = useCallback(() => {
  if (hasUnsavedChanges) {
    setPendingConfirm({
      message: "You have unsaved work. Exit anyway?",
      onConfirm: () => {
        resetWorkflow();
        localStorage.removeItem("focus-builder-autosave-new");
        onExit?.();
      },
    });
    return;
  }
  resetWorkflow();
  localStorage.removeItem("focus-builder-autosave-new");
  onExit?.();
}, [hasUnsavedChanges, resetWorkflow, onExit]);
```

Hergebruikt de bestaande `pendingConfirm` inline-banner (regel 1277) -- geen nieuw UI-element
nodig.

## Tests

- `FocusModeBuilderEnhanced.dag2.test.tsx` -- DATA-006: 2 tests GREEN
  - hasUnsavedChanges true -> confirmation zichtbaar, onExit niet direct aangeroepen
  - hasUnsavedChanges false -> onExit direct aangeroepen (bestaand gedrag bewaard)

## Trainingssamenvatting

### Flow 1: Exit builder met onopgeslagen wijzigingen

- Actor: Gebruiker die werkt in de Focus Mode Builder
- Voorwaarde: `hasUnsavedChanges === true` in de workflow store
- Actie: Gebruiker klikt op de "Exit (Esc)"-knop of drukt op Esc
- Systeemreactie: `pendingConfirm`-banner verschijnt met tekst "You have unsaved work. Exit anyway?"
- Succesrespons: Gebruiker bevestigt -> resetWorkflow() aangeroepen, autosave gewist, onExit() uitgevoerd
- Foutrespons: n.v.t.
- Uitzonderingen: hasUnsavedChanges false -> directe exit zonder banner (bestaand gedrag)

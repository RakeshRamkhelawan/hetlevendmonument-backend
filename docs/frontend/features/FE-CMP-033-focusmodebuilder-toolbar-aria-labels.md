# FE-CMP-033 -- FocusModeBuilderEnhanced toolbar aria-labels (A11Y-005)

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 5
**Audit-bevinding:** A11Y-005

---

## Probleemstelling

De Undo- en Redo-knoppen in de FocusModeBuilderEnhanced toolbar waren icon-only: ze hadden alleen een `title` attribute maar geen `aria-label`. Screenreaders kondigen de knop aan zonder naam, wat WCAG 2.1 SC 4.1.2 schendt. Bovendien ontbrak `type="button"` (impliciete form-submit risico) en `aria-hidden="true"` op de SVG-iconen.

## Implementatie

**Bestand:** `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx`

Undo-knop (regels ~1166-1178):

```tsx
<button
  type="button"
  onClick={undo}
  disabled={!canUndo}
  aria-label="Ongedaan maken (Ctrl+Z)"
  title="Undo (Ctrl+Z)"
  className="..."
>
  <svg aria-hidden="true" width="18" height="18" ...>
```

Redo-knop (regels ~1181-1203):

```tsx
<button
  type="button"
  onClick={redo}
  disabled={!canRedo}
  aria-label="Opnieuw uitvoeren (Ctrl+Y)"
  title="Redo (Ctrl+Y)"
  className="..."
>
  <svg aria-hidden="true" width="18" height="18" ...>
```

Wijzigingen:

- `type="button"` toegevoegd (voorkomt impliciete form-submit)
- `aria-label` met Nederlandse naam + sneltoets toegevoegd
- `aria-hidden="true"` op beide SVG-iconen (decoratief wanneer knop een label heeft)

## Trainingssamenvatting

**Actor:** Screenreader-gebruiker werkt aan een workflow in de FocusMode editor.

**Voorwaarde:** FocusMode builder is open; toolbar is zichtbaar; gebruiker navigeert met Tab.

**Actie:** Gebruiker tabbert naar de Undo-knop en activeert die.

**Systeemreactie:** Screenreader kondigt aan: "Ongedaan maken (Ctrl+Z), knop". De laatste actie wordt ongedaan gemaakt.

**Succesrespons:** Gebruiker weet wat de knop doet zonder de SVG visueel te interpreteren.

**Foutrespons:** Knop is disabled (`disabled={!canUndo}`) als er niets te undoen is; screenreader kondigt aan als "uitgeschakeld".

**Uitzonderingen:** `title` blijft behouden als tooltip voor muisgebruikers.

---

## Tests

- `FocusModeBuilderEnhanced.a11y.test.tsx > FocusModeBuilderEnhanced accessibility: toolbar aria-labels (A11Y-005)` -- 2 tests GROEN

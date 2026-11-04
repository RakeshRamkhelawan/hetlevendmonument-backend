# FE-CMP-036 -- KeyboardShortcutsModal focus trap + aria-modal (A11Y-008)

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 5
**Audit-bevinding:** A11Y-008

---

## Probleemstelling

De KeyboardShortcutsModal miste een focus trap en `aria-modal="true"`. Bij openen werd focus niet verplaatst naar de modal; Tab-toetsen konden de modal verlaten; VoiceOver kon met de virtuele cursor achter de modal navigeren. Dit schendt WCAG 2.1 SC 2.1.2 (No Keyboard Trap -- focus moet IN de modal blijven) en SC 4.1.2.

## Implementatie

**Bestand:** `frontend/src/components/studio/KeyboardShortcutsModal.tsx`

Hergebruik van het bestaande `useFocusTrap` hook (`frontend/src/hooks/useFocusTrap.ts`):

```tsx
import { useFocusTrap } from "@/hooks/useFocusTrap";

const { containerRef } = useFocusTrap(isOpen);
```

Dialog div (regels ~78-84):

```tsx
<div
  ref={containerRef}
  className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[420px] max-h-[80vh] overflow-y-auto shadow-2xl"
  onClick={(e) => e.stopPropagation()}
  role="dialog"
  aria-modal="true"
  aria-label={copy.studio.shortcuts.title}
>
```

`useFocusTrap` gedrag:

- Bewaart de vorige focus (`document.activeElement`) bij activatie
- Focust het eerste focusbare element in de container
- Traps Tab en Shift+Tab (opnieuw zoeken in DOM bij elke Tab-press -- geen stale-closure)
- Herstelt de vorige focus bij deactivatie (isOpen=false)

`aria-modal="true"`: verhindert dat VoiceOver/NVDA met de virtuele cursor achter de modal navigeert.

Bestaande Escape-key `useEffect` is behouden -- `useFocusTrap` handelt alleen Tab af.

## Trainingssamenvatting

**Actor:** Toetsenbord-gebruiker of screenreader-gebruiker opent de sneltoetsen-modal via "?".

**Voorwaarde:** Studio is open; gebruiker drukt op "?" om sneltoetsen te tonen.

**Actie:** Modal verschijnt.

**Systeemreactie:** Focus springt automatisch naar de sluit-knop (eerste focusbaar element). Tab en Shift+Tab bewegen focus alleen binnen de modal. Escape sluit de modal en geeft focus terug aan het triggerelement.

**Succesrespons:** Gebruiker kan de modal volledig met toetsenbord bedienen zonder naar achtergrond-content te ontsnappen.

**Foutrespons:** N.v.t. -- modal is statisch (geen laadfout).

**Uitzonderingen:** De modal heeft momenteel 1 focusbaar element (sluit-knop). Tab wrap-gedrag is dan triviaal (focus blijft op sluit-knop), maar de hook is correct gewired en retourneert focus bij sluiten.

---

## Tests

- `KeyboardShortcutsModal.test.tsx > Accessibility: focus management (A11Y-008)` -- 5 tests GROEN

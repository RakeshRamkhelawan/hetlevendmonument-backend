# FE-CMP-034 -- ChatPanel tab bar ARIA semantics (A11Y-006)

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 5
**Audit-bevinding:** A11Y-006

---

## Probleemstelling

De Chat/Suggesties tab-balk in ChatPanel gebruikte gewone `<button>`-elementen zonder ARIA tab-semantics. Screenreaders presenteerden het als twee losse knoppen, niet als een tabblad-widget. Dit schendt WCAG 2.1 SC 1.3.1 en het WAI-ARIA Authoring Practices tablist-patroon.

## Implementatie

**Bestand:** `frontend/src/components/studio/ChatPanel.tsx`

Tab-container (regel ~125):

```tsx
<div role="tablist" className="shrink-0 flex border-b border-zinc-800">
```

Chat-tab (regels ~126-142):

```tsx
<button
  type="button"
  role="tab"
  id="tab-chat"
  aria-selected={activeTab === 'chat'}
  tabIndex={activeTab === 'chat' ? 0 : -1}
  ...
>
```

Suggesties-tab (regels ~143-160):

```tsx
<button
  type="button"
  role="tab"
  id="tab-suggestions"
  aria-selected={activeTab === 'suggestions'}
  tabIndex={activeTab === 'suggestions' ? 0 : -1}
  ...
>
```

Tabpanels (regels ~170-283):

```tsx
{activeTab === 'suggestions' ? (
  <div id="panel-suggestions" role="tabpanel" aria-labelledby="tab-suggestions" ...>
) : (
  <div id="panel-chat" role="tabpanel" aria-labelledby="tab-chat" ...>
)}
```

Bewuste keuze: geen `aria-controls` -- bij ternary rendering is slechts het actieve panel in de DOM. `aria-controls` op een inactieve tab zou verwijzen naar een afwezig element (WCAG 4.1.2 schending). Het `role="tabpanel"` + `aria-labelledby` patroon is voldoende per ARIA spec.

## Amendment: ArrowLeft/ArrowRight navigatie (FA-003 fix)

**Toegevoegd na Final Approver bevinding FA-003 (SP-STUDIO-UI-FIX Dag 5)**

`handleTabKeyDown` handler + refs voor focus-management (regels ~103-112):

```tsx
const chatTabRef = useRef<HTMLButtonElement>(null);
const suggestionsTabRef = useRef<HTMLButtonElement>(null);

const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    const newTab: Tab = activeTab === "chat" ? "suggestions" : "chat";
    setActiveTab(newTab);
    (newTab === "suggestions"
      ? suggestionsTabRef
      : chatTabRef
    ).current?.focus();
  }
};
```

Beide knoppen krijgen `ref` en `onKeyDown={handleTabKeyDown}`. Met 2 tabs zijn ArrowRight en ArrowLeft equivalent (toggle). WCAG 2.1.1 schending opgelost.

## Trainingssamenvatting

**Actor:** Toetsenbord-gebruiker of screenreader-gebruiker werkt in de Studio met de ChatPanel.

**Voorwaarde:** ChatPanel is open; Chat-tab is actief; gebruiker heeft focus op de tab-balk.

**Actie:** Gebruiker drukt ArrowRight om naar Suggesties-tab te wisselen.

**Systeemreactie:** Suggesties-tab krijgt `aria-selected=true`, focus springt naar de Suggesties-knop. Screenreader kondigt aan: "Suggesties, tabblad, geselecteerd, 2 van 2".

**Succesrespons:** Gebruiker kan de volledige tab-widget navigeren zonder muis.

**Foutrespons:** N.v.t. -- tabwisseling is altijd beschikbaar als panel zichtbaar is.

**Uitzonderingen:** Home/End toetsen zijn niet geimplementeerd (2-tab widget -- geen praktische meerwaarde).

---

## Tests

- `ChatPanel.test.tsx > Accessibility: tab semantics (A11Y-006)` -- 3 tests GROEN
- `ChatPanel.test.tsx > Accessibility: arrow key tab navigation (A11Y-009)` -- 4 tests GROEN

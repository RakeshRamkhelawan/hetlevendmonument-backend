# FE-CMP-035 -- ChatPanel message feed live region (A11Y-007)

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 5
**Audit-bevinding:** A11Y-007

---

## Probleemstelling

De berichtenfeed in ChatPanel laadde nieuwe berichten dynamisch maar had geen `aria-live` region. Screenreaders kondigen nieuwe chatberichten niet aan, waardoor gebruikers elke keer handmatig moeten navigeren om nieuwe berichten te lezen. Dit schendt WCAG 2.1 SC 4.1.3.

## Implementatie

**Bestand:** `frontend/src/components/studio/ChatPanel.tsx`

Berichtenfeed container (regels ~193-198):

```tsx
<div
  role="log"
  aria-live="polite"
  aria-label="Chatgesprek"
  className="flex-1 overflow-y-auto p-4 space-y-4"
>
```

Keuzes:

- `role="log"`: semantisch juist voor conversatiegeschiedenissen; impliceert `aria-live="polite"` maar expliciete declaratie vergroot AT-compatibiliteit.
- `aria-live="polite"`: wacht op een natural break; chatberichten zijn niet urgent.
- `aria-label="Chatgesprek"`: geeft de live region een toegankelijke naam voor screenreaders die meerdere live regions onderscheiden.
- `aria-relevant` (default `additions text`) is niet overschreven -- standaardgedrag is correct voor chat.

## Trainingssamenvatting

**Actor:** Screenreader-gebruiker voert een gesprek met de AI Copilot.

**Voorwaarde:** ChatPanel is open; Chat-tab is actief; gebruiker heeft een bericht verstuurd.

**Actie:** AI-copilot stuurt een antwoord terug.

**Systeemreactie:** Screenreader kondigt het nieuwe AI-bericht op een natural break aan, zonder dat de gebruiker de focus hoeft te verplaatsen.

**Succesrespons:** Gebruiker hoort het antwoord automatisch voorgelezen zonder navigatieactie.

**Foutrespons:** N.v.t. -- live region is altijd actief als Chat-tab zichtbaar is.

**Uitzonderingen:** Wanneer Suggesties-tab actief is, is de berichtenfeed niet in de DOM (ternary rendering); live region is dan ook niet actief.

---

## Tests

- `ChatPanel.test.tsx > Accessibility: message feed live region (A11Y-007)` -- 2 tests GROEN

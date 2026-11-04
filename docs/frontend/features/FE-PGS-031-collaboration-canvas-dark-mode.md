# FE-PGS-031 -- CollaborationCanvas ADR-028 Dark-Mode Retrofit

**Sprint:** SP-FE-2G CollaborationCanvas ADR-028 afsluiting
**Status:** APPROVED
**Datum:** 2026-07-01
**Bestand:** `frontend/src/pages/CollaborationCanvas.tsx`

---

## Beschrijving

ADR-028 dark-mode compliance retrofit voor de drie subcomponenten van `CollaborationCanvas.tsx`.
De pagina-wrapper was al dark-compliant (`bg-gradient-to-br from-slate-900 via-violet-900 to-slate-900`).
Vijf locaties in `ConnectionBanner`, `NodeChip` en `CanvasArea` gebruikten nog light-mode Tailwind tokens.

Route, lazy-import en sidebar-link zijn aangemaakt in SP-SEC-002 (FE-PGS-030).

---

## Gewijzigde tokens per subcomponent

| Subcomponent | Locatie | Oud | Nieuw |
|---|---|---|---|
| `ConnectionBanner` | connecting-state | `bg-amber-100 text-amber-800` | `bg-amber-900/30 text-amber-300` |
| `ConnectionBanner` | disconnected-state | `bg-red-100 text-red-800` | `bg-red-900/30 text-red-300` |
| `NodeChip` | base card | `bg-white` | `bg-slate-900 text-slate-100` |
| `NodeChip` | idle border | `border-gray-300 hover:border-violet-300` | `border-slate-700 hover:border-violet-400` |
| `NodeChip` | selected ring | `ring-violet-300` | `ring-violet-500/30` |
| `CanvasArea` | canvas achtergrond | `bg-white border-gray-200` | `bg-slate-950 border-slate-800` |
| `CanvasArea` | sticky note knop | `bg-amber-100 text-amber-800 border-amber-300 hover:bg-amber-200` | `bg-amber-900/30 text-amber-300 border-amber-800 hover:bg-amber-900/50` |
| `CanvasArea` | empty-state tekst | `text-gray-400` | `text-slate-500` |

Contrast-ratios berekend door code-reviewer:
- `text-amber-300` op `bg-amber-900/30` (slate-900 achtergrond): ~7.1:1 -- WCAG AA OK
- `text-red-300` op `bg-red-900/30` (slate-900 achtergrond): ~5.2:1 -- WCAG AA OK
- `text-slate-100` op `bg-slate-900`: ~17:1 -- WCAG AA OK

---

## Trainingssamenvatting

- Actor: gebruiker op de `/collaboration` pagina
- Voorwaarde: ingelogd; WebSocket-verbinding actief of offline
- Actie: pagina laden
- Systeemreactie: canvas wordt getoond in het donkere ADR-028 kleurenpalet
  - `CanvasArea`: `bg-slate-950` achtergrond met `border-slate-800`
  - `NodeChip`: `bg-slate-900` kaartjes met `text-slate-100` labels
  - `ConnectionBanner` (connecting): `bg-amber-900/30` met `text-amber-300`
  - `ConnectionBanner` (disconnected): `bg-red-900/30` met `text-red-300`
  - Sticky note knop: `bg-amber-900/30` met `text-amber-300`
- Succesrespons: alle acht subcomponent-tokens zijn compliant met de ADR-028 dark-mode token-set
- Foutrespons: geen; deze retrofit raakt geen gedragslogica
- Uitzonderingen: `NodeChip` positie-layout via inline style (`left`/`top`) blijft ongewijzigd

---

## Tests

Nieuw testbestand: `frontend/src/pages/__tests__/CollaborationCanvas.darkmode.test.tsx`
- 7 dark-mode compliance tests (RED voor fix, GREEN na fix)
- Bestaand: `CollaborationCanvas.test.tsx` (8 tests), `CollaborationCanvas.ws.test.tsx` (21 tests), `CollaborationCanvas.route.test.tsx` (3 tests)
- Totaal na fix: 39 tests / 0 failed

---

## Niet aangeraakt

- WebSocket-logica (connect, onmessage, onclose, reconnect)
- `data-testid` attributen
- `aria-*` attributen
- `SyncedCommentsSidebar` (buiten scope)
- `LiveCursorOverlay` (buiten scope)
- Pagina-wrapper (al dark-compliant)

# FE-SEC-011 Kaart-popup zonder HTML-injectie

**ID:** `FE-SEC-011` | **Datum:** 2026-11-01 | **Bron:** markt-review 2026-09-24, blokkade 5

## Wat

`portal/src/components/Map.tsx` zette titel, plaatsnaam en afbeeldingsadres van inzenders
ongefilterd in een HTML-string (`setHTML`). Een titel als `<img src=x onerror=...>` werd
uitgevoerd bij iedere bezoeker van de kaart (stored XSS). Nieuw: `portal/src/components/map-popup.ts`
bouwt de popup als DOM-boom met `textContent`; `Map.tsx` gebruikt `setDOMContent`.
Afbeeldingsadressen alleen met `http(s)://` of een enkel `/` (niet `//` of `/\`).

## Trainingssamenvatting

- **Actor:** bezoeker van de kaart.
- **Voorwaarde:** er staat een goedgekeurd verhaal met locatie op de kaart.
- **Actie:** klikt op of opent met het toetsenbord een markering.
- **Systeemreactie:** toont plaats, titel, eventueel afbeelding en een link naar het verhaal.
- **Succes:** tekst van inzenders verschijnt letterlijk, nooit als code.
- **Fout:** een onveilig afbeeldingsadres wordt weggelaten; de rest van de popup blijft.
- **Uitzonderingen:** geen plaatsnaam -> "Nederland".

## Gemeten

`portal/src/__tests__/MapPopup.test.ts` (10 tests). Mutatie: `titel.textContent` -> `innerHTML`
geeft 2 rode tests. Volledige portal-suite en `tsc --noEmit` groen.

# FE-CMP-029 -- LibraryPanel ARIA tab panel semantiek volledig

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 4
**Audit-bevinding:** A11Y-001

---

## Probleemstelling

LibraryPanel had al `role="tablist"`, `role="tab"` en `aria-selected` (partieel correct), maar miste `id` + `aria-controls` op de tabs en `role="tabpanel"` + `aria-labelledby` + `id` op de panels. Hierdoor konden screenreaders de relatie tussen tab en panel niet afleiden.

## Implementatie

**Bestand:** `frontend/src/components/studio/LibraryPanel.tsx`

- Workflows-tab: `id="tab-workflows"`, `aria-controls="panel-workflows"`
- Templates-tab: `id="tab-templates"`, `aria-controls="panel-templates"`
- Workflows-panel: `id="panel-workflows"`, `role="tabpanel"`, `aria-labelledby="tab-workflows"`
- Templates-panel: `id="panel-templates"`, `role="tabpanel"`, `aria-labelledby="tab-templates"`
- Panels omgezet van `<>` Fragment naar `<div>` met ARIA-attributen

## Trainingssamenvatting

**Actor:** Screenreader-gebruiker navigeert via toetsenbord door de Studio bibliotheek.

**Voorwaarde:** LibraryPanel is zichtbaar; gebruiker heeft toetsenbordnavigatie actief.

**Actie:** Gebruiker drukt Tab om de tablijst te bereiken; navigeert met pijltoetsen tussen "Workflows" en "Templates".

**Systeemreactie:** Screenreader kondigt: "Workflows, tab, 1 van 2, geselecteerd" of "Templates, tab, 2 van 2".

**Succesrespons:** Screenreader kondigt het actieve tabpanel correct aan inclusief naam van de bijbehorende tab.

**Foutrespons:** n.v.t. -- ARIA-attributen zijn statisch en kunnen niet mislukken.

**Uitzonderingen:** Indien CSS het panel visueel verbergt maar niet uit de DOM verwijdert, is `aria-hidden` de aangewezen aanpak (niet toegepast, panels worden volledig gemount/unmount).

---

## Tests

- `LibraryPanel.test.tsx > Accessibility: tab panel semantics (A11Y-001 volledig)` -- 3 tests GROEN
- Bestaande A11Y-001 tests (3) nog steeds GROEN

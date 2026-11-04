# FE-CMP-030 -- LibraryPanel delete-knop toetsenbordtoegang (A11Y-002)

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 4
**Audit-bevinding:** A11Y-002 (TDD-verify -- code was al correct)

---

## Probleemstelling

Auditbevinding A11Y-002: de delete-knop in LibraryPanel verdween visueel bij `opacity-0` en was onzichtbaar voor toetsenbordgebruikers die via Tab navigeren (focus-indicator ontbrak).

## Bevinding bij TDD-verify

Na schrijven van de rode test bleek de code al correct: de delete-knop heeft `focus-visible:opacity-100` en `focus-visible:ring-1 focus-visible:ring-red-400/50`. De bestaande test was meteen GROEN. Geen code change vereist.

**Bestand:** `frontend/src/components/studio/LibraryPanel.tsx:229`

```tsx
className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-1 focus-visible:ring-red-400/50 rounded p-1 text-zinc-500 hover:text-red-400 transition-all"
```

## Trainingssamenvatting

**Actor:** Toetsenbordgebruiker navigeert door de workflowlijst in de Studio bibliotheek.

**Voorwaarde:** LibraryPanel is zichtbaar met minimaal 1 workflow; gebruiker tabnavigeert door de lijst.

**Actie:** Gebruiker tabbt naar de delete-knop van een workflow-rij.

**Systeemreactie:** Delete-knop wordt volledig zichtbaar (opacity-100) en toont een rode focus-ring als visuele indicator.

**Succesrespons:** Gebruiker ziet de delete-knop en kan Enter/Space drukken om de soft-delete te activeren.

**Foutrespons:** n.v.t. -- focus-visible is CSS-gedreven en kan niet mislukken.

**Uitzonderingen:** In browsers zonder focus-visible support (IE11 -- buiten scope) valt de knop terug op `group-hover:opacity-100`.

---

## Tests

- `LibraryPanel.test.tsx > Accessibility: delete button keyboard visibility (A11Y-002)` -- GROEN (TDD-verify)

# FE-CMP-031 -- Studio zoekvelden en textarea labels (A11Y-003)

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 4
**Audit-bevinding:** A11Y-003 (TDD-verify -- code was al correct)

---

## Probleemstelling

Auditbevinding A11Y-003: zoekvelden in LibraryPanel (workflows en templates) misten een koppelbaar label, waardoor screenreaders geen context konden aankondigingen bij focus.

## Bevinding bij TDD-verify

Na schrijven van de rode tests bleek beide inputs al een `aria-label` te hebben:
- Workflows-zoekveld: `aria-label="Zoek workflows"` (LibraryPanel.tsx:166)
- Templates-zoekveld: `aria-label="Zoek templates"` (LibraryPanel.tsx:256)

Beide tests waren meteen GROEN. Geen code change vereist.

## Trainingssamenvatting

**Actor:** Screenreader-gebruiker doorzoekt workflows of templates in de Studio bibliotheek.

**Voorwaarde:** LibraryPanel is zichtbaar; de juiste tab is actief.

**Actie:** Gebruiker tabbt naar het zoekveld.

**Systeemreactie:** Screenreader kondigt aan: "Zoek workflows, bewerkbaar tekstveld" of "Zoek templates, bewerkbaar tekstveld".

**Succesrespons:** Gebruiker begrijpt het doel van het invoerveld en kan typen om te filteren.

**Foutrespons:** n.v.t. -- aria-label is statisch attribuut.

**Uitzonderingen:** n.v.t.

---

## Tests

- `LibraryPanel.test.tsx > Accessibility: search field labels (A11Y-003)` -- 2 tests GROEN (TDD-verify)

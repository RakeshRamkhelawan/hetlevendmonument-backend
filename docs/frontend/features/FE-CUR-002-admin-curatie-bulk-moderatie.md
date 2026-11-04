# Feature-spec: FE-CUR-002 AdminCuratie Bulk Moderatie & Multi-Select

**ID:** `FE-CUR-002`  
**Onderwerp:** AdminCuratie Multi-Select Wachtrij, Indeterminate Checkbox, Floating Toolbar & DSA Art. 17 Afwijsmodal  
**Aanmaakdatum:** 2026-09-15  
**Status:** Geimplementeerd & Geverifieerd  
**Sprint / Context:** ADR-029 P1 / P2 Erfgoedportaal Curatie & Schaalbaarheid  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

Voor curatoren en erfgoedbeheerders is het handmatig één voor één beoordelen van tientallen inzendingen een tijdrovende taak. `FE-CUR-002` breidt het curatiepaneel ([AdminCuratie.tsx](file:///c:/Users/rsram/OneDrive/Documenten/GitHub/het-levend-monument/portal/src/pages/AdminCuratie.tsx)) uit met een volledige multi-select bulk moderatie functionaliteit:

1. **Multi-Select Checkboxen:** In de 'pending' wachtrij beschikt elk item over een checkbox met uniek `aria-label`.
2. **"Alles Selecteren" Toggle:** Header balk met native checkbox die automatisch tri-state `indeterminate` synchroniseert via React `ref` wanneer een subset geselecteerd is.
3. **Zwevende Bulk-Actiebalk (Floating Toolbar):**
   - Verschijnt onderaan het scherm wanneer $\ge 1$ item geselecteerd is.
   - Bevat een `aria-live="polite"` statusindicator met het aantal geselecteerde items.
   - Actieknoppen: "Goedkeuren (X)" en "Afwijzen (X)".
   - "Wissen" knop en `Escape`-toets ondersteuning om selectie direct op te heffen.
4. **DSA Art. 17 Bulk Afwijsmodal:**
   - Opent bij klik op "Afwijzen".
   - Dwingt een gemotiveerde verklaring (minimaal 5 tekens) af conform de EU Digital Services Act.
   - Bevat live karakterteller en duidelijke waarschuwing dat alle geselecteerde inzenders deze motivering ontvangen.
5. **Digitale Toegankelijkheid (WCAG 2.1 AA):**
   - Volledige toetsenbordbediening, correcte ARIA roles (`role="toolbar"`, `role="dialog"`, `role="status"`), 0 axe-core schendingen.

---

## 2. Component & Client Integratie

- **`portal/src/types/index.ts`:** `BulkFailedItem`, `BulkModerationResponse`.
- **`portal/src/api/client.ts`:**
  - `bulkApproveContent(contentIds: number[])`: voert bulk-goedkeuring uit.
  - `bulkRejectContent(contentIds: number[], rejectionReason: string)`: voert bulk-afwijzing uit.
- **`portal/src/pages/AdminCuratie.tsx`:**
  - Selectie-state (`selectedIds`), indeterminate effect, floating toolbar en afwijsmodal.

---

## 3. Trainingssamenvatting

- **Actor**: Stichtingscurator / Moderator
  - **Flow**: De curator opent de curatiewachtrij (`/admin/curatie`), selecteert de gewenste items individueel of via 'Alles selecteren'. Onderaan het scherm verschijnt de zwevende actiebalk met de selectieteller. De curator kiest 'Goedkeuren' voor directe publicatie of 'Afwijzen' om de gezamenlijke motivering in te voeren. Na bevestiging worden de gemodereerde items direct uit de actieve wachtrij verwijderd en ontvangt de curator een toegankelijke bevestigingsmelding.

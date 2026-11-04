# Feature-spec: FE-CUR-001 AdminCuratie Notice & Takedown Moderatie Tab & Afhandelingsmodal

**ID:** `FE-CUR-001`  
**Onderwerp:** AdminCuratie Notice & Takedown Moderatie Interface & Afhandelingsmodal  
**Aanmaakdatum:** 2026-09-15  
**Status:** Geimplementeerd & Geverifieerd  
**Sprint / Context:** ADR-029 P1 / P2 Erfgoedportaal Curatie & NTD Compliance  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

Voor curatoren en beheerders van een stichtingserfgoedportaal is een toegankelijke, snelle en betrouwbare beheerinterface essentieel om binnengekomen meldingen van inbreuk of bezwaar (Notice & Takedown) tijdig te beoordelen conform de wettelijke termijnen (24-48 uur).

`FE-CUR-001` voorziet [AdminCuratie.tsx](file:///c:/Users/rsram/OneDrive/Documenten/GitHub/het-levend-monument/portal/src/pages/AdminCuratie.tsx) van een dedicated beheer-tabblad:
1. **Notice & Takedown Tab:** Biedt een overzicht van binnengekomen meldingen met badge-teller voor openstaande verzoeken.
2. **Statusfilters:** `Alle`, `In Behandeling (Pending)`, `Offline Gehaald (Approved)`, `Afgewezen (Rejected)`, `Geëscaleerd (Escalated)`.
3. **Meldingskaarten:** Tonen direct het referentienummer (`#NTD-X`), datum, melder, het betwiste erfgoeditem en de juridische grondslag (`legal_basis`).
4. **Interactieve Afhandelingsmodal:** Stelt de curator in staat om met één klik het besluit toe te passen (`APPROVED` / `REJECTED` / `ESCALATED`) met een verplicht motiveringsveld (`resolution_note`).
5. **Toegankelijkheid (WCAG 2.1 AA):** Volledig toetsenbordbedienbaar, duidelijke ARIA-labels, en live regions (`role="status"`, `role="alert"`) voor fout- en succesmeldingen.

---

## 2. Component & Client Integratie

- **`portal/src/types/index.ts`:** `TakedownListItem`, `TakedownListResponse`, `TakedownDetailResponse`, `TakedownResolveRequest`, `TakedownResolveResponse`.
- **`portal/src/api/client.ts`:**
  - `getCuratieTakedowns(params)`: haalt de meldingen op.
  - `getCuratieTakedownDetail(id)`: haalt diepere details op.
  - `resolveCuratieTakedown(id, data)`: verwerkt de toewijzing/afwijzing.
  - `restoreContent(id)`: herstelt offline gehaald item.
- **`portal/src/pages/AdminCuratie.tsx`:**
  - Tabnavigatie uitgebreid met `'takedowns'`.
  - Takedown paneel en afhandelingsmodal met formulieren en feedback.

---

## 3. Trainingssamenvatting

- **Actor**: Stichtingscurator / Moderator
  - **Flow**: De curator logt in op het erfgoedportaal, klikt op 'Curatie' in het hoofdmenu, en schakelt naar het tabblad 'Notice & Takedown'. De curator ziet de openstaande meldingen en filtert optioneel op status. Bij een openstaande melding klikt de curator op 'Beoordelen', kiest de gewenste actie ('Toewijzen & Offline halen', 'Afwijzen' of 'Escaleren'), typt een motivering in het tekstveld, en bevestigt het besluit. De interface geeft direct een toegankelijke statusnotificatie en werkt de lijst automatisch bij.


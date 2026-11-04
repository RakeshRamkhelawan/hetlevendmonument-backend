# Feature Specification: FE-PAGE-014 Admin Portal White-Label Branding & Theme Customizer Interface

**Feature ID:** `FE-PAGE-014`  
**Onderdeel:** Frontend Portal (`portal/src/pages/AdminCuratie.tsx`, `portal/src/api/client.ts`, `portal/src/types/index.ts`)  
**Sprint / Taak:** ADR-029 White-Label Branding & Settings Management  
**Status:** In Development  

---

## 1. Doel & Scope
Voor het Levend Monument platform is het essentieel dat beheerders en curatoren van een stichting eenvoudig hun white-label merkidentiteit kunnen beheren zonder dat er code-wijzigingen nodig zijn.

Deze specificatie omvat:
1. TypeScript contracten voor `PortalSettingsUpdateRequest`.
2. API-client integratie (`updatePortalSettings`) in `portal/src/api/client.ts`.
3. UI-uitbreiding in `AdminCuratie.tsx` met een tabblad "Branding & Instellingen" naast "Moderatie Wachtrij" en "KPI Analytics".
4. Formulier met:
   - Platformnaam (Nederlands en Engels).
   - Kleurkiezers met live hex input voor Primaire kleur en Accentkleur.
   - Logo URL en Favicon URL invoervelden.
   - Contact e-mailadres.
   - Guidelines en Over Ons teksten.
   - Live visual preview component die toont hoe het merk oogt.
5. Volledige WCAG 2.1 AA toegankelijkheid (axe-core getoetst).

---

## 2. Component Ontwerp & Toegankelijkheid
- Toegankelijke invoervelden met expliciet gekoppelde labels (`htmlFor`), duidelijke foutmeldingen en `aria-describedby`.
- Kleurinputs met zowel native HTML5 color picker als synchroon tekstveld met hex-validatie.
- Succesnotificaties via ARIA live regions (`role="status"`).

---

## Trainingssamenvatting

- **Actor**: Stichtingsbeheerder / Curator
  - **Flow**: De beheerder opent het beheerportaal (`/admin/curatie`) en kiest het tabblad "Branding & Instellingen". Het formulier laadt de huidige instellingen op via `api.getSettings()`. De beheerder selecteert een nieuwe primaire kleur via de interactieve color picker en vult de officiële contact-e-mail in. In het live preview venster ziet de beheerder direct het visuele effect. Bij het klikken op "Instellingen Opslaan" verstuurt de frontend een PUT request via `api.updatePortalSettings()`. Er verschijnt een toegankelijke succesmelding en de nieuwe huisstijl wordt direct actief.

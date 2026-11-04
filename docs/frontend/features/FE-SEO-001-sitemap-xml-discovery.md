# Frontend Feature Specification

## Metadata

- Feature ID: `FE-SEO-001`
- Feature naam: Sitemap XML Discovery & Search Engine Harvester Integration
- Status: Completed
- Auteur: Senior Frontend Developer / Architect
- Reviewer: Red Team / Shadow CEO
- Datum: 2026-09-12
- Gerelateerde user story / ticket: ADR-029 Foundation Portal, P2-5 Zoekmachine & Harvester Discovery
- Gerelateerde pagina / route: `portal/public/robots.txt`, `portal/src/pages/DataExport.tsx`, `portal/src/components/Layout.tsx`
- Gerelateerde backend endpoints: `GET /api/v1/foundation/sitemap.xml`, `GET /{tenantSlug}/foundation/sitemap.xml` (`BE-EP-043`)
- Versie: 1.0.0

---

## Doel en Scope

### Doel
Het vindbaar maken van Het Levend Monument en aangesloten erfgoedstichtingen voor zoekmachines (Google, Bing) en erfgoed-harvesters (zoals Netwerk Digitaal Erfgoed). Dit omvat een correcte `robots.txt` met `Sitemap:` instructie, een directe link in de portal footer, en weergave van het sitemap-endpoint op de `DataExport.tsx` pagina inclusief handige copy-to-clipboard functionaliteit.

### In Scope
1. **Robots.txt (`portal/public/robots.txt`):**
   - Directives voor webcrawlers met uitsluiting van beheer- en authenticatieroutes (`/admin`, `/docenten`, `/magic-link`).
   - Verwijzing naar `Sitemap: /api/v1/foundation/sitemap.xml`.
2. **DataExport Pagina (`portal/src/pages/DataExport.tsx`):**
   - 5e query-kaart voor XML Sitemap met toelichting op de FAIR-data interoperabiliteit.
   - Toegankelijke copy-to-clipboard knop met `title` en `aria-label` statusindicatie.
   - Correctie van OAI-PMH endpoint URL naar de officiële `/{tenantSlug}/foundation/oai-pmh` route.
3. **Layout Footer (`portal/src/components/Layout.tsx`):**
   - Directe link naar "Sitemap (XML)" onder de sectie "Informatie & Open Data" met `target="_blank"` en `rel="noopener noreferrer"`.
4. **Unit Tests (`portal/src/__tests__/SitemapDiscovery.test.tsx`):**
   - Vitest tests voor weergave, klembordinteractie en footer-link (3 tests PASS).

### Out of Scope
- Server-side prerendering / dynamic SSR (Vite SPA met gecachete backend XML sitemap volstaat voor zoekmachines conform ADR-029).

---

## Build Summary

- **Nieuw gebouwd:**
  - `portal/public/robots.txt`
  - `portal/src/__tests__/SitemapDiscovery.test.tsx`
- **Gewijzigd:**
  - `portal/src/pages/DataExport.tsx` (toevoegen sitemap query en copy feedback)
  - `portal/src/components/Layout.tsx` (toevoegen sitemap link in footer)

---

## Trainingssamenvatting

- **Component**: Sitemap XML Discovery in Levend Monument Portal.
- **Doel**: Interoperabiliteit en SEO vindbaarheid via webstandaarden.
- **Geverifieerd met**: Vitest suite (25/25 tests PASS), `tsc --noEmit` (0 fouten), `eslint .` (0 fouten), Vite production build clean.
- **Actor**: Bezoeker / Erfgoedonderzoeker
  - **Flow**: Bezoeker navigeert naar footer of `/data-export` -> Ziet directe koppeling naar XML Sitemap -> Klikt op "Kopieer URL" -> URL wordt op het klembord geplaatst met visuele en auditieve bevestiging.


# Frontend Feature Specification

## Metadata

- Feature ID: `FE-EDU-002`
- Feature naam: Teacher Portal Live Educational Access Code Management
- Status: Completed
- Auteur: Senior Frontend Developer / Architect
- Reviewer: Red Team / Shadow CEO
- Datum: 2026-09-12
- Gerelateerde user story / ticket: ADR-029 Foundation Portal, P2-EDU Docentenportaal Koppeling
- Gerelateerde pagina / route: `portal/src/pages/TeacherPortal.tsx`
- Gerelateerde backend endpoints: `POST /{tenantSlug}/foundation/edu/codes`, `GET /{tenantSlug}/foundation/edu/codes`, `DELETE /{tenantSlug}/foundation/edu/codes/{id}` (`BE-EP-044`)
- Versie: 1.0.0

---

## Doel en Scope

### Doel

Vervangen van de client-side dummy code generator (`Math.random()`) in het docentenportaal door een live API-koppeling met de backend access-code generator (`BE-EP-044`). Hierdoor kunnen docenten echte, cryptografisch beveiligde toegangscodes genereren voor hun schoolklassen, met configureerbare geldigheidsduur, foutafhandeling, toegankelijke feedback (aria-busy, live alerts) en een handige kopieerknop voor directe distributie in het klaslokaal.

### In Scope

1. **API Client Integratie (`portal/src/api/client.ts` & `portal/src/types/index.ts`)**:
   - Uitbreiding van `FoundationApiClient` met `createEduCode(request)`, `getEduCodes()` en `revokeEduCode(id)`.
   - Correctie van `validateEduAccess(code)` naar het officiële `/edu/session` POST-endpoint.
   - Types: `CreateEduCodeRequest`, `EduCodeCreateResponse`, `EduCodeListResponse`, `EduCodeItem`.

2. **Docentenportaal UI (`portal/src/pages/TeacherPortal.tsx`)**:
   - Formulier voor invoer van klasnaam (verplicht), docenten e-mail (verplicht) en geldigheidsduur (select: 4 uur, 24 uur, 7 dagen, 30 dagen).
   - Dynamische foutmelding alert (`role="alert"`) bij API-fouten.
   - Laadstatus met `aria-busy="true"` en visuele tekst ("Bezig met genereren...").
   - Resultaatkaart met de unieke 8-teken toegangscode, vervaldatum en klembord-kopieerknop met directe visuele feedback ("Gekopieerd!").

3. **Toegankelijkheid & UX (a11y)**:
   - Duidelijke `<label>` koppelingen met `htmlFor`.
   - Schermlezer-vriendelijke statusmeldingen en focus-beheer.
   - Geen verlies van formulierstatus bij netwerkfouten.

4. **Unit Tests (`portal/src/__tests__/TeacherPortalCodes.test.tsx`)**:
   - 4 uitgebreide React Testing Library tests voor formulieren, API-aanroepen, foutweergave en kopieerinteractie (100% PASS).

---

## Trainingssamenvatting

- **Component**: Teacher Portal Live Access Codes (`FE-EDU-002`)
- **Doel**: Docenten voorzien van veilige, live erfgoedcodes voor hun klas.
- **Architectuurregel**: Geen mock willekeurige getallen op de frontend; enkel cryptografische API-codes uit de backend.
- **Geverifieerd met**: Vitest suite (`npm test`), `tsc --noEmit`, `eslint .`, Vite production build.
- **Actor**: Docent
  - **Flow**: Docent navigeert naar `/docenten` -> Vult klasnaam ("Groep 8A") en e-mailadres in -> Kiest 24 uur geldigheidsduur -> Klikt op "Genereer Toegangscode" -> Systeem toont gegenereerde code met klembordknop -> Docent kopieert de code en deelt deze op het digibord met de leerlingen.

## Update 2026-11-03 (BE-EP-055)

De losse codegenerator op /docenten is vervangen door de docentenomgeving (zie
`docs/backend/features/BE-EP-055-docentenomgeving.md`). Een docent maakt nu een klas; de klascode
komt eenmalig terug van `POST /docent/klassen`. De tests in
`portal/src/__tests__/TeacherPortalCodes.test.tsx` toetsen dezelfde vier gedragingen (formulier,
code tonen, kopieren, foutmelding) in de nieuwe vorm. `/edu/codes` voor curatoren (BE-EP-044) blijft
ongewijzigd bestaan.

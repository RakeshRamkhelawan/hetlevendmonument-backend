# Feature: FE-SEC-010 Portal hCaptcha Bot-Protectie Integratie

## Metadata
- **Feature ID:** `FE-SEC-010`
- **Titel:** Portal hCaptcha Bot-Protectie Integratie
- **Sprint:** ADR-029 Foundation Portal (Levend Monument)
- **Status:** IMPLEMENTATION
- **Auteur:** AI Agent (Senior Architect / Developer)
- **Datum:** 2026-09-12
- **Gerelateerde ADRs:** ADR-029 (Levend Monument Foundation Portal P1-3), OWASP Automated Threats Mitigation
- **Backend Tegenhanger:** `BE-SEC-051` (Bestaande `@require_hcaptcha` decorator & validatieservice)

---

## 1. Doel & Context
Publieke formulieren op internet (zoals inloggen via magic links, nieuwsbriefinschrijvingen en takedown-verzoeken) zijn kwetsbaar voor geautomatiseerde spam, credential harvesting en brute-force aanvallen.
In de backend zijn de endpoints `POST /{tenantSlug}/foundation/auth/magic-link`, `POST /{tenantSlug}/foundation/newsletter/subscribe` en `POST /{tenantSlug}/foundation/takedown` reeds uitgerust met `@require_hcaptcha` en accepteren een optionele `hcaptcha_token`.

`FE-SEC-010` realiseert de frontend integratie in `portal/`:
1. Een herbruikbaar, toegankelijk `HCaptchaWidget` component (`portal/src/components/HCaptchaWidget.tsx`).
2. Ondersteuning voor dynamische script-injectie met respect voor Content Security Policy en privacy.
3. Een robuuste fallback-modus voor test-, staging- en ontwikkelomgevingen waar geen live hCaptcha site key geconfigureerd is.
4. Integratie in de API client (`portal/src/api/client.ts`) en in de drie publieke pagina's (`Login.tsx`, `Newsletter.tsx` en `NoticeTakedown.tsx`).

---

## 2. Technische Architectuur & Componenten

### `HCaptchaWidget.tsx`
- Props:
  - `onVerify: (token: string) => void`
  - `onExpire?: () => void`
  - `onError?: (err: unknown) => void`
  - `className?: string`
- Werking:
  - Leest `import.meta.env.VITE_HCAPTCHA_SITE_KEY`.
  - Indien aanwezig: laadt dynamisch `https://js.hcaptcha.com/1/api.js?render=explicit` en mount het widget in een toegankelijke container met `aria-label="Spambeveiliging verificatie"`.
  - Indien afwezig (dev/test): toont een niet-opdringerige badge ("Bot-protectie: Testmodus") en triggert automatisch `onVerify("test-mock-token")` zodat testen en ontwikkeling soepel blijven verlopen.

### `portal/src/api/client.ts`
- `requestMagicLink(email: string, hcaptchaToken?: string | null)`
- `subscribeNewsletter(email: string, name?: string, preferences?: string[], hcaptchaToken?: string | null)`
- `submitTakedown(data: TakedownRequestData, hcaptchaToken?: string | null)`

### Formulieren Integratie
- `Login.tsx`: render widget onder het e-mailinvoerveld; verzend `hcaptcha_token` mee bij form submit.
- `Newsletter.tsx`: render widget onder de categoriekeuze; verzend `hcaptcha_token` mee bij form submit.
- `NoticeTakedown.tsx`: render widget onder de motivering; verzend `hcaptcha_token` mee bij takedown submit.

---

## 3. Toegankelijkheid (WCAG 2.1 AA)
- Het widget heeft duidelijke labels en instructies voor toetsenbord- en screenreadergebruikers.
- Foutmeldingen worden gecommuniceerd via `role="alert"`.

---

## Trainingssamenvatting

- **Component**: Portal hCaptcha Bot-Protectie Integratie (`FE-SEC-010`)
- **Doel**: Beschermen van publieke formulieren tegen geautomatiseerde bots en abuse.
- **Architectuurregel**: Formulieren bieden een `HCaptchaWidget` en sturen `hcaptcha_token` mee naar de backend endpoints. In afwezigheid van een site key treedt een veilige dev-fallback in werking.
- **Geverifieerd met**: `portal/src/__tests__/HCaptchaIntegration.test.tsx` en vitest E2E/component tests.
- **Actor**: Bezoeker / Inzender
  - **Flow**: Bezoeker vult publiek formulier in (inloggen, nieuwsbrief of takedown) -> Bezoeker voltooit de hCaptcha uitdaging -> Widget ontvangt verificatietoken via `onVerify` -> Token wordt bij form submission meegeleverd aan de backend API -> Backend valideert het token via de hCaptcha verificatieservice.

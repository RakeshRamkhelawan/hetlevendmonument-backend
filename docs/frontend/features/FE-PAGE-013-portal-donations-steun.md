# FE-PAGE-013: Foundation Portal Donatie & Erfgoed Adoptie Pagina

**Status:** APPROVED  
**Auteur:** SanskritiSetu Senior Architect  
**Datum:** 2026-09-12  
**Sprint:** ADR-029 P2-2  
**Component:** `portal/src/pages/Donate.tsx`  

---

## 1. Doel & Gebruikerservaring

`FE-PAGE-013` implementeert de officiële donatie- en erfgoed-adoptiepagina (`/doneren`) voor het Levend Monument en aangesloten erfgoedstichtingen.

### Gebruikersfunctionaliteiten
1. **Bedragselectie**:
   - Vaste keuzeknoppen: €5 ("Onderhoud een Verhaal"), €15 ("Adopteer een Foto/Audioarchief"), €25 ("Educatiepakket voor een Klas"), €50 ("Erfgoedbehoud & Digitalisering").
   - Vrij bedraginvoerveld met automatische validatie (€1 tot €5.000).
2. **Frequentie**:
   - Eenmalige donatie.
   - Maandelijkse steunbijdrage ("Word Vriend van het Monument").
3. **Persoonlijk Bericht & Doel**:
   - Optioneel bericht achterlaten voor op de donateursmuur (max 500 tekens).
   - Optionele koppeling aan een specifiek monument of erfgoedverhaal.
4. **Privacy & Anonimiteit**:
   - Vinkvakje "Doneer anoniem" om de naam te verbergen op de publieke donateursmuur.
5. **Beveiliging & Toegankelijkheid**:
   - Geïntegreerd met `HCaptchaWidget` voor bot-protectie.
   - Voldoet 100% aan WCAG 2.1 AA (semantische labels, aria-live meldingen, contrast en toetsenbordnavigatie).
   - Transparante weergave van stichtingsstatistieken (reeds opgehaald bedrag en aantal donateurs).

---

## 2. API-Koppeling (`portal/src/api/client.ts`)

De pagina communiceert met:
- `POST /{tenantSlug}/foundation/donations/checkout` (`createDonationCheckout`)
- `GET /{tenantSlug}/foundation/donations/stats` (`getDonationStats`)

Bij succesvolle sessiecreatie wordt de gebruiker doorgestuurd naar de veilige Stripe Checkout pagina (of bedankpagina in testmodus).

---

## 3. Trainingssamenvatting

- **Component**: Foundation Portal Donatie & Erfgoed Adoptie Pagina (`FE-PAGE-013`)
- **Doel**: Een interactieve, toegankelijke en warme gebruikerservaring bieden om het monument te steunen.
- **Architectuurregel**: Bedragen in centen naar de backend, WCAG 2.1 AA validatie via `vitest-axe`, fail-open statistieken en veilige bot-protectie.
- **Geverifieerd met**: `portal/src/__tests__/DonatePage.test.tsx` (5 tests PASS, 0 a11y violations).
- **Actor**: Bezoeker / Donateur
  - **Flow**: Bezoeker navigeert naar `/doneren` -> Kiest frequentie en bedrag -> Vult contactgegevens in en kiest eventueel voor anonimiteit -> Formulier valideert invoer en hCaptcha -> Bezoeker klikt op afronden en wordt doorgestuurd naar de Stripe betaalpagina.

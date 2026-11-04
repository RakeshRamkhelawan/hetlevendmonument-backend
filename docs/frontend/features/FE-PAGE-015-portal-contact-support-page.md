# Feature-spec: FE-PAGE-015 Portal Contact & Ondersteuning Pagina

**ID:** `FE-PAGE-015`  
**Onderwerp:** Levend Monument Contactformulier & Support Integratie  
**Aanmaakdatum:** 2026-09-12  
**Status:** In Review  
**Sprint / Context:** ADR-029 P2 Contact & Community Support  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

De contactpagina (`portal/src/pages/Contact.tsx`) stelt burgers, onderzoekers en scholen in staat om laagdrempelig in contact te komen met de erfgoedstichting.

Voorheen bevatte de pagina een simulatie met `setTimeout` en ontbrak een echte API-aanroep en bot-protectie.
Deze feature integreert:
- Echte API-koppeling via `api.submitContactForm()`.
- hCaptcha bot-protectie via `<HCaptchaWidget />`.
- Categoriekeuze (`algemeen`, `educatie`, `donatie`, `archief`, `samenwerking`).
- Duidelijke bevestigingsweergave inclusief traceerbaar referentienummer (`CON-YYYYMMDD-XXXX`).
- Toegankelijke statusmeldingen en foutafhandeling met `role="alert"` / `aria-live`.
- WCAG 2.1 AA a11y garantie (0 axe-core overtredingen).

---

## 2. Component Ontwerp & Flow

- **Pad:** `/contact` in `portal/src/pages/Contact.tsx`.
- **API Client:** `api.submitContactForm(payload)`.
- **Feedback:**
  - Bij verzenden: laadindicator op de verzendknop (`Verzenden...`).
  - Bij succes: scherm met groen checkicoon, referentie-ID en herhaling van het ingevoerde e-mailadres.
  - Bij fout: rode alertbox met duidelijke Nederlandse foutmelding en mogelijkheid tot opnieuw proberen.

---

## 3. Trainingssamenvatting

- **Actor**: Bezoeker / Burger / Onderzoeker
  - **Flow**: De bezoeker opent de contactpagina (`/contact`) in de browser. De bezoeker selecteert een categorie (bijv. "Archief & Verhalen" of "Educatie & Scholen"), vult naam, e-mailadres, onderwerp en de vraag in, en voltooit eventueel de hCaptcha-uitdaging. Na het klikken op "Bericht Verzenden" toont de interface een laadindicator. De frontend stuurt het payload naar `api.submitContactForm()`. Na een succesvol antwoord toont de pagina een toegankelijk groen successcherm met het toegekende referentienummer (`CON-YYYYMMDD-XXXX`). Bij een fout toont de component een duidelijke foutmelding zonder de ingevoerde tekst te wissen.
- **Actor**: Stichting Curator
  - **Flow**: De curator kan het binnengekomen contactverzoek direct identificeren aan de hand van het verstrekte referentienummer.

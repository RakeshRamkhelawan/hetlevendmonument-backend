# Feature-spec: FE-PAGE-016 Portal About Pagina White-Label Branding & Theming Injection

**ID:** FE-PAGE-016  
**Onderwerp:** Dynamische injectie van stichtings-specifieke huisstijl, introductie, missie en community-richtlijnen in About.tsx via TenantContext  
**Aanmaakdatum:** 2026-09-12  
**Status:** In Review  
**Sprint / Context:** ADR-029 P2 White-Label Branding & Theming  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

De over-ons pagina (portal/src/pages/About.tsx) informeert bezoekers, erfgoedpartners en burgers over de missie, ethische principes en het ontstaan van het erfgoedarchief.
Voorheen bevatte de pagina uitsluitend statische teksten en hield geen rekening met de white-label instellingen die curatoren via BE-EP-047 en FE-PAGE-014 hebben geconfigureerd.

Deze feature breidt de frontend uit met:
- Verrijking van TenantContext.tsx met een settings state (PortalSettingsResponse | null) en loadSettings() helper.
- Dynamische rendering in About.tsx:
  - Aangepaste platformnaam (platform_name_nl / tenant 
ame).
  - Stichtingsspecifieke missie en introductietekst (bout_nl).
  - Stichtingsspecifieke community- en erfgoedrichtlijnen (guidelines_nl).
  - Directe contactmogelijkheid naar het geconfigureerde contact_email.
  - Weergave van stichtingslogo (logo_url) indien geüpload.
  - Dynamische fallback naar standaardteksten indien instellingen ontbreken of niet zijn ingevuld.
- Strikte naleving van WCAG 2.1 AA (contrasten, 0 axe-core overtredingen, semantische landmarks en juiste heading-hiërarchie).

---

## 2. Component Ontwerp & Flow

- **Pad:** /over in portal/src/pages/About.tsx.
- **Context:** useTenant() levert zowel 	enant als settings.
- **Weergavelogica:**
  - Hero titel: settings.platform_name_nl || tenant.name || 'Het Levend Monument'.
  - Hero introductie: settings.about_nl vervangt of verrijkt de statische lead paragraaf.
  - Missieblok: toont stichtingsmissie indien aanwezig.
  - Richtlijnenblok: toont settings.guidelines_nl in een speciale community & gedragscode kaart.
  - Contact e-mail: direct doorgelinkt naar mailto: indien aanwezig.
  - Fallback: als settings leeg of niet geconfigureerd zijn, blijft de vertrouwde standaard Levend Monument tekst behouden.

---

## 3. Trainingssamenvatting

- **Actor**: Bezoeker / Burger / Onderzoeker
  - **Flow**: De bezoeker opent de "Over Ons" pagina (/over). De frontend leest via useTenant() de geconfigureerde portaalinstellingen van de actieve stichting uit. De pagina toont direct de herkenbare naam van de stichting, haar specifieke missie, eventuele communityrichtlijnen en het officiële contactadres. Indien de stichting nog geen specifieke teksten heeft ingevuld, toont de pagina naadloos de hoogwaardige standaardteksten van het Levend Monument platform.
- **Actor**: Stichting Curator
  - **Flow**: De curator past in het beheerportaal (/beheer -> Branding & Instellingen) de stichtingsintroductie (bout_nl) of richtlijnen (guidelines_nl) aan. Wanneer bezoekers vervolgens de Over Ons pagina bekijken, zien zij direct de bijgewerkte stichtingsboodschap.


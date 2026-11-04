# FE-SEC-012 Beveiligingsheaders, eigen lettertypes en API via dezelfde herkomst

**ID:** `FE-SEC-012` | **Datum:** 2026-11-01 | **Bron:** markt-review 2026-09-24 blokkade 5 (CSP) en 7 (Google Fonts zonder toestemming)

## Wat

- `portal/security-headers.conf` (nieuw): CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy,
  Permissions-Policy, X-XSS-Protection 0. Wordt in ELKE location ge-include: nginx erft
  `add_header` niet naar een location met een eigen `add_header`, waardoor index.html en alle
  statische bestanden in de oude config GEEN headers kregen.
- `portal/nginx.conf` is een envsubst-template: `/api/` gaat via nginx naar `${API_UPSTREAM}`
  (dezelfde herkomst, geen CORS, CSP `connect-src 'self'`). Resolver + variabele, zodat nginx ook
  start als de backend er nog niet is. Dubbele headers van de backend worden verborgen.
- Lettertypes via `@fontsource-variable/dm-sans` en `@fontsource-variable/playfair-display`
  (exact gepind); de Google Fonts-links zijn weg.

## Trainingssamenvatting

- **Actor:** bezoeker van het portaal.
- **Voorwaarde:** opent een willekeurige pagina.
- **Actie:** de browser laadt pagina, scripts, lettertypes, kaarttegels.
- **Systeemreactie:** elke response draagt de beveiligingsheaders; lettertypes komen van het eigen domein.
- **Succes:** geen verzoek naar Google; een ingevoegd script van een vreemde bron wordt door de browser geweigerd.
- **Fout:** de backend is onbereikbaar: `/api/` geeft 502, de pagina's blijven werken.
- **Uitzonderingen:** hCaptcha, OpenStreetMap-tegels en Stripe staan expliciet toegestaan.

## Gemeten (container `lm-portal:test`, 2026-11-01)

Headers aanwezig op `/` en op een `/assets/*.js`; 0 verwijzingen naar googleapis in index.html;
12 woff2-bestanden in de build; `/privacy` 200; `/api/` 502 met nginx draaiend zonder backend.
Niet gemeten: een geslaagd `/api/`-verzoek met draaiende backend (volgt bij de uitrol in Azure).

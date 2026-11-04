# FE-SEC-009: een late 401 van voor het inloggen logt niet meer uit

**Sprint:** nazorg acceptant scenario 5
**Status:** APPROVED
**Datum:** 2026-10-05
**Tak:** `fix/auth-race-e2e` (basis `5ea09d34`)

## Probleem (gemeten)

Nazorgtoets scenario 5 (`scratch/acceptant-nazorg-scenario5/c.out`): op `/login` vertrekt de
sessiecontrole `GET /api/v1/auth/me`. De gebruiker logt in; het 401-antwoord op die oude `/me`
komt pas binnen als de app al op `/instellingen/vier-ogen/uitleg` staat. Twee plekken reageerden
daarop alsof de NIEUWE sessie verlopen was:

1. `client.ts`: de pagina is dan geen publieke pagina meer, dus de client startte
   `POST /auth/refresh` en bij mislukken `handleSessionExpired` (uitloggen, naar `/login`).
2. `AuthContext.restoreSession`: de `catch` deed `logoutAction()` op elke 401.

Gevolg: "Your session has expired", en op de uitlegpagina werd het PUT-verzoek van
"Bevestigen en doorgaan" afgebroken.

De refresh gaf daarbij 422 in plaats van 401; zie BE-SEC-052.

## Oplossing

Een sessiegeneratie in `frontend/src/lib/api/client.ts`. Hij telt op bij een geslaagde
`authApi.login` en bij `authApi.logout`. Elk verzoek onthoudt de generatie waarin het vertrok:

- een 401 uit een oudere generatie geeft een gewone 401-fout terug, zonder verversen en zonder
  uitloggen;
- mislukt een verversing terwijl er intussen is ingelogd, dan ook geen uitlog;
- `restoreSession` negeert een `/me`-antwoord (goed of fout) uit een oudere generatie.

Verzoeken die NA de login vertrekken houden het bestaande gedrag: een echte verlopen sessie
wordt nog steeds ververst of uitgelogd.

## Tests (eerst rood, daarna groen)

- `frontend/src/lib/api/__tests__/client.stale-401-after-login.test.ts` -- bootst de echte
  volgorde na: `/me` in de lucht, login, navigatie naar de uitlegpagina, dan de late 401.
  Rood op `5ea09d34`: verversing gestart (1 aanroep), `isAuthenticated` false, pad `/login`.
- `frontend/src/contexts/__tests__/AuthContext.stale-restore-after-login.test.tsx` -- rood op
  `5ea09d34`: `isAuthenticated` false na de late 401 van de sessiecontrole.

## Trainingssamenvatting

- Actor: Beheerder of medewerker
- Voorwaarde: de inlogpagina is geopend; de sessiecontrole van de app is nog niet beantwoord.
- Actie: de gebruiker logt in en gaat verder, bijvoorbeeld naar de vier-ogen-uitleg.
- Systeemreactie: het late antwoord van de oude sessiecontrole wordt genegeerd.
- Succesrespons: de gebruiker blijft ingelogd en "Bevestigen en doorgaan" wordt opgeslagen.
- Foutrespons: verloopt de nieuwe sessie later echt, dan volgt de gewone melding en `/login`.
- Uitzonderingen: geen.

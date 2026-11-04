# Frontend Feature Specification

## Metadata

- Feature ID: FE-API-001
- Feature naam: foundationApiClient
- Status: Completed (kickoff -- auth/settings/takedown/newsletter; content/curatie volgt later)
- Auteur: ADR-029 Dag 4
- Reviewer: zelfde sessie, tweede leespas
- Datum: 2026-08-26
- Gerelateerde user story / ticket: ADR-029 Foundation Portal, Dag 4 van 6
- Gerelateerde pagina / route: nog geen (client-kickoff, UI-pagina's volgen in latere dagen)
- Gerelateerde backend endpoints: BE-EP-023 (auth/settings/takedown/newsletter), BE-EP-034 (audit + rate-limit hardening op dezelfde endpoints)
- Gerelateerde design componenten: N/A (API-client, geen UI-component)
- Versie: 1.0.0

---

## Doel en scope

### Doel

Een typed API-client (`foundationApiClient`) die de Foundation Portal backend-endpoints
(magic-link-auth, publieke portal-instellingen, takedown-verzoeken, newsletter-
subscribe/unsubscribe) ontsluit voor toekomstige Foundation Portal-pagina's, zonder dat elke
component zelf `fetch`-aanroepen en URL-opbouw hoeft te herhalen.

### In scope

- `requestMagicLink`, `verifyMagicLink`, `logout` (auth)
- `getSettings` (publieke portal-branding)
- `submitTakedown` (vereist een portal-JWT als Bearer-token)
- `subscribeNewsletter`, `unsubscribeNewsletter`
- Tenant-slug-in-pad-patroon (`/{tenantSlug}/foundation/...`), NIET het gebruikelijke
  `X-Tenant-ID`-header-patroon van `publicApiClient` -- de Foundation Portal is per ontwerp
  bereikbaar voor anonieme bezoekers van een specifieke tenant-portal, dus tenant-identiteit
  kan hier niet uit een JWT-claim komen zoals bij de rest van de applicatie (ADR-003).

### Out of scope

- Content-lijst/detail/upload-endpoints en curatie-endpoints (bestaan al backend-zijde,
  BE-EP-022, maar zijn nog niet in deze client gewrapped -- volgt in een latere dag).
- React Query-hooks / React-componenten die deze client daadwerkelijk aanroepen (dit is de
  kale client-laag, geen UI).
- Retry-gedrag verder dan wat `retryWithBackoff` (gedeeld met `publicApiClient`) al doet.

---

## Build summary

- Nieuw gebouwd:
  - `frontend/src/lib/api/foundationClient.ts`
- Gewijzigd:
  - Geen (geen bestaande component roept dit nog aan -- kickoff, zie "Out of scope")
- Verwijderd:
  - Geen
- Beinvloede bestaande flows:
  - Geen (nieuwe, ongebruikte module -- geen regressierisico voor bestaande pagina's)

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-API-001 | foundationApiClient | API-client (utility) | `frontend/src/lib/api/foundationClient.ts` | Nieuw | (nog geen FE-FLW, UI-pagina's volgen later) |

---

## Technische beschrijving

`foundationApiClient` is bewust GEEN uitbreiding van het bestaande `publicApiClient`
(`publicClient.ts`): dat client's `get`/`post`-methoden accepteren geen custom headers, wat
nodig is voor `submitTakedown`'s `Authorization: Bearer <token>`. In plaats daarvan
hergebruikt `foundationClient.ts` dezelfde onderliggende bouwstenen
(`handleApiResponse`, `retryWithBackoff`, `normalizeApiBaseUrl`) via twee lokale helpers
(`foundationGet`, `foundationPost`) die wel een optionele bearer-token accepteren.

Elke methode is een dunne, typed wrapper rond een van die twee helpers -- geen eigen
foutafhandeling, dat loopt via de gedeelde `handleApiResponse` (gooit een `ApiError` op een
niet-2xx-status, net als `publicApiClient`).

Response-types (`MagicLinkResponse`, `TokenResponse`, `PortalSettings`, `TakedownResponse`,
`NewsletterResponse`) zijn handmatig gespiegeld aan de backend-Pydantic-schemas
(`src/core/api/v1/foundation/schemas.py`) -- geen gegenereerde OpenAPI-types, dus een
toekomstige backend-schemawijziging synchroniseert niet automatisch. Geaccepteerd risico voor
een kickoff-implementatie; een gegenereerde-types-aanpak is een latere verbetering.

## Acceptatiecriteria

- `npm run type-check` (`tsc --noEmit`): 0 fouten.
- `npx eslint src/lib/api/foundationClient.ts`: 0 fouten.
- Elke methode in `FoundationApiClient` heeft een concrete, non-`any` return-type.
- `submitTakedown` is de enige methode die een bearer-token-parameter accepteert en
  doorgeeft als `Authorization`-header.

## Open aannames

- `logout` roept `POST /auth/logout` aan (matcht de backend, die stateless is en alleen
  client-side token-verwijdering verwacht) -- de daadwerkelijke token-verwijdering
  (localStorage/cookie) is NIET onderdeel van deze client-methode, dat is aan de aanroepende
  component/hook.

## Risico's

- Geen gegenereerde types (zie Technische beschrijving) -- een drift-risico bij toekomstige
  schema-wijzigingen, bewust geaccepteerd voor deze kickoff-schaal.

---

## Trainingssamenvatting

- Actor: een toekomstige React-component of hook die de Foundation Portal (magic-link-login,
  publieke instellingen, takedown, newsletter) moet aanroepen
- Voorwaarde: de tenant-slug van de betreffende portal is bekend (uit de URL-route)
- Actie (request): een `foundationApiClient`-methode aanroepen met die tenant-slug (en, voor
  `submitTakedown`, een geldig portal-JWT verkregen via `verifyMagicLink`)
- Systeemverwerking: `foundationGet`/`foundationPost` bouwt de tenant-gescoopte URL
  (`/{tenantSlug}/foundation/...`), voegt een `Authorization`-header toe indien een
  bearer-token is meegegeven, en verwerkt de respons via de gedeelde `handleApiResponse`
- Succesrespons: het typed response-object (`MagicLinkResponse`, `TokenResponse`,
  `PortalSettings`, `TakedownResponse` of `NewsletterResponse`)
- Foutrespons: een `ApiError` (gegooid door `handleApiResponse`) met de HTTP-status en
  server-detail, bijvoorbeeld 404 (onbekende tenant-slug) of 429 (rate-limiet bereikt, zie
  BE-EP-034)
- Uitzonderingen: `submitTakedown` zonder geldig bearer-token faalt met 401/403 (backend-
  zijdige `require_portal_user`-afdwinging, niet client-zijdig gevalideerd)

---

## Definition of Done

- [x] Component/utility is gebouwd
- [x] Type-check groen (`tsc --noEmit`)
- [x] Lint groen (ESLint)
- [x] Acceptatiecriteria zijn testbaar en voldaan
- [x] Open aannames en risico's benoemd
- [x] Review: APPROVED (zie review-FE-API-001.md)

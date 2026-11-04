# Frontend Feature Specification

## Metadata

- Feature ID: FE-FLW-003
- Feature naam: CopilotSidebar op het governed /copilot/turn-pad + right-to-explanation
- Status: Implemented
- Auteur: Implementatie-agent (Dag 5)
- Reviewer: code-reviewer + security-reviewer (Gate 2, beiden APPROVED)
- Datum: 2026-07-09
- Gerelateerde user story / ticket: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 5 (samengevoegd 5+8)
- Gerelateerde pagina / route: CopilotSidebar (GlobalCopilot surface); `/explain?decision_id=...`
- Gerelateerde backend endpoints: `POST /api/v1/copilot/turn`; `GET /api/v1/cva/explain`
- Gerelateerde design componenten: CopilotSidebar, apiClient (`@/lib/api/client`)
- Versie: 1.0

---

## Doel en scope

### Doel

De CopilotSidebar praatte in productie tegen een mock (`serena__chat`) i.p.v. het governance-pad. Daardoor liep chat nooit door PromptGuard/Council/audit, en bereikte `decision_id` (EU AI Act art. 13 right-to-explanation) de UI nooit. Deze feature sluit de sidebar aan op het echte `/copilot/turn`-pad zodat elk antwoord governed is en de "waarom dit antwoord?"-link werkt.

### In scope

- `CopilotService.chat()` routeert via de gecentraliseerde apiClient naar `POST /api/v1/copilot/turn`.
- `decision_id` + `verdict` uit de turn-response worden op het assistant-bericht gezet.
- Echte error-state bij backend-fout (geen misleidende "Serena"-tekst).
- Mock-gate in `serenaService.ts` browser-veilig via `import.meta.env` (mock onmogelijk in productie-build).

### Out of scope

- WebSocket-pad (dag 6 -- nog niet gehard).
- REST task-endpoints.
- `parseIntent` (aparte, productie-dode methode -- ongewijzigd).
- `ai_disclosure` per-bericht surfacing: op moment van FE-FLW-003 gedekt door het persistent "AI Assistant"-label in de sidebar-header (CopilotSidebar.tsx:99-102). Dit is naderhand alsnog per-bericht gesurfaced in FE-FLW-004 (Dag 5 CSRF+compliance hardening, WS4).

---

## Build summary

- Nieuw gebouwd: niets nieuws aan UI (why-link, /explain-route en `CopilotMessage.decision_id` bestonden al).
- Gewijzigd: `frontend/src/services/copilotService.ts` (`chat()` rewire); `frontend/src/services/serenaService.ts` (mock-gate).
- Verwijderd: `serena__chat`-mock uit de sidebar-chatflow (via chat()).
- Beinvloede bestaande flows: CopilotSidebar chat (sendMessage -> chat -> governed turn); right-to-explanation-link wordt nu bereikbaar.

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-FLW-003 | Sidebar chat via governed turn + uitleg | Flow | `frontend/src/services/copilotService.ts`, `frontend/src/components/layout/CopilotSidebar.tsx` | Wijziging | FE-FLW-003 |
| FE-UTL-050 | CopilotService.chat() governed-turn transport | Utility (service) | `frontend/src/services/copilotService.ts` | Wijziging | FE-FLW-003 |
| FE-UTL-051 | SerenaService mock-gate via import.meta.env | Utility (service) | `frontend/src/services/serenaService.ts` | Wijziging | FE-FLW-003 |

---

## Gebruikersflows

### Flow ID: FE-FLW-003

- Naam: Copilot-vraag stellen via het governed pad met uitleg-link
- Startconditie: gebruiker is ingelogd; CopilotSidebar is open.
- Trigger: gebruiker typt een bericht en verzendt (Enter / verzendknop).
- Hoofdstappen: `handleSubmit` -> `useCopilotStore.sendMessage` -> `CopilotService.chat` -> `apiClient.post('/api/v1/copilot/turn', {message, context:{}, stream:false, language:'nl'})` -> backend PromptGuard + Council + audit -> response met `decision_id`/`verdict`.
- Succespad: assistant-bericht verschijnt met de tekst; als `decision_id` gezet is, verschijnt de "Waarom dit antwoord?"-link naar `/explain?decision_id=...`; bij `verdict === 'hitl_required'` verschijnt de goedkeurings-badge.
- Foutpad: bij backend-fout gooit `chat()` de `ApiError` door; de store toont een error-banner en een generiek fout-bericht (geen misleidende "Serena"-tekst).
- Eindtoestand: bericht in de chat-historie; governance-audit-entry backend-zijdig; uitleg-link beschikbaar.

---

## Detaildocumentatie per item

## [FE-UTL-050] CopilotService.chat() governed-turn transport

### 1. Type
Service-methode (transport).

### 2. Locatie
`frontend/src/services/copilotService.ts` -- `CopilotServiceClass.chat()`.

### 3. Gerelateerde flow
FE-FLW-003.

### 4. Doel
De sidebar-chat door het governance-pad laten lopen en de Council-`decision_id` naar de UI brengen.

### 5. Functionele beschrijving
De gebruiker stelt een vraag; het antwoord komt van de echte Co-Pilot (Council-goedgekeurd), met een uitleg-link wanneer een beslissing is vastgelegd.

### 6. Technische beschrijving
`chat(query)` bouwt een `CopilotTurnRequest` (`{message, context:{}, stream:false, language:'nl'}`) en roept `this.apiClient.post<CopilotTurnResponse>('/api/v1/copilot/turn', body)` aan. Het `{data}`-envelope wordt uitgepakt; `content=data.message`, `decision_id=data.decision_id ?? null`, `verdict=data.verdict ?? null`. Geen try/catch: een `ApiError` propageert naar `useCopilotStore.sendMessage`. `context:{}` bevat nooit `tenant_id` (CLAUDE.md regel 6); de backend leidt de tenant uit de sessie af.

### 7. Zichtbaarheids- en toegangsregels
- Vereiste authenticatie: sessiecookie (apiClient `credentials: include`) + CSRF-header voor POST.
- Tenant-isolatie: tenant nooit van de client; backend-derived.

### 8. Input
`query: string` (gebruikersbericht).

### 9. Output
`CopilotMessage` met `content`, `decision_id`, `verdict`.

### 10-13. Validaties / business rules / afhankelijkheden
Backend valideert `CopilotTurnRequest` (`extra="forbid"`); afhankelijk van `/api/v1/copilot/turn` en de apiClient.

### 14. Foutafhandeling
`ApiError` propageert -> store toont error-state. Geen stacktrace of interne details in de UI.

### 15-16. Telemetry / Accessibility
apiClient-timeout ('ai'-groep); geen a11y-impact op deze service-laag (de sidebar-UI is ongewijzigd en al toegankelijk).

### 17. Acceptatiecriteria
- chat() roept `/api/v1/copilot/turn` via apiClient aan, niet `serena__chat`.
- `decision_id` + `verdict` worden op het bericht gezet.
- payload bevat geen `tenant_id`.
- backend-fout -> error-state, geen "Serena"-tekst.

### 18. Gebruikersuitleg
- Stel je vraag in de Copilot-zijbalk; je krijgt een AI-antwoord.
- Bij "Waarom dit antwoord?" zie je de uitleg achter de beslissing.
- Bij een storing verschijnt een foutmelding i.p.v. een nep-antwoord.

### 19. Trainingssamenvatting
Zie sectie Trainingssamenvatting onderaan.

## [FE-UTL-051] SerenaService mock-gate via import.meta.env

### 1. Type
Service-configuratie (mock-gate).

### 2. Locatie
`frontend/src/services/serenaService.ts` -- `executeTool()`.

### 6. Technische beschrijving
De mock-gate gebruikt `import.meta.env.DEV && !import.meta.env.VITE_API_URL` i.p.v. `process.env`. Vite vervangt `import.meta.env.DEV` statisch door `false` in een productie-build, waardoor mock-mode in productie onmogelijk is (dead-code-eliminated).

### 17. Acceptatiecriteria
- Bronbestand bevat geen `process.env`.
- Mock-mode kan niet activeren in een productie-build.

---

## Handleidingstekst

### Voor eindgebruikers

Zie `docs/user-guide/frontend/copilot-sidebar-governed-turn.md`.

---

## Open aannames

- `parseIntent` is niet bereikbaar vanuit een productie-UI (alleen tests/mocks).

## Open vragen

- Geen.

## Risico's

- Dev-build met `VITE_API_URL` gezet raakt nu de echte backend i.p.v. mock voor de (dode) parseIntent-methode -- gewenste richting.

---

## Trainingssamenvatting

### Flow 1: Copilot-vraag via governed turn met uitleg

- Actor: ingelogde gebruiker in de CopilotSidebar.
- Voorwaarde: sidebar open, geldige sessie.
- Actie: typt een bericht en verzendt.
- Systeemreactie: `chat()` POST naar `/api/v1/copilot/turn` (PromptGuard + Council + audit); response bevat `decision_id`/`verdict`.
- Succesrespons: assistant-bericht met tekst; "Waarom dit antwoord?"-link bij aanwezige `decision_id`; goedkeurings-badge bij `hitl_required`.
- Foutrespons: error-banner + generiek fout-bericht (geen "Serena"-tekst).
- Uitzonderingen: geen `decision_id` -> geen uitleg-link; tenant nooit van client.

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle interactieve elementen zijn geinventariseerd
- [x] Alle relevante states zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Gebruikersuitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED

# Frontend Feature Specification

## Metadata

- Feature ID: FE-FLW-004
- Feature naam: Governed copilot/mission mutaties -- CSRF-enforcement + AI-disclosure + eerlijke foutafhandeling
- Status: Implemented
- Auteur: Implementatie-agent (Dag 5 -- CSRF+compliance hardening, WS1-WS9)
- Reviewer: code-reviewer + security-reviewer (Gate 2, beiden APPROVED) -- zie `docs/frontend/review/review-FE-FLW-004.md`
- Datum: 2026-07-07
- Gerelateerde user story / ticket: Dag 5 CSRF+compliance hardening (iter/copilot-fase-b, gemerged naar develop); volgt op de gedeferde Info/Low-items uit `review-FE-FLW-003.md`
- Gerelateerde pagina / route: CopilotSidebar + CommandPalette (GlobalCopilot surface); MissionProposalModal
- Gerelateerde backend endpoints: `POST /api/v1/copilot/turn`, `POST /api/v1/copilot/audit/*`, `POST /api/v1/copilot/proactive-respond`, `POST /api/v1/missions`, `POST /api/v1/missions/{id}/approve`, `POST /api/v1/missions/{id}/reject`, `/contest`
- Gerelateerde design componenten: CopilotSidebar, CommandPalette, MissionProposalModal, apiClient (`@/lib/api/client`), `getHeaders(true)`
- Versie: 1.0

---

## Doel en scope

### Doel

Na FE-FLW-003 (sidebar op het governed turn-pad) bleven drie compliance-/security-gaten open die in de FE-FLW-003-review expliciet naar backlog waren geschoven:

1. State-changing POSTs naar de governed copilot/mission-endpoints gingen als kale `fetch` zonder CSRF-token de deur uit (SEC-010).
2. De `MissionProposalModal` toonde verzonnen kosten (`Math.random`), een verzonnen risicoscore en drie hardgecodeerde "passed" compliance-checks als echte data -- compliance theater op een EU-AI-Act-surface.
3. De machine-leesbare `ai_disclosure` (EU AI Act art. 50) werd door de backend meegestuurd maar nooit getoond.

Deze feature dicht die drie gaten end-to-end en maakt de foutafhandeling eerlijk (geen nep-antwoord-bubbels, geen valse consent-dismiss).

### In scope

- CSRF-header (`X-CSRF-Token` via `getHeaders(true)`) op alle state-changing copilot/mission-POSTs vanuit de frontend; backend handhaaft CSRF op dezelfde endpoints (WS1/WS2/WS8/WS9).
- `MissionProposalModal`: `riskLevel` en compliance-samenvatting afgeleid uit de echte `verdict` + `council_summary`; `costUsd`/`riskScore` optioneel en gerenderd als "Not estimated" wanneer er geen echte bron is (WS3).
- `ai_disclosure` per assistant-bericht gerenderd in de CopilotSidebar en in de CommandPalette-responssectie (WS4).
- Eerlijke error-state: bij backend-fout geen misleidend assistant-bericht en geen valse consent-afhandeling (WS5).
- Cross-surface governance-pariteit + verwijderen van dode `IntentDetail`/serena-resten (WS6/WS7).

### Out of scope

- Backend CSRF-middleware zelf (bestond al; hier alleen de per-endpoint enforcement + de frontend die de header meestuurt). De backend-invariant wordt bewaakt door `tests/architecture/test_copilot_mission_csrf_enforced.py`.
- WebSocket-pad (ongewijzigd).
- Numerieke kostenraming: er is geen echte kostenbron in de turn-response; bewust "Not estimated".

---

## Build summary

- Nieuw gebouwd: per-bericht `ai_disclosure`-caption (sidebar + CommandPalette); per-call-site CSRF-guardtest.
- Gewijzigd: `copilotService.ts`, `useAuditContest.ts`, `useChainVerify.ts`, `useCouncilDecision.ts` (CSRF-header); `MissionProposalModal.tsx` (verzonnen impact verwijderd); `CopilotSidebar.tsx` + `CommandPalette.tsx` (disclosure render + eerlijke fout/consent); `useCopilotStore.ts` (error-state).
- Verwijderd: `Math.random`-kosten/risico en hardgecodeerde compliance-checks uit de mission-proposal; dode `IntentDetail`/serena-verdict-resten.
- Beinvloede bestaande flows: FE-FLW-003 (sidebar-chat) -- de `ai_disclosure`-note die daar als "Out of scope" stond wordt nu wel getoond; MissionProposalModal-goedkeuringsflow.

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-FLW-004 | Governed copilot/mission mutaties met CSRF + disclosure + eerlijke fouten | Flow | copilot/mission surfaces | Wijziging | FE-FLW-004 |
| FE-CMP-060 | AI-disclosure caption per assistant-bericht | UI-component (caption) | `CopilotSidebar.tsx`, `CommandPalette.tsx` | Nieuw | FE-FLW-004 |
| FE-UTL-060 | CSRF-header op state-changing copilot/mission POSTs | Utility (transport) | `copilotService.ts`, `useAuditContest.ts`, `useChainVerify.ts`, `useCouncilDecision.ts` | Wijziging | FE-FLW-004 |
| FE-MOD-060 | MissionProposalModal zonder verzonnen impact | Modal | `MissionProposalModal.tsx` | Wijziging | FE-FLW-004 |

---

## Gebruikersflows

### Flow ID: FE-FLW-004

- Naam: Missie voorstellen/goedkeuren en copilot-antwoord ontvangen langs het gehardende governance-pad
- Startconditie: gebruiker is ingelogd met geldige sessie; CSRF-token is beschikbaar in de sessie.
- Trigger: gebruiker verzendt een copilot-bericht, of stelt een missie voor / keurt goed / wijst af / betwist een audit-beslissing.
- Hoofdstappen: de frontend-call voegt via `getHeaders(true)` de `X-CSRF-Token`-header toe -> backend valideert CSRF + JWT + tenant -> governance (PromptGuard/Council/audit) -> response met `verdict`, `decision_id` en `ai_disclosure`.
- Succespad: assistant-antwoord met, indien aanwezig, de `ai_disclosure`-caption eronder; missie-proposal toont alleen echte impact (risk uit verdict, "Not estimated" voor onbekende kosten).
- Foutpad: bij ontbrekende/ongeldige CSRF-token weigert de backend (403); de UI toont een eerlijke error-state -- geen nep-antwoord en geen valse consent-dismiss.
- Eindtoestand: governance-audit-entry backend-zijdig; UI-state consistent met de echte uitkomst.

---

## Detaildocumentatie per item

## [FE-UTL-060] CSRF-header op state-changing copilot/mission POSTs

### 1. Type
Utility / transport-gedrag.

### 2. Locatie
`frontend/src/hooks/useAuditContest.ts`, `frontend/src/hooks/useChainVerify.ts`, `frontend/src/hooks/useCouncilDecision.ts`, `frontend/src/services/copilotService.ts`.

### 3. Gerelateerde flow
FE-FLW-004.

### 4. Doel
Elke state-changing POST naar een governed copilot/mission-endpoint stuurt een CSRF-token mee, zodat de backend-enforcement (SEC-010) de call accepteert en cross-site request forgery onmogelijk is.

### 5. Functionele beschrijving
Voor de gebruiker onzichtbaar: acties (missie voorstellen, goedkeuren, afwijzen, betwisten, chatten) blijven werken, maar zijn nu beschermd tegen CSRF.

### 6. Technische beschrijving
Kale `fetch`-calls die eerst `headers: { 'Content-Type': 'application/json' }` gebruikten, gebruiken nu `headers: await getHeaders(true)` (de `true` schakelt de CSRF-header in). GET-calls blijven ongewijzigd (alleen state-changing methodes vereisen CSRF). De guardtest (`copilot-turn-csrf.guard.test.ts`) is herschreven van file-niveau naar per-call-site en method-aware.

### 7. Zichtbaarheids- en toegangsregels
Sessiecookie (`credentials: include`) + CSRF-header voor POST/PUT/DELETE; tenant nooit van de client.

### 8-13. Input / output / validaties / afhankelijkheden
Afhankelijk van `getHeaders(true)` uit `@/lib/api/client`; backend valideert de token.

### 14. Foutafhandeling
Ontbrekende/ongeldige token -> backend 403 -> `ApiError` propageert naar de aanroepende hook/store -> eerlijke error-state (zie FE-MOD-060 / WS5).

### 17. Acceptatiecriteria
- Elke state-changing copilot/mission-POST stuurt `X-CSRF-Token` mee.
- GET-calls sturen geen CSRF-header.
- De per-call-site guardtest is groen en faalt zodra een governed state-changing call de header weglaat.

### 18. Gebruikersuitleg
- Je hoeft niets te doen; je acties zijn nu beter beveiligd.
- Bij een beveiligingsfout zie je een nette foutmelding in plaats van een nep-antwoord.

## [FE-CMP-060] AI-disclosure caption per assistant-bericht

### 1. Type
UI-component (caption / transparantieverklaring).

### 2. Locatie
`frontend/src/components/layout/CopilotSidebar.tsx` (per assistant-bericht) en `frontend/src/components/copilot/CommandPalette.tsx` (responssectie).

### 4. Doel
EU AI Act art. 50: de gebruiker expliciet en per-antwoord informeren dat de inhoud machine-gegenereerd is.

### 6. Technische beschrijving
De turn-response bevat `ai_disclosure`; die wordt op `CopilotMessage` gemapt. In de sidebar rendert een `<p>` met `aria-label="AI-transparantieverklaring"` onder elk assistant-bericht wanneer `msg.role === 'assistant' && msg.ai_disclosure`. In de CommandPalette rendert een `role="note"`-blok wanneer `currentResponse.ai_disclosure` aanwezig is.

### 8. States en gedrag
- Aanwezig: caption zichtbaar onder het antwoord.
- Afwezig (`ai_disclosure` leeg/undefined): geen caption (geen lege ruimte).
- User-bericht: nooit een disclosure.

### 16. Accessibility-notities
Sidebar: `aria-label="AI-transparantieverklaring"`. CommandPalette: `role="note"`.

### 17. Acceptatiecriteria
- Caption zichtbaar wanneer `ai_disclosure` aanwezig is (getest in `CopilotSidebar.test.tsx`).
- Geen caption bij afwezige disclosure of op user-berichten.

### 18. Gebruikersuitleg
- Onder elk AI-antwoord staat een korte verklaring dat het antwoord door AI is gegenereerd.

## [FE-MOD-060] MissionProposalModal zonder verzonnen impact

### 1. Type
Modal (missie-voorstel).

### 2. Locatie
`frontend/src/components/copilot/MissionProposalModal.tsx` -- `deriveProposalFromDecision`, `Step2_PlanApproval`, `Step3_Confirmation`.

### 4. Doel
Nooit verzonnen kosten/risico/compliance tonen op een EU-AI-Act-surface; alleen echte, uit de Council-beslissing afgeleide data.

### 6. Technische beschrijving
`riskLevel` = `decision.verdict === 'modified' ? 'medium' : 'low'`. Compliance-checks = een enkele "Council review"-entry met status `passed` bij `approved`, anders `warning`, en een `message` afgeleid uit `council_summary`. `costUsd`/`riskScore` zijn optioneel; ontbreken zij, dan rendert de UI "Not estimated". `Math.random` is volledig verwijderd. Een guardtest (`MissionProposalModal.no-fabricated-impact.guard.test.ts`) faalt als `Math.random` terugkeert of een van de `verdict` losgekoppelde "passed" wordt getoond.

### 8. States en gedrag
- Verdict `approved`: compliance-status `passed`.
- Verdict `modified`: `riskLevel` medium, compliance-status `warning`.
- Geen kostenbron: "Not estimated" i.p.v. een bedrag.

### 17. Acceptatiecriteria
- Geen `Math.random` in het bronbestand.
- Kosten renderen "Not estimated" wanneer er geen echte waarde is.
- Compliance-entry weerspiegelt de echte `verdict`/`council_summary`.

### 18. Gebruikersuitleg
- Het missie-voorstel toont alleen echte informatie; onbekende kosten staan als "Not estimated".
- De compliance-regel weerspiegelt het echte oordeel van de Council.

---

## Handleidingstekst

### Voor eindgebruikers

Zie `docs/user-guide/frontend/copilot-mission-csrf-compliance-hardening.md`.

---

## Open aannames

- De sessie bevat een geldige CSRF-token voordat een state-changing call wordt gedaan (verzorgd door `getHeaders(true)`/apiClient).

## Open vragen

- Geen.

## Risico's

- Geen nieuwe; de wijziging verwijdert misleidende data en voegt een bestaande, backend-geleverde disclosure toe.

---

## Trainingssamenvatting

### Flow 1: State-changing copilot/mission-actie met CSRF-bescherming

- Actor: ingelogde gebruiker die een missie voorstelt/goedkeurt/afwijst, een audit betwist, of chat.
- Voorwaarde: geldige sessie met CSRF-token.
- Actie: verzendt de actie via een governed POST-endpoint.
- Systeemreactie: frontend voegt `X-CSRF-Token` toe (`getHeaders(true)`); backend valideert CSRF + JWT + tenant en draait governance.
- Succesrespons: de actie wordt uitgevoerd; het antwoord toont echte impact en, bij assistant-antwoorden, de AI-disclosure.
- Foutrespons: ontbrekende/ongeldige token -> 403 -> eerlijke error-state (geen nep-antwoord, geen valse consent-dismiss).
- Uitzonderingen: GET-calls sturen geen CSRF-header; user-berichten tonen geen disclosure.

### Flow 2: AI-disclosure tonen per antwoord

- Actor: ingelogde gebruiker die een AI-antwoord ontvangt.
- Voorwaarde: de turn-response bevat een `ai_disclosure`-veld.
- Actie: geen (systeem rendert automatisch).
- Systeemreactie: onder het assistant-bericht verschijnt een korte, machine-gegenereerde transparantieverklaring.
- Succesrespons: de disclosure-caption is zichtbaar en toegankelijk (aria-label / role=note).
- Foutrespons: geen disclosure-veld -> geen caption (geen lege ruimte).
- Uitzonderingen: user-berichten krijgen nooit een disclosure.

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
- [x] QA-checks zijn uitgevoerd (backend 17 tests + ruff + pyright 0e; frontend guards + surfaces groen)
- [x] Review door reviewer-prompt: APPROVED

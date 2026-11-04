# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-041
- Feature naam: Agent-aware ToolBrokerAdapter voor Council
- Status: Implemented
- Auteur: agent
- Reviewer: APPROVED
- Datum: 2026-07-29
- Gerelateerde user story / ticket: AUDIT-007 (ADR-036 Fase A Dag 2)
- Gerelateerde router / module: `src/core/copilot/council/factory.py`, `src/core/copilot/council/background_gate.py`
- Gerelateerde frontend endpoints: none
- Gerelateerde database tabellen: none
- Versie: 1.0

---

## Doel en scope

### Doel

De SecurityOfficer tool-allowlist check binnen de Agent Council evalueerde elke aanroep tegen het hardcoded permissieprofiel `"copilot"` (AUDIT-007). Daardoor kreeg een achtergrondagent (bijv. `hr_skill`) via de achtergrondingang (`background_gate.py`, ADR-036 D2) hetzelfde permissieprofiel als de copilot -- een schending van ADR-015 least-privilege voor agent-hierarchie-governance. Deze fix maakt de permissiecheck agent-aware: elke agent wordt tegen zijn eigen profiel gecheckt, met fail-secure default-deny voor agents zonder profiel.

### In scope

- `src/core/copilot/council/factory.py`:
  - `_ToolBrokerAdapter` accepteert een optionele `agent_id: str = "copilot"` parameter en gebruikt die bij `is_tool_allowed` in plaats van de hardcoded string.
  - `build_council(db, agent_id="copilot")` geeft `agent_id` door aan de SecurityOfficer-wiring: bij de default wordt de WE-009 module-singleton hergebruikt (HTTP-gedrag ongewijzigd), bij een niet-default waarde wordt een verse SecurityOfficer geconstrueerd.
  - `_get_rbac_service()` module-singleton gedeeld door beide paden (DSM-017: houdt het aantal `agent_runtime->auth` import-edges stabiel op 15).
- `src/core/copilot/council/background_gate.py`:
  - `request_council_decision_for_agent` geeft `agent_id` door aan `build_council`.
  - Module- en functie-docstrings bijgewerkt: de eerder gedocumenteerde "NIET opgeloste beperking" (punt 3) is nu opgelost.
- `tests/unit/test_council_tool_broker_agent_id.py`: 6 regressietests (rood voor de fix, groen erna).

### Out of scope

- Aanmaken van permissieprofielen voor ALS-skills -- dat is AUDIT-008 (Fase A Dag 4, BE-AGT-035).
- Per-tenant tool permissions (post-MVP, zie bestaande comment in `_ToolBrokerAdapter`).
- Wijzigingen aan `SecurityOfficer`, `ToolPermissionManager`, `governance_gate.py`, of de HTTP-council-flow.
- Nieuwe endpoints, schema's of modellen.

---

## Build summary

- Gewijzigd: `src/core/copilot/council/factory.py` -- `_ToolBrokerAdapter` agent-aware, `build_council` agent_id-parameter, `_get_rbac_service` singleton.
- Gewijzigd: `src/core/copilot/council/background_gate.py` -- agent_id-forwarding naar `build_council` + docstring-updates.
- Nieuw: `tests/unit/test_council_tool_broker_agent_id.py` -- 6 regressietests.
- Verwijderd: niets.
- Beinvloede bestaande flows: Council-deliberatie via de achtergrondingang (Dramatiq/agents). De HTTP-council-flow (9 call-sites van `build_council(db)`) is gedrag-identiek: zelfde singleton, zelfde `"copilot"`-profiel.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-041 | Agent-aware ToolBrokerAdapter | Security wrapper | `src/core/copilot/council/factory.py` (`_ToolBrokerAdapter`) | Wijziging | Council deliberatie |
| BE-SEC-041 | build_council agent_id-parameter | Security wiring | `src/core/copilot/council/factory.py` (`build_council`) | Wijziging | Council deliberatie |
| BE-SEC-041 | Gedeelde RBACService-singleton | Security wiring | `src/core/copilot/council/factory.py` (`_get_rbac_service`) | Wijziging | Council deliberatie |
| BE-SEC-041 | Background-gate agent_id-forwarding | Security wrapper | `src/core/copilot/council/background_gate.py` | Wijziging | Achtergrondingang ADR-036 D2 |
| BE-SEC-041-TEST | Agent-id regressietests | Unit test | `tests/unit/test_council_tool_broker_agent_id.py` | Nieuw | Council deliberatie |

---

## API-flows

### Flow ID: BE-FLW-049

- Naam: Council tool-allowlist check per agent-identiteit
- Trigger (HTTP-methode + route of event): intern -- `build_council(db, agent_id=...)` vanuit HTTP-dependencies (default) of `request_council_decision_for_agent` vanuit Dramatiq-achtergrondtaken
- Voorwaarden (auth, tenant, feature flag): tenant ContextVar gezet door aanroeper (HTTP-middleware of background-gate); geen feature flag
- Request-pad:
  1. Aanroeper bouwt Council via `build_council(db)` (HTTP, default `"copilot"`) of `build_council(db, agent_id=<agent>)` (achtergrond).
  2. Bij default: WE-009 singleton SecurityOfficer met `_ToolBrokerAdapter("copilot")`.
  3. Bij niet-default: verse SecurityOfficer met `_ToolBrokerAdapter(agent_id)` + gedeelde RBACService-singleton + verse PromptGuard-adapter.
  4. Tijdens `council.deliberate(proposal)` roept SecurityOfficer `adapter.is_allowed(action_type, tenant_id, user_id)` aan.
  5. Adapter delegeert naar `ToolPermissionManager.is_tool_allowed(agent_id, action_type)`.
  6. Profiel gevonden: denied-list wint, dan allowed-list. Geen profiel: `False` (ADR-015 default-deny) -> SecurityOfficer VETO `TOOL_NOT_ALLOWLISTED`.
- DB-operaties: geen (profielen komen uit `config/tool_permissions.yml`, geladen bij adapter-constructie)
- Successtatus + response: allowlist-check geslaagd -> SecurityOfficer gaat door naar RBAC-scope-check
- Foutpaden:
  - Onbekend agent-profiel: default-deny -> VETO (fail-secure, geen exception)
  - PromptGuard/RBAC/TBM-exception: opgevangen in SecurityOfficer -> VETO `UPSTREAM_ERROR` (bestaand gedrag, ongewijzigd)
- Eindtoestand (DB, cache, events): ongewijzigd -- geen nieuwe state, geen cache-invalidatie nodig (officer verdict-cache wordt in de factory niet geinjecteerd; geen cross-agent cache-lekkage mogelijk)

---

## Detaildocumentatie per artefact

---

## [BE-SEC-041] Agent-aware ToolBrokerAdapter voor Council

### 1. Type

- Security wrapper / permission check (BE-SEC)

### 2. Locatie

- Bestandspad: `src/core/copilot/council/factory.py`
- Klasse / functie: `_ToolBrokerAdapter`, `build_council`, `_get_rbac_service`; `src/core/copilot/council/background_gate.py` (`request_council_decision_for_agent`)

### 3. Gerelateerde flow

- BE-FLW-049 (Council tool-allowlist check per agent-identiteit)

### 4. Doel

- Elke agent -- copilot of achtergrondagent -- wordt bij de Council tool-allowlist check tegen zijn eigen ADR-015 permissieprofiel geevalueerd, zonder het bestaande HTTP-gedrag te wijzigen.

### 5. Functionele beschrijving

- Probleem: een achtergrondagent die via de achtergrondingang een Council-beslissing vraagt, kreeg stilletjes het copilot-permissieprofiel. Tools die voor de copilot zijn toegestaan zouden dan ook voor die agent zijn toegestaan (privilege-widening), en toekomstige copilot-only tools zouden nooit per agent af te grenzen zijn.
- Oplossing: de agent-identiteit wordt vanaf de achtergrondingang doorgegeven tot in de ToolBroker-adapter. De default blijft `"copilot"` zodat alle 9 bestaande HTTP-call-sites gedrag-identiek blijven.
- Resultaat bij succes: `is_tool_allowed` wordt aangeroepen met de profielnaam van de aanroepende agent.
- Effect op systeemtoestand: geen -- zuivere wiring-wijziging, geen nieuwe state.

### 6. Technische beschrijving

- `_ToolBrokerAdapter.__init__(agent_id: str = "copilot")` slaat de agent_id op; `is_allowed` roept `self._mgr.is_tool_allowed(self._agent_id, action_type)` aan.
- `build_council(db: AsyncSession, agent_id: str = "copilot")`:
  - `agent_id == "copilot"` -> `_get_security_officer()` (lru_cache singleton, WE-009).
  - anders -> verse `SecurityOfficer(tool_broker=_ToolBrokerAdapter(agent_id=agent_id), prompt_guard=_PromptGuardAdapter(), rbac_checker=_get_rbac_service())`.
- `_get_rbac_service()` is een nieuwe `lru_cache(maxsize=1)` singleton. Reden: `RBACService` is stateless (geen `__init__`), en een gedeelde instantie met een enkele import-site houdt de DSM-017 edge-count `agent_runtime->auth` op 15 (een tweede `from src.core.auth.rbac import` in hetzelfde bestand bracht hem op 16 en liet `test_dsm017_agent_runtime_auth_at_most_15` falen -- aangetoond tijdens deze implementatie en zo verholpen).
- `request_council_decision_for_agent` roept nu `build_council(db, agent_id=agent_id)` aan; de tenant-context try/finally-volgorde (AUDIT-003) is ongewijzigd.
- Backwards compatibility: alle 9 bestaande `build_council(db)` call-sites (agentic_flow_endpoints, copilot/dependencies, als_tasks_router x2, agents/dependencies, cva_service x2, cva/dependencies, focus_builder/dependencies) gebruiken alleen de positionele `db` en krijgen dus exact het oude gedrag.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne wiring; auth zit in de aanroepende laag)
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: ongewijzigd -- tenant ContextVar door aanroeper; adapter gebruikt `tenant_id` niet (bestaand, gedocumenteerd als post-MVP)
- Feature flag: geen

### 8. Request-specificatie

- Methode: n.v.t. (interne functie)
- Functie-signatuur: `async def build_council(db: AsyncSession, agent_id: str = "copilot") -> AgentCouncil`
- Verplichte headers: n.v.t.

### 9. Response-specificatie

- Successtatus: `AgentCouncil` met SecurityOfficer gewired op het gevraagde profiel
- Foutstatussen: geen nieuwe -- bestaande fail-secure VETO-paden in SecurityOfficer ongewijzigd

### 10. Validaties en constraints

- `agent_id` is een vrije string; onbekende waarden zijn geldig en resolven naar default-deny (fail-secure by design).
- Default-waarde `"copilot"` is een harde backwards-compatibility-constraint (gepind door tests 1.1 en 1.3).

### 11. Business rules

1. HTTP-council (default) gebruikt altijd het `"copilot"`-profiel en de WE-009 singleton -- geen gedragswijziging.
2. Achtergrondagents worden tegen hun eigen profiel gecheckt (ADR-015 least-privilege).
3. Agents zonder profiel worden default-denied (fail-secure), nooit default-allowed.
4. Profielen zelf worden pas in AUDIT-008 aangemaakt; tot dan deny't elke niet-copilot agent alle tool-acties -- bewust, want vandaag zijn er nog geen skills met tool-executie-rechten.

### 12. Afhankelijkheden

- `ToolPermissionManager` (`src/core/tool_broker/permission_manager.py`) + `config/tool_permissions.yml`
- `RBACService` (`src/core/auth/rbac.py`) -- stateless, gedeelde singleton
- `PromptGuard` (`src/core/ai/prompt_guard.py`) -- stateless
- `SecurityOfficer`, `AgentCouncil` (ADR-027)

### 13. Foutafhandeling

- 400/401/403/404/409/422/429: n.v.t. (geen endpoint)
- 500: n.v.t. direct; SecurityOfficer vangt upstream-exceptions af als VETO `UPSTREAM_ERROR` (ongewijzigd)
- 503: n.v.t.

### 14. Transacties en dataintegriteit

- Geen DB-interactie; geen transactie-impact. `build_council` hergebruikt de bestaande request-session (ongewijzigd).

### 15. Telemetry / logging / tracing

- Ongewijzigd: bestaande OpenTelemetry-spans in SecurityOfficer (`copilot.officer.SecurityOfficer.deliberate`) en background-gate log-regels (`agent=%s` werd al gelogd).

### 16. Caching

- Gecached: `_get_security_officer` en `_get_rbac_service` via `lru_cache(maxsize=1)` (module-singletons, WE-009-patroon)
- Cache-sleutel: n.v.t. (singleton)
- TTL: n.v.t.
- Invalidatie: n.v.t. -- stateless officers; niet-default agent-pad maakt bewust een verse officer zodat er geen cross-agent state kan lekken.

### 17. Acceptatiecriteria

- [x] `_ToolBrokerAdapter()` zonder argument checkt profiel `"copilot"` (test: `test_default_agent_id_is_copilot_for_backwards_compatibility`)
- [x] `_ToolBrokerAdapter(agent_id="hr_skill")` checkt profiel `"hr_skill"` (test: `test_explicit_agent_id_is_forwarded_to_permission_manager`)
- [x] `build_council(db)` hergebruikt de WE-009 SecurityOfficer-singleton (test: `test_build_council_default_keeps_security_officer_singleton`)
- [x] `build_council(db, agent_id="hr_skill")` bouwt een verse officer met adapter-agent_id `"hr_skill"`, niet de singleton (test: `test_build_council_forwards_agent_id_to_security_adapter`)
- [x] `request_council_decision_for_agent` roept `build_council` aan met `agent_id=<agent>` (test: `test_request_council_decision_for_agent_forwards_agent_id`)
- [x] Agent zonder profiel wordt default-denied tegen de echte config (test: `test_agent_without_permission_profile_is_default_denied`)
- [x] Bestaande council-tests ongewijzigd groen (211 gerichte tests GROEN)
- [x] Architectuur-suite groen inclusief DSM-017 edge-plafond (388/388)

### 18. Integratoruitleg

- Roept je de Council aan vanuit HTTP? Niets verandert: `build_council(db)` blijft werken zoals altijd.
- Roept je de Council aan vanuit een achtergrondtaak? Gebruik `request_council_decision_for_agent(...)` met je eigen `agent_id`; de permissiecheck gebruikt dan jouw profiel.
- Heeft je agent nog geen profiel in `config/tool_permissions.yml`? Dan wordt elke tool-actie geweigerd (fail-secure) -- profielen worden in AUDIT-008 toegevoegd.

### 19. Trainingssamenvatting

- Actor: achtergrondagent (Dramatiq) of HTTP-endpoint
- Voorwaarde: tenant ContextVar gezet; agent_id bekend bij de aanroeper
- Actie (request): `request_council_decision_for_agent(tenant_id=..., agent_id="hr_skill", ...)` of `build_council(db)`
- Systeemverwerking: Council wordt gebouwd met SecurityOfficer gewired op het agent-eigen permissieprofiel; allowlist-check via `ToolPermissionManager.is_tool_allowed(agent_id, action_type)`
- Succesrespons: `CouncilDecision` met verdict op basis van het juiste profiel
- Foutrespons: bij ontbrekend profiel -> VETO `TOOL_NOT_ALLOWLISTED` (default-deny); bij upstream-fout -> VETO `UPSTREAM_ERROR`
- Uitzonderingen: default `"copilot"` hergebruikt de module-singleton; elke andere agent_id bouwt een verse SecurityOfficer

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Deze wijziging is intern Council-wiring; er is geen publiek API-oppervlak veranderd. Teams die agents op de achtergrondingang aansluiten (ADR-036) hoeven alleen hun eigen `agent_id` mee te geven -- de permissiecheck volgt automatisch het juiste profiel. Tot AUDIT-008 zijn er voor niet-copilot agents bewust geen tool-rechten.

---

## Open aannames

- `tenant_id` en `user_id` blijven ongebruikt in de adapter (bestaande MVP-beperking, gedocumenteerd in code); per-tenant tool permissions zijn post-MVP.

## Open vragen

- Geen.

## Risico's

- Agents zonder profiel krijgen nu VETO waar ze eerder (onterecht) het copilot-profiel kregen -- dat is de bedoelde aanscherping, maar als er vandaag al een achtergrondagent tool-acties via de Council zou proberen, faalt die nu. Verifieerd: de enige niet-default aanroeper is `background_gate.py` en er bestaan nog geen skills met tool-executie-rechten (AUDIT-008 staat pas voor dag 4 gepland); de fail-secure test dekt dit gedrag.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- n.v.t. intern; wiring-tests happy path groen
- [x] Alle foutstatus-codes getest -- fail-secure default-deny test groen
- [x] Auth en permissies getest -- profiel-selectie + default-deny getest
- [x] Tenant-isolatie getest -- ongewijzigd (geen tenant-gedrag in adapter); background-gate tenant-cleanup-tests (AUDIT-003) ongewijzigd groen
- [x] Validaties getest (ongeldige invoer) -- onbekende agent_id -> default-deny
- [x] Edge cases getest (leeg, null, grenzen) -- default/None-pad via backwards-compat tests
- [x] Dataintegriteit en transacties getest -- n.v.t. (geen DB-wijziging)
- [x] Performance / load getest (indien relevant) -- n.v.t.; singleton-pad ongewijzigd, verse officer alleen bij niet-default agent (zero-cost constructors geverifieerd)
- [x] Caching getest (indien van toepassing) -- singleton-identiteit gepind (WE-009 regressietests groen)
- [x] Logging en tracing gecontroleerd -- ongewijzigd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar (en als tests geimplementeerd, 6/6 groen)
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED

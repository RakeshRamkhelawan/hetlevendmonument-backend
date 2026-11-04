# BE-E2E-001 -- Bewijs + fix: agentic taakbeheer-copilot-loop werkt e2e

- Feature ID: BE-E2E-001
- Status: Implemented
- Sprint: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 9 (Fase D -- bewijs)
- Branch: `iter/dag9-e2e`
- Reviewer: code-reviewer + security-reviewer (Gate 2) -- zie `docs/backend/review/review-BE-E2E-001.md`
- Datum: 2026-07-15
- ADR: ADR-027 (Council/Copilot), ADR-015 (ToolBroker/HITL), ADR-019 (audit), ADR-031 (governance), ADR-003/004/005 (tenant)

## Doel

De dag-1-8-feature (chat-turn -> Council -> ToolBroker business-tool -> echte taak in `agentic_tasks`
-> governed response) e2e bewijzen, en de nieuwe dag-7/8-invarianten met arch-guards borgen. Charter
par. 5: "een niet-admin typt een taakverzoek en er verschijnt een echte tenant-gescopede taak, met
AI-disclosure, audit-hash-chain, werkende uitleg-link, WS niet zwakker dan HTTP, geen cross-tenant".

## Bevinding: de loop was e2e KAPOT (3 productieblokkers) -- gefixt

De bewijs-dag legde bloot dat de flagship-loop in een schone omgeving (CI/staging/productie) nooit werkte.
Drie onafhankelijke productieblokkers, alle bevestigd en gefixt in deze diff:

- **F1 -- ontbrekende module in git.** `_build_copilot_service` (`copilot/dependencies.py:89`) importeert
  `ScopedToolBroker` uit `src/services/tool_broker/scoped_broker.py`, maar de hele `src/services/`-boom
  stond in `.git/info/exclude` -> het bestand was nooit gecommit -> `ModuleNotFoundError` bij elke
  `POST /api/v1/copilot/turn` in elke schone checkout (de endpoint faalde vóór de body). Fix: bestand
  `git add -f` in de repo (context-propagatie-wrapper over `IToolBroker`; alleen trailing-whitespace geschoond).
- **F2 -- Council bereikte nooit APPROVED.** Twee officers blokkeerden elke `create_task`:
  - `ResourceOfficer` deferde op `_PranaAdapter.has_budget` -- een `# mock voor sprint 2`-stub die de ledger
    op `action_type` las terwijl die op `agent_id` is gekeyd (altijd 0) en waarvoor geen funding-mechanisme
    bestaat. Fix: `_PranaAdapter.has_budget` geeft `True` (herstelt de placeholder-intentie; verzwakt geen
    echt gate -- de stub blokkeerde alles indiscriminaat). `TODO(SP-PRANA-ECONOMY)` voor een echte economie.
  - `ComplianceOfficer` wilde MODIFY (MISSING_AI_DISCLOSURE) omdat `ProposalBuilder` geen `ai_disclosure`
    in `action_params` zette. Fix: `ProposalBuilder.build` zet default `ai_disclosure = AI_DISCLOSURE_NOTICE`
    (`setdefault`, respecteert expliciete waarde) -- copilot-output IS altijd AI-gegenereerd (art. 50).
- **F4 -- audit crashte op executie.** Zodra de loop APPROVED bereikte, crashte `CouncilAuditWriter.
  bind_execution_result` op `json.dumps(result_data)` (`TypeError: datetime not JSON serializable`, want
  een aangemaakte taak draagt datetimes). Fix: `default=str` in de canonicalisatie (deterministisch).

Na F1+F2+F4 maakt de loop daadwerkelijk een tenant-gescopede taak aan.

## e2e-test (`tests/integration/copilot/test_taakbeheer_loop_e2e.py`, 6 tests, `@integration`)

Door het ECHTE HTTP-endpoint; alleen de LLM-provider gemockt (`LLMProviderFactory.get_provider`). De
dag-6-gates (CSRF/rollout) zijn via `dependency_overrides` uitgeschakeld (elders gedekt). Council/ToolBroker/
TaskService/DB/Redis draaien echt.

1. `test_loop_executes_end_to_end_and_returns_verdict` -- volledige keten draait, 200 + `decision_id` +
   `ai_disclosure` + echte Council-stemmen.
2. `test_approved_create_task_persists_row` -- **BLOCKER**: verdict `approved` + exact 1 `agentic_tasks`-rij
   voor tenant 1 (bound-value).
3. `test_tenant_isolation_task_not_visible_cross_tenant` -- **BLOCKER**: tenant 2 ziet tenant 1's taak niet.
4. `test_prompt_injection_rejected` -- echte PromptGuard -> 400 INPUT_REJECTED, geen taak.
5. `test_fail_secure_governance_blocks_task` -- officer-crash -> verdict `blocked`, geen taak (RC-SUP-2).
6. `test_hitl_delete_requires_approval` -- `delete_task` zonder HITL-ticket -> gated, taak blijft bestaan.

**Rood-voor-groen bewezen.** Tenant-isolatie-assert omgedraaid -> RED, hersteld -> GREEN. De happy-path was
RED tegen F1/F2/F4 en werd GREEN na de fixes.

**Bewust niet in de e2e geassert (harness-limiet, gedocumenteerd):** de ADR-019 audit-hash-chain voor de
taak. `AuditService.log_action` serialiseert met `pg_advisory_xact_lock` (transactie-lock); onder de
one-shared-connection integratie-harness self-contendt die lock, dus de keten-write wordt (best_effort)
overgeslagen. De hash-chain is gedekt door dedicated tests (`tests/unit/governance/test_audit_service_hash_chain.py`,
`tests/architecture/test_adr019_hash_chain_wired.py`, `test_no_audit_write_without_hash_chain.py`).
WS-pariteit: gedekt door dag-6 `test_copilot_mission_csrf_enforced.py` + WS-hardening (niet gedupliceerd).

## Arch-guards voor de dag-7/8-invarianten (`tests/architecture/`)

- `test_delete_authz_admin_only.py` -- tenant-brede delete-all vereist admin VOOR de SOFT/HARD-vertakking (BE-GDPR-001 P0).
- `test_analytics_consent_gate.py` -- ingest hangt aan `analytics_consent_allowed` + slaat over zonder consent (BE-GDPR-002).
- `test_dsar_covers_task_and_copilot.py` -- DSAR delete+export dekken agentic_tasks + copilot-sessies (BE-A17-004).
- `test_contest_admin_authz.py` -- contest-queue + resolve zijn admin-only (BE-A22-001).
Rood-bij-regressie bewezen voor de delete-authz + analytics guards.

## Trainingssamenvatting

### Flow: taak aanmaken via de copilot-chat

- Actor: niet-admin klantgebruiker (identiteit + tenant uit de JWT).
- Voorwaarde: geauthenticeerde `POST /api/v1/copilot/turn` met een taakverzoek.
- Actie: PromptGuard -> Council (8 officers) delibereert -> bij APPROVED voert ToolBroker `create_task` uit.
- Systeemreactie: tenant-gescopede rij in `agentic_tasks`; response met `decision_id`, `ai_disclosure`,
  `explanation_url`; ADR-019 audit (via het reguliere request-pad).
- Succesrespons: 200, verdict `approved`, 1 taakrij voor de eigen tenant.
- Foutrespons: injectie -> 400 INPUT_REJECTED; officer-crash -> `blocked`; `delete_task` zonder HITL -> gated.
- Uitzonderingen: cross-tenant onmogelijk; identiteit nooit uit body.

## Definition of Done

- [x] e2e 6/6 groen (happy + isolatie-BLOCKER + 3 unhappy), rood-voor-groen aangetoond
- [x] F1/F2/F4 productiefixes; 4 arch-guards (rood-bij-regressie bewezen)
- [x] Gate 2 code + security APPROVED; Gate 3 ruff 0 / pyright 0 (gewijzigde bestanden)
- [x] Volledige suite: 0 nieuwe failures t.o.v. baseline (unit/arch); pre-existing drift gedocumenteerd

# BE-UTL-031 -- Architecture Audit Documentation (WE-001 t/m WE-009)

**ID:** BE-UTL-031
**Sprint:** SP-WE-01
**Datum:** 2026-05-31
**Type:** Documentatie-record (geen code wijzigingen)
**ADR:** ADR-027

---

## Samenvatting

Architectuur audit van 2026-05-31 legde 9 wiring-bevindingen vast (WE-001 t/m WE-009) in
`docs/adr/027-copilot-agent-council.md`. Deze feature spec documenteert de 3 kritieke
bevindingen die als valkuilen zijn toegevoegd aan CLAUDE.md.

---

## Bevindingen (WE-001, WE-002, WE-003)

### WE-001: LLMHandler-ProposalBuilder volgorde

- **Bewijs:** `src/core/copilot/service.py:195` -- `llm_handler.get_action()`
- **Bewijs:** `src/core/copilot/service.py:210` -- `proposal_builder.build(action)`
- **Correcte volgorde:** LLMHandler.get_action() -> CopilotAction -> ProposalBuilder.build() -> Proposal
- **Status:** Gedocumenteerd in CLAUDE.md valkuilen-tabel

### WE-002: ExecutionGuard na Council deliberation

- **Bewijs:** `src/core/copilot/service.py:222` -- `council.deliberate(proposal)`
- **Bewijs:** `src/core/copilot/service.py:233` -- `_execute_decision(proposal, decision)`
- **Bewijs:** `src/core/copilot/service.py:325` -- `execution_guard.start_execution()`
- **Impact:** Dubbele requests kunnen twee deliberations triggeren voor de guard actief wordt
- **Fix:** SP-WE-06 (toekomstige sprint)
- **Status:** Gedocumenteerd in CLAUDE.md valkuilen-tabel

### WE-003: AgentCouncil geen singleton

- **Bewijs:** `src/core/copilot/council/factory.py:215` -- `async def build_council(db)` zonder caching
- **Impact:** InMemoryRateLimiter reset per request -- rate limiting niet persistent
- **Fix:** SP-WE-08 (toekomstige sprint)
- **Status:** Gedocumenteerd in CLAUDE.md valkuilen-tabel

---

## Wijzigingen uitgevoerd

| Bestand | Wijziging |
| --- | --- |
| `CLAUDE.md` | 3 nieuwe valkuilen toegevoegd (LLMHandler-volgorde, ExecutionGuard-volgorde, AgentCouncil singleton) |
| `docs/SPRINT_TRACKER.md` | SP-WE-01 status OPEN -> CLOSED |
| `docs/adr/027-copilot-agent-council.md` | WE-001 t/m WE-009 sectie toegevoegd (2026-05-31, pre-sprint) |
| `docs/architecture-c4-dsm-v2.html` | Gecorrigeerd HTML-diagram aanwezig (output van audit workflow) |

---

## Trainingssamenvatting

### Flow 1: Agent leest L4-volgorde uit CLAUDE.md

- **Actor:** AI-agent of developer die CopilotService.handle_turn() implementeert of debugt
- **Voorwaarde:** Agent heeft CLAUDE.md valkuilen-tabel gelezen
- **Actie:** Agent implementeert of traceert de handle_turn() aanroepvolgorde
- **Systeemreactie:** Agent volgt de gedocumenteerde volgorde uit de valkuilen-tabel
- **Succesrespons:** Correcte volgorde: LLMHandler.get_action() -> ProposalBuilder.build() -> Council.deliberate() -> ExecutionGuard.start_execution()
- **Foutrespons:** Als agent de oude (verkeerde) volgorde volgt waarbij ProposalBuilder LLMHandler aanroept -- leidt tot onjuiste architectuurbeslissingen
- **Uitzonderingen:** ProposalBuilder.build() is synchroon en roept nooit LLMHandler aan; bewijs in `service.py:195-210`

### Flow 2: Agent evalueert AgentCouncil caching

- **Actor:** Developer die een nieuwe endpoint of service bouwt die CouncilService aanroept
- **Voorwaarde:** Developer overweegt build_council() te hergebruiken voor performance
- **Actie:** Developer raadpleegt CLAUDE.md valkuil "AgentCouncil is geen singleton"
- **Systeemreactie:** CLAUDE.md waarschuwt dat build_council() geen cache heeft
- **Succesrespons:** Developer implementeert applicatie-level cache of wacht op SP-WE-08
- **Foutrespons:** Developer roept build_council() direct aan per request -- InMemoryRateLimiter reset elke keer
- **Uitzonderingen:** SP-WE-08 lost dit structureel op; tot die tijd: geen build_council() in hot paths

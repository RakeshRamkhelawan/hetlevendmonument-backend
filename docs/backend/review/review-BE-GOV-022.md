# Review: BE-GOV-022 — SP-GOV-ENTRYPOINT-AUDIT (OP-11 dag 2)

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-GOV-022-entrypoint-action-classification.md` |
| Reviewer | Fresh-eyes zelfreview (subagents niet toegestaan in deze sessie; expliciet gemeld aan Rakesh) |
| Datum | 2026-07-31 |
| Uitkomst | **APPROVED WITH NOTED RISK** |

---

## Controle tegen de code (geen aannames)

| Claim in spec | Verificatie | Oordeel |
| --- | --- | --- |
| 403 komt van de policy-engine, niet van CSRF of auth | Response body uitgelezen via een tijdelijke diagnostiek-test: `GOVERNANCE_BLOCK: Policy violations: Action 'route_task' is denied by default` | Correct, empirisch |
| CSRF uitgesloten | Slechts 2 "Missing CSRF token"-logregels in de hele run, beide van de copilot-audit-test (cluster G) | Correct |
| AI Act-blok uitgesloten | `classify_agent` geeft MINIMAL voor AgentRouterAgent, MasterOrchestratorAgent en CriticAgent | Correct |
| Ontbrekende tenant uitgesloten | `safe_get_tenant_id` gooit 401, geen 403 | Correct |
| Zeven ongeklassificeerde namen, niet zes | Live scan over `src/`: route_and_execute stond niet in de docstring van de tracking-test | Correct -- spec vermeldt dit expliciet |
| Vangrail dekt de afweging niet | `DESTRUCTIVE_SUBSTRINGS` = delete/remove/drop/deploy/migrate/write/payment; geen enkele kandidaat matcht | Correct |
| `orchestrate_task` stond al in de lijst | Bevestigd; die test werd na de cluster A-fix groen zonder allowlist-wijziging | Correct |
| Diepere poorten niet aangeraakt | `git diff` raakt alleen policy_engine.py (lijst + comment) en websocket.py (naam); `BREAKTHROUGH_ACTIONS` en `ai_act_classifier` ongewijzigd | Correct |

## Bevindingen

Geen CRITICAL. Geen HIGH.

**NOTED RISK (bewust geaccepteerd besluit Rakesh, niet een openstaand defect):**
`autonomous_breakthrough` mag nu een pad starten zonder mens in de lus, terwijl de
autonomie-ladder uit ADR-031 nog niet gewired is. Ik heb dit voorafgaand aan de wijziging
gemeld en het advies gegeven om die ene naam geweigerd te houden; Rakesh heeft anders
besloten. Vastgelegd op drie plaatsen zodat het geen stille keuze is: comment bij de
constante, de spec (par. Restrisico) en
`test_autonomous_breakthrough_deeper_gates_remain_intact`.

Aanbeveling voor de ADR-036-roadmap: neem het wiren van de autonomie-ladder (Fase 5, D4/D8)
op als voorwaarde voordat `cva_autonomous_trigger.py` in productie autonoom mag draaien.

MINOR (opgelost tijdens de review):
- R1 -- De tracking-test stond nog op `xfail(strict=True)` nadat het gat gesloten was.
  Zonder ingrijpen zou een opgelost item als "open" gemarkeerd blijven staan en de suite
  bij de volgende XPASS alsnog rood worden. Marker verwijderd, docstring bijgewerkt.

## Kwaliteitspoorten

- ruff: clean op alle gewijzigde bestanden.
- pyright: 0 errors (baseline gehaald).
- ASCII: geen non-ASCII in code of tests.
- Tenant-isolatie: niet geraakt -- er is geen query- of tenant_id-pad gewijzigd.
- Security: de wijziging verbreedt bewust het startoppervlak van agent-paden. Geen
  destructieve eindoperatie is toegevoegd; de drie diepere poorten blijven intact. Het
  `stream`-geval is opgelost zonder de allowlist te verbreden.
- Regressie: 1039 tests in de governance- + architecture-set groen; orchestration-integratie
  van 20 failed naar 0 failed (26 passed).

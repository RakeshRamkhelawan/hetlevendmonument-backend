# BE-GOV-022: SP-GOV-ENTRYPOINT-AUDIT -- classificatie van alle task_action-strings

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-GOV-022 |
| Flow-ID | BE-FLW-055 |
| Sprint | OP-11 (integratie-baseline herstel) Dag 2 |
| Datum | 2026-07-31 |
| ADR-koppeling | ADR-017 (deterministische policy-enforcement), ADR-031 (governance-contract + autonomie-ladder) |
| Status | Geimplementeerd |
| Commits | `e106ec1d` (rode tests), `816c620f` (fix) |
| Besluit | Rakesh, 2026-07-31 (in chat) |

## Probleem

`PolicyEngine.validate_action` weigert in stap 8 elke actie die in geen enkele allowlist
staat (deny-by-default). Dat vangnet is correct, maar zeven `task_action="..."`-literals
in `src/` stonden nergens geclassificeerd. Die dispatch-paden gaven daardoor stil 403.

Concreet gemeten (response body, niet aangenomen):

```text
GOVERNANCE_BLOCK: Policy violations: Action 'route_task' is denied by default.
Not in allowed actions list.
```

Gevolg: `POST /api/v1/orchestrate/route` en `POST /api/v1/orchestrate/critique` waren
voor iedere aanroeper onbruikbaar. Zichtbaar in 7 rode integratietests die niemand
draaide. De namen stonden sinds 2026-07 als openstaand gat in
`tests/unit/test_governance_entrypoint_gaps_tracked.py` met
`TODO(SP-GOV-ENTRYPOINT-AUDIT)`: expliciet besluit vereist per naam.

De live scan vond **zeven** namen; de docstring van die tracking-test noemde zes --
`route_and_execute` was gemist.

## Waarom de bestaande vangrail niet volstond

`tests/unit/test_policy_engine_architecture.py::test_agent_entrypoint_actions_no_destructive_verbs`
blokkeert alleen namen die de substrings `delete/remove/drop/deploy/migrate/write/payment`
bevatten. Alle zeven kandidaten komen daar mechanisch door. De vangrail vervangt dus geen
menselijke afweging -- dat is expliciet vastgelegd in het commentaar bij de constante.

## Besluit en motivatie per naam

Zes namen toegevoegd aan `PolicyEngine.AGENT_ENTRYPOINT_ACTIONS`:

| Actie | Call-site | Motivatie |
| --- | --- | --- |
| `route_task` | `orchestration/workflow_router.py` | read-only: kiest een agent, voert niets uit |
| `critique_output` | `orchestration/critic_router.py` | read-only: beoordeelt output, geeft score/issues |
| `route_and_execute` | `agents/agent_router_agent.py` | dispatch; zelfde vorm als het al toegestane `create_and_execute`. De doelagent doet zijn eigen governance-check via `process_task` |
| `execute_specialist` | `agents/subagents_manager.py` | dispatch naar subagent; zelfde vorm als het al toegestane `delegate_sub_task` |
| `start_swarm` | `api/swarm_websocket_endpoints.py` | dispatch met fan-out naar meerdere agents |
| `autonomous_breakthrough` | `agents/cva_autonomous_trigger.py` | dispatch **zonder menselijke trigger** -- zie restrisico |

De zevende, `stream`, is **niet** toegevoegd: het was een naam-mismatch met het al
bestaande `stream_execution`. De call-site in `src/core/api/v1/agentic/websocket.py`
gebruikt nu die goedgekeurde naam, zodat de allowlist niet verder verbreed hoefde te
worden.

## Restrisico (expliciet, bewust geaccepteerd)

`autonomous_breakthrough` is de enige actie die een pad start **zonder mens in de lus**,
terwijl de autonomie-ladder uit ADR-031 nog niet gewired is. Dit risico is voorafgaand
aan de wijziging gemeld; Rakesh heeft de naam bewust meegenomen.

Wat het risico begrenst -- geen van deze poorten is aangeraakt:

1. **AI Act-risicoclassificatie** (`ai_act_classifier.classify_agent`) op
   department/specialisation/capabilities.
2. **`OversightGate.BREAKTHROUGH_ACTIONS`** -- `code_generation`, `file_creation`,
   `database_migration`, `deployment`, `config_change`, `permission_change` vereisen
   human approval, ongeacht wie het pad startte.
3. **ShadowCEO-veto** (pre-executie).

`AGENT_ENTRYPOINT_ACTIONS` geeft uitsluitend toegang tot het **starten** van een pad,
nooit tot een destructieve eindoperatie.

Vastgelegd in code (comment bij de constante) en in
`test_autonomous_breakthrough_deeper_gates_remain_intact`, die faalt zodra iemand een van
die zes eindoperaties uit `BREAKTHROUGH_ACTIONS` haalt.

## Preventie

`tests/unit/test_policy_engine_entrypoint_classification.py`:

1. `test_no_unclassified_task_action_literals_in_src` -- scant `src/` op
   `task_action="..."`-literals en faalt op elke naam die in geen enkele allowlist staat.
   Leest de **echte** constanten, dus nieuwe call-sites worden direct gevangen.
2. `test_classified_action_passes_policy_engine` (7x geparametriseerd) -- elke
   geclassificeerde actie moet de PolicyEngine daadwerkelijk passeren.
3. `test_stream_call_site_uses_the_classified_name` -- voorkomt terugval naar de mismatch.
4. `test_autonomous_breakthrough_deeper_gates_remain_intact` -- bewaakt het restrisico.

Twee bestaande guards zijn meegegroeid: `EXPECTED_AGENT_ENTRYPOINT_ACTIONS` (7 -> 13,
die test dwingt af dat de lijst alleen met een expliciete PR-wijziging groeit) en de
tracking-test, waarvan de `xfail(strict=True)` is verwijderd omdat het gat nu gesloten is.

## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker, agent of achtergrondproces dat een agent-pad start
- Voorwaarde: De aanroeper geeft een `task_action` mee die in een allowlist staat
  (`AGENT_ENTRYPOINT_ACTIONS`, `DEFAULT_ALLOW_ACTIONS` of `BREAKTHROUGH_ACTIONS`).
- Actie: De governance-gate wordt aangeroepen voordat het pad start, bijvoorbeeld via
  `POST /api/v1/orchestrate/route` of `AgentRouterAgent.route_and_execute()`.
- Systeemreactie: `PolicyEngine.validate_action` doorloopt 8 stappen: tenant-regels,
  geblokkeerde domeinen/IP's, systeembestanden, approval-acties, entrypoint-allowlist,
  default-allow, en tot slot deny-by-default.
- Succesrespons: De actie passeert en het pad start; de diepere poorten (AI Act,
  human approval, ShadowCEO) blijven daarna onverminderd gelden.
- Foutrespons: HTTP 403 met `GOVERNANCE_BLOCK: <reden>` als de actie niet geclassificeerd
  is of een policy-regel schendt.
- Uitzonderingen: Een nieuwe `task_action`-literal in `src/` faalt de preventietest totdat
  iemand hem expliciet classificeert -- dat is bewust, want de stille variant hiervan
  kostte deze sprint 7 rode tests en twee onbruikbare productie-endpoints.

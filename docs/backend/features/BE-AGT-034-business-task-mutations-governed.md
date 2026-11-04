# BE-AGT-034 -- Muterende Business Task Tools, governed (Dag 4)

> Sprint: **AGENTIC-COPILOT-TAAKBEHEER-2026-07** (Dag 4)
> Datum: 2026-07-08
> Samenhangende IDs: `BE-AGT-034`, `BE-SEC-035`, `BE-SEC-036`, `BE-SCH-031`, `BE-TSK-013`, `BE-SEC-037`
> Scope: `update_task` (medium) + `delete_task` (HIGH -> HITL-gated) als business tools; ADR-019 audit-hash-chain per actie; fail-secure governance-default (RC-SUP-2); machine-leesbare AI-disclosure (EU AI Act art. 50 / ADR-036 D9). Geen endpoints/frontend (fase B), geen WS-hardening, geen LLM-provenance (naar dag 5).

---

## A. Build Summary

Dag 4 maakt de ToolBroker-uitvoerlaag geschikt voor **muterende en destructieve** taak-acties, met de governance eromheen als kern:

- `update_task` + `delete_task` toegevoegd aan `BusinessToolRegistry`; `delete_task` is HIGH-risk en loopt door de **bestaande** ToolBroker HITL-gate (geen nieuwe gate gebouwd).
- Per geslaagde create/update/delete een ADR-019 audit-hash-chain-entry via `AuditService.log_action`, in `best_effort` (blokkeert de primaire actie nooit). Alleen niet-gevoelige metadata (`task_id` + gewijzigde veldnamen), geen veldwaarden (PII-minimalisatie).
- Governance-default omgezet van fail-OPEN naar **fail-SECURE** (`CVA_GOVERNANCE_FAIL_SECURE` default `true`).
- Machine-leesbare AI-disclosure toegevoegd aan elk copilot-turn-antwoord.

Geen wijziging nodig aan `service.py` (dispatcht al elke `known_tool_names()`-tool en de HITL-gate vuurt al vóór dispatch) en geen wijziging aan `config/tool_permissions.yml` (copilot-profiel had `update_task`/`delete_task` al).

---

## B. Backend Inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging |
| --- | --- | --- | --- | --- |
| BE-AGT-034 | update_task/delete_task handlers + audit-wiring | Tool registry | `src/core/tool_broker/business_registry.py` | Wijziging |
| BE-SEC-035 | Risk levels update_task=medium, delete_task=high (HITL) | Config | `src/core/config/tool_risk_levels.yml` | Wijziging |
| BE-SEC-036 | CVA governance fail-secure default (RC-SUP-2) | Config/guard | `src/core/services/cva_service.py` | Wijziging |
| BE-SCH-031 | CopilotTurnResponse.ai_disclosure (art. 50 / D9) | Pydantic schema | `src/core/copilot/schemas.py` | Wijziging |
| BE-TSK-013 | Unit tests mutations + audit + fail-secure + disclosure | Test | `tests/unit/tool_broker/test_business_task_mutations.py`, `.../test_business_task_audit.py`, `tests/unit/governance/test_fail_secure_default.py`, `tests/unit/copilot/test_ai_disclosure.py` | Nieuw |
| BE-SEC-037 | Integratietest muterende tools + audit-chain (echte DB) | Test | `tests/integration/tool_broker/test_business_task_mutations.py` | Nieuw |

---

## C. Functionele specificatie

### C.1 update_task (BE-AGT-034, medium)

Werkt een bestaande taak van de aanroepende tenant bij via `TaskService.update(task_id, TaskUpdate)`. `task_id` komt uit de payload en wordt gevalideerd als UUID; ongeldige/ontbrekende `task_id` -> gestructureerde `ToolExecutionException` (geen bare 500). Bestaat de taak niet of hoort ze bij een andere tenant, dan retourneert de service `None` en geeft de tool een generieke fout `"Task not found"` -- zonder te onthullen of de taak bestaat bij een andere tenant. Payload wordt ontdaan van `tenant_id/user_id/decision_id/id` (`_clean_task_data`) plus de control-velden `task_id`/`_hitl_ticket_ref` vóór `TaskUpdate`-validatie.

### C.2 delete_task (BE-AGT-034, HIGH -> HITL-gated)

Verwijdert een taak via `TaskService.delete(task_id)`. `delete_task` is als HIGH geclassificeerd, waardoor de bestaande ToolBroker HITL-gate (`service.py` ~186-235) een goedgekeurd ticket eist: zonder `_hitl_ticket_ref` met status `approved` faalt de aanroep met een `ToolExecutionException` ("requires human approval (HIGH risk)"). Er wordt géén parallelle gate gebouwd. Resultaat-contract: `{"success": true, "data": {"deleted": <bool>}}`.

### C.3 Audit-hash-chain (BE-AGT-034 / ADR-019)

Na elke geslaagde create/update/delete schrijft de registry een `AuditService.log_action`-entry (tabel `audit_logs`) binnen `async with best_effort(...)`, gevolgd door `session.commit()`. De SHA-256-keten (`previous_hash`/`audit_hash`) wordt door `AuditService` zelf gezet (advisory lock per tenant). `details` bevat uitsluitend `{"task_id": ..., "fields_changed": [<veldnamen>]}` -- geen veldwaarden (PII-minimalisatie). Dit is een aparte keten van de dode `tool_audit_logs` (`ToolAuditRepository` wordt nergens geinjecteerd), dus geen dubbeltelling.

### C.4 Fail-secure default (BE-SEC-036 / RC-SUP-2)

`_CVA_FAIL_SECURE` default omgezet van `false` naar `true`. Bij een Council-infrastructuurfout blokkeert `CVAService.chat`/`chat_stream` nu standaard (HTTP 503) i.p.v. door te lopen zonder goedkeuring. `GovernanceVetoError` blijft altijd propageren. Het `/copilot/turn`-pad (`CopilotService.handle_turn`) was al fail-secure (blokkeert bij elke Council-fout) en leest deze vlag niet -- alleen bewezen met een regressietest.

### C.5 AI-disclosure (BE-SCH-031 / art. 50 / D9)

`CopilotTurnResponse` krijgt een veld `ai_disclosure: str` met een stabiele, machine-leesbare ASCII-default (`AI_DISCLOSURE_NOTICE`). Omdat het een default is, dragen alle constructie-plekken (approved/modified/deferred/hitl_required/blocked) de disclosure automatisch; `extra="forbid"` blijft van kracht.

---

## D. Dataflow (delete_task, HITL-gated)

```text
CopilotService._execute_decision (agent_id="copilot")
    |
    v
ToolBrokerService.execute_tool(tool_name="delete_task", payload={task_id, _hitl_ticket_ref}, context={tenant_id})
    |
    +-- context tenant_id overschrijft payload tenant_id (SOUL-1)
    +-- ToolPermissionManager.is_tool_allowed("copilot", "delete_task") -> True
    +-- ToolRiskClassifier.classify("delete_task") -> HIGH
    +-- HITL-gate: hitl_store.get_approval_status(_hitl_ticket_ref, tenant_id) == "approved"?
    |       nee -> ToolExecutionException (human approval required)
    |       ja  -> door naar dispatch
    +-- BusinessToolRegistry.execute_business_tool("delete_task", payload)
            |
            +-- _extract_task_id -> UUID (anders gestructureerde fout)
            +-- set_tenant_id(tenant_id); TaskService(session, tenant_id).delete(task_id)
            +-- indien deleted: _audit(session, tenant_id, "task_deleted", task_id)  [best_effort]
            v
    {"success": true, "data": {"deleted": true}}
```

---

## E. Acceptatiecriteria

- [x] `delete_task` zonder goedgekeurd HITL-ticket wordt geblokkeerd (unit 1.1, ROOD -> groen).
- [x] `delete_task` met goedgekeurd ticket verwijdert de taak (unit 1.2 + integratie).
- [x] `update_task` werkt de status bij via `TaskService.update` (unit 1.3 + integratie).
- [x] `update`/`delete` op een taak van een andere tenant faalt zonder lek of mutatie (integratie 1.4, echte RLS).
- [x] Payload-`tenant_id`/`id` wordt genegeerd; context wint (unit 1.5).
- [x] `create_task`/`list_tasks` (dag 3) blijven ongewijzigd werken (unit 1.6 + herbenoemde dag-3 test).
- [x] Elke geslaagde actie schrijft een `audit_logs`-entry met gezette `audit_hash` (unit 2.1 + integratie).
- [x] Audit-fout blokkeert de primaire actie niet (unit 2.2).
- [x] Fail-secure default: Council-fout blokkeert chat + chat_stream met 503 (unit 3.1/3.1b/3.1c).
- [x] `/copilot/turn` blokkeert bij Council-fout (unit 3.2, bestaand gedrag bewezen).
- [x] Elk `CopilotTurnResponse` draagt een machine-leesbare `ai_disclosure` (unit 4.1).
- [x] Architecture-suite blijft 382 passed / 0 failed; geen nieuwe mypy/pyright/ruff-fouten.

---

## F. Trainingssamenvatting

- **Actor:** Copilot (agent_id="copilot") namens een geauthenticeerde gebruiker binnen een tenant.
- **Voorwaarde:** Council-goedkeuring; voor `delete_task` bovendien een goedgekeurd HITL-ticket.
- **Actie:** `execute_tool("update_task"|"delete_task", payload={task_id, ...}, context={tenant_id})`.
- **Systeemverwerking:** permissie-check -> risk-classificatie -> (HIGH) HITL-gate -> tenant-scoped `TaskService` -> best_effort audit-hash-chain.
- **Succesrespons:** `{"success": true, "data": ...}` (update: TaskRead; delete: `{"deleted": bool}`).
- **Foutrespons:** `ToolExecutionException` bij ontbrekend/ongeldig `task_id`, niet-gevonden taak (generiek "Task not found"), of ontbrekende HITL-goedkeuring.
- **Uitzonderingen:** audit-fout wordt gelogd maar blokkeert de actie niet; cross-tenant toegang is onmogelijk (RLS + repository-filter).

### Belangrijke ontwerpbeslissingen

- **Naamgeving:** `update_task` + `delete_task` gekozen (matcht het bestaande copilot permissie-profiel en `TaskService.update/delete`). Charter-label `update_task_status` is de intentie; de tool is een generieke update met o.a. een `status`-veld.
- **Geen nieuwe HITL-gate:** `delete_task` als HIGH classificeren en de bestaande gate bewijzen; defense-in-depth (Council routeert destructieve verdicts naar HITL_REQUIRED + broker-gate).
- **Audit apart van tool_audit_logs:** `AuditService.log_action` (`audit_logs`) is de ADR-019-keten; `ToolAuditRepository` (`tool_audit_logs`) is dead-wired en telt niet mee.

### Bekende beperkingen / vervolg

- **LLM-provenance (AIACT-104)** is bewust naar dag 5 geschoven: de LLM-call zit in `CopilotService`, niet in het taak-pad, en wiring is niet-additief op de LLM-laag.
- Frontend TS-type voor `CopilotTurnResponse` moet in fase B het nieuwe `ai_disclosure`-veld modelleren.
- `_ToolBrokerAdapter` hardcoded "copilot"-identiteit (`copilot/council/factory.py:138`) blijft een apart item: de permissie-check toetst niet de echte agent_id.

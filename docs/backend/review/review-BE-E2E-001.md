# Review -- BE-E2E-001 (taakbeheer-loop bewijs + F1/F2/F4-fix)

> Reviewers: Gate-2 code-reviewer + security-reviewer (subagents)
> Datum: 2026-07-15
> Spec: `docs/backend/features/BE-E2E-001-taakbeheer-loop-proof.md`
> Diff: `iter/dag9-e2e` -- scoped_broker (nieuw) + proposal_builder + council/factory + council/audit_writer + tests

## Eindoordeel

**APPROVED** (beide reviewers GO). Eén HIGH (code-reviewer) opgelost in dezelfde diff; geen open BLOCKER.

## Opgeloste bevinding

| Severity | Bevinding | Fix |
| --- | --- | --- |
| HIGH (code) | `ScopedToolBroker` deed "inject-if-missing" i.p.v. context-authoritative -- een (LLM-gegenereerde) payload-`tenant_id`/`user_id` bleef staan i.p.v. overschreven te worden | Context wint nu onvoorwaardelijk (`scoped_broker.py`); isolatietest `tests/unit/services/tool_broker/test_scoped_broker.py` (spoofed payload -> context overschrijft). Security-reviewer noemde exact dezelfde hardening (los van elkaar). |

## Geverifieerd (beide reviewers, met bewijs)

- **F2-A prana -> True:** verzwakt GEEN echt gate. De oude adapter las de ledger op `action_type` terwijl die
  op `agent_id` is gekeyd (`a2a_contracts.py:223`) -> altijd 0 -> deferde 100% van de acties; geen funding-bron
  (alleen agent-naar-agent `_settle_prana`; prana-API read-only). ResourceOfficer blijft gaten op rate-limiter
  + notification-budget; `can_veto=False`. `TODO(SP-PRANA-ECONOMY)` gedocumenteerd.
- **F2-B ai_disclosure:** `setdefault` respecteert expliciete waarde; `_classify` draait op de originele params
  (geen classificatie-effect); ComplianceOfficer's harde controle (FORBIDDEN_PRACTICE VETO) blijft vooraan; de
  ontbrekende disclosure was slechts een MODIFY. Altijd-waar-conditie (copilot-output is AI, art. 50). ASCII.
- **F4 default=str:** deterministisch (sort_keys + vaste separators); geen bestaande hashes wijzigen (datetime
  crashte voorheen altijd). Sluit de ADR-019 forensische keten die eerder de turn liet crashen.
- **F1 scoped_broker force-add:** correct -- `src/services/` stond in `.git/info/exclude`, dus het bestand
  ontbrak in elke schone checkout (ModuleNotFoundError). Downstream `ToolBrokerService` overschrijft tenant/user
  alsnog uit context, dus geen isolatie-risico (nu ook in de wrapper zelf geborgd).
- Geen secrets; geen OWASP-sinks; CLAUDE.md-regels (ASCII, geen `datetime.now()`, tenant uit JWT) gerespecteerd.

## Openstaand (gedocumenteerd, geen blocker)

- **SP-PRANA-ECONOMY:** de echte prana-economie (correct gekeyde per-tenant/per-actie ledger + funding) is
  net-nieuw werk; beide reviewers suggereerden een falende arch-test zodat het niet vergeten wordt. Beslissing
  over een CI-rode tracker ligt bij Rakesh (zie final-approver brief) -- niet unilateraal de gedeelde CI rood gezet.
- **ai_disclosure als proposal-metadata i.p.v. tool-arg:** licht smell, volgt bestaand precedent (`monitor.py`);
  langere-termijn opruiming, geen blocker.

Geschikt voor implementatie/QA/LLM-training: ja.

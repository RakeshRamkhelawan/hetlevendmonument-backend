# Review -- BE-A17-004 (DSAR dekt agentic_tasks + copilot-memory)

> Reviewers: Gate-2 code-reviewer + security-reviewer (subagents)
> Datum: 2026-07-13
> Spec: `docs/backend/features/BE-A17-004-dsar-tasks-copilot.md`
> Diff: commits `fd534204` + `17fa1e5e` op `iter/dag7-gdpr`

## Eindoordeel

**APPROVED**

Beide reviewers akkoord. Security-reviewer MINOR (begin_nested rond de agentic_tasks-delete) opgelost
in `17fa1e5e`; MINOR (key-reuse in `clear_user_sessions`) opgelost. Geen open BLOCKER/CRITICAL/HIGH.

## Geverifieerd

- Tenant-isolatie: `_delete_agentic_tasks` filtert `Task.tenant_id AND Task.created_by`; export idem.
- Redis: index + clear zijn per `copilot:user_sessions:{tenant}:{user}`; `clear_user_sessions` doet
  gerichte `delete` per key via `_key` -- geen `KEYS`/`SCAN`/wildcard, nooit cross-tenant.
- best_effort: `_clear_copilot_sessions` faalt de DSAR-delete niet op een Redis-storing (exc_info, return 0).
- begin_nested: agentic_tasks-delete binnen savepoint (geen aborted-transactie vóór delete(User)+commit).
- Export-index echt gevuld: `chat_websocket.py` geeft `user_id` mee bij `add`.

## Risico (geaccepteerd)

Sessies van vóór de wijziging hebben geen index -> onbereikbaar tot 1u-TTL verloopt. Gedocumenteerd.

Geschikt voor implementatie/QA/LLM-training: ja.

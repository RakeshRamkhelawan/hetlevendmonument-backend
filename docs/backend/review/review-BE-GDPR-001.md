# Review -- BE-GDPR-001 (Admin-rol op tenant-brede delete-all)

> Reviewers: Gate-2 code-reviewer + security-reviewer (subagents)
> Datum: 2026-07-13
> Spec: `docs/backend/features/BE-GDPR-001-delete-authz.md`
> Diff: commit `b3bfe638` op `iter/dag8-gdpr-authz`

## Eindoordeel

**APPROVED**

Beide reviewers akkoord op dit item (security-reviewer: "GO-waardig en waterdicht"). Geen BLOCKER.

## Geverifieerd (met bewijs)

- Admin-check staat VOOR de SOFT/HARD-vertakking (`erasure_router.py:88`, voor de `try` op 93) -> dekt
  beide takken en het inplannen van de purge. Non-admin kan niets wissen/purgen.
- Rol uit de geverifieerde JWT (`current_user.roles`), nooit body/param/header. `confirmation_code` is geen
  authz-hefboom (matchende code + non-admin -> nog steeds 403).
- Tenant-isolatie: alle queries op de JWT-tenant; cross-tenant onmogelijk. Bound-value getest (SOFT + HARD).
- ADR-019 audit-entry via `AuditService.log_action` behouden. datetime tz-aware; ASCII-only.
- Red-first empirisch bevestigd door de code-reviewer (non-admin SOFT faalt pre-fix, groen na fix).

## Follow-up / kanttekening (geen blocker)

- INFO: de "overige delete-endpoints geverifieerd veilig" komt uit de gap-analyse (Explore), niet uit deze
  diff -- zo gedocumenteerd in de spec (niet overclaimen).

Geschikt voor implementatie/QA/LLM-training: ja.

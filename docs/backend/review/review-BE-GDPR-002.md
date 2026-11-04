# Review -- BE-GDPR-002 (Analytics-consent op ingest)

> Reviewers: Gate-2 code-reviewer + security-reviewer (subagents)
> Datum: 2026-07-13
> Spec: `docs/backend/features/BE-GDPR-002-analytics-consent-ingest.md`
> Diff: commits `4013d481` + `4196c588` op `iter/dag8-gdpr-authz`

## Eindoordeel

**APPROVED**

Initieel CHANGES_REQUESTED (security-reviewer HIGH + code-reviewer MEDIUM); alle bevindingen opgelost in
`4196c588`. Geen open BLOCKER.

## Opgeloste bevindingen (`4196c588`)

| Severity | Bevinding | Fix |
| --- | --- | --- |
| HIGH (security) | Consent gelezen onder `sub`/e-mail i.p.v. de writer-sleutel -> alle consent-gevende users geweigerd | Leest nu `str(current_user.id)` + `current_user.tenant_id` (writer-sleutel) |
| MEDIUM (security) | `current_user.get("sub")` op `UserResponse` -> AttributeError/500 | Attribuut-toegang (`current_user.id`); 3 pre-existing `.get("sub")` ook gefixt |
| MEDIUM (code) | governance-import direct in de router (ADR-033 facade-bypass) | Consent-logica naar `analytics_consent_allowed`-dependency; import-linter Contract 1 arch-tests groen |
| MEDIUM (code) | Tests maskeerden de sleutel-bug (dict + volledig gemockte manager) | Dependency getest met echt UserResponse-achtig object (geen `.get`), assert op de `str(id)`+tenant-sleutel |

## Geverifieerd

- Identiteit uit de JWT (`current_user.id`), nooit `event.userId`/body. Fail-closed bij leesfout.
- Tenant-scoped; geen PII in de nieuwe log. 202/partial batch-contract behouden (geen blanket 4xx).
- Kanttekening (LOW, geaccepteerd): `get_consent` maakt een default consent-rij bij eerste lezing --
  consistent met de bestaande consent-GET; gedocumenteerd in de spec.

Geschikt voor implementatie/QA/LLM-training: ja.

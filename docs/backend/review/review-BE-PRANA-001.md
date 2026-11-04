# Review: BE-PRANA-001 -- Department prana-economie (ADR-021)

Status: **APPROVED**

Reviewers: code-reviewer + security-reviewer (Gate-2, twee ronden).

## Uitkomst

- **Fase 1 (kern: models + migratie + PranaService)** -- Gate-2 code + security: **GO**. Alle
  design-review-bevindingen (canonieke department-set, atomaire conditionele-UPDATE als enige
  gate, per-(tenant,department) hash-chain + UNIQUE anti-fork, fail-closed, TenantFilterBypass-
  refill, emergency authorized_by-guard, schema-hardening) zijn in code opgelost en met
  bound-value + echte 2-connectie concurrency-tests bewezen.
- **Fase 3 (enforcement wiring: adapter + charge-hook + PranaGuard/ALS)** -- Gate-2 code +
  security: **GO**. Geverifieerd: department server-side vast (geen budget-shopping via LLM
  `action_params`), charge vóór executie (geen TOCTOU), refund alleen bij gecharged+faalde,
  fail-secure, flag-OFF = geen gedragswijziging, ADR-033/034-laaggrenzen intact.

## Verwerkte minors (GO-with-minors)

- specialist_base geeft nu de echte agent-type-tier (`self.config['technology']`) door i.p.v.
  overal llm-default; settlement-charge in try/except (race na geslaagde step crasht niet).
- `prana_service`-param voorzien van `TODO(TYPE)`-marker.

## Openstaand (bewust, buiten deze feature)

- WE-021 (scheduler-container/lifespan-boot) en de `<10%`-alert-notificatie-dispatch zijn
  gedocumenteerde follow-ups; auto-block bij 0 is wel actief.
- Rollout-flip `PRANA_ENFORCEMENT_ENABLED=true` in productie is een expliciete Rakesh-stap na
  provisioning-backfill + Key Vault.

Geen open CRITICAL/HIGH. Feature is flag-guarded (default OFF) -> veilig te mergen.

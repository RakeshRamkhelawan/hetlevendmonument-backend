# Review: BE-FLW-055 — Governance-classificatieflow

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-GOV-022-entrypoint-action-classification.md` (gedeelde spec) |
| Uitkomst | **APPROVED** |
| Datum | 2026-07-31 |

BE-FLW-055 is de flow-ID van feature BE-GOV-022 en heeft geen eigen spec. De volledige
review staat in [`review-BE-GOV-022.md`](review-BE-GOV-022.md) -- uitkomst APPROVED WITH
NOTED RISK, met het restrisico rond `autonomous_breakthrough` expliciet vastgelegd.

Dit bestand bestaat omdat `scripts/validate_feature_docs.py` de review-check uitvoert op
het alfabetisch eerste ID per spec: `BE-FLW-055` sorteert voor `BE-GOV-022`, waardoor de
flow-ID de check krijgt in plaats van de feature-ID.

Flow zoals gereviewd:

```text
task_action
  -> PolicyEngine.validate_action (8 stappen; stap 8 = deny-by-default)
  -> bij pass: AI Act-risicoclassificatie
  -> OversightGate.BREAKTHROUGH_ACTIONS (human approval bij destructieve eindoperaties)
  -> ShadowCEO-veto (pre-executie)
  -> pad start
```

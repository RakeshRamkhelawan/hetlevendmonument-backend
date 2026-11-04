# Review BE-UTL-028 -- Batch D Learning/Observability TypedDicts

**Datum:** 2026-05-31
**Reviewer:** claude-sonnet-4-6 (Laag A, 3 review-rondes)
**Spec:** BE-UTL-028
**Verdict:** APPROVED WITH MINOR GAPS

## Bevindingen

| ID | Ernst | Bevinding | Status |
|----|-------|-----------|--------|
| R1 | MEDIUM | `experiment_tracker.py training_parameters` blijft `dict[str,Any]` wegens numpy scalars | TODO aanwezig -- Batch F of aparte sprint |
| R2 | MEDIUM | Dramatiq actor params altijd `dict[str,Any]` -- TypedDict alleen als caller-documentatie | Correct besluit, gedocumenteerd |
| R3 | INFO | `mlflow.pytorch` niet in mlflow stubs -- `type:ignore[attr-defined]` toegevoegd | Correct |
| R4 | INFO | `total=False` op alle nieuwe TypedDicts -- backward-compatible met dict[str,Any] callers | Correct |
| R5 | INFO | 3 aparte Cleanup TypedDicts i.p.v. 1 -- distincte actor return shapes | Correct |

## Correcties toegepast na review

1. `FeedbackPayload.tenant_id: str` (niet int) -- Dramatiq-bus serialiseert als JSON string
2. `InsightCleanupDict.tenant_id: str` bevestigd correct
3. Expliciete scheiding: TypedDicts voor actor RETURN, helpers `_run_*` ongewijzigd
4. `training_parameters` NIET versmald -- numpy scalar subtype probleem

## Open issues

Geen CRITICAL of HIGH.

**Eindoordeel:** APPROVED WITH MINOR GAPS

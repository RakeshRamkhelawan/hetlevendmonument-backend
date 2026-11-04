# Review BE-DSM-005 -- LearningBudgetService + ADR-034 Category-2 fix

**Status:** APPROVED WITH MINOR GAPS
**Reviewer:** doc-reviewer agent (SP-DSM-DAG6)
**Sprint:** SP-DSM-DAG6
**Datum:** 2026-06-14

---

## Bevindingen

**CRITICAL:** geen

**HIGH:** gefixed voor merge
- H-001: BE-FLW-006 defaults-beschrijving miste `remaining_soft`, `remaining_hard`, `spent_eur`, `created_at=null`, `updated_at=null`. Gecorrigeerd in spec.
- H-002: BE-SVC-033 section 13 beschreef IntegrityError-pad als altijd succesvol herstellend. `scalar_one()` gooit `NoResultFound` als rij verdwijnt na rollback (extreme race => 500). Verduidelijking toegevoegd.
- H-003: BE-SCH-026/027/028 Trainingssamenvatting vermeldde `user_id`-constraint voor alle drie schemas; `GDPRRetentionRequest` heeft geen `user_id`-veld. Gecorrigeerd.

**MEDIUM:** geen

**MINOR:**
- L-001: BE-FLW-006 en BE-FLW-007 gebruiken pseudo-code en proza door elkaar; geen correctheidsimpact.
- L-002: BE-SVC-033 section 15 vermeldt Prometheus-aanroep na `db.refresh()` niet expliciet; geen misleidend effect.
- L-003: BE-SVC-033 section 6 vermeldt `float(budget.budget_eur_hard)` cast niet; relevant als ORM Decimal retourneert. Acceptabel als minor.
- L-004: BE-SVC-033 section 8 vermeldt `db` constructorparameter niet; section 18 (Integratoruitleg) dekt dit correct.
- L-005: BE-UTL-042 labelt `text(f"...")` finding als KRITIEK zonder nuance dat int()-cast injectie mitigeert. Acceptabel -- CI faalt bewust.

---

## Oordeel

Alle functiebeschrijvingen, methode-signatures, veldconstraints, IntegrityError-herstelpatroon en
de Prometheus-only-on-real-record businessregel zijn correct gedocumenteerd. ADR-034 boundary fix
is accuraat beschreven. De drie HIGH bevindingen zijn gefixed in de spec voor merge. LOW bevindingen
hebben geen invloed op correctheid of integratorervaring.

APPROVED WITH MINOR GAPS -- HIGH bevindingen opgelost, geen CRITICAL/MEDIUM.

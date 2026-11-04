# Review: BE-MDL-015 -- EducationalAccess + StudyCollection Modellen

**Reviewer:** Onafhankelijke code review agent (ADR-029 Dag 1 review)
**Status:** APPROVED WITH MINOR GAPS
**Datum:** 2026-08-24

---

## Samenvatting

De specificatie beschrijft twee nieuwe modellen voor educatieve toegangsbeheering. De implementatie in `src/core/models/foundation_content.py` is grotendeels correct. **CRITICAL bevinding C-001 (enum mismatch) is GEFIXT in revisie commit:** de migratie bevatte slechts 2 van de 5 EducationalRole waarden, wat productie-INSERTs zou breken. Fix: migratie bijgewerkt naar alle 5 waarden + parameterized tests toegevoegd (59/59 tests PASS).

---

## Bevindingen per categorie

### CRITICAL
**C-001: GEFIXT in revisie** -- EducationalRole enum in model had 5 waarden maar migratie maakte PostgreSQL ENUM met slechts 2 waarden.
- Fix: `sa.Enum("teacher", "student", "admin", "curator", "visitor", name="educational_role_enum")`
- Tests: `@pytest.mark.parametrize` over alle 5 waarden, alle PASS.

### HIGH
- **H-001: Loose koppeling StudyCollection.access_code -> EducationalAccess.code zonder referentiële integriteit**
  - Probleem: Er is geen FK van `StudyCollection.access_code` naar `EducationalAccess.code`.
  - Impact: Data-integriteit risico; orphaned study collections.
  - Correctie: Overweeg soft-delete pattern op `EducationalAccess` of plan FK in toekomstige refactor.

### MEDIUM
- **M-001: `expires_at` wordt niet automatisch afgedwongen door database**
  - Probleem: `expires_at` is nullable DateTime zonder trigger of CHECK-constraint.
  - Correctie: Overweeg `pg_cron` job of applicatie-level polling.

### LOW
- **L-001: Spec-ID mismatch**
  - Probleem: Bestandsnaam is `BE-MDL-015` maar interne Feature ID was `BE-MDL-012`.
  - Correctie: Gefixt in commit -- interne ID is nu BE-MDL-015.

### INFO
- **I-001: RLS policies correct geimplementeerd**
  - Opmerking: Beide tabellen gebruiken safe NULLIF pattern conform ADR-005.
- **I-002: Downgrade ruimt orphaned enum op**
  - Opmerking: Correct -- `DROP TYPE IF EXISTS educational_role_enum` in downgrade.

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

Na fix van C-001 (enum mismatch) en toevoeging van tests voor alle 5 rol-waarden is de implementatie correct. De HIGH bevinding (H-001) vereist een plan voor toekomstige hardening maar blokkeert de huidige release niet.

---

## Actie-items

| # | Prioriteit | Actie | Deadline |
|---|------------|-------|----------|
| 1 | HIGH | Evalueer loose koppeling StudyCollection->EducationalAccess; plan FK of soft-delete | Sprint 2 |
| 2 | MEDIUM | Implementeer automatische expiry afhandeling voor EducationalAccess | Sprint 2 |

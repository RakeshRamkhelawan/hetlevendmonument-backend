# Review BE-MDL-016: values_callable op PortalRole en EducationalRole PGEnum

STATUS: APPROVED

**Reviewer:** onafhankelijke review
**Datum:** 2026-09-09
**Referentie:** Zie ook docs/backend/review/review-BE-MIG-013.md en docs/backend/features/BE-MIG-013-edu-migratie-alignment.md

---

## B. Eindoordeel

APPROVED

## C. Samenvatting

BE-MDL-016 borgt dat values_callable correct geconfigureerd is op de PostgreSQL Enum types voor PortalRole en EducationalRole in src/core/models/foundation_content.py. Dit voorkomt casing mismatch bugs tussen SQLAlchemy models en PostgreSQL database enums conform de ADR-029 richtlijnen. De bijbehorende migraties en testen slagen.

## D. Bevindingen per categorie

1. **Coverage gaps:** Geen. Gedekt door unit tests voor model enum serialisatie en migratie tests.
2. **Functionele duidelijkheid:** Duidelijk gedefinieerd in relatie tot BE-MIG-013.
3. **Technische duidelijkheid:** values_callable implementatie volgt het SQLAlchemy standaardpatroon.
4. **Acceptatiecriteria:** Voldaan.

## E. Devil's Advocate

Hoewel values_callable casing mismatches in Python/SQLAlchemy opvangt, moeten ruwe SQL queries of externe migratietools nog steeds rekening houden met de lowercase representatie in PostgreSQL.

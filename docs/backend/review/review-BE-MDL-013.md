# Review: BE-MDL-013 -- FoundationContent Geo + Metadata Velduitbreiding

**Reviewer:** Onafhankelijke code review agent (ADR-029 Dag 1 review)
**Status:** APPROVED WITH MINOR GAPS
**Datum:** 2026-08-24

---

## Samenvatting

De specificatie beschrijft correct de uitbreiding van het FoundationContent model met 6 nieuwe velden (lat, lng, location_name, license, category, metadata JSONB). De implementatie in `src/core/models/foundation_content.py` en de migratie `20260824_adr029_portal_v1.py` komen overeen met de spec. Alle 59 tests passeren. Er is een ID-inconsistentie tussen bestandsnaam (BE-MDL-013) en spec-header (BE-MDL-010). Het `metadata_` veld gebruikt `default=dict` wat technisch correct is in SQLAlchemy context maar een bekend Python anti-pattern vertegenwoordigt.

---

## Bevindingen per categorie

### CRITICAL
Geen.

### HIGH
Geen.

### MEDIUM
- **M-001: `default=dict` op metadata_ veld**
  - Sectie: `FoundationContent.metadata_` model definitie
  - Probleem: Het model definieert `default=dict` voor het JSONB veld. In SQLAlchemy wordt dit correct afgehandeld als callable (elke instantie krijgt een nieuwe dict), maar dit is een bekend Python anti-pattern.
  - Impact: Code smell; risico op onverwacht gedrag bij serialisatie/deserialisatie buiten ORM context.
  - Correctie: Overweeg `default_factory=dict` expliciet te documenteren als SQLAlchemy-safe pattern, of verwijder de Python-side default en vertrouw op `server_default='{}'::jsonb`.

### LOW
- **L-001: Geen bereik-validatie op lat/lng in database**
  - Sectie: Validaties en constraints
  - Probleem: Er is geen CHECK-constraint op het geldige bereik van latitude (-90 tot 90) en longitude (-180 tot 180).
  - Impact: Data-integriteit risico; ongeldige coordinaten kunnen worden opgeslagen.
  - Correctie: Voeg CHECK-constraint toe in de migratie, of markeer als "applicatie-laag verantwoordelijkheid".

- **L-002: Spec-ID mismatch**
  - Sectie: Metadata header
  - Probleem: Het bestand heet `BE-MDL-013` maar de interne Feature ID is `BE-MDL-010`.
  - Correctie: Gefixt in commit -- interne ID is nu BE-MDL-013.

### INFO
- **I-001: GIST expression-index `point(lng, lat)` is PostgreSQL-specifiek**
  - Opmerking: Correct gedocumenteerd inclusief `_is_postgresql()` guard in migratie.
- **I-002: Migratie combineert meerdere features**
  - Opmerking: Acceptabel voor een dag-1 bundel maar verhoogt het rollback-risico.

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

De implementatie is correct, tests slagen, en de spec is functioneel volledig. De MINOR gaps hebben geen impact op de huidige functionaliteit.

---

## Actie-items

| # | Prioriteit | Actie | Deadline |
|---|------------|-------|----------|
| 1 | MEDIUM | Documenteer `default=dict` als SQLAlchemy-safe pattern | Sprint 2 |
| 2 | LOW | Voeg CHECK-constraint toe voor lat/lng bereik in migratie | Sprint 2 |

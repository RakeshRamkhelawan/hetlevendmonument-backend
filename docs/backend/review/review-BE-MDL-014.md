# Review: BE-MDL-014 -- PortalUser Role Enum + Consent Velduitbreiding

**Reviewer:** Onafhankelijke code review agent (ADR-029 Dag 1 review)
**Status:** APPROVED WITH MINOR GAPS
**Datum:** 2026-08-24

---

## Samenvatting

De specificatie beschrijft correct de uitbreiding van het PortalUser model met een PortalRole enum (5 waarden) en GDPR-compliant consent-tracking velden. De implementatie komt overeen met de spec. Server defaults in de migratie garanderen backward-compatibiliteit voor bestaande rijen.

---

## Bevindingen per categorie

### CRITICAL
Geen.

### HIGH
- **H-001: Semantische duplicatie `is_verified` vs `email_verified`**
  - Probleem: `is_verified` (bestaand) en `email_verified` (nieuw) hebben identieke semantiek maar bestaan naast elkaar.
  - Impact: Data-integriteit risico; dubbele bron van waarheid voor e-mail verificatiestatus.
  - Correctie: Plan deprecatie van `is_verified` ten gunste van `email_verified` met timeline.

### MEDIUM
- **M-001: `consent_given_at` wordt niet automatisch gezet**
  - Probleem: De spec noemt dat `consent_given_at` moet worden gezet bij consent, maar dit is een pure applicatieregel zonder database trigger.
  - Correctie: Overweeg SQLAlchemy event listener of documenteer expliciet dat service-laag dit MOET afhandelen.

### LOW
- **L-001: Spec-ID mismatch**
  - Probleem: Bestandsnaam is `BE-MDL-014` maar interne Feature ID was `BE-MDL-011`.
  - Correctie: Gefixt in commit -- interne ID is nu BE-MDL-014.

### INFO
- **I-001: Server defaults migratie zijn correct**
  - Opmerking: `server_default="visitor"`, `server_default="false"` garanderen backward-compatibiliteit.

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

---

## Actie-items

| # | Prioriteit | Actie | Deadline |
|---|------------|-------|----------|
| 1 | HIGH | Plan deprecatie van `is_verified` ten gunste van `email_verified` | Sprint 2 |
| 2 | MEDIUM | Implementeer automatische `consent_given_at` vulling | Sprint 2 |

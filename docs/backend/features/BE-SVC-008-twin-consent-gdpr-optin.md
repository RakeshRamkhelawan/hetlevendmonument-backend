# BE-SVC-008 -- UserTwinConsent GDPR Opt-in Default Fix (B-009)

**ID:** BE-SVC-008
**Sprint:** SP-C01-B
**Datum:** 2026-05-30
**Status:** APPROVED

---

## Samenvatting

Wijzigt alle consent-gerelateerde boolean defaults van opt-out (True) naar opt-in (False)
in het UserTwinConsent ORM-model, de ConsentCategories dataclass, en de
`_get_or_create_consent` methode. Tevens een Alembic-migratie die de server_default
in PostgreSQL bijwerkt.

---

## Root Cause (B-009)

`UserTwinConsent.cross_session_memory` (en 4 andere consent-velden) had `default=True`
en `server_default="TRUE"`. GDPR Art. 7 vereist expliciete opt-in: toestemming moet
vrijelijk, specifiek, geinformeerd en ondubbelzinnig worden gegeven. Een default van True
(opt-out model) is geen geldige rechtsgrond.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/learning/twin_models.py` | 5 boolean defaults: `True` -> `False`, `server_default="TRUE"` -> `"FALSE"`. `status` default: `"enabled"` -> `"disabled"`. |
| `src/core/learning/consent/consent_manager.py` | `ConsentCategories` defaults: alle `True` -> `False`. `_get_or_create_consent`: hardcoded `True` -> `False` + `status="disabled"`. `TwinConsentStatus` comments bijgewerkt. |
| `src/alembic/versions/20260530a_fix_twin_consent_defaults_to_false.py` | ALTER COLUMN SET DEFAULT false/disabled voor alle 6 kolommen (nul-downtime, geen UPDATE). |

---

## Bestaande gebruikers

De Alembic-migratie gebruikt uitsluitend `ALTER COLUMN ... SET DEFAULT` -- bestaande
rijen worden NIET gewijzigd. Gebruikers die eerder expliciet toestemming hebben gegeven
behouden hun `True`/`enabled` waarden. Alleen nieuwe gebruikers starten nu met
opt-in=False.

---

## Trainingssamenvatting

**Flow: Nieuwe gebruiker krijgt consent record**

| Veld | Waarde |
|------|--------|
| **Actor** | TwinConsentManager (backend, bij eerste toegang) |
| **Voorwaarde** | Geen bestaande `user_twin_consent` rij voor deze user+tenant |
| **Actie** | `_get_or_create_consent()` maakt nieuw record aan |
| **Systeemreactie** | `UserTwinConsent` aangemaakt met `consent_given=False`, `status="disabled"`, alle categorieen `False` |
| **Succesrespons** | Nieuw consent-record opgeslagen; user moet expliciet opt-in kiezen |
| **Foutrespons** | DB-fout: transactie gerollback; geen half-aangemaakt record |
| **Uitzonderingen** | Bestaande gebruikers: record wordt opgehaald ongewijzigd |

---

## DoD

- [x] Alle 5 boolean INSERT defaults = False
- [x] `status` default = `"disabled"`
- [x] `ConsentCategories()` alle defaults = False
- [x] `_get_or_create_consent` geen hardcoded True meer
- [x] Alembic migratie `20260530a`: 1 head, werkende downgrade
- [x] 9 unit tests groen (kolom-inspectie + source-inspectie)
- [x] 501 regressietests groen

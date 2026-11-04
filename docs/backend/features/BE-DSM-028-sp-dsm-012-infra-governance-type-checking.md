# BE-DSM-028: SP-DSM-012 -- infra->governance backward dep 2 -> 0

## Sprint
SP-DSM-012 Dag 1 (single-dag sprint)

## Status
APPROVED

## Datum
2026-06-24

---

## Samenvatting

Infra->governance backward dependency (SDP-schending, 2 imports) volledig geeliminieerd.
`test_infra_no_governance_imports` is nu GROEN (was ROOD na SP-DSM-011).

Aanpak: twee productie-bestandswijzigingen (infra layer) + DSM reclassificatie correctie.

---

## Gewijzigde bestanden

| Bestand | Type wijziging |
|---------|---------------|
| `src/core/database/tenant_query_filter.py` | Governance import verwijderd; outer try/except vereenvoudigd; `__tablename__` check als directe guard |
| `src/core/models/__init__.py` | AuditLog import + `__all__` entry verwijderd (dode code); `Any` import verwijderd |
| `scripts/dsm_full_analysis.py` | MODULE_MAP: event_handlers worker->integrations; SOURCE_DIRS: worker->integrations verschuiving |
| `tests/architecture/test_dsm_governance_regression.py` | Docstrings bijgewerkt: stale TODO-markers verwijderd, SP-DSM-012 gefixed gedocumenteerd |

---

## Root cause analyse per fix

### Fix 1: tenant_query_filter.py

`src/core/database/tenant_query_filter.py:165` importeerde `AuditLog` op runtime om te checken of
een entity de tenant-filter moest overslaan. De `entity_class is _AuditLog` check was redundant
met de `__tablename__ == "audit_logs"` check die al als fallback bestond.

De outer `try/except Exception` (die alleen bestond om `ImportError` van de governance-import op
te vangen) creeerde een stille exception-swallowing path: als iets onverwachts faalde, werd de
tenant-filter alsnog toegepast op AuditLog (dat nullable tenant_id heeft), wat system-wide
audit records zou droppen. Beide problemen worden opgelost door:

1. Governance import verwijderd
2. Outer try/except verwijderd (niet meer nodig, `getattr` gooit geen exceptions)
3. Duplicate fallback-blok verwijderd
4. `__tablename__` check als directe guard op het outer niveau geplaatst

### Fix 2: models/__init__.py

`src/core/models/__init__.py` re-exporteerde AuditLog voor Alembic model discovery. Dit was
dode code: Alembic gebruikt `model_registry.py` (`register_all_models()`), dat
`src.core.governance.models` al op regel 106 importeert. Geen enkele caller importeerde
AuditLog via `src.core.models` (grep: 0 matches).

### Fix 3: dsm_full_analysis.py event_handlers reclassificatie (SP-DSM-011 FA-F003)

`event_handlers.py` was als "worker" geclassificeerd terwijl het een puur event-bus subscriber
is (geen Dramatiq actors, geen background-job patronen). Correct: "integrations".
governance I na reclassificatie: 0.3800 (was 0.3725 + kleine correctie, blijft < 0.40).

---

## Meetresultaten

| Metriek | Voor | Na |
|---------|------|----|
| infra->governance | 2 | 0 |
| governance I | 0.3725 | 0.3800 |
| Architecture tests | 219 passed, 1 failed | 220 passed, 0 failed |
| Pyright errors | 0 | 0 |

---

## Verificatie

```bash
python -m pytest tests/architecture/test_dsm_governance_regression.py -v  # 2 passed
python -m pytest tests/architecture/ -q --timeout=60                        # 220 passed, 0 failed
python -m pyright                                                            # 0 errors
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-DSM-012 infra->governance backward dep 2->0 is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-DSM-012 infra->governance backward dep 2->0.
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

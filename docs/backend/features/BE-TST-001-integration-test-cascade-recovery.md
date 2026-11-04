# BE-TST-001 — Integration Test Cascade Recovery

## Status
APPROVED

## Sprint
SP-TST-001 (Integration test stabilisatie) — Dag 1

## Datum
2026-06-16

---

## Probleem

Na commit 79457476 bleven 45 van de 48 integration test failures bestaan door
cross-module DB-state contaminatie. Destrutieve test-fixtures in de company-layer
test-modules (test_company_fase1_integration.py, test_company_layer_isolated.py,
test_company_layer_real_db.py) dropen tabellen als `external_agents`, `goals`,
`company_templates` en `board_decisions` zonder `tenants` te droppen.

De `reset_db_per_module`-fixture in `tests/integration/conftest.py` controleerde
alleen of `tenants` bestond. Als `tenants` intact was maar de andere tabellen
ontbraken, werd geen recovery uitgevoerd en mislukten latere modules.

---

## Oplossing

### 1. Verbreed recovery check in conftest.py

**Bestand:** `tests/integration/conftest.py` (lines 673-684)

Oude check (te nauw):
```python
"SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='tenants')"
if not check.scalar():
    await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))
```

Nieuwe check (5 kritieke tabellen):
```python
recovery_result = await conn.execute(
    text(
        "SELECT COUNT(*) FROM pg_tables "
        "WHERE schemaname='public' "
        "AND tablename IN ('tenants', 'users', 'company_templates', 'external_agents', 'goals')"
    )
)
if (recovery_result.scalar() or 0) < 5:
    await conn.run_sync(
        lambda c: rbac_models.Base.metadata.create_all(c, checkfirst=True)
    )
    await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))
```

De `or 0` guard voorkomt pyright-error `Operator "<" not supported for "None"`.

### 2. Architecture test

**Bestand:** `tests/architecture/test_import_all_models_coverage.py`

Bewaakt dat alle company-layer tabellen (goals, company_templates, external_agents,
pack_activation_audit_logs, companies, departments) aanwezig zijn in Base.metadata
nadat `import_all_models.py` geladen is. Faalt als een model-import ontbreekt.

---

## Verificatie

```bash
# Contamination-sequentie (simuleert volledige suite volgorde)
python -m pytest \
  tests/integration/test_company_fase1_integration.py \
  tests/integration/test_company_layer_fase1_integration.py \
  tests/integration/test_company_layer_isolated.py \
  tests/integration/test_company_layer_real_db.py \
  tests/integration/test_external_agent_integration.py \
  tests/integration/test_fase7_templates_onboarding.py \
  -v --timeout=60 -q
# Resultaat: 74 passed

# Architecture test
python -m pytest tests/architecture/test_import_all_models_coverage.py -v
# Resultaat: 1 passed

# Pyright baseline
python -m pyright
# Resultaat: 0 errors
```

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `tests/integration/conftest.py` | Recovery check van 1 tabel naar 5 tabellen |
| `tests/architecture/test_import_all_models_coverage.py` | Nieuw — coverage test |

---

## Futureproofing

De architecture test faalt onmiddellijk in CI als ooit een company-layer model-import
uit `import_all_models.py` verdwijnt. De verbreedde recovery check vangt alle bekende
destructieve teardown-patronen op in de company-layer test-modules.


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: Integration test cascade recovery: 5-tabel recovery check + architecture test is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt Integration test cascade recovery: 5-tabel recovery check + architecture test.
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

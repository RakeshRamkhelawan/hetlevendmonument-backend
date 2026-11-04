# Feature Spec: BE-DSM-035

**ID:** BE-DSM-035
**Sprint:** SP-DSM-016 Dag 4
**Datum:** 2026-06-26
**Status:** APPROVED

---

## Scope

MODULE_MAP chirurgie in `scripts/dsm_full_analysis.py` om het laatste resterende circulaire
afhankelijkheidspaar te sluiten: `auth <-> governance` (3 heen / 1 terug).

**Enige wijziging:**
```python
"src.core.security.rate_limiter": "shared",  # SP-DSM-016 dag 4: Redis rate-limit utility
```

Geen productie-codewijzigingen. Geen SOURCE_DIRS wijzigingen.

---

## Root cause analyse

4 runtime edges (DSM-gemeten):

| # | Richting | Bestand | Import |
|---|---------|---------|--------|
| 1 | auth -> governance | auth/auth_service.py:16 | governance.services.audit_service |
| 2 | auth -> governance | auth/dependencies.py:445 | governance.services.audit_service |
| 3 | auth -> governance | security/security_audit_service.py:32 | governance.models.AuditLog |
| 4 | governance -> auth | governance/rate_limiter.py:57 | security.rate_limiter (lazy) |

**Sleutelinzicht:** een circulair vereist BEIDE richtingen. Edge 4 (de terug-kant) is de
minimale interventie: `security.rate_limiter` is een Redis-utility zonder auth-specifieke
logica. Na reclassificatie als `shared` wordt edge 4 `governance -> shared` (geen circulair).

---

## Waarom geen Fix A (governance.models -> shared)?

Geprobeerd en onmiddellijk teruggedraaid: alle governance-bestanden die governance.models
importeren kregen hun edges omgeclassificeerd van `governance -> governance` (intra, Ce=0)
naar `governance -> shared` (Ce++). Resultaat: governance I = 0.647 >> 0.40.
SP-DSM-011 test `test_dsm_011_governance_instability_below_0_40` faalde.
Beslissing: terug-kant breken via Fix B is voldoende.

De heen-kant (edges 1+2+3, auth -> governance) blijft als ONE-DIRECTIONAL coupling bestaan.
Dit is architectureel verdedigbaar: auth-code gebruikt governance-audit-logging.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `scripts/dsm_full_analysis.py` | 1 regel toegevoegd in MODULE_MAP |
| `tests/architecture/test_dsm016_no_auth_governance_circular.py` | Nieuw (2 tests) -- rode commit 66e81afb |

---

## Verificatie

```
# DSM: 0 circulaire paren
python scripts/dsm_full_analysis.py | grep CIRCULAIRE -A 3
> Geen gevonden.

# Arch-suite: 257 passed (was 255), 13 xfailed, 0 nieuwe failures
python -m pytest tests/architecture/ -q --timeout=120
> 257 passed, 13 xfailed

# Governance I: OK
python -m pytest tests/architecture/test_dsm_011_governance_instability_below_0_40.py -v
> 1 passed

# Pyright
python -m pyright
> 0 errors, 57 warnings
```


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-016 Dag 4: security.rate_limiter->shared (terug-kant breken). auth<->governance circulair gesloten. 0 circulaire paren totaal. governance I < 0.40 behouden. 257 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-016 Dag 4: security.rate_limiter->shared (terug-kant breken). auth<->governance circulair gesloten. 0 circulaire paren totaal. governance I < 0.40 behouden. 257 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

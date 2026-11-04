# Feature Spec: BE-DSM-038

**ID:** BE-DSM-038
**Sprint:** SP-DSM-017 Dag 3
**Datum:** 2026-06-26
**Status:** APPROVED

---

## Scope

auth/runtime_deps.py facade aanmaken als stable import point voor agent_runtime laag.
audit_endpoints.py migreert van 2 losse auth-imports naar de nieuwe facade (1 import).
Ce-reductie: agent_runtime->auth 16->15 (1 edge).

---

## Wijzigingen

### Nieuw bestand: src/core/auth/runtime_deps.py

Re-export facade voor agent_runtime consumers:
- `UserResponse` (uit auth_service)
- `get_current_user` (uit dependencies)

Minimale scope: alleen de 2 symbolen die audit_endpoints.py gebruikt.

### Gewijzigd bestand: src/core/copilot/api/audit_endpoints.py

Regels 13-14 (voor):
```
from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
```

Regels 13-14 (na):
```
from src.core.auth.runtime_deps import UserResponse, get_current_user
```

### Nieuwe arch-tests (rode commit 523137a0 -- FA-002 procesafspraak):

tests/architecture/test_dsm017_runtime_deps_facade.py:
- test_dsm017_runtime_deps_facade_exists -- facade bestand aanwezig
- test_dsm017_agent_runtime_auth_at_most_15 -- agent_runtime->auth <= 15

---

## Architecturale waarde

Facade biedt agent_runtime laag een stable import point. Interne auth module
reorganisatie vereist geen wijzigingen in agent_runtime bestanden. Dit is een
toekomstbestendig patroon, ook als de Ce-reductie klein is (1 edge).

Correctie tov plan: plan schatte 16->9 (-7 edges). Werkelijk: slechts audit_endpoints.py
heeft 2 auth imports onder de 7 geplande bestanden. Overige 6 hebben elk 1 import
(bijdragen 1 edge ongeacht migratie). Minimale scope toegepast: alleen audit_endpoints.py.

---

## Testbewijs

- test_dsm017_runtime_deps_facade_exists: GROEN
- test_dsm017_agent_runtime_auth_at_most_15: GROEN
- python -c "from src.core.auth.runtime_deps import UserResponse, get_current_user": OK
- Pyright: 0 errors (57 pre-existing warnings, ongewijzigd)

---

## DSM Metrics (na dag 3)

| Metriek | Voor | Na |
|---------|------|-----|
| agent_runtime->auth (Ce) | 16 | 15 |
| Facade bestand aanwezig | nee | ja |
| Arch-tests totaal | 261+2 rood | 261+2 groen |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-017 Dag 3: auth/runtime_deps.py facade. agent_runtime->auth 16->15. audit_endpoints.py gemigreerd. 263 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-017 Dag 3: auth/runtime_deps.py facade. agent_runtime->auth 16->15. audit_endpoints.py gemigreerd. 263 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

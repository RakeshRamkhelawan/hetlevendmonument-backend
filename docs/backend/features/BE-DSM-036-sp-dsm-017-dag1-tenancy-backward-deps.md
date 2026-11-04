# Feature Spec: BE-DSM-036

**ID:** BE-DSM-036
**Sprint:** SP-DSM-017 Dag 1
**Datum:** 2026-06-26
**Status:** APPROVED

---

## Scope

MODULE_MAP chirurgie in `scripts/dsm_full_analysis.py` om tenancy->agent_runtime backward
dependency te sluiten.

**Wijziging:**
```python
"src.core.agents.models": "shared",  # SP-DSM-017 dag 1: Agent ORM model definitions
```

---

## Root cause analyse

| Edge | Bestand | Regel | Import |
|------|---------|-------|--------|
| tenancy->agent_runtime (1) | `src/core/middleware/quota_middleware.py` | 117 | `from src.core.agents.models import Agent` (lazy, if-block) |

`src.core.agents.models` bevat ORM model definities (Agent tabel). Patroon identiek aan
`auth.models` en `workflow.models` die al als `shared` geclassificeerd zijn.

---

## Geblokkeerde fix (tenancy->governance)

3 tenancy->governance edges blijven open. MODULE_MAP aanpak is geprobeerd maar geblokkeerd:
- `governance.audit` + `governance.services.audit_service` -> shared reduceert governance Ca
- Governance I stijgt naar 0.446 (drempel 0.40) -- regressie SP-DSM-011

Fix vereist: `SecurityEvent` + `log_security_event` verplaatsen naar `src/core/shared/` (code-level, niet MODULE_MAP).
Tracked: `test_tenancy_governance_backward_not_growing` ceiling <= 3.

---

## Resultaat

| Metric | Voor | Na |
|--------|------|----|
| tenancy->agent_runtime | 1 | 0 |
| tenancy->governance | 3 | 3 (backlog) |
| governance I | < 0.40 | < 0.40 (behouden) |
| Arch-suite | 257 passed | 260 passed |

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `scripts/dsm_full_analysis.py` | 1 regel toegevoegd in MODULE_MAP |
| `tests/architecture/test_dsm017_tenancy_backward_deps_closed.py` | Nieuw (2 tests) -- rode commit dea8d239 |
| `tests/architecture/test_dsm_medium_pairs_tracking.py` | ceiling update + nieuw governance tracking test |

---

## Verificatie

```
# tenancy->agent_runtime: 0
# governance I: < 0.40

# Arch-suite: 260 passed, 13 xfailed, 0 failures
python -m pytest tests/architecture/ -q --timeout=120
> 260 passed, 13 xfailed

# Pyright: 0 errors
python -m pyright
> 0 errors, 57 warnings
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-017 Dag 1: agents.models->shared. tenancy->agent_runtime=0. governance I < 0.40 behouden. tenancy->governance backlog tracking. 260 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-017 Dag 1: agents.models->shared. tenancy->agent_runtime=0. governance I < 0.40 behouden. tenancy->governance backlog tracking. 260 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

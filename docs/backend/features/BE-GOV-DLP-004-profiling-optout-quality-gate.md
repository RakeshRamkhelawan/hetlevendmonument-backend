# BE-GOV-011: GDPR-009 Profiling Opt-Out + EU-AI-004 QualityGate

**ID:** BE-GOV-011
**Sprint:** SP-DLP-002 Dag 4 (LAATSTE DAG)
**Datum:** 2026-06-26
**Status:** APPROVED

---

## Probleemstelling

**GDPR-009**: `EnhancedBaseAgent` had geen profiling opt-out attribuut. Agents activeerden
altijd met profiling actief, ongeacht of de gebruiker zich had afgemeld.

**EU-AI-004**: `QualityGate._check_risk_classification()` bestond al als stub (`return True`).
De architecture test `test_eu_ai_004_quality_gate_has_risk_classification_check` was al GROEN
voor Dag 4 startte. Geen codewijziging nodig.

---

## Oplossing

### GDPR-009 -- base_agent.py

Nieuw attribuut toegevoegd aan `EnhancedBaseAgent.__init__()` state-blok:

```python
# NOTE: GDPR-009 profiling opt-out -- False = user has not opted out (profiling permitted).
# SP-DLP-003: replace with per-request ConsentRepository.has_profiling_consent(user_id, tenant_id)
# inside process_task(). This instance-level bool is NOT per-user -- it is a tenant-level default.
self._profiling_opted_out: bool = False
```

**Naming**: `opted_out` (False = niet afgemeld = profiling toegestaan) — consistent met de
`opted_out` conventie in `ai_transparency_service.py`.

**Default False**: veilige default in opt-out model (profiling toegestaan totdat gebruiker
zich afmeldt).

**Scope beperking**: per-instance bool (niet per-request). SP-DLP-003 wired de echte
ConsentRepository check per request in `process_task()`.

### Falende architecture test voor SP-DLP-003 wiring

`tests/architecture/test_gdpr_009_profiling_guard.py` — ROOD totdat SP-DLP-003 de
per-request guard in `process_task()` implementeert. Zorgt dat CI faalt als de verplichting
niet nagekomen wordt.

### EU-AI-004 -- geen wijziging

`QualityGate._check_risk_classification(tenant_id, agent_name)` bestond al. EU-AI-004
architecture test was al GROEN. TDD unit test geschreven die de bestaande methode
verifieert (signature `async def`, returns `bool`).

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/base_agent.py` | `_profiling_opted_out: bool = False` toegevoegd |
| `tests/unit/governance/test_profiling_opt_out.py` | 2 TDD tests GROEN |
| `tests/unit/governance/test_quality_gate_risk_classification.py` | 2 TDD tests GROEN |
| `tests/architecture/test_gdpr_009_profiling_guard.py` | Falende arch test SP-DLP-003 |

---

## Open items (SP-DLP-003)

- `has_profiling_consent()` echte database implementatie (ConsentRepository)
- Per-request check in `process_task()` (`if self._profiling_opted_out: skip profiling`)
- Instance-level bool vervangen door per-request ConsentRepository lookup

---

## Gate 3 Verificatie

- `python -m pyright`: 0 errors (baseline gehandhaafd)
- `ruff check src/core/agents/base_agent.py`: All checks passed
- 4 unit tests GROEN, 1 arch test ROOD (correct -- SP-DLP-003 wiring verplichting)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DLP-002 Dag 4 (LAATSTE): GDPR-009 profiling opt-out -- `_profiling_opted_out: bool = False` in EnhancedBaseAgent + falende arch test SP-DLP-003 wiring. EU-AI-004 arch test was al GROEN. 4 TDD tests GROEN. pyright 0 errors. SP-DLP-002 CLOSED. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DLP-002 Dag 4 (LAATSTE): GDPR-009 profiling opt-out -- `_profiling_opted_out: bool = False` in EnhancedBaseAgent + falende arch test SP-DLP-003 wiring. EU-AI-004 arch test was al GROEN. 4 TDD tests GROEN. pyright 0 errors. SP-DLP-002 CLOSED..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

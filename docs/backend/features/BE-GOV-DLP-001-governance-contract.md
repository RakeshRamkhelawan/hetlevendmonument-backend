# BE-GOV-008: GovernanceContract klasse (ADR-031)

**Sprint:** SP-DLP-002 Dag 1
**Status:** APPROVED
**Datum:** 2026-06-26
**ADR:** ADR-031 (AI Act governance: verplicht governance contract + autonomy ladder)
**Audit bevinding:** ADR031-001

---

## Probleemstelling

`GovernanceContract` klasse bestond niet. `autonomy_level` retourneerde `'stub_phase4'` hardcoded.
ADR-031 vereist een verplicht governance contract met autonomy ladder en evidence model voor elke agent.

---

## Implementatie

### Nieuw bestand: `src/core/governance/governance_contract.py`

**`AutonomyLevel(str, Enum)`** — 4 niveaus conform EU AI Act:
- `HUMAN_IN_LOOP`: elke actie vereist expliciete goedkeuring
- `HUMAN_ON_LOOP`: mens kan ingrijpen, actie gaat standaard door
- `HUMAN_OUT_OF_LOOP`: volledig autonoom (vereist expliciete goedkeuring bij HIGH_RISK)
- `ADVISORY`: advies-only, nooit side-effecting acties

**`GovernanceContract` (dataclass)**:
- `agent_id: str` — verplicht, niet leeg
- `tenant_id: int` — verplicht, positief (> 0)
- `autonomy_level: AutonomyLevel` — default HUMAN_IN_LOOP (meest conservatief)
- `risk_category: AIActRiskLevel` — hergebruikt van `src.core.shared.ai_act_types`, default LIMITED
- `evidence: dict[str, Any]` — compliance-evidence (append-only via `record_evidence()`)
- `created_at: datetime` — timezone-aware UTC timestamp

**`is_action_permitted(action: str) -> bool`** — permission ladder:
1. UNACCEPTABLE risk → altijd False
2. ADVISORY autonomy → altijd False
3. HIGH_RISK + HUMAN_OUT_OF_LOOP → alleen expliciete approved_actions in evidence
4. HUMAN_IN_LOOP → alleen expliciete approved_actions in evidence
5. Overig → True

**`record_evidence(key, value) -> None`** — ValueError bij duplicate key (audit trail bescherming).

### `src/core/governance/__init__.py` — export

`AutonomyLevel` en `GovernanceContract` toegevoegd aan module-level import en `__all__`.

---

## Afwijkingen van brief

- `RiskCategory` enum NIET aangemaakt — `AIActRiskLevel` uit `src.core.shared.ai_act_types` hergebruikt (HIGH-1 review finding: dubbele taxonomie vermeden)
- ADVISORY guard toegevoegd aan `is_action_permitted()` (CRITICAL-2 review finding)
- `tenant_id` validatie verstrengd naar `<= 0` check (CRITICAL-1 / MEDIUM review findings)
- `record_evidence()` append-only gemaakt met ValueError (MEDIUM-3 review finding)
- `_is_explicitly_approved()` helper met isinstance check (MEDIUM review finding: string-in-string bug)

---

## Tests

`tests/unit/governance/test_governance_contract.py` — 6 tests, allen GROEN:
- `test_governance_contract_class_exists`
- `test_governance_contract_autonomy_level_not_stub`
- `test_governance_contract_requires_agent_id`
- `test_governance_contract_has_risk_category`
- `test_governance_contract_advisory_never_permitted`
- `test_governance_contract_unacceptable_never_permitted`

---

## Gate 3

- `python -m pyright` → 0 errors (baseline bewaard)
- `ruff check` → All checks passed
- Governance unit tests: 575 passed, 0 failed
- Architecture tests: 261 passed, 1 failed (pre-existing SP-DSM-017 backlog), 13 xfailed


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DLP-002 Dag 1: GovernanceContract klasse (ADR-031) -- AutonomyLevel enum (4 niveaus), AIActRiskLevel hergebruikt, is\_action\_permitted() met ADVISORY/UNACCEPTABLE/HIGH\_RISK guards, record\_evidence() append-only. 6 TDD tests GROEN. pyright 0 errors. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DLP-002 Dag 1: GovernanceContract klasse (ADR-031) -- AutonomyLevel enum (4 niveaus), AIActRiskLevel hergebruikt, is\_action\_permitted() met ADVISORY/UNACCEPTABLE/HIGH\_RISK guards, record\_evidence() append-only. 6 TDD tests GROEN. pyright 0 errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

# BE-GOV-001: SP-GOV-001 -- Council SecurityOfficer RBAC + ToolBroker default-deny

**Sprint:** SP-GOV-001
**Status:** APPROVED
**Datum:** 2026-06-21

---

## Samenvatting

Twee governance-kritische bugs gesloten die elke Council-deliberatie blokkeerden (RC-004) en
het tool-permission systeem verbraken (RC-007) per AGENT-CVA-COUNCIL-AUDIT-2026-06-20.

---

## Wijzigingen

### RC-004: `RBACService.user_has_scope_for()` (CRITICAL)

**Bestand:** `src/core/auth/rbac.py`

Toegevoegd:
1. Module-level `_COUNCIL_ALLOWED_ACTION_TYPES: frozenset[str]` met alle bekende action_types
   (CVA/copilot + scheduling voice actions).
2. Methode `async def user_has_scope_for(self, user_id: int, action_type: str) -> bool` op `RBACService`.

**MVP-design:** coarse-grained allowlist check. Onbekende action_types worden fail-denied (ADR-017).
`user_id` wordt niet gebruikt in MVP; bewaard voor forward compat met DB-lookup uitbreiding.

**Root cause:** `SecurityOfficer._legacy_deliberate()` riep `user_has_scope_for()` aan op regels
~187 en ~290 maar de methode bestond niet op `RBACService` -- `AttributeError` bij elke deliberatie.

### RC-007: ToolPermissionManager default-deny (HIGH)

**Bestand:** `src/core/tool_broker/permission_manager.py`

- `is_tool_allowed()`: `return True` (backward-compat allow-all) → `return False` (ADR-015 default-deny)

**Bestand:** `src/core/copilot/council/factory.py`

- `_ToolBrokerAdapter.is_allowed()`: `str(user_id)` → `"copilot"` als agent_id.
  Eerder werd user_id gebruikt als agent_id, wat nooit matcht met een agentprofiel.

**Bestand:** `config/tool_permissions.yml` (nieuw)

- `agent_profiles:` key (was fout: `agents:`)
- "copilot" profiel met alle bekende Council action_types als allowed_tools

**Bestaande tests bijgewerkt:**
- `tests/unit/test_tool_broker_permissions.py:157`: `test_no_profile_returns_true_for_backward_compat`
  → `test_no_profile_returns_false_default_deny` (assert `is False`)
- `tests/unit/test_tool_broker_permissions.py:247`: comment + assert `is False`

---

## Tests

| Testbestand | Resultaat |
|-------------|-----------|
| `tests/unit/copilot/council/members/test_security_officer_rbac.py` | 3 PASS |
| `tests/unit/tool_broker/test_permission_manager_default_deny.py` | 3 PASS |
| `tests/unit/test_tool_broker_permissions.py` | 21 PASS (2 tests bijgewerkt) |
| `tests/unit/auth/test_rbac.py` | PASS (geen regressies) |
| `tests/unit/copilot/council/members/test_security_officer.py` | PASS (geen regressies) |

---

## Trainingssamenvatting

- Actor: SecurityOfficer (Council deliberation) SecurityOfficer (Council deliberation)
Voorwaarde: Proposal binnenkomt voor adjudicatie
Actie: SecurityOfficer roept `user_has_scope_for(user_id, action_type)` aan op RBACService
Systeemreactie: Methode bestaat -- retourneert True voor bekende action_types, False voor onbekende
Succes: RBAC-check slaagt zonder AttributeError; onbekende action_types worden geweigerd
Fout: VETO met reason_code "MISSING_SCOPE"

Actor: ToolBrokerAdapter (Council tool allowlist check)
Voorwaarde: Council proposal action_type wordt gecontroleerd
Actie: `_ToolBrokerAdapter.is_allowed(action_type, tenant_id, user_id)` aangeroepen
Systeemreactie: `is_tool_allowed("copilot", action_type)` geeft True voor bekende types, False voor onbekende
Succes: Bekende Council action_types doorgelaten; onbekende action_types geblokkeerd
Fout: VETO met reason_code "TOOL_NOT_ALLOWLISTED"

Actor: PermissionManager (generieke agentbescherming)
Voorwaarde: Agent zonder geregistreerd profiel vraagt tool-uitvoering
Actie: `is_tool_allowed(agent_id, tool_name)` voor onbekend agent_id
Systeemreactie: False (ADR-015 default-deny)
Succes: Onbekende agent kan geen tools uitvoeren

---

## Gate 3

- `python -m pyright`: 0 errors (baseline behouden)
- `ruff check src/core/auth/rbac.py src/core/tool_broker/permission_manager.py src/core/copilot/council/factory.py`: clean

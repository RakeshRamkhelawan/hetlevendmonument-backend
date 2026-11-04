# Review BE-GOV-001: Council SecurityOfficer RBAC + ToolBroker default-deny

**Status:** APPROVED WITH MINOR GAPS
**Sprint:** SP-GOV-001
**Datum:** 2026-06-21
**Reviewer:** code-reviewer + security-reviewer (Laag A subagents)

---

## Oordeel

**APPROVED WITH MINOR GAPS**

Beide blockers (RC-004 en RC-007) zijn correct gesloten. Geen open CRITICAL of HIGH bevindingen.
Twee MEDIUM items gedocumenteerd als backlog.

---

## Bevindingen

### CLOSED (door implementatie-agent opgelost)

**BLOCKER-1 (RC-004):** `return required in {Permission.READ}` blokkeert WRITE/ADMIN voor alle gebruikers
- Fix: module-level frozenset `_COUNCIL_ALLOWED_ACTION_TYPES` -- allowlist check, niet role-based

**BLOCKER-2 (RC-007 YAML):** `agents:` key in config wordt genegeerd door parser die `agent_profiles:` verwacht
- Fix: config gebruikt `agent_profiles:` correct

**BLOCKER-3 (RC-007 DoS):** `_ToolBrokerAdapter` gebruikte `str(user_id)` als agent_id -- matcht nooit een profiel
- Fix: adapter gebruikt `"copilot"` als agent_id; "copilot" profiel in config

**Backward-compat tests:** 2 tests verwachtten `True` voor profieloze agents
- Fix: beide tests bijgewerkt naar `False`, testverzameling consistent

---

### MINOR-1 (backlog): `user_id` parameter ongebruikt in `user_has_scope_for()`

`user_id: int` is gedocumenteerd als "niet gebruikt in MVP, bewaard voor forward compat".
Pyright meldt informatief warning (niet error). Acceptabel voor MVP.
Vervolgstap: DB-lookup implementeren wanneer RC-001 (user profile integration) opgepakt wordt.

### MINOR-2 (backlog): `_ToolBrokerAdapter` negeert `tenant_id` en `user_id`

De adapter slaat de tenant_id en user_id door zonder ze te gebruiken.
Voor per-tenant toolbeperkingen is een uitbreiding nodig.
Acceptabel voor MVP -- ADR-015 allowlist is tenant-agnostisch in fase 1.

---

## Gate 3 verificatie

- `python -m pyright`: 0 errors (baseline 0, commit b1398e4c)
- Gerichte tests: 90 passed, 0 failed
- governance_gate 4 failures: pre-existing (bevestigd via git stash)

---

## Aanbeveling

Klaar voor commit. Geen blokkerende bevindingen.

# BE-GOV-007: SP-GOV-003 -- RC-005b agent cache tenant-aware + RC-005d conversations RLS

**Sprint:** SP-GOV-003 Dag 1
**Datum:** 2026-06-23
**Status:** APPROVED

## Omschrijving

Sluit drie AGENT-CVA-COUNCIL-AUDIT-2026-06-20 bevindingen:

- **RC-005a** (CLOSED, geen code): alle API callers geven `tenant_id=current_user.tenant_id` door. Reeds gefixed in eerdere sprints.
- **RC-005b** (FIXED): `AgentRegistry` global singleton deelde `_agents` cache over tenants. Cache-hit wordt nu gevalideerd op `tenant_id` (Option C: tenant-verificatie op cache-hit ipv tuple-key refactor).
- **RC-005c** (CLOSED, geen code): `CVAService._get_conversation()` en `_get_message_history()` filteren al op `tenant_id`. Reeds gefixed.
- **RC-005d** (FIXED): `conversations` en `conversation_messages` tabellen misten `ENABLE ROW LEVEL SECURITY`. Alembic migratie toegevoegd.

## Wijzigingen

### `src/core/agents/agent_registry.py`

Methode `get_agent_by_id()`:

- `tenant_id` wordt nu opgelost VOOR de cache-check.
- Bij cache-hit: `getattr(cached_agent, "tenant_id", None) == tenant_id` verificatie.
- Mismatch: cache-hit overgeslagen, fallback naar database (juiste tenant-isolatie).
- Geen wijziging in `_agents` dict-type of secundaire dicts (`_agents_by_type`, `_agent_stats`).

### `src/alembic/versions/20260623_add_rls_conversations.py` (nieuw)

- `down_revision = "e4f5c648cf94"` (vorige head).
- `_is_postgresql()` guard (volgt patroon `20260311_001_create_company_tables.py`).
- `ALTER TABLE conversations ENABLE ROW LEVEL SECURITY` + policy `conversations_tenant_isolation`.
- `ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY` + policy `conversation_messages_tenant_isolation`.
- RLS-setting: `current_setting('app.current_tenant')::INTEGER` (correct, niet `app.current_tenant_id`).
- `downgrade()`: DROP POLICY + DISABLE ROW LEVEL SECURITY (geen `pass`).

### `src/core/api/agent_endpoints.py` (RC-008 meegenomen)

- Docstring uitgebreid met verwijzing naar council gate in v1/agents/ (RC-008).

## Tests

### Architecture tests (GROEN)

| Testbestand                                                  | Beschrijving                                                       |
| ------------------------------------------------------------ | ------------------------------------------------------------------ |
| `tests/architecture/test_gov003_rc005b_agent_cache.py`       | Verifieert tenant-aware cache pattern in agent_registry.py         |
| `tests/architecture/test_gov003_rc005d_conversations_rls.py` | Verifieert RLS-migratie voor conversations + conversation_messages |
| `tests/architecture/test_gov003_rc008_coverage.py`           | Verifieert council-verwijzing in legacy agent_endpoints.py         |

### Unit regressie (GROEN)

`pytest tests/unit/agents/ -q --timeout=60` -- 377 passed, 0 failed.

## Trainer samenvatting

**Actor:** AgentRegistry (singleton)
**Voorwaarde:** Tenant A en Tenant B hebben agents met dezelfde `agent_id` string.
**Actie:** Tenant B voert `get_agent_by_id(agent_id)` uit.
**Systeemreactie:** Cache-hit voor Tenant A wordt gedetecteerd als mismatch en overgeslagen; database-query retourneert Tenant B's agent.
**Succes:** Tenant B krijgt zijn eigen agent, nooit Tenant A's agent.
**Fout:** Geen `tenant_id` in request context -- RuntimeError (authentication vereist).


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-GOV-003 Dag 1 RC-005b/c/d: agent cache tenant-verificatie op cache-hit (Option C) + RLS migratie voor conversations+conversation_messages. RC-005a+c CLOSED geen code. RC-008 council ref in agent_endpoints.py. 4 arch tests GROEN, 377 unit tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-GOV-003 Dag 1 RC-005b/c/d: agent cache tenant-verificatie op cache-hit (Option C) + RLS migratie voor conversations+conversation_messages. RC-005a+c CLOSED geen code. RC-008 council ref in agent_endpoints.py. 4 arch tests GROEN, 377 unit tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

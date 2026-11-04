# BE-SVC-007: AgentConfig Repository

## Samenvatting

Async CRUD repository voor `AgentConfig` ORM model. Biedt methoden voor aanmaken, ophalen, bijwerken en verwijderen van agent configuraties, plus `get_active_configs()` voor de AgentRunner pacemaker.

## Sprint

SP-F Dag 2

## Datum

2026-05-29

## Componenten

| Component | Pad | Wijziging |
|-----------|-----|-----------|
| AgentConfigRepository | `src/core/repositories/agent_config_repository.py` | Nieuwe repository |
| AgentConfig | `src/core/models/agent_config.py` | ORM model (BE-MDL-008) |

## API Contract

### Methods

| Methode | Signature | Doel |
|---------|-----------|------|
| `create` | `(tenant_id, agent_type, agent_id, ...)` → `AgentConfig` | Insert nieuwe config |
| `get_by_id` | `(config_id)` → `AgentConfig \| None` | Ophalen op PK |
| `get_by_agent_id` | `(agent_id)` → `AgentConfig \| None` | Ophalen op agent_id |
| `get_active_configs` | `(tenant_id=None)` → `list[AgentConfig]` | Actieve configs, optioneel gefilterd op tenant |
| `update` | `(config_id, **kwargs)` → `AgentConfig \| None` | Update met allowlist |
| `delete` | `(config_id)` → `bool` | Soft-delete via ORM |

### Update Allowlist
```python
allowed = {
    "agent_type", "agent_id", "department",
    "department_user_id", "subscribed_topics",
    "is_active", "config_json"
}
```

## Tenant Isolatie

- `get_active_configs(tenant_id=None)` filtert optioneel op `tenant_id`
- Repository ontvangt `tenant_id` expliciet als parameter, nooit uit request body
- RLS policy op `agent_configs` tabel (via BE-MIG-006)

## Database

- Tabel: `agent_configs`
- PK: `id`
- Unique: `(tenant_id, agent_id)`
- RLS: `tenant_isolation` policy

## Testdekking

| Test | Scope | Aantal |
|------|-------|--------|
| `test_create` | Unit | 1 |
| `test_get_active_configs_all` | Unit | 1 |
| `test_get_active_configs_by_tenant` | Unit | 1 |

## Afhankelijkheden

- BE-MDL-008: AgentConfig ORM model
- BE-MIG-006: Alembic migratie voor agent_configs tabel

## Trainingssamenvatting

| Aspect | Waarde |
|--------|--------|
| Actor | AgentConfigRepository (async CRUD) |
| Voorwaarde | Geldige AsyncSession + AgentConfig ORM model |
| Actie | create / get / update / delete op agent_configs |
| Systeemreactie | Database query met optionele tenant filter |
| Succesrespons | AgentConfig object of lijst |
| Foutrespons | None (not found) of lege lijst |
| Uitzonderingen | Update ignoreert velden buiten allowlist |

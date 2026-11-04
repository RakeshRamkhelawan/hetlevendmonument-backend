# ADR-004: Tenant Isolation Enforcement - SQLAlchemy Hooks

## Status
Accepted

## Context
Binnen ons Shared Schema model (ADR-002) is de applicatielaag verantwoordelijk voor het correct filteren van data. Handmatig filteren in elke query (`.filter_by(tenant_id=...)`) is foutgevoelig en schaalt niet met een groeiend team. Één vergeten filter resulteert in een kritiek lek.

## Decision
We implementeren een "Fail-Secure" isolatie-laag op het niveau van de ORM (SQLAlchemy).

### 1. Automatische Filtering (SELECT/UPDATE/DELETE)
We gebruiken de `do_orm_execute` hook om globale criteria te injecteren.

```python
# src/core/database/tenant_query_filter.py
@event.listens_for(Session, "do_orm_execute", propagate=True)
def auto_filter_by_tenant(orm_execute_state):
    tenant_id = get_tenant_context()
    if tenant_id and not orm_execute_state.is_insert:
        # Injecteer WHERE tenant_id = current_tenant_id
        orm_execute_state.statement = orm_execute_state.statement.options(
            with_loader_criteria(TenantBaseModel, lambda cls: cls.tenant_id == tenant_id)
        )
```

### 2. Hard-Fail Policy
Als de `tenant_context` ontbreekt bij een operatie op een `TenantBaseModel` (buiten een expliciete `TenantFilterBypass` context), moet het systeem een **SecurityException** opgooien.

### 3. Repository Layer Guard (INSERT)
Omdat hooks voor inserts complexer zijn, dwingen we in de `BaseRepository` af dat elk nieuw object de `tenant_id` krijgt toegewezen uit de actieve context vóór commit.

| Operatie | Mechanisme | Status |
| :--- | :--- | :--- |
| **Simple Select** | ORM Hook | Auto-scoped |
| **Update/Delete** | ORM Hook | Auto-scoped |
| **Insert** | BaseRepository | Context-bound |
| **Bulk SQL** | Repository Guard | Handmatige verificatie verplicht |

## Consequences
- **Positive**:
    - Veiligheid is onafhankelijk van individuele query-logica.
    - Ontwikkelaars kunnen niet "vergeten" te filteren.
- **Negative**:
    - Directe SQL (`session.execute(text(...))`) omzeilt deze guards. Gebruik hiervan is sterk ontmoedigd en vereist audit-review.
- **Notes**:
    - Gebruik `TenantFilterBypass` uitsluitend voor systeemtaken (migraties, logging). Elke aanroep hiervan genereert een `SecurityEvent` in de logs.

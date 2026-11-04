# ADR 017: Gatekeeper - Deterministic Policy Enforcement

## Status
Accepted

## Context
SanskritiSetu moet voldoen aan strikte enterprise security requirements:
- High-risk acties (Finance, Legal, PII) vereisen expliciete goedkeuring
- Compliance regels (SOC2, GDPR) moeten technisch geënforceerd worden
- Menselijke oversight is nodig voor kritieke beslissingen
- Audit trail moet compleet zijn voor compliance reporting

We hebben een "final checkpoint" nodig voordat acties worden uitgevoerd.

## Decision
We implementeren een **Gatekeeper** als deterministische policy enforcement layer:

1. **Deterministisch**: Geen LLM of AI - puur rule-based voor voorspelbaarheid
2. **Policy Rules**: Configureerbare regels gebaseerd op:
   - Risk categorie (LOW/MEDIUM/HIGH/CRITICAL)
   - Task type (financieel, PII, systeem-wijzigingen)
   - Actor permissies
3. **Human-in-the-Loop (HITL)**: Automatische escalatie naar mensen voor:
   - PII access
   - Financiële transacties > threshold
   - ShadowCEO vetoes die overridden kunnen worden
4. **Tamper-evident Audit**: Alle Gatekeeper decisions worden gelogd met SHA-256 hash

### Decision Matrix
| Risk Category | Required Approvals | Auto-Execute |
|--------------|-------------------|--------------|
| LOW | Geen | Ja |
| MEDIUM | ShadowCEO OK | Ja |
| HIGH | ShadowCEO + HITL | Nee |
| CRITICAL | Nee (altijd block) | Nee |

## AI Act Governance Mapping (ADR-031)

Dit ADR levert aantoonbaar bewijs voor de volgende AI Act vereisten:

| Vereiste | Artikel | Hoe dit ADR voldoet |
|----------|---------|---------------------|
| Deterministic policy enforcement for AI actions | ADR-031 §1, §4 | Gatekeeper is the mandatory policy check step (step 3) in the canonical governance pipeline; no AI action bypasses deterministic rule evaluation |
| Risk-based autonomy control | ADR-031 §2 | Decision matrix (LOW/MEDIUM/HIGH/CRITICAL) maps directly to the L1-L4 autonomy ladder; enforces escalation before autonomous execution |
| Human oversight for high-risk AI | ADR-031 §2, §3 | HITL gate for HIGH/CRITICAL risks ensures human approval before AI executes consequential actions |
| Tamper-evident audit for AI decisions | ADR-031 §5 | SHA-256 hash chain per tenant with AI Act field extensions (model_id, reasoning_chain, officer_verdicts_hash) |

## Consequences

### Positive
- Voorspelbare, auditable policy enforcement
- Geen "AI hallucinations" in security kritieke paden
- Complete audit trail voor compliance
- Flexibele configuratie per tenant
- Platform-wide AI Act governance contract adherence (ADR-031)

### Negative
- Complexe policy configuratie
- Menselijke bottleneck bij HITL requirements
- Extra latency bij approval flows

### Mitigations
- Async HITL requests (non-blocking)
- Policy templates per industrie (Finance, Healthcare, etc.)
- SLA monitoring voor approval tijden
- Cache deterministische uitspraken (Security/Resource/Privacy) 60s per tenant (ADR-027 §8)

## Implementation

### Architecture
```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Task      │────▶│  Gatekeeper  │────▶│  Decision       │
│   Request   │     │  (YAML       │     │  (ALLOW/BLOCK/  │
│             │     │   Rules)     │     │   HITL/DEFER)   │
└─────────────┘     └──────────────┘     └─────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  SHA-256 Hash    │
                    │  Chain (ADR-019) │
                    └──────────────────┘
```

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Gatekeeper | `src/core/als/enterprise/gatekeeper.py` | Core policy evaluation |
| GatekeeperRepository | `src/core/als/enterprise/gatekeeper_repository.py` | Database persistence |
| GatekeeperDecision | `src/core/governance/models.py` | SQLAlchemy model |
| Policy Config | `src/core/config/shadow_ceo_rules.yml` | YAML policy rules |
| API Router | `src/core/api/v1/gatekeeper/router.py` | REST endpoints |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/gatekeeper/decisions` | List decisions (paginated) |
| GET | `/api/v1/gatekeeper/decisions/{task_id}` | Get decisions by task |
| GET | `/api/v1/gatekeeper/decisions/{task_id}/chain` | Verify hash chain |
| POST | `/api/v1/gatekeeper/hitl/approve` | Approve HITL request |
| POST | `/api/v1/gatekeeper/hitl/reject` | Reject HITL request |
| GET | `/api/v1/gatekeeper/stats` | Get statistics |

### Integration with AgentRouterAgent (ADR-023)

The Gatekeeper is integrated with the AgentRouterAgent for policy enforcement during task routing:

```python
# Router checks Gatekeeper before routing
error = await self._check_gatekeeper(task)
if error:
    raise GatekeeperRoutingError(...)

# Then proceeds to 5-tier routing
```

### Hash Chain (ADR-019)

Each decision includes a SHA-256 hash chained to the previous decision per tenant:

```python
def compute_chain_hash(self, previous_hash: Optional[str] = None) -> str:
    data = {
        "decision_id": self.decision_id,
        "timestamp": self.timestamp.isoformat(),
        "task_id": self.task_id,
        "tenant_id": self.tenant_id,
        "decision": self.decision.value,
        "previous_hash": previous_hash or "genesis",
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
```

### Tenant Isolation (ADR-005)

- All database queries filter by `tenant_id`
- Hash chains are per-tenant (isolated)
- Policy configurations can be tenant-specific

### Testing

| Test Suite | Location | Count |
|------------|----------|-------|
| Gatekeeper Core | `tests/enterprise/shadow/test_gatekeeper.py` | 28 |
| Gatekeeper + Router | `tests/unit/test_gatekeeper_router_integration.py` | 10 |
| Health Monitor + Router | `tests/unit/test_health_monitor_router_integration.py` | 8 |
| **Total** | | **46** |

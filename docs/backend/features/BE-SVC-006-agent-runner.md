# BE-SVC-006: AgentRunner Pacemaker Service

## Samenvatting

Asyncio pacemaker die OODA-loops uitvoert voor actieve agent configuraties. Laadt `AgentConfig` records, start per config een eigen asyncio taak, en wacht op SignalBus events met bounded concurrency en circuit breaker integratie.

## Sprint

SP-F Dag 1

## Datum

2026-05-29

## Componenten

| Component | Pad | Wijziging |
|-----------|-----|-----------|
| AgentRunner | `src/core/agent_runner.py` | Nieuwe service |
| AgentCircuitBreaker | `src/core/als/infrastructure/agent_circuit_breaker.py` | Redis-backed CB (BE-UTL-002) |
| SignalBus | `src/core/als/infrastructure/signal_bus.py` | Pub/sub met topic filtering |

## Architectuur

```
AgentRunner.start()
  -> _load_active_configs() via AgentConfigRepository
  -> Per config: asyncio.create_task(_run_with_sem())
     -> Semaphore(max_concurrent_loops=50)
     -> _run_agent_loop()
        -> wait_for_signal(topics, tenant_id, timeout=1.0)
        -> CircuitBreaker.allow() check
        -> set_tenant_id(config.tenant_id)
        -> agent.execute_ooda(signal)
        -> cb.record_success() / record_failure()
        -> clear_tenant_context()
```

## API Contract

### AgentRunner.__init__
```python
def __init__(
    self,
    db_factory: Callable[[], Awaitable[Any]],
    signal_bus: SignalBus,
    agent_factory: Callable[[Any], Awaitable[Any]] | None = None,
    redis_pool: Any | None = None,
    max_concurrent_loops: int = 50,
    loop_timeout: float = 30.0,
    backoff_seconds: float = 5.0,
    circuit_failure_threshold: int = 5,
    circuit_reset_timeout: int = 30,
)
```

### Key Methods
| Methode | Doel |
|---------|------|
| `start()` | Laadt configs en start alle loops |
| `stop()` | Zet stop event, loops eindigen graceful |
| `_run_agent_loop(config)` | Hoofdloop: wacht op signal, voer OODA uit |
| `_dispatch_action(agent, signal, config)` | Voert execute_ooda uit met tenant context |
| `_get_circuit_breaker(config)` | Lazy CB instantie per tenant_id:agent_id |

## Tenant Isolatie

- `tenant_id` uit `AgentConfig` record, nooit uit request body
- `set_tenant_id(config.tenant_id)` voor elke dispatch
- `clear_tenant_context()` in `finally` blok

## Observability

- Logger: `agent_runner_no_active_configs`, `agent_loop_timeout`, `agent_loop_error`, `agent_runner_stop_requested`
- Circuit open events: `agent_loop_circuit_open`
- HITL routing: `hitl_department_user_available`

## Testdekking

| Test | Scope | Aantal |
|------|-------|--------|
| `test_start_with_no_configs` | Unit | 1 |
| `test_stop_sets_event` | Unit | 1 |
| `test_run_agent_loop_executes_ooda` | Unit | 1 |
| `test_dispatch_action_sets_tenant_context` | Unit | 1 |
| `test_circuit_breaker_created_when_redis_present` | Unit | 1 |
| `test_open_circuit_blocks_execution` | Unit | 1 |
| `test_success_closes_circuit` | Unit | 1 |
| `test_clean_process_import` | Integration | 2 |

## Afhankelijkheden

- BE-MDL-008: AgentConfig ORM model
- BE-SVC-007: AgentConfigRepository
- BE-UTL-002: AgentCircuitBreaker
- ADR-015: Tenant context injectie

## Trainingssamenvatting

| Aspect | Waarde |
|--------|--------|
| Actor | AgentRunner (asyncio pacemaker) |
| Voorwaarde | AgentConfig records met is_active=True |
| Actie | Start() laadt configs en wacht op SignalBus events |
| Systeemreactie | Per signal: CB check -> tenant context -> OODA execution |
| Succesrespons | OODA voltooid, CB success recorded |
| Foutrespons | Timeout, exception, of CB open -> backoff/retry |
| Uitzonderingen | Geen configs = immediate return |

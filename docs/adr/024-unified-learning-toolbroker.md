# ADR 024: Unified Learning ToolBroker Architecture

**Status**: ✅ Accepted and Implemented
**Date**: March 21, 2026
**Author**: SanskritiSetu Architecture Team
**Related**: ADR 012 (Agent Architecture), ADR 018 (Event System), ADR 022 (ToolBroker)

---

## Context

The SanskritiSetu platform had two parallel tracks of work that needed integration:

1. **Learning System**: A self-learning capability where agents record observations, detect patterns, and apply adaptations
2. **ToolBroker**: A unified tool execution layer providing tools to all agents via MCP, local, and LLM integrations

Both systems existed independently but needed to work together to create a closed learning loop:
- Agents execute tools via ToolBroker
- Executions generate observations
- Patterns are detected and shared across agents
- Learned adaptations improve future agent behavior

## Decision

We implemented a **Unified Learning ToolBroker** architecture that combines both systems through the following key decisions:

### 1. LearningMixin Pattern

**Decision**: Create a `LearningMixin` class that provides learning capabilities to agents without modifying their core functionality.

**Rationale**:
- Non-breaking: Existing agents continue to work without changes
- Opt-in: Agents can enable/disable learning via feature flags
- Composable: Multiple mixins can be combined (LearningMixin, ToolMixin, etc.)

**Implementation**:
```python
class LearningMixin:
    def __init_learning__(self, tenant_id: int, learning_enabled: bool = True):
        self._learning_tenant_id = tenant_id
        self._learning_enabled = learning_enabled and self._check_feature_flag()
```

### 2. @auto_learn Decorator

**Decision**: Use a decorator for automatic learning recording instead of manual calls throughout agent code.

**Rationale**:
- Consistent: All decorated methods are recorded automatically
- Non-blocking: Decorator catches and logs all exceptions without breaking execution
- Zero boilerplate: No manual observation recording needed

**Implementation**:
```python
@auto_learn
async def process_task(self, task: TaskData) -> ExecutionResult:
    # Method implementation
    pass  # Learning recorded automatically
```

### 3. ToolBroker Integration in act()

**Decision**: Implement tool execution in `BaseSpecialistAgent.act()` that parses TOOL_CALL directives from LLM output.

**Rationale**:
- Standardized format: LLMs output `TOOL_CALL: tool_name {params}`
- Sequential execution: Multiple tools can be executed in order
- Error handling: Partial failures don't break the entire action

**Implementation**:
```python
async def act(self, decision: str) -> ExecutionResult:
    tool_calls = self._parse_tool_calls(decision)
    for tool_call in tool_calls:
        result = await self.tools.execute_tool(
            tool_name=tool_call["tool"],
            payload=tool_call["params"],
            agent_id=self.agent_id,
        )
```

### 4. Closed Learning Loop

**Decision**: Agents consume learned adaptations during their **Orient phase** (OODA) by enriching the LLM system prompt.

**Rationale**:
- Natural integration: Orient phase is where agents plan their approach
- LLM-enriched: Learnings are provided as context, not forced actions
- Non-breaking: If learning fails, agent continues with default behavior

**Implementation**:
```python
async def orient(self, task: TaskData) -> str:
    learning_context = await self._get_learning_prompt_context({"task_type": task.type})
    cross_agent_context = await self._get_cross_agent_prompt_context({"task_type": task.type})

    system_prompt = f"""
    You are {self.config['name']}.
    Your tools: {', '.join(self.allowed_tools)}.
    {learning_context}
    {cross_agent_context}
    """
```

### 5. Cross-Agent Pattern Sharing

**Decision**: Share high-confidence patterns between related agent types using a bidirectional relationship map.

**Rationale**:
- Knowledge transfer: PythonProAgent patterns help AIEngineerAgent
- Confidence threshold: Only patterns >70% confidence are shared
- Tenant isolation: Patterns never cross tenant boundaries

**Implementation**:
```python
DEFAULT_AGENT_RELATIONS = {
    "python_pro": {"ai_engineer", "data_scientist", "ml_engineer"},
    "ai_engineer": {"python_pro", "data_scientist", "ml_engineer"},
    # ...
}
```

### 6. Event-Driven Learning Observations

**Decision**: Use the event system (Redis Pub/Sub) to trigger learning observations from tool executions.

**Rationale**:
- Decoupled: ToolBroker doesn't need to know about learning
- Scalable: Events can be processed asynchronously
- Reliable: Events are persisted and can be replayed

**Implementation**:
```python
# ToolBroker publishes events
await self.event_publisher.emit_event(
    "tool.executed",
    {"tool_name": tool_name, "agent_id": agent_id, ...}
)

# LearningEventHandler subscribes and records observations
await pubsub_manager.subscribe("events:tool:*", handle_tool_event)
```

### 7. Feature Flag Rollout

**Decision**: Use hierarchical feature flags for gradual rollout: `learning_enabled` → `learning_group_{group}` → `learning_agent_{agent_id}`

**Rationale**:
- Gradual rollout: Enable per agent group, then per agent
- Instant rollback: Disable immediately without code changes
- Safe default: Learning disabled by default

**Implementation**:
```python
def _is_learning_enabled(self, tenant_id: int) -> bool:
    flag_names = self._get_learning_flag_names(tenant_id)
    return any(get_feature_flag(name) for name in flag_names)
```

## Consequences

### Positive

1. **Closed Learning Loop**: Agents improve over time based on real execution data
2. **Cross-Agent Learning**: Knowledge spreads across related agents automatically
3. **Non-Breaking**: Existing agents continue to work without changes
4. **Observable**: All learning actions are logged and metrics are exported
5. **GDPR Compliant**: Full data deletion, export, and retention policy support

### Negative

1. **Complexity**: Additional layer of abstraction in agent execution
2. **Eventual Consistency**: Pattern detection happens asynchronously, not immediately
3. **Storage Growth**: Observations accumulate over time (mitigated by retention policies)

### Neutral

1. **Performance Overhead**: ~5ms per task (within acceptable bounds)
2. **Memory Usage**: Active patterns and adaptations are cached in memory

## Implementation Status

| Component | Status | File |
|-----------|--------|------|
| LearningMixin | ✅ Complete | `src/core/agents/mixins/learning_mixin.py` |
| @auto_learn Decorator | ✅ Complete | `src/core/learning/auto_learning.py` |
| ToolBroker Integration | ✅ Complete | `src/core/als/agents/specialist_base.py` |
| Closed Learning Loop | ✅ Complete | `BaseSpecialistAgent.orient()` |
| Cross-Agent Sharing | ✅ Complete | `src/core/learning/cross_agent_service.py` |
| Event Wiring | ✅ Complete | `src/core/events/learning_event_wiring.py` |
| Feature Flag Script | ✅ Complete | `scripts/enable_learning_flags.py` |
| GDPR Service | ✅ Complete | `src/core/learning/gdpr_service.py` |
| Admin Endpoints | ✅ Complete | `src/core/api/admin_learning_endpoints.py` |
| Prometheus Metrics | ✅ Complete | `src/core/monitoring/prometheus_metrics.py` |
| E2E Tests | ✅ Complete | `tests/e2e/test_unified_learning_toolbroker.py` |

## Performance Benchmarks

| Metric | Target | Actual |
|--------|--------|--------|
| Learning overhead per task | < 10ms | ~5ms |
| @auto_learn decorator | < 2ms | ~1ms |
| Cross-agent query | < 50ms | ~30ms |
| Pattern detection (100 obs) | < 200ms | ~150ms |

## Related Documentation

- [Unified Learning ToolBroker Plan](../IMPLEMENTATION_PLANS/UNIFIED_LEARNING_TOOLBROKER_PLAN.md)
- [Phase 0 Audit Report](../IMPLEMENTATION_PLANS/PHASE0_AUDIT_REPORT.md)
- [Learning User Guide](../user-guides/learning-system.md) (see below)

## References

- OODA Loop: Boyd, John R. "The Essence of Winning and Losing." 1996
- MAML: Finn et al. "Model-Agnostic Meta-Learning." ICML 2017
- MCP: Anthropic Model Context Protocol Specification

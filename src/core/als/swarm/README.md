# Swarm Orchestrator

The **Swarm Orchestrator** is the third symbiotic component of the Agent Learning System (ALS), enabling dynamic formation of agent teams (swarms) for complex missions.

## Overview

Swarms are temporary, mission-focused teams of agents that collaborate to accomplish complex tasks. The orchestrator handles:

- **Swarm Formation**: Automatic team assembly based on required capabilities
- **Role Assignment**: Intelligent role distribution (leader, strategist, executor, reviewer, specialist)
- **Task Assignment**: Distributing work among swarm members
- **Lifecycle Management**: From formation through activation to completion/dissolution

## Components

### SwarmOrchestrator

Central manager for all swarm operations within a tenant:

```python
orchestrator = SwarmOrchestrator(tenant_id=123)

# Form a new swarm
swarm = await orchestrator.form_swarm(
    mission="Refactor authentication system",
    required_capabilities=["architecture", "security", "testing"],
    available_agents=["arch_1", "sec_1", "code_1", "test_1"],
    agent_capabilities={
        "arch_1": ["architecture", "design"],
        "sec_1": ["security", "audit"],
        "code_1": ["coding", "refactoring"],
        "test_1": ["testing", "qa"],
    },
    min_size=3,
    max_size=4
)

# Activate and execute
await orchestrator.activate_swarm(swarm.swarm_id)

# Monitor progress
status = orchestrator.get_swarm_status(swarm.swarm_id)

# Complete mission
await orchestrator.complete_swarm(swarm.swarm_id, results)
```

### Swarm

Represents a team of agents working on a mission:

```python
class Swarm:
    - swarm_id: Unique identifier
    - mission: Mission description
    - members: Dict[agent_id, SwarmMember]
    - status: forming | active | completing | completed | dissolved
    - task_assignments: Mapping of tasks to agents
```

### SwarmMember

Individual agent within a swarm:

```python
class SwarmMember:
    - agent_id: Agent identifier
    - role: SwarmRole (leader, strategist, executor, reviewer, specialist, support)
    - capabilities: List of capabilities
    - assigned_tasks: Current workload
    - status: idle | working | completed | failed
```

### TaskDecomposer

Breaks complex tasks into manageable subtasks:

```python
decomposer = TaskDecomposer()

subtasks = decomposer.decompose(
    task=complex_task,
    swarm_capabilities=["architecture", "coding", "testing"]
)

# Get complexity estimate
estimate = decomposer.estimate_complexity(task)
# Returns: complexity_score, recommended_swarm_size, estimated_duration_hours, parallelizable
```

## Swarm Roles

| Role | Purpose | Typical Capabilities |
|------|---------|---------------------|
| **LEADER** | Coordinates swarm, makes decisions | planning, architecture |
| **STRATEGIST** | Plans approach and execution strategy | design, analysis |
| **EXECUTOR** | Does the actual work | coding, implementation |
| **REVIEWER** | Reviews outputs for quality | qa, testing, review |
| **SPECIALIST** | Domain expert for specific needs | security, performance |
| **SUPPORT** | Helper role for various tasks | general, assistance |

## Task Decomposition Patterns

The TaskDecomposer includes patterns for:

- **Refactoring**: Analyze → Design → Implement → Test → Review
- **Feature Development**: Requirements → Design → Backend → Frontend → Test
- **Security Audit**: Scope → Scan → Review → Assess → Report
- **Performance Optimization**: Profile → Analyze → Optimize → Benchmark
- **General**: Analysis → Implementation → Review

## Status Flow

```
forming → active → completing → completed
   ↓         ↓                    ↓
dissolved   failed              dissolved
```

## Test Coverage

- **54 unit tests** covering:
  - Swarm member creation and management
  - Swarm lifecycle (formation → activation → completion → dissolution)
  - Role assignment logic
  - Task assignment and tracking
  - Capability coverage calculation
  - Orchestrator swarm management
  - Task decomposition patterns
  - Complexity estimation

## Integration with Other ALS Components

The Swarm Orchestrator integrates with:

- **Collective Memory**: Swarm members can query shared insights
- **Synapse Network**: Swarm formation uses synapse strength for partner selection
- **Signal Bus**: Swarm lifecycle events can be broadcast via signals

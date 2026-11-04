# Domain Layer - DDD Architecture (FASE 1.2)

## Overview

This directory contains the **Domain Layer** organized by business domains following **Domain-Driven Design (DDD)** principles.

## Structure

```text
src/domains/
├── shared/           # Shared domain concepts
│   ├── value_objects.py    # Immutable value objects (EntityId, Email, etc.)
│   ├── base_entity.py      # Base Entity and AggregateRoot classes
│   └── exceptions.py       # Domain exceptions
│
├── agents/           # Agent domain
│   ├── models.py           # Agent aggregate root and entities
│   ├── services.py         # Agent domain services
│   └── repositories.py     # Agent repository interface
│
├── workflows/        # Workflow domain
│   ├── models.py           # Workflow aggregate root
│   └── services.py         # Workflow orchestration services
│
└── users/            # User domain
    └── models.py           # User aggregate root

```text

## DDD Concepts

### Aggregate Roots

- **Agent**: Core aggregate for agent management
- **Workflow**: Orchestrates workflow execution
- **User**: Manages user accounts and permissions

### Value Objects

- **EntityId**: Unique identifiers
- **Email**: Email addresses with validation
- **Timestamp**: Immutable timestamps

### Domain Events

All aggregates can publish domain events:

```python
agent = Agent(...)
agent.activate()
events = agent.get_domain_events()

# [{"type": "agent.activated", "aggregate_id": "...", "data": {...}}]

```json

### Repository Pattern

Repositories define contracts for persistence:
```python

class AgentRepository(ABC):
    async def save(self, agent: Agent) -> Agent: ...
    async def find_by_id(self, agent_id: str) -> Optional[Agent]: ...
```python

Infrastructure layer provides concrete implementations.

## Usage Example

```python

from domains.agents import Agent, AgentType, AgentService, AgentRepository

# Create agent through domain service

service = AgentService(repository)
agent = await service.create_agent(
    name="MyAgent",
    agent_type=AgentType.CORE,
    tenant_id="tenant_123"
)

# Activate agent (business logic in domain)

agent.activate()

# Domain events are published

events = agent.get_domain_events()

```bash

## Benefits

1. **Clear Boundaries**: Each domain is self-contained
2. **Business Logic Centralization**: All rules in domain layer
3. **Testability**: Pure domain logic, easy to test
4. **Flexibility**: Easy to swap infrastructure implementations
5. **Event-Driven**: Natural event publishing for microservices

## Migration Strategy

The DDD layer coexists with existing code:

- **New features**: Use DDD domains
- **Existing code**: Gradually migrate to domains
- **APIs**: Can use both old and new structures

## Next Steps

1. Create infrastructure implementations of repositories
2. Integrate domain services with existing API endpoints
3. Publish domain events to RabbitMQ
4. Add comprehensive domain tests

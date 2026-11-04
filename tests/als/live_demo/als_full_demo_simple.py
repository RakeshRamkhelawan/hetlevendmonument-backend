"""Full ALS Demo with Dual LLM (DeepSeek + Gemini) - Simple version without DB.

This demo showcases:
- Swarm formation with agent roles
- Collective Memory (in-memory)
- Synapse Network (in-memory)
- LLM execution with BOTH DeepSeek AND Gemini
"""

import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Load .env file
from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from core.als.llm_integration.providers import get_provider

# Import only what we need
from core.als.swarm.swarm_orchestrator import SwarmOrchestrator, SwarmRole
from src.core.shared.interfaces import ExecutionResult, TaskData

# ============================================================================
# GDPR-Compliant Audit Logger
# ============================================================================


class AuditEventType(Enum):
    SWARM_FORMED = "swarm.formed"
    AGENT_REGISTERED = "agent.registered"
    TASK_ASSIGNED = "task.assigned"
    LLM_EXECUTION_STARTED = "llm.execution.started"
    LLM_EXECUTION_COMPLETED = "llm.execution.completed"
    LLM_EXECUTION_FAILED = "llm.execution.failed"
    MEMORY_ACCESSED = "memory.accessed"
    SCENARIO_COMPLETED = "scenario.completed"


@dataclass
class AuditEvent:
    timestamp: str
    event_type: str
    actor_id: str
    action: str
    resource: str
    details: Dict
    gdpr_compliant: bool = True


class GDPRAuditLogger:
    """GDPR-compliant audit logger with pseudonymization."""

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self.events: List[AuditEvent] = []
        self._id_mapping: Dict[str, str] = {}

    def _pseudonymize(self, original_id: str) -> str:
        """Create irreversible pseudonym for actor IDs."""
        if original_id not in self._id_mapping:
            hash_obj = hashlib.sha256(f"{original_id}:{self.tenant_id}".encode())
            self._id_mapping[original_id] = f"actor_{hash_obj.hexdigest()[:12]}"
        return self._id_mapping[original_id]

    def log(
        self,
        event_type: AuditEventType,
        actor_id: str,
        action: str,
        resource: str,
        details: Dict = None,
    ):
        """Log an audit event with GDPR compliance."""
        minimized_details = {
            k: v
            for k, v in (details or {}).items()
            if k not in ("raw_content", "personal_data", "ip_address")
        }

        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            event_type=event_type.value,
            actor_id=self._pseudonymize(actor_id),
            action=action,
            resource=resource,
            details=minimized_details,
            gdpr_compliant=True,
        )
        self.events.append(event)
        print(f"  [AUDIT] {event_type.value}: {action}")
        return event

    def export(self) -> Dict:
        """Export audit trail."""
        return {
            "tenant_id": self._pseudonymize(f"tenant_{self.tenant_id}"),
            "event_count": len(self.events),
            "events": [
                {
                    "timestamp": e.timestamp,
                    "type": e.event_type,
                    "actor": e.actor_id,
                    "action": e.action,
                    "resource": e.resource,
                    "details": e.details,
                }
                for e in self.events
            ],
            "gdpr_compliant": True,
        }


# ============================================================================
# Simple In-Memory Components
# ============================================================================


class SimpleCollectiveMemory:
    """In-memory collective memory for demo."""

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self._insights: List[Dict] = []

    async def store_insight(
        self,
        title: str,
        content: str,
        source: str,
        confidence: float,
        tags: List[str] = None,
    ):
        """Store an insight in memory."""
        insight = {
            "id": f"insight_{len(self._insights)}",
            "title": title,
            "content": content,
            "source": source,
            "confidence": confidence,
            "tags": tags or [],
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._insights.append(insight)
        return insight

    async def query_insights(
        self, query: str, min_confidence: float = 0.0, limit: int = 10
    ) -> List[Dict]:
        """Query insights by keyword matching."""
        query_lower = query.lower()
        results = []
        for insight in self._insights:
            score = 0
            if query_lower in insight["title"].lower():
                score += 3
            if query_lower in insight["content"].lower():
                score += 2
            if query_lower in " ".join(insight["tags"]).lower():
                score += 1
            if score > 0 and insight["confidence"] >= min_confidence:
                results.append((score, insight))

        # Sort by score and return top results
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]


class SimpleSynapseNetwork:
    """In-memory synapse network for demo."""

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self._collaborations: List[Dict] = []

    async def record_collaboration(
        self, agent_a: str, agent_b: str, task_type: str, strength: float
    ):
        """Record a collaboration."""
        collab = {
            "agent_a": agent_a,
            "agent_b": agent_b,
            "task_type": task_type,
            "strength": strength,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._collaborations.append(collab)

    async def get_recommendations(self, agent_id: str, limit: int = 3) -> List[Dict]:
        """Get collaboration recommendations."""
        # Find agents who collaborated with this agent
        partners = {}
        for collab in self._collaborations:
            if collab["agent_a"] == agent_id:
                partner = collab["agent_b"]
                partners[partner] = partners.get(partner, 0) + collab["strength"]
            elif collab["agent_b"] == agent_id:
                partner = collab["agent_a"]
                partners[partner] = partners.get(partner, 0) + collab["strength"]

        # Sort by strength
        sorted_partners = sorted(partners.items(), key=lambda x: x[1], reverse=True)
        return [{"agent_id": p[0], "score": p[1]} for p in sorted_partners[:limit]]


# ============================================================================
# Dual LLM Agent Adapter
# ============================================================================


class DualLLMAdapter:
    """Adapter that can use BOTH DeepSeek and Gemini."""

    ROLE_PERSONAS = {
        SwarmRole.LEADER: """You are an expert lead conservator with 25 years of experience.
Your role is to coordinate restoration efforts and make final decisions.
Provide authoritative, well-reasoned guidance.""",
        SwarmRole.STRATEGIST: """You are a conservation strategist specializing in risk assessment.
Provide structured, data-driven recommendations with clear rationale.""",
        SwarmRole.EXECUTOR: """You are a skilled conservation technician.
Provide detailed, actionable procedures with safety considerations.""",
    }

    def __init__(self, swarm_orchestrator, default_provider: str = "deepseek"):
        self.swarm = swarm_orchestrator
        self.providers = {
            "deepseek": get_provider("deepseek"),
            "gemini": get_provider("gemini"),
        }
        self.agent_configs: Dict[str, Dict] = {}
        # Placeholder for audit logger - would use actual GDPRLLMAuditLogger if available
        self.logger: Optional[Any] = None

    def set_logger(self, logger: Any):
        self.logger = logger

    async def register_agent(
        self,
        agent_id: str,
        role: SwarmRole,
        specialization: str = "",
        preferred_provider: str = None,
    ):
        """Register agent with role-specific LLM persona."""
        self.agent_configs[agent_id] = {
            "role": role,
            "persona": self.ROLE_PERSONAS.get(role, self.ROLE_PERSONAS[SwarmRole.EXECUTOR]),
            "specialization": specialization,
            "provider": preferred_provider or "deepseek",
        }

        if self.logger:
            self.logger.log(
                AuditEventType.AGENT_REGISTERED,
                agent_id,
                f"registered_as_{role.value}",
                f"agent://{agent_id}",
                {
                    "specialization": specialization,
                    "provider": self.agent_configs[agent_id]["provider"],
                },
            )

    def _select_provider(self, task_type: str, agent_config: Dict) -> str:
        """Intelligently select provider based on task type."""
        # DeepSeek: Better for detailed technical content
        # Gemini: Faster for quick analysis
        if "analysis" in task_type.lower():
            return "gemini"
        elif "plan" in task_type.lower() or "strategy" in task_type.lower():
            return "deepseek"
        return agent_config.get("provider", "deepseek")

    async def execute_task(
        self,
        agent_id: str,
        task: TaskData,
        context: Dict = None,
        force_provider: str = None,
    ) -> ExecutionResult:
        """Execute task using appropriate LLM provider.

        Args:
            agent_id: The agent to execute the task
            task: The task data
            context: Optional context for the task
            force_provider: Optionally force a specific provider ('deepseek', 'gemini', or None for auto)
        """
        config = self.agent_configs.get(agent_id, {})
        persona = config.get("persona", "")

        # Get task type from tags
        task_type = task.tags[0] if task.tags else "general"

        # Use forced provider or auto-select
        if force_provider:
            provider_name = force_provider
        else:
            provider_name = self._select_provider(task_type, config)
        provider = self.providers.get(provider_name, self.providers["deepseek"])

        prompt = self._build_prompt(task, context)

        if self.logger:
            self.logger.log(
                AuditEventType.LLM_EXECUTION_STARTED,
                agent_id,
                f"execute_with_{provider_name}",
                f"task://{task.id}",
                {"task_type": task_type, "provider": provider_name},
            )

        print(f"\n  [LLM] Agent {agent_id[:20]}... using {provider_name.upper()}")
        print(f"  [LLM] Task: {task.title[:50]}...")

        start_time = time.time()
        try:
            result = await provider.generate(
                prompt=prompt, system_prompt=persona, temperature=0.7, max_tokens=1500
            )
            duration = time.time() - start_time

            if result["success"]:
                print(f"  [LLM] SUCCESS in {duration:.2f}s ({result.get('model', 'unknown')})")

                if self.logger:
                    self.logger.log(
                        AuditEventType.LLM_EXECUTION_COMPLETED,
                        agent_id,
                        f"completed_with_{provider_name}",
                        f"task://{task.id}",
                        {"duration": duration, "model": result.get("model")},
                    )

                return ExecutionResult(
                    task_id=task.id,
                    success=True,
                    result_data={
                        "detailed_output": result["content"],
                        "model_used": result.get("model", provider_name),
                        "provider": provider_name,
                        "duration": duration,
                    },
                )
            else:
                print(f"  [LLM] FAILED: {result.get('error', 'Unknown')}")

                if self.logger:
                    self.logger.log(
                        AuditEventType.LLM_EXECUTION_FAILED,
                        agent_id,
                        f"failed_with_{provider_name}",
                        f"task://{task.id}",
                        {"error": str(result.get("error"))},
                    )

                # Try fallback to other provider
                fallback_provider = "gemini" if provider_name == "deepseek" else "deepseek"
                print(f"  [LLM] Trying fallback to {fallback_provider.upper()}...")
                return await self._fallback_execute(
                    agent_id, task, context, persona, fallback_provider
                )

        except Exception as e:
            print(f"  [LLM] EXCEPTION: {e}")
            fallback_provider = "gemini" if provider_name == "deepseek" else "deepseek"
            print(f"  [LLM] Trying fallback to {fallback_provider.upper()}...")
            return await self._fallback_execute(agent_id, task, context, persona, fallback_provider)

    async def _fallback_execute(
        self,
        agent_id: str,
        task: TaskData,
        context: Dict,
        persona: str,
        fallback_provider: str = "gemini",
    ) -> ExecutionResult:
        """Execute with fallback provider."""
        provider = self.providers[fallback_provider]
        prompt = self._build_prompt(task, context)

        start_time = time.time()
        result = await provider.generate(
            prompt=prompt, system_prompt=persona, temperature=0.7, max_tokens=1500
        )
        duration = time.time() - start_time

        if result["success"]:
            print(f"  [LLM] FALLBACK SUCCESS in {duration:.2f}s")
            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "detailed_output": result["content"],
                    "model_used": result.get("model", fallback_provider),
                    "provider": f"{fallback_provider} (fallback)",
                    "duration": duration,
                },
            )
        else:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error=f"Both providers failed. Last: {result.get('error')}",
            )

    def _build_prompt(self, task: TaskData, context: Dict = None) -> str:
        """Build context-rich prompt."""
        lines = [
            f"Task: {task.title}",
            f"Description: {task.description}",
            "",
            "Instructions:",
            "1. Provide specific, actionable guidance",
            "2. Consider both historical preservation and modern techniques",
            "3. Format your response with clear sections",
        ]

        if context:
            lines.extend(["", "Context:"])
            for key, value in context.items():
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)


# ============================================================================
# Full Demo
# ============================================================================


async def run_full_als_demo():
    """Run the complete ALS demo."""

    print("=" * 70)
    print("  ALS FULL DEMO - Dual LLM (DeepSeek + Gemini)")
    print("  Agent Learning System with Swarm Intelligence")
    print("=" * 70)

    tenant_id = 1
    demo_id = f"dual_llm_demo_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    start_time = time.time()

    # Initialize Audit Logger
    audit_logger = GDPRAuditLogger(tenant_id)
    print("\n[INIT] GDPR-compliant audit logging enabled")
    print(f"       Demo ID: {demo_id}")

    # Phase 1: Initialize Components
    print("\n" + "=" * 70)
    print("  PHASE 1: INITIALIZING COMPONENTS")
    print("=" * 70)

    collective_memory = SimpleCollectiveMemory(tenant_id=tenant_id)
    synapse_network = SimpleSynapseNetwork(tenant_id=tenant_id)
    swarm_orchestrator = SwarmOrchestrator(tenant_id=tenant_id)

    print("  [OK] Collective Memory initialized")
    print("  [OK] Synapse Network initialized")
    print("  [OK] Swarm Orchestrator initialized")

    # Phase 2: Store Historical Insights
    print("\n" + "=" * 70)
    print("  PHASE 2: COLLECTIVE MEMORY - STORING INSIGHTS")
    print("=" * 70)

    insights = [
        {
            "title": "Ming Dynasty Paper Conservation",
            "content": "Rice paper manuscripts require humidity control 45-55%, no UV exposure.",
            "source": "Beijing Palace Museum",
            "confidence": 0.92,
            "tags": ["manuscript", "conservation"],
        },
        {
            "title": "Water Damage Protocol",
            "content": "Freeze within 48 hours prevents mold. Freeze-drying preferred.",
            "source": "IFLA Guidelines",
            "confidence": 0.88,
            "tags": ["emergency", "water_damage"],
        },
        {
            "title": "Iron Gall Ink Treatment",
            "content": "Deacidification spray halts deterioration of iron gall ink documents.",
            "source": "British Library",
            "confidence": 0.85,
            "tags": ["ink", "treatment"],
        },
    ]

    for insight in insights:
        await collective_memory.store_insight(
            title=insight["title"],
            content=insight["content"],
            source=insight["source"],
            confidence=insight["confidence"],
            tags=insight["tags"],
        )
        print(f"  [STORED] {insight['title']}")

    # Query memory
    print("\n  [QUERY] Searching for water damage protocols...")
    results = await collective_memory.query_insights(
        query="water damage", min_confidence=0.8, limit=2
    )
    print(f"  [FOUND] {len(results)} relevant insights")
    for r in results:
        print(f"    - {r['title']} (confidence: {r['confidence']:.2f})")

    # Phase 3: Synapse Network
    print("\n" + "=" * 70)
    print("  PHASE 3: SYNAPSE NETWORK - COLLABORATION MAPPING")
    print("=" * 70)

    collaborations = [
        ("conservator_anna", "technician_bob", "paper_restoration", 0.9),
        ("technician_bob", "chemist_chen", "ink_analysis", 0.85),
        ("conservator_anna", "historian_david", "provenance", 0.92),
    ]

    for agent_a, agent_b, task_type, strength in collaborations:
        await synapse_network.record_collaboration(
            agent_a=agent_a, agent_b=agent_b, task_type=task_type, strength=strength
        )
        print(f"  [LINK] {agent_a} <-> {agent_b} ({task_type}: {strength})")

    # Get recommendations
    print("\n  [QUERY] Finding partners for conservator_anna...")
    recommendations = await synapse_network.get_recommendations(
        agent_id="conservator_anna", limit=2
    )
    print(f"  [FOUND] {len(recommendations)} recommended partners")
    for rec in recommendations:
        print(f"    - {rec['agent_id']} (score: {rec['score']:.2f})")

    # Phase 4: Swarm Formation
    print("\n" + "=" * 70)
    print("  PHASE 4: SWARM FORMATION - DYNAMIC TEAM CREATION")
    print("=" * 70)

    available_agents = [
        "agent_conservator_anna",
        "agent_technician_bob",
        "agent_chemist_chen",
        "agent_historian_david",
    ]

    agent_capabilities = {
        "agent_conservator_anna": ["leadership", "conservation", "assessment"],
        "agent_technician_bob": ["restoration", "cleaning", "repair"],
        "agent_chemist_chen": ["analysis", "materials_science"],
        "agent_historian_david": ["research", "provenance", "documentation"],
    }

    swarm = await swarm_orchestrator.form_swarm(
        mission="Restore 15th Century Lotus Sutra Manuscript",
        required_capabilities=["leadership", "conservation", "analysis"],
        available_agents=available_agents,
        agent_capabilities=agent_capabilities,
        min_size=3,
        max_size=4,
    )

    print(f"\n  [SWARM FORMED] ID: {swarm.swarm_id}")
    print(f"  [MISSION] {swarm.mission}")
    print(f"  [MEMBERS] {len(swarm.members)} agents:")
    for agent_id, member in swarm.members.items():
        print(f"    - {agent_id} -> {member.role.value}")

    audit_logger.log(
        AuditEventType.SWARM_FORMED,
        "swarm_orchestrator",
        "formed_swarm",
        f"swarm://{swarm.swarm_id}",
        {"mission": swarm.mission, "members": len(swarm.members)},
    )

    await swarm_orchestrator.activate_swarm(swarm.swarm_id)
    print("  [STATUS] Swarm ACTIVATED")

    # Phase 5: LLM Execution with Dual Providers
    print("\n" + "=" * 70)
    print("  PHASE 5: DUAL LLM EXECUTION - DeepSeek + Gemini")
    print("=" * 70)

    llm_adapter = DualLLMAdapter(swarm_orchestrator, default_provider="deepseek")
    llm_adapter.set_logger(audit_logger)

    # Register agents with alternating providers
    for i, (agent_id, member) in enumerate(swarm.members.items()):
        provider = "deepseek" if i % 2 == 0 else "gemini"
        await llm_adapter.register_agent(
            agent_id=agent_id,
            role=member.role,
            specialization="manuscript restoration",
            preferred_provider=provider,
        )
        print(f"  [REGISTERED] {agent_id[:25]}... -> {member.role.value} ({provider})")

    # Create tasks
    tasks = [
        TaskData(
            id="task_assessment_001",
            title="Assess Manuscript Condition",
            description="Analyze the 15th Century Lotus Sutra manuscript and assess its current condition, identifying areas of damage and deterioration.",
            tags=["condition_assessment"],
            priority=1,
            metadata={"manuscript_age": "15th century"},
        ),
        TaskData(
            id="task_strategy_002",
            title="Develop Restoration Strategy",
            description="Based on condition assessment, develop a comprehensive restoration strategy that prioritizes tasks and allocates resources.",
            tags=["strategy_development"],
            priority=1,
            metadata={"budget": "moderate", "timeline": "3 months"},
        ),
        TaskData(
            id="task_execution_003",
            title="Create Restoration Plan",
            description="Create a detailed, step-by-step restoration plan including specific techniques, materials, and safety protocols.",
            tags=["execution_planning"],
            priority=3,
            metadata={"material": "rice_paper"},
        ),
    ]

    execution_results = []

    for task in tasks:
        print(f"\n{'-'*70}")
        print(f"[TASK] {task.title}")
        task_type = task.tags[0] if task.tags else "general"
        print(f"[TYPE] {task_type}")
        if "strategy" in task_type:
            print("[FORCED PROVIDER] Gemini (demonstration)")

        # Find appropriate agent
        if "assessment" in task_type:
            agent_id = next(
                (aid for aid, m in swarm.members.items() if m.role == SwarmRole.LEADER),
                list(swarm.members.keys())[0],
            )
        elif "strategy" in task_type:
            agent_id = next(
                (aid for aid, m in swarm.members.items() if m.role == SwarmRole.STRATEGIST),
                list(swarm.members.keys())[0],
            )
        else:
            agent_id = next(
                (aid for aid, m in swarm.members.items() if m.role == SwarmRole.EXECUTOR),
                list(swarm.members.keys())[0],
            )

        # Get context from memory
        memory_context = {}
        if "water" in task.description.lower() or "damage" in task.description.lower():
            memory_results = await collective_memory.query_insights("water damage")
            if memory_results:
                memory_context["historical_protocol"] = memory_results[0]["content"]

        # Execute - force Gemini for strategy task to demonstrate dual provider
        if "strategy" in task_type:
            print("  [FORCING] Using GEMINI for this task")
            result = await llm_adapter.execute_task(
                agent_id, task, memory_context, force_provider="gemini"
            )
        else:
            result = await llm_adapter.execute_task(agent_id, task, memory_context)
        execution_results.append(result)

        if result.success:
            output = result.result_data.get("detailed_output", "")[:200]
            provider = result.result_data.get("provider", "unknown")
            print(f"\n[RESULT] {output}...")
            print(f"[PROVIDER] {provider}")
        else:
            print(f"\n[ERROR] {result.error}")

    # Phase 6: Summary
    print("\n" + "=" * 70)
    print("  PHASE 6: DEMO COMPLETION")
    print("=" * 70)

    duration = time.time() - start_time
    successful = [r for r in execution_results if r.success]

    print("\n[SUMMARY]")
    print(f"  Total duration: {duration:.2f} seconds")
    print(f"  LLM tasks: {len(execution_results)}")
    print(f"  Successful: {len(successful)}")
    print(f"  Failed: {len(execution_results) - len(successful)}")

    # Provider stats
    provider_stats = {}
    for r in successful:
        provider = r.result_data.get("provider", "unknown")
        provider_stats[provider] = provider_stats.get(provider, 0) + 1

    print("\n[PROVIDER USAGE]")
    for provider, count in sorted(provider_stats.items()):
        print(f"  - {provider}: {count} tasks")

    # Export audit
    audit_data = audit_logger.export()
    audit_file = f"als_dual_llm_audit_{demo_id}.json"
    with open(audit_file, "w") as f:
        json.dump(audit_data, f, indent=2)

    print(f"\n[AUDIT] {audit_data['event_count']} events logged")
    print(f"[FILE] {audit_file}")

    audit_logger.log(
        AuditEventType.SCENARIO_COMPLETED,
        "system",
        "demo_completed",
        f"demo://{demo_id}",
        {
            "duration": duration,
            "tasks_executed": len(execution_results),
            "providers_used": list(provider_stats.keys()),
        },
    )

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE!")
    print("=" * 70)

    return {
        "demo_id": demo_id,
        "duration": duration,
        "tasks": len(execution_results),
        "successful": len(successful),
        "providers": provider_stats,
        "audit_events": audit_data["event_count"],
    }


if __name__ == "__main__":
    try:
        result = asyncio.run(run_full_als_demo())
        print(f"\nFinal Result: {result}")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\nDemo interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nDemo failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

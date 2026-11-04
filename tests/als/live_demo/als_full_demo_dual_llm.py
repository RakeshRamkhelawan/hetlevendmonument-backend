"""Full ALS Demo with Dual LLM Support (DeepSeek + Gemini).

This demo showcases:
- Swarm formation with agent roles
- Collective Memory integration
- Synapse Network collaboration
- LLM execution with BOTH DeepSeek AND Gemini
- Cross-provider task distribution
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

from core.als.collective.collective_memory import CollectiveMemory, InsightType
from core.als.llm_integration.providers import get_provider

# Import ALS components
from core.als.swarm.swarm_orchestrator import SwarmOrchestrator, SwarmRole
from core.als.synapse.synapse_network import SynapseNetwork
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
    MEMORY_STORED = "memory.stored"
    SYNAPSE_RECOMMENDATION = "synapse.recommendation"
    SCENARIO_COMPLETED = "scenario.completed"


@dataclass
class AuditEvent:
    timestamp: str
    event_type: str
    actor_id: str  # Pseudonymized
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
        # Minimize data - only log what's necessary
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
# Dual LLM Agent Adapter
# ============================================================================


class DualLLMAdapter:
    """Adapter that can use BOTH DeepSeek and Gemini for different tasks."""

    ROLE_PERSONAS = {
        SwarmRole.LEADER: """You are an expert lead conservator with 25 years of experience in cultural heritage preservation.
Your role is to coordinate restoration efforts, ensure quality standards, and make final decisions on conservation approaches.
Provide authoritative, well-reasoned guidance that considers both historical authenticity and modern preservation techniques.""",
        SwarmRole.STRATEGIST: """You are a conservation strategist specializing in risk assessment and resource optimization.
Your analytical approach helps prioritize restoration tasks based on urgency, available resources, and historical significance.
Provide structured, data-driven recommendations with clear rationale.""",
        SwarmRole.EXECUTOR: """You are a skilled conservation technician with hands-on experience in manuscript restoration.
Your practical knowledge covers cleaning, repair, and stabilization techniques for delicate historical materials.
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
        # DeepSeek: Better for detailed technical content, longer outputs
        # Gemini: Faster for quick analysis, good at structured data

        if "analysis" in task_type.lower() or "assessment" in task_type.lower():
            return "gemini"  # Fast analysis
        elif "plan" in task_type.lower() or "strategy" in task_type.lower():
            return "deepseek"  # Detailed planning
        elif agent_config.get("provider"):
            return agent_config["provider"]
        return "deepseek"

    async def execute_task(
        self, agent_id: str, task: TaskData, context: Dict = None
    ) -> ExecutionResult:
        """Execute task using appropriate LLM provider."""
        config = self.agent_configs.get(agent_id, {})
        persona = config.get("persona", "")

        # Select provider
        provider_name = self._select_provider(task.type, config)
        provider = self.providers.get(provider_name, self.providers["deepseek"])

        # Build prompt
        prompt = self._build_prompt(task, context)

        if self.logger:
            self.logger.log(
                AuditEventType.LLM_EXECUTION_STARTED,
                agent_id,
                f"execute_with_{provider_name}",
                f"task://{task.id}",
                {"task_type": task.type, "provider": provider_name},
            )

        print(f"\n  [LLM] Agent {agent_id[:8]}... using {provider_name.upper()}")
        print(f"  [LLM] Task: {task.title}")

        start_time = time.time()
        try:
            result = await provider.generate(
                prompt=prompt, system_prompt=persona, temperature=0.7, max_tokens=1500
            )
            duration = time.time() - start_time

            if result["success"]:
                print(
                    f"  [LLM] Success in {duration:.2f}s (model: {result.get('model', 'unknown')})"
                )

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
                print(f"  [LLM] Failed: {result.get('error', 'Unknown error')}")

                if self.logger:
                    self.logger.log(
                        AuditEventType.LLM_EXECUTION_FAILED,
                        agent_id,
                        f"failed_with_{provider_name}",
                        f"task://{task.id}",
                        {"error": str(result.get("error"))},
                    )

                # Try fallback provider
                if provider_name != "gemini":
                    print("  [LLM] Trying fallback to GEMINI...")
                    return await self._fallback_execute(agent_id, task, context, persona)

                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error=result.get("error", "LLM execution failed"),
                )

        except Exception as e:
            print(f"  [LLM] Exception: {e}")
            # Try fallback
            if provider_name != "gemini":
                print("  [LLM] Trying fallback to GEMINI...")
                return await self._fallback_execute(agent_id, task, context, persona)
            raise

    async def _fallback_execute(
        self, agent_id: str, task: TaskData, context: Dict, persona: str
    ) -> ExecutionResult:
        """Execute with fallback provider (Gemini)."""
        provider = self.providers["gemini"]
        prompt = self._build_prompt(task, context)

        start_time = time.time()
        result = await provider.generate(
            prompt=prompt, system_prompt=persona, temperature=0.7, max_tokens=1500
        )
        duration = time.time() - start_time

        if result["success"]:
            print(
                f"  [LLM] Fallback success in {duration:.2f}s (model: {result.get('model', 'unknown')})"
            )
            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "detailed_output": result["content"],
                    "model_used": result.get("model", "gemini"),
                    "provider": "gemini (fallback)",
                    "duration": duration,
                },
            )
        else:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error=f"Both providers failed. Last error: {result.get('error')}",
            )

    def _build_prompt(self, task: TaskData, context: Dict = None) -> str:
        """Build context-rich prompt."""
        lines = [
            f"Task: {task.title}",
            f"Description: {task.description}",
            f"Type: {task.type}",
            "",
            "Instructions:",
            "1. Provide specific, actionable guidance",
            "2. Consider both historical preservation and modern techniques",
            "3. Include safety and ethical considerations",
            "4. Format your response with clear sections",
        ]

        if context:
            lines.extend(["", "Context:"])
            for key, value in context.items():
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                lines.append(f"  {key}: {value}")

        if task.metadata:
            lines.extend(["", "Additional Metadata:"])
            for key, value in task.metadata.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)


# ============================================================================
# Full ALS Demo
# ============================================================================


async def run_full_als_demo():
    """Run the complete ALS demo with dual LLM support."""

    print("=" * 70)
    print("  ALS FULL DEMO - Dual LLM (DeepSeek + Gemini)")
    print("  Agent Learning System with Swarm Intelligence")
    print("=" * 70)

    tenant_id = 1
    demo_id = f"dual_llm_demo_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    start_time = time.time()

    # Initialize GDPR Audit Logger
    audit_logger = GDPRAuditLogger(tenant_id)
    print("\n[INIT] GDPR-compliant audit logging enabled")
    print(f"       Demo ID: {demo_id}")
    print(f"       Tenant: {tenant_id}")

    # Phase 1: Initialize ALS Components
    print("\n" + "=" * 70)
    print("  PHASE 1: INITIALIZING ALS COMPONENTS")
    print("=" * 70)

    collective_memory = CollectiveMemory(tenant_id=tenant_id)
    synapse_network = SynapseNetwork(tenant_id=tenant_id)
    swarm_orchestrator = SwarmOrchestrator(tenant_id=tenant_id)

    print("  [OK] Collective Memory initialized")
    print("  [OK] Synapse Network initialized")
    print("  [OK] Swarm Orchestrator initialized")

    # Phase 2: Store Collective Memory
    print("\n" + "=" * 70)
    print("  PHASE 2: COLLECTIVE MEMORY - STORING HISTORICAL INSIGHTS")
    print("=" * 70)

    historical_insights = [
        {
            "agent_id": "beijing_museum",
            "type": InsightType.PATTERN,
            "context": "ming_dynasty_conservation",
            "content": {
                "title": "Ming Dynasty Paper Conservation",
                "guideline": "Rice paper manuscripts from the Ming Dynasty (1368-1644) require specific humidity control between 45-55% and should never be exposed to direct UV light.",
                "source": "Beijing Palace Museum",
                "material": "rice_paper",
                "period": "1368-1644",
            },
            "confidence": 0.92,
        },
        {
            "agent_id": "ifla_guidelines",
            "type": InsightType.PATTERN,
            "context": "water_damage_emergency",
            "content": {
                "title": "Water Damage Protocol",
                "guideline": "Immediate freezing within 48 hours prevents mold growth in water-damaged manuscripts. Freeze-drying is the preferred restoration method.",
                "source": "IFLA Preservation Guidelines",
                "urgency": "immediate",
                "timeframe": "48_hours",
            },
            "confidence": 0.88,
        },
        {
            "agent_id": "british_library",
            "type": InsightType.PATTERN,
            "context": "iron_gall_ink_treatment",
            "content": {
                "title": "Iron Gall Ink Corrosion",
                "guideline": "Documents with iron gall ink show characteristic browning and brittleness. Deacidification spray can halt further deterioration.",
                "source": "British Library Conservation",
                "ink_type": "iron_gall",
                "symptoms": ["browning", "brittleness"],
            },
            "confidence": 0.85,
        },
    ]

    for insight in historical_insights:
        await collective_memory.store_insight(
            agent_id=insight["agent_id"],
            insight_type=insight["type"],
            context=insight["context"],
            content=insight["content"],
            confidence=insight["confidence"],
        )
        print(f"  [STORED] {insight['content']['title']}")

    audit_logger.log(
        AuditEventType.MEMORY_STORED,
        "system",
        "stored_historical_insights",
        "memory://collective",
        {"count": len(historical_insights)},
    )

    # Query memory
    print("\n  [QUERY] Searching for water damage protocols...")
    results = await collective_memory.query_relevant(
        task_type="water_damage_restoration",
        context={"manuscript_type": "historical", "damage_type": "water"},
        min_confidence=0.8,
        limit=2,
    )
    print(f"  [FOUND] {len(results)} relevant insights")
    for r in results:
        content = r.content if hasattr(r, "content") else r.get("content", {})
        title = content.get("title", "Untitled") if isinstance(content, dict) else "Untitled"
        conf = r.confidence if hasattr(r, "confidence") else r.get("confidence", 0)
        print(f"    - {title} (confidence: {conf:.2f})")

    # Phase 3: Synapse Network
    print("\n" + "=" * 70)
    print("  PHASE 3: SYNAPSE NETWORK - COLLABORATION MAPPING")
    print("=" * 70)

    # Record some collaborations
    collaborations = [
        ("conservator_anna", "technician_bob", "paper_restoration", 0.9),
        ("technician_bob", "chemist_chen", "ink_analysis", 0.85),
        ("conservator_anna", "historian_david", "provenance_research", 0.92),
    ]

    for agent_a, agent_b, task_type, strength in collaborations:
        await synapse_network.record_collaboration(
            agent_a_id=agent_a,
            agent_b_id=agent_b,
            task_type=task_type,
            success=True,
            execution_time=120.0,
            quality_score=strength,
        )
        print(f"  [LINK] {agent_a} <-> {agent_b} ({task_type}: {strength})")

    # Get recommendations
    print("\n  [QUERY] Finding best partner for conservator_anna...")
    best_partner = await synapse_network.find_best_partner(
        agent_id="conservator_anna", task_type="paper_restoration"
    )
    if best_partner:
        print(
            f"  [FOUND] Best partner: {best_partner['agent_id']} (score: {best_partner['synapse_strength']:.2f})"
        )
    else:
        print("  [INFO] No suitable partner found yet")

    # Phase 4: Swarm Formation
    print("\n" + "=" * 70)
    print("  PHASE 4: SWARM FORMATION - DYNAMIC TEAM CREATION")
    print("=" * 70)

    # Available agents with capabilities
    available_agents = [
        "agent_conservator_anna",
        "agent_technician_bob",
        "agent_chemist_chen",
        "agent_historian_david",
        "agent_photographer_eve",
    ]

    agent_capabilities = {
        "agent_conservator_anna": [
            "leadership",
            "conservation",
            "decision_making",
            "assessment",
        ],
        "agent_technician_bob": ["restoration", "cleaning", "repair", "hands_on"],
        "agent_chemist_chen": [
            "analysis",
            "materials_science",
            "dating",
            "authentication",
        ],
        "agent_historian_david": [
            "research",
            "provenance",
            "historical_context",
            "documentation",
        ],
        "agent_photographer_eve": [
            "imaging",
            "documentation",
            "condition_reporting",
            "multimedia",
        ],
    }

    # Form swarm for manuscript restoration
    required_capabilities = ["leadership", "conservation", "analysis", "documentation"]

    swarm = await swarm_orchestrator.form_swarm(
        mission="Restore 15th Century Lotus Sutra Manuscript",
        required_capabilities=required_capabilities,
        available_agents=available_agents,
        agent_capabilities=agent_capabilities,
        min_size=3,
        max_size=5,
    )

    print(f"\n  [SWARM FORMED] ID: {swarm.id}")
    print(f"  [MISSION] {swarm.mission}")
    print(f"  [MEMBERS] {len(swarm.members)} agents assigned:")

    for agent_id, member in swarm.members.items():
        print(f"    - {agent_id} -> {member.role.value}")

    audit_logger.log(
        AuditEventType.SWARM_FORMED,
        "swarm_orchestrator",
        "formed_swarm",
        f"swarm://{swarm.id}",
        {"mission": swarm.mission, "members": len(swarm.members)},
    )

    # Activate swarm
    await swarm_orchestrator.activate_swarm(swarm.id)
    print("  [STATUS] Swarm activated")

    # Phase 5: LLM Execution with Dual Providers
    print("\n" + "=" * 70)
    print("  PHASE 5: DUAL LLM EXECUTION - DeepSeek + Gemini")
    print("=" * 70)

    # Initialize dual LLM adapter
    llm_adapter = DualLLMAdapter(swarm_orchestrator, default_provider="deepseek")
    llm_adapter.set_logger(audit_logger)

    # Register agents with preferred providers
    for agent_id, member in swarm.members.items():
        # Distribute between providers for demo
        provider = "deepseek" if len(llm_adapter.agent_configs) % 2 == 0 else "gemini"
        await llm_adapter.register_agent(
            agent_id=agent_id,
            role=member.role,
            specialization="manuscript restoration",
            preferred_provider=provider,
        )
        print(f"  [REGISTERED] {agent_id} -> {member.role.value} (provider: {provider})")

    # Create and execute tasks
    tasks = [
        TaskData(
            id="task_assessment_001",
            title="Assess Manuscript Condition",
            description="Analyze the 15th Century Lotus Sutra manuscript and assess its current condition, identifying areas of damage and deterioration.",
            type="condition_assessment",
            priority=1,
            metadata={"manuscript_age": "15th century", "type": "religious_text"},
        ),
        TaskData(
            id="task_strategy_002",
            title="Develop Restoration Strategy",
            description="Based on the condition assessment, develop a comprehensive restoration strategy that prioritizes tasks and allocates resources effectively.",
            type="strategy_development",
            priority=1,
            metadata={"budget": "moderate", "timeline": "3 months"},
        ),
        TaskData(
            id="task_execution_003",
            title="Create Restoration Plan",
            description="Create a detailed, step-by-step restoration plan including specific techniques, materials, and safety protocols for the manuscript restoration.",
            type="execution_planning",
            priority=2,
            metadata={"material": "rice_paper", "ink_type": "iron_gall"},
        ),
    ]

    execution_results = []

    for task in tasks:
        print(f"\n  [TASK] {task.title}")
        print(f"  [TYPE] {task.type}")

        # Find appropriate agent for task
        if "assessment" in task.type:
            agent_id = next(
                (aid for aid, m in swarm.members.items() if m.role == SwarmRole.LEADER),
                list(swarm.members.keys())[0],
            )
        elif "strategy" in task.type:
            agent_id = next(
                (aid for aid, m in swarm.members.items() if m.role == SwarmRole.STRATEGIST),
                list(swarm.members.keys())[0],
            )
        else:
            agent_id = next(
                (aid for aid, m in swarm.members.items() if m.role == SwarmRole.EXECUTOR),
                list(swarm.members.keys())[0],
            )

        # Get context from collective memory
        memory_context = {}
        if "water" in task.description.lower() or "damage" in task.description.lower():
            memory_results = await collective_memory.query_relevant(
                task_type="water_damage_restoration",
                context={"manuscript_type": "historical"},
                limit=1,
            )
            if memory_results:
                content = (
                    memory_results[0].content
                    if hasattr(memory_results[0], "content")
                    else memory_results[0].get("content", {})
                )
                memory_context["relevant_historical_protocols"] = (
                    content.get("guideline", "") if isinstance(content, dict) else str(content)
                )

        # Execute with LLM
        result = await llm_adapter.execute_task(agent_id, task, memory_context)
        execution_results.append(result)

        if result.success:
            output = result.result_data.get("detailed_output", "")[:150]
            provider = result.result_data.get("provider", "unknown")
            print(f"  [RESULT] {output}...")
            print(f"  [PROVIDER] {provider}")
        else:
            print(f"  [ERROR] {result.error}")

    # Phase 6: Completion & Summary
    print("\n" + "=" * 70)
    print("  PHASE 6: DEMO COMPLETION")
    print("=" * 70)

    duration = time.time() - start_time

    successful_executions = [r for r in execution_results if r.success]

    print("\n  [SUMMARY]")
    print(f"    Total duration: {duration:.2f} seconds")
    print(f"    LLM tasks: {len(execution_results)}")
    print(f"    Successful: {len(successful_executions)}")
    print(f"    Failed: {len(execution_results) - len(successful_executions)}")

    # Provider usage stats
    provider_usage = {}
    for r in successful_executions:
        provider = r.result_data.get("provider", "unknown")
        provider_usage[provider] = provider_usage.get(provider, 0) + 1

    print("\n  [PROVIDER USAGE]")
    for provider, count in provider_usage.items():
        print(f"    - {provider}: {count} tasks")

    # Export audit trail
    audit_data = audit_logger.export()
    audit_file = f"als_dual_llm_audit_{demo_id}.json"
    with open(audit_file, "w") as f:
        json.dump(audit_data, f, indent=2)

    print(f"\n  [AUDIT] {audit_data['event_count']} events logged")
    print(f"  [FILE] {audit_file}")

    audit_logger.log(
        AuditEventType.SCENARIO_COMPLETED,
        "system",
        "demo_completed",
        f"demo://{demo_id}",
        {
            "duration": duration,
            "tasks_executed": len(execution_results),
            "providers_used": list(provider_usage.keys()),
        },
    )

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE!")
    print("=" * 70)

    return {
        "demo_id": demo_id,
        "duration": duration,
        "tasks": len(execution_results),
        "successful": len(successful_executions),
        "providers": provider_usage,
        "audit_events": audit_data["event_count"],
    }


if __name__ == "__main__":
    try:
        result = asyncio.run(run_full_als_demo())
        print(f"\nFinal Result: {result}")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nDemo failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

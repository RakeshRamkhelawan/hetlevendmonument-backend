"""
ALS + Gemini LLM Integration Live Demonstratie

Dit script demonstreert het volledige ALS systeem met GEMINI integratie:
- Collective Memory
- Synapse Network
- Swarm Orchestrator
- LLM Agent Adapter (GEMINI)

Met echte Gemini LLM calls voor task execution!
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.path.insert(0, "c:\\Users\\rsram\\OneDrive\\Documenten\\GitHub\\SanskritiSetu.org")


# Load .env manually
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value


load_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("als_llm_gemini_demo.log", encoding="utf-8", mode="w"),
    ],
)

logger = logging.getLogger("ALS.GEMINI.DEMO")


class GDPRCompliantLogger:
    """GDPR-compliant audit logger."""

    def __init__(self, tenant_id: int, demo_id: str):
        self.tenant_id = tenant_id
        self.demo_id = demo_id
        self.audit_trail: List[Dict] = []
        self.start_time = datetime.now(timezone.utc)

    def _hash_sensitive(self, data: str) -> str:
        return hashlib.sha256(f"{data}:{self.demo_id}".encode()).hexdigest()[:16]

    def log(
        self,
        action: str,
        component: str,
        actor: str,
        resource_type: str,
        resource_id: str,
        details: Dict[str, Any],
        success: bool = True,
    ) -> Dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "demo_id": self.demo_id,
            "tenant_id": self.tenant_id,
            "action": action,
            "component": component,
            "actor": self._hash_sensitive(actor),
            "resource_type": resource_type,
            "resource_id": resource_id,
            "success": success,
            "details": {
                k: v
                for k, v in details.items()
                if k
                in [
                    "insight_type",
                    "confidence",
                    "capability",
                    "synapse_strength",
                    "swarm_size",
                    "task_type",
                    "coverage_ratio",
                    "llm_provider",
                    "llm_model",
                ]
            },
            "session_id": self.demo_id,
        }
        self.audit_trail.append(entry)
        status_icon = "[OK]" if success else "[FAIL]"
        logger.info(
            f"[{status_icon}] {component.upper():12} | {action:35} | actor={entry['actor'][:8]}..."
        )
        return entry

    def export(self) -> Dict:
        return {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "demo_id": self.demo_id,
            "tenant_id": self.tenant_id,
            "total_events": len(self.audit_trail),
            "duration_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            "gdpr_compliance": {"data_minimization": True, "pseudonymization": True},
            "events": self.audit_trail,
        }


async def main():
    print(
        """
================================================================================

           ALS + GEMINI LLM INTEGRATIE - LIVE DEMONSTRATIE

   Componenten:
   * Collective Memory    - Gedeelde kennis opslag
   * Synapse Network      - Agent samenwerkings netwerk
   * Swarm Orchestrator   - Dynamische team formatie
   * LLM Agent Adapter    - GEMINI (Google) integratie

   Scenario: AI-gestuurde nood-restauratie van een manuscript

================================================================================
    """
    )

    tenant_id = 999
    demo_id = f"gemini_demo_{uuid.uuid4().hex[:8]}"
    audit = GDPRCompliantLogger(tenant_id, demo_id)

    logger.info("=" * 70)
    logger.info(f"ALS+GEMINI DEMO STARTED - {demo_id}")
    logger.info("=" * 70)

    # Phase 1: Initialize components
    logger.info("\n" + "=" * 70)
    logger.info("FASE 1: COMPONENT INITIALISATIE")
    logger.info("=" * 70)

    from src.core.als.llm_integration import LLMAgentAdapter
    from src.core.als.swarm import SwarmOrchestrator, SwarmRole
    from src.core.als.synapse import SynapseNetwork

    swarm_orchestrator = SwarmOrchestrator(tenant_id)
    synapse_network = SynapseNetwork(tenant_id)

    # Initialize LLM adapter with GEMINI
    try:
        llm_adapter = LLMAgentAdapter(
            swarm_orchestrator=swarm_orchestrator,
            provider_name="gemini",  # <-- Using Gemini!
        )
        logger.info(f"[OK] LLM Adapter initialized with Gemini ({llm_adapter.provider.model})")
        audit.log(
            "llm_adapter_initialized",
            "llm",
            "system",
            "service",
            "llm_adapter",
            {"llm_provider": "gemini", "llm_model": llm_adapter.provider.model},
        )
    except Exception as e:
        logger.error(f"[FAIL] Failed to initialize LLM adapter: {e}")
        return

    # Phase 2: Set up Collective Memory
    logger.info("\n" + "=" * 70)
    logger.info("FASE 2: COLLECTIVE MEMORY - KENNIS OPSLAG")
    logger.info("=" * 70)

    from src.core.als.collective import CollectiveMemory

    collective_memory = CollectiveMemory(tenant_id)

    # Store restoration insights
    insights = [
        (
            "conservator_01",
            "lesson",
            "manuscript_restoration",
            {
                "technique": "controlled_dehydration",
                "critical_factor": "gradual_humidity_reduction",
                "success_rate": 0.94,
            },
            0.87,
        ),
        (
            "microbiologist_01",
            "pattern",
            "mold_treatment",
            {
                "fungicide": "thymol_solution",
                "application": "gentle_swab",
                "drying_hours": 48,
            },
            0.91,
        ),
    ]

    from src.core.als.collective.collective_memory import InsightType

    for agent, itype, context, content, conf in insights:
        try:
            insight = await collective_memory.store_insight(
                agent_id=agent,
                insight_type=InsightType(itype),
                context=context,
                content=content,
                confidence=conf,
            )
            audit.log(
                "insight_stored",
                "collective",
                agent,
                "insight",
                insight.id,
                {"insight_type": itype, "confidence": conf},
            )
            logger.info(f"[OK] Stored insight: {itype} from {agent}")
        except Exception as e:
            logger.warning(f"Insight storage failed (expected without DB): {e}")

    # Phase 3: Synapse Network
    logger.info("\n" + "=" * 70)
    logger.info("FASE 3: SYNAPSE NETWORK - SAMENWERKING OPZETTEN")
    logger.info("=" * 70)

    collaborations = [
        ("conservator_01", "chemist_01", 0.95, "chemical_analysis"),
        ("conservator_01", "microbiologist_01", 0.88, "mold_assessment"),
    ]

    for a, b, score, task in collaborations:
        await synapse_network.record_collaboration(a, b, task, True, quality_score=score)
        audit.log(
            "collaboration_recorded",
            "synapse",
            a,
            "synapse",
            f"{a}:{b}",
            {"synapse_strength": score, "task_type": task},
        )
        logger.info(f"[OK] Recorded collaboration: {a} <-> {b} (score: {score})")

    # Phase 4: Swarm Formation with LLM
    logger.info("\n" + "=" * 70)
    logger.info("FASE 4: SWARM FORMATIE - AI TEAM SAMENSTELLEN")
    logger.info("=" * 70)

    from src.core.shared.interfaces import TaskData

    emergency_task = TaskData(
        id="emergency_001",
        title="Nood-restauratie Lotus Sutra manuscript",
        description="15e-eeuws manuscript met waterschade en schimmel",
        tags=["emergency", "manuscript", "water_damage"],
    )

    # Form swarm
    swarm = await swarm_orchestrator.form_swarm(
        mission=emergency_task.title,
        required_capabilities=["restoration", "chemistry", "microbiology"],
        available_agents=["conservator_01", "chemist_01", "microbiologist_01"],
        agent_capabilities={
            "conservator_01": ["restoration", "leadership"],
            "chemist_01": ["chemistry", "analysis"],
            "microbiologist_01": ["microbiology", "mold_treatment"],
        },
        min_size=2,
        max_size=3,
    )

    if not swarm:
        logger.error("[FAIL] Swarm formation failed")
        return

    logger.info(f"[OK] Swarm formed: {swarm.swarm_id} with {swarm.size} agents")
    audit.log(
        "swarm_formed",
        "swarm",
        "system",
        "swarm",
        swarm.swarm_id,
        {"swarm_size": swarm.size},
    )

    # Register agents with LLM
    for agent_id, member in swarm.members.items():
        await llm_adapter.register_agent(
            agent_id=agent_id,
            role=member.role,
            specialization=member.capabilities[0] if member.capabilities else None,
        )
        logger.info(f"[OK] Registered {agent_id} with Gemini LLM ({member.role.value})")

    await swarm_orchestrator.activate_swarm(swarm.swarm_id)
    logger.info("[OK] Swarm activated")

    # Phase 5: LLM Task Execution with GEMINI
    logger.info("\n" + "=" * 70)
    logger.info("FASE 5: GEMINI LLM TASK EXECUTIE - AI VOERT TAKEN UIT")
    logger.info("=" * 70)

    # Create tasks
    tasks = [
        TaskData(
            id="task_analysis",
            title="Analyze manuscript damage",
            description="Analyze the extent of water and mold damage to the Lotus Sutra manuscript. Identify affected areas and severity.",
            tags=["analysis", "assessment"],
        ),
        TaskData(
            id="task_treatment_plan",
            title="Create restoration plan",
            description="Based on the damage analysis, create a detailed restoration plan including chemical treatments and mold remediation steps.",
            tags=["planning", "chemistry"],
        ),
    ]

    # Execute tasks with GEMINI
    for task in tasks:
        logger.info(f"\n--- Executing: {task.title} ---")

        # Assign to leader
        leader_id = swarm.leader.agent_id
        swarm.assign_task(task.id, leader_id)

        # Execute with Gemini LLM
        logger.info(f"Calling Gemini LLM ({llm_adapter.provider.model}) for {leader_id}...")
        try:
            result = await llm_adapter.execute_task(
                agent_id=leader_id,
                task=task,
                context={
                    "artifact": "15th century Lotus Sutra manuscript",
                    "damage": "water and mold",
                    "urgency": "high",
                },
            )

            if result.success:
                logger.info("[OK] Gemini task completed successfully!")
                output = result.result_data.get(
                    "detailed_output", result.result_data.get("summary", "No output")
                )
                logger.info(f"Output preview: {output[:200]}...")
                audit.log(
                    "llm_task_completed",
                    "llm",
                    leader_id,
                    "task",
                    task.id,
                    {
                        "success": True,
                        "task_type": task.title[:30],
                        "llm_model": llm_adapter.provider.model,
                    },
                )
            else:
                logger.error(f"[FAIL] Gemini task failed: {result.error_message}")
                audit.log(
                    "llm_task_failed",
                    "llm",
                    leader_id,
                    "task",
                    task.id,
                    {"success": False},
                    success=False,
                )

            await swarm_orchestrator.complete_task(swarm.swarm_id, task.id, result.success)

        except Exception as e:
            logger.error(f"[FAIL] Gemini execution error: {e}")
            audit.log(
                "llm_execution_error",
                "llm",
                leader_id,
                "task",
                task.id,
                {"error": str(e)},
                success=False,
            )

    # Phase 6: Complete
    logger.info("\n" + "=" * 70)
    logger.info("FASE 6: VOLTOOIING")
    logger.info("=" * 70)

    from src.core.shared.interfaces import ExecutionResult

    final_result = ExecutionResult(
        task_id="emergency_001",
        success=True,
        result_data={
            "status": "mission_completed",
            "agents_used": list(swarm.members.keys()),
            "llm_provider": "gemini",
            "llm_model": llm_adapter.provider.model,
            "tasks_completed": len(tasks),
        },
    )

    await swarm_orchestrator.complete_swarm(swarm.swarm_id, final_result)
    audit.log(
        "swarm_completed",
        "swarm",
        "system",
        "swarm",
        swarm.swarm_id,
        {
            "success": True,
            "tasks_completed": len(tasks),
            "llm_model": llm_adapter.provider.model,
        },
    )

    logger.info("[OK] Swarm mission completed with Gemini AI assistance!")
    logger.info(f"[INFO] LLM Model used: {llm_adapter.provider.model}")

    # Export audit
    report = audit.export()
    report_file = f"als_gemini_audit_{demo_id}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("=" * 70)
    logger.info("GEMINI DEMO VOLTOOID")
    logger.info("=" * 70)
    logger.info(f"Total events: {report['total_events']}")
    logger.info(f"Duration: {report['duration_seconds']:.2f} seconds")
    logger.info(f"Audit file: {report_file}")
    logger.info("=" * 70)

    print("\n" + "=" * 70)
    print("ALS + GEMINI DEMO COMPLETED")
    print("=" * 70)
    print(f"Demo ID: {demo_id}")
    print(f"Total events: {report['total_events']}")
    print(f"Duration: {report['duration_seconds']:.2f} seconds")
    print("LLM Provider: Gemini (Google)")
    print(f"LLM Model: {llm_adapter.provider.model}")
    print(f"Audit file: {report_file}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

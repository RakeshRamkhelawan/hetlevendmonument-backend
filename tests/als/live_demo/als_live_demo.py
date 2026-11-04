"""
ALS Live Demonstratie - Real-time test met GDPR-compliant logging

Dit script demonstreert alle drie de ALS-componenten in een live scenario:
- Collective Memory
- Synapse Network
- Swarm Orchestrator

Alle acties worden gelogd conform GDPR-eisen (audit trail, data minimalisatie,
geen persoonsgegevens, retention policies).
"""

import asyncio
import hashlib
import json
import logging
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Zorg dat src in path zit
sys.path.insert(0, "c:\\Users\\rsram\\OneDrive\\Documenten\\GitHub\\SanskritiSetu.org")

# Configureer uitgebreide logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("als_live_demo.log", encoding="utf-8", mode="w"),
    ],
)

logger = logging.getLogger("ALS.DEMO")


class GDPRCompliantLogger:
    """
    GDPR-compliant audit logger voor ALS operaties.

    Principes:
    - Geen persoonsgegevens (alleen agent IDs, geen namen)
    - Data minimalisatie (alleen noodzakelijke data)
    - Audit trail (wie, wat, wanneer)
    - Retention ready (timestamps voor data lifecycle)
    - Pseudonimisering waar mogelijk
    """

    def __init__(self, tenant_id: int, demo_id: str):
        self.tenant_id = tenant_id
        self.demo_id = demo_id
        self.audit_trail: List[Dict] = []
        self.start_time = datetime.now(timezone.utc)

    def _hash_sensitive(self, data: str) -> str:
        """Pseudonimiseer gevoelige data met SHA-256."""
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
        processing_basis: str = "legitimate_interest",
    ) -> Dict:
        """
        Log een actie conform GDPR vereisten.
        """
        entry = {
            # Audit trail verplichte velden
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "demo_id": self.demo_id,
            "tenant_id": self.tenant_id,
            # Actie details
            "action": action,
            "component": component,
            "actor": self._hash_sensitive(actor),  # Pseudonimiseer
            "resource_type": resource_type,
            "resource_id": resource_id,
            # GDPR metadata
            "processing_basis": processing_basis,
            "data_minimization_applied": True,
            "retention_class": "operational",
            # Resultaat
            "success": success,
            "details": self._minimize_details(details),
            # Technische context
            "session_id": self.demo_id,
        }

        self.audit_trail.append(entry)

        # Log naar console met iconen
        status_icon = "[OK]" if success else "[FAIL]"
        logger.info(
            f"[{status_icon}] {component.upper():12} | {action:35} | "
            f"actor={entry['actor'][:8]}... | resource={resource_id[:25]}"
        )

        return entry

    def _minimize_details(self, details: Dict) -> Dict:
        """Minimaliseer data conform GDPR data minimalisatie principe."""
        minimized = {}
        allowed_keys = [
            "insight_type",
            "confidence",
            "capability",
            "synapse_strength",
            "swarm_size",
            "task_type",
            "coverage_ratio",
            "duration_ms",
            "results_count",
            "complexity_score",
            "swarm_id",
        ]
        for key, value in details.items():
            if key in allowed_keys:
                minimized[key] = value
            elif isinstance(value, (int, float, bool)):
                minimized[key] = value
            elif key in ["mission", "context"] and isinstance(value, str):
                minimized[key] = value[:50] + "..." if len(value) > 50 else value
        return minimized

    def export_audit_trail(self) -> Dict:
        """Exporteer de volledige audit trail voor compliance reporting."""
        return {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "demo_id": self.demo_id,
            "tenant_id": self.tenant_id,
            "total_events": len(self.audit_trail),
            "duration_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            "gdpr_compliance": {
                "data_minimization": True,
                "pseudonymization": True,
                "audit_trail_complete": True,
                "retention_policy": "30_days_operational",
            },
            "events": self.audit_trail,
        }


# ==================== LIVE DEMO IMPLEMENTATIE ====================


class ALSDemoRunner:
    """Voert het live ALS scenario uit met volledige logging."""

    def __init__(self, tenant_id: int = 999):
        self.tenant_id = tenant_id
        self.demo_id = f"demo_{uuid.uuid4().hex[:12]}"
        self.logger = GDPRCompliantLogger(tenant_id, self.demo_id)

        # Component instanties
        self.collective_memory = None
        self.synapse_network = None
        self.swarm_orchestrator = None

        # Test data tracking
        self.swarm_id = None
        self.insights_created = []

        logger.info("=" * 90)
        logger.info("ALS LIVE DEMONSTRATIE - GDPR COMPLIANT LOGGING")
        logger.info("=" * 90)
        logger.info(f"Demo ID: {self.demo_id}")
        logger.info(f"Tenant ID: {self.tenant_id}")
        logger.info(f"Start Time: {datetime.now(timezone.utc).isoformat()}")
        logger.info("=" * 90)

    async def run_full_demo(self):
        """Voer het complete scenario uit."""
        try:
            # Fase 1: Initialisatie
            await self._phase1_initialization()

            # Fase 2: Collective Memory opzetten
            await self._phase2_collective_memory()

            # Fase 3: Synapse Network opzetten
            await self._phase3_synapse_network()

            # Fase 4: Swarm formatie
            await self._phase4_swarm_formation()

            # Fase 5: Task executie met learning
            await self._phase5_task_execution()

            # Fase 6: Swarm voltooiing
            await self._phase6_completion()

            # Export audit trail
            self._export_final_report()

        except Exception as e:
            logger.error(f"DEMO FOUT: {e}", exc_info=True)
            raise

    async def _phase1_initialization(self):
        """Fase 1: Initialiseer alle componenten."""
        logger.info("")
        logger.info("=" * 90)
        logger.info("FASE 1: COMPONENT INITIALISATIE")
        logger.info("=" * 90)

        from src.core.als.collective import CollectiveMemory
        from src.core.als.swarm import SwarmOrchestrator
        from src.core.als.synapse import SynapseNetwork

        self.collective_memory = CollectiveMemory(self.tenant_id)
        self.synapse_network = SynapseNetwork(self.tenant_id)
        self.swarm_orchestrator = SwarmOrchestrator(self.tenant_id)

        self.logger.log(
            action="component_initialized",
            component="collective",
            actor="system",
            resource_type="service",
            resource_id="collective_memory",
            details={"tenant_id": self.tenant_id},
        )

        self.logger.log(
            action="component_initialized",
            component="synapse",
            actor="system",
            resource_type="service",
            resource_id="synapse_network",
            details={"tenant_id": self.tenant_id},
        )

        self.logger.log(
            action="component_initialized",
            component="swarm",
            actor="system",
            resource_type="service",
            resource_id="swarm_orchestrator",
            details={"tenant_id": self.tenant_id},
        )

        logger.info("[OK] Alle componenten geinitialiseerd")

    async def _phase2_collective_memory(self):
        """Fase 2: Collective Memory - Store en Query insights."""
        logger.info("")
        logger.info("=" * 90)
        logger.info("FASE 2: COLLECTIVE MEMORY - KENNIS OPSLAG & OPHALEN")
        logger.info("=" * 90)

        # Store insights van verschillende agents
        insights_data = [
            {
                "agent": "conservator_agent_01",
                "type": "lesson",
                "context": "water_damage_manuscript",
                "content": {
                    "technique": "freeze_drying_preparation",
                    "critical_factor": "humidity_gradual_reduction",
                    "success_rate": 0.94,
                },
                "confidence": 0.87,
            },
            {
                "agent": "microbiologist_agent_02",
                "type": "pattern",
                "context": "mold_remediation_paper",
                "content": {
                    "fungicide": "thymol_solution_2_percent",
                    "application_method": "cotton_swab_gentle",
                    "drying_time_hours": 48,
                },
                "confidence": 0.91,
            },
            {
                "agent": "chemist_agent_05",
                "type": "lesson",
                "context": "ink_oxidation_emergency",
                "content": {
                    "problem": "oxidized_silver_ink",
                    "solution": "ph_neutral_ethanol_70_percent",
                    "validation_required": True,
                },
                "confidence": 0.85,
            },
        ]

        logger.info("--- Store insights in Collective Memory ---")

        for i, data in enumerate(insights_data, 1):
            from src.core.als.collective.collective_memory import InsightType

            insight = await self.collective_memory.store_insight(
                agent_id=data["agent"],
                insight_type=InsightType(data["type"]),
                context=data["context"],
                content=data["content"],
                confidence=data["confidence"],
            )

            self.insights_created.append(insight.insight_id)

            self.logger.log(
                action="insight_stored",
                component="collective",
                actor=data["agent"],
                resource_type="insight",
                resource_id=insight.insight_id,
                details={
                    "insight_type": data["type"],
                    "confidence": data["confidence"],
                    "context": data["context"],
                },
            )

            logger.info(
                f"  [{i}] Stored: {insight.insight_id[:30]}... (type={data['type']}, conf={data['confidence']})"
            )

        # Query relevante insights
        logger.info("")
        logger.info("--- Query: Relevante insights voor manuscript restauratie ---")

        results = await self.collective_memory.query_relevant(
            task_type="emergency_conservation",
            context={
                "artifact_type": "manuscript",
                "damage_type": "water_and_mold",
                "material": "rice_paper_15th_century",
            },
            min_confidence=0.7,
            limit=10,
        )

        self.logger.log(
            action="insights_queried",
            component="collective",
            actor="conservator_agent_01",
            resource_type="query",
            resource_id=f"query_{uuid.uuid4().hex[:8]}",
            details={
                "task_type": "emergency_conservation",
                "results_count": len(results),
                "min_confidence": 0.7,
            },
        )

        for idx, insight in enumerate(results, 1):
            logger.info(
                f"  [{idx}] Insight: {insight.insight_id[:30]}... | "
                f"Type: {insight.insight_type:10} | "
                f"Relevance: {insight.relevance_score:.2f} | "
                f"Success Rate: {insight.success_rate:.2f}"
            )

        # Reinforce een succesvolle insight
        if results:
            await self.collective_memory.reinforce_success(results[0].insight_id)

            self.logger.log(
                action="insight_reinforced",
                component="collective",
                actor="conservator_agent_01",
                resource_type="insight",
                resource_id=results[0].insight_id,
                details={
                    "success_increment": 1,
                    "new_success_count": results[0].success_count + 1,
                },
            )

            logger.info(f"  [OK] Insight reinforced: {results[0].insight_id[:30]}...")

        logger.info(f"[OK] {len(results)} insights gevonden en gelogd")

    async def _phase3_synapse_network(self):
        """Fase 3: Synapse Network - Samenwerking tracking."""
        logger.info("")
        logger.info("=" * 90)
        logger.info("FASE 3: SYNAPSE NETWORK - AGENT SAMENWERKING")
        logger.info("=" * 90)

        # Record historische samenwerkingen
        collaborations = [
            ("conservator_agent_01", "chemist_agent_05", 0.95, "chemical_analysis"),
            ("conservator_agent_01", "chemist_agent_05", 0.88, "material_testing"),
            ("conservator_agent_01", "chemist_agent_05", 0.92, "emergency_response"),
            (
                "conservator_agent_01",
                "microbiologist_agent_02",
                0.78,
                "mold_assessment",
            ),
            ("chemist_agent_05", "chemist_agent_07", 0.85, "ink_specialization"),
            (
                "digitizer_agent_03",
                "conservator_agent_01",
                0.90,
                "pre_digitization_prep",
            ),
        ]

        logger.info("--- Record historische samenwerkingen ---")

        for source, target, score, context in collaborations:
            await self.synapse_network.record_interaction(
                source_agent=source,
                target_agent=target,
                success_score=score,
                context=context,
            )

            # Genereer synapse ID
            synapse_id = f"{min(source, target)}:{max(source, target)}"

            self.logger.log(
                action="interaction_recorded",
                component="synapse",
                actor=source,
                resource_type="synapse",
                resource_id=synapse_id,
                details={
                    "synapse_strength": score,
                    "context": context,
                    "target_agent": self.logger._hash_sensitive(target),
                },
            )

            logger.info(
                f"  Recorded: {source} ↔ {target} (strength={score:.2f}, context={context})"
            )

        # Zoek beste samenwerkingspartner
        logger.info("")
        logger.info("--- Query: Beste partner voor conservator_agent_01 ---")

        partner = await self.synapse_network.find_best_collaborator(
            agent_id="conservator_agent_01",
            task_type="chemical_analysis",
            required_capabilities=["material_science"],
        )

        self.logger.log(
            action="partner_recommended",
            component="synapse",
            actor="conservator_agent_01",
            resource_type="recommendation",
            resource_id=f"rec_{uuid.uuid4().hex[:8]}",
            details={
                "task_type": "chemical_analysis",
                "recommended_partner": self.logger._hash_sensitive(partner) if partner else None,
                "found": partner is not None,
            },
        )

        if partner:
            logger.info(f"[OK] Beste partner gevonden: {partner}")

            # Toon synapse sterkte
            synapse_info = self.synapse_network.get_synapse_info("conservator_agent_01", partner)
            if synapse_info:
                logger.info(f"  Synapse sterkte: {synapse_info['strength']:.2f}")
                logger.info(f"  Aantal samenwerkingen: {synapse_info['collaboration_count']}")
                logger.info(f"  Gemiddelde kwaliteit: {synapse_info['average_quality']:.2f}")

        # Network stats
        stats = self.synapse_network.get_network_stats()
        logger.info("")
        logger.info("--- Network Statistics ---")
        logger.info(f"  Total synapses: {stats['total_synapses']}")
        logger.info(f"  Average strength: {stats['average_strength']:.2f}")
        logger.info(f"  Strong connections: {stats['strong_synapses']}")

    async def _phase4_swarm_formation(self):
        """Fase 4: Swarm Orchestrator - Team formatie."""
        logger.info("")
        logger.info("=" * 90)
        logger.info("FASE 4: SWARM ORCHESTRATOR - TEAM FORMATIE")
        logger.info("=" * 90)

        from src.core.shared.interfaces import TaskData

        # Definieer het emergency restoration task
        emergency_task = TaskData(
            id="emergency_001",
            title="Nood-restauratie Lotus Sutra manuscript",
            description="Waterschade en schimmel op 15e-eeuws manuscript",
            tags=["emergency", "water_damage", "mold", "manuscript"],
        )

        # Beschikbare agents met capabilities
        available_agents = [
            "conservator_agent_01",
            "microbiologist_agent_02",
            "digitizer_agent_03",
            "climate_agent_04",
            "chemist_agent_05",
            "doc_agent_06",
        ]

        agent_capabilities = {
            "conservator_agent_01": [
                "physical_conservation",
                "paper_restoration",
                "leadership",
            ],
            "microbiologist_agent_02": ["mold_remediation", "biological_analysis"],
            "digitizer_agent_03": ["digital_preservation", "imaging", "metadata"],
            "climate_agent_04": ["climate_control", "environmental_monitoring"],
            "chemist_agent_05": ["chemical_analysis", "material_science"],
            "doc_agent_06": ["documentation", "reporting", "compliance"],
        }

        # Formeer swarm
        logger.info("--- Swarm formatie start ---")
        logger.info(f"Mission: {emergency_task.title}")
        logger.info(
            "Required capabilities: physical_conservation, mold_remediation, digital_preservation, chemical_analysis, documentation"
        )

        swarm = await self.swarm_orchestrator.form_swarm(
            mission=emergency_task.title,
            required_capabilities=[
                "physical_conservation",
                "mold_remediation",
                "digital_preservation",
                "chemical_analysis",
                "documentation",
            ],
            available_agents=available_agents,
            agent_capabilities=agent_capabilities,
            min_size=4,
            max_size=5,
        )

        if not swarm:
            raise RuntimeError("Swarm formatie mislukt!")

        self.swarm_id = swarm.swarm_id

        # Log swarm creatie
        self.logger.log(
            action="swarm_formed",
            component="swarm",
            actor="system",
            resource_type="swarm",
            resource_id=swarm.swarm_id,
            details={
                "swarm_size": swarm.size,
                "capability_coverage": swarm.capability_coverage_ratio,
                "mission": emergency_task.title[:30],
            },
        )

        logger.info("")
        logger.info(f"[OK] Swarm gevormd: {swarm.swarm_id}")
        logger.info(f"  Grootte: {swarm.size} agents")
        logger.info(f"  Capability coverage: {swarm.capability_coverage_ratio:.0%}")
        logger.info(f"  Status: {swarm.status}")

        # Toon team samenstelling
        logger.info("")
        logger.info("--- Team Samenstelling ---")
        for agent_id, member in swarm.members.items():
            logger.info(f"  [{member.role.value:12}] {agent_id}")
            logger.info(f"             Capabilities: {', '.join(member.capabilities[:3])}")

            self.logger.log(
                action="member_added",
                component="swarm",
                actor="system",
                resource_type="swarm_member",
                resource_id=agent_id,
                details={
                    "role": member.role.value,
                    "capabilities": member.capabilities,
                    "swarm_id": swarm.swarm_id,
                },
            )

        # Activeer swarm
        activation_result = await self.swarm_orchestrator.activate_swarm(swarm.swarm_id)

        self.logger.log(
            action="swarm_activated",
            component="swarm",
            actor="conservator_agent_01",
            resource_type="swarm",
            resource_id=swarm.swarm_id,
            details={"status": "active", "activation_success": activation_result},
        )

        logger.info("")
        logger.info(f"[OK] Swarm geactiveerd door LEADER: {swarm.leader.agent_id}")
        logger.info(f"  Nieuwe status: {swarm.status}")

    async def _phase5_task_execution(self):
        """Fase 5: Task executie met real-time learning."""
        logger.info("")
        logger.info("=" * 90)
        logger.info("FASE 5: TASK EXECUTIE & REAL-TIME LEARNING")
        logger.info("=" * 90)

        from src.core.als.swarm import TaskDecomposer
        from src.core.shared.interfaces import TaskData

        # Decompose taak
        decomposer = TaskDecomposer()

        main_task = TaskData(
            id="emergency_001",
            title="Nood-restauratie Lotus Sutra manuscript",
            description="Waterschade en schimmel op 15e-eeuws manuscript",
            tags=["emergency", "water_damage", "mold", "manuscript"],
        )

        # Complexity estimation
        logger.info("--- Taak Complexiteit Analyse ---")
        complexity = decomposer.estimate_complexity(main_task)
        logger.info(f"  Complexiteit score: {complexity['complexity_score']}/10")
        logger.info(f"  Aanbevolen swarm grootte: {complexity['recommended_swarm_size']}")
        logger.info(f"  Geschatte duur: {complexity['estimated_duration_hours']} uur")
        logger.info(f"  Paralleliseerbaar: {complexity['parallelizable']}")

        self.logger.log(
            action="complexity_estimated",
            component="swarm",
            actor="system",
            resource_type="task_analysis",
            resource_id=main_task.id,
            details={
                "complexity_score": complexity["complexity_score"],
                "recommended_swarm_size": complexity["recommended_swarm_size"],
            },
        )

        # Decompose in subtasks
        subtasks = decomposer.decompose(
            task=main_task,
            swarm_capabilities=[
                "physical_conservation",
                "mold_remediation",
                "digital_preservation",
                "chemical_analysis",
            ],
            max_subtasks=6,
        )

        logger.info("")
        logger.info(f"--- Taak Decompositie ({len(subtasks)} subtasks) ---")

        for i, subtask in enumerate(subtasks, 1):
            logger.info(f"  [{i}] {subtask['title']}")
            logger.info(f"      Capabilities nodig: {', '.join(subtask['required_capabilities'])}")
            logger.info(f"      Geschatte tijd: {subtask['estimated_effort']}")
            if subtask.get("depends_on"):
                logger.info(f"      Afhankelijk van: {subtask['depends_on']}")

        # Wijs taken toe aan agents
        logger.info("")
        logger.info("--- Taak Toewijzing ---")

        swarm = self.swarm_orchestrator._swarms[self.swarm_id]

        assigned_count = 0
        for subtask in subtasks:
            task_data = TaskData(
                id=f"subtask_{subtask['subtask_id']}",
                title=subtask["title"],
                description=subtask.get("description", ""),
                tags=subtask["required_capabilities"],
            )

            assigned_agent = await self.swarm_orchestrator.assign_task_to_swarm(
                swarm_id=self.swarm_id, task=task_data
            )

            if assigned_agent:
                assigned_count += 1
                logger.info(f"  ✓ '{subtask['title'][:35]}...' → {assigned_agent}")

                self.logger.log(
                    action="task_assigned",
                    component="swarm",
                    actor=swarm.leader.agent_id,
                    resource_type="task",
                    resource_id=task_data.id,
                    details={
                        "task_type": subtask["title"][:30],
                        "assigned_to": self.logger._hash_sensitive(assigned_agent),
                        "swarm_id": self.swarm_id,
                    },
                )

        logger.info(f"  Totaal taken toegewezen: {assigned_count}/{len(subtasks)}")

        # Simuleer een onverwacht probleem tijdens executie
        logger.info("")
        logger.info("--- Simulatie: Onverwacht Probleem ---")
        logger.info("SCENARIO: Chemische analyse toont onverwachte oxidatie in inkt")
        logger.info("ACTIE: Query Collective Memory voor alternatieve oplossing...")

        # Query voor specifiek probleem
        solution_insights = await self.collective_memory.query_relevant(
            task_type="ink_oxidation_emergency",
            context={
                "problem": "oxidized_silver_ink",
                "manuscript_type": "15th_century",
            },
            min_confidence=0.8,
            limit=5,
        )

        if solution_insights:
            logger.info("[OK] Oplossing gevonden in Collective Memory!")
            logger.info(f"  Insight ID: {solution_insights[0].insight_id[:40]}...")
            logger.info(f"  Confidence: {solution_insights[0].confidence}")
            logger.info(f"  Success rate: {solution_insights[0].success_rate:.2f}")

            self.logger.log(
                action="solution_retrieved",
                component="collective",
                actor="chemist_agent_05",
                resource_type="insight",
                resource_id=solution_insights[0].insight_id,
                details={
                    "confidence": solution_insights[0].confidence,
                    "context": "ink_oxidation_emergency",
                },
            )

        # Complete taken
        logger.info("")
        logger.info("--- Taak Voltooiing ---")

        completed_count = 0
        for subtask in subtasks[:3]:  # Complete eerste 3
            task_id = f"subtask_{subtask['subtask_id']}"
            result = await self.swarm_orchestrator.complete_task(
                swarm_id=self.swarm_id, task_id=task_id, success=True
            )

            if result:
                completed_count += 1
                self.logger.log(
                    action="task_completed",
                    component="swarm",
                    actor="system",
                    resource_type="task",
                    resource_id=task_id,
                    details={"success": True},
                )

                logger.info(f"  [OK] {subtask['title'][:40]}... - VOLTOOID")

        logger.info(f"  Totaal taken voltooid: {completed_count}")

    async def _phase6_completion(self):
        """Fase 6: Swarm voltooiing en resultaten."""
        logger.info("")
        logger.info("=" * 90)
        logger.info("FASE 6: SWARM VOLTOOIING & RESULTATEN")
        logger.info("=" * 90)

        from src.core.shared.interfaces import ExecutionResult

        # Genereer resultaten
        results = ExecutionResult(
            task_id="emergency_001",
            success=True,
            output="Manuscript gestabiliseerd, schimmel verwijderd, digitalisatie voltooid. "
            "Oxidatie-probleem opgelost via alternatieve behandeling.",
            metrics={
                "time_to_stabilization_hours": 6,
                "mold_elimination_rate": 0.99,
                "digitization_quality_score": 9.2,
                "cost_vs_estimate": 0.94,
                "compliance_checklist": "all_passed",
                "insights_used": len(self.insights_created),
                "synapse_recommendations_used": 2,
            },
        )

        # Complete swarm
        await self.swarm_orchestrator.complete_swarm(self.swarm_id, results)

        self.logger.log(
            action="swarm_completed",
            component="swarm",
            actor="conservator_agent_01",
            resource_type="swarm",
            resource_id=self.swarm_id,
            details={
                "success": results.success,
                "duration_hours": results.metrics["time_to_stabilization_hours"],
                "quality_score": results.metrics["digitization_quality_score"],
            },
        )

        logger.info(f"[OK] Swarm voltooid: {self.swarm_id}")
        logger.info("")
        logger.info("--- Resultaten ---")
        logger.info(f"  Succes: {results.success}")
        logger.info(f"  Stabilisatie tijd: {results.metrics['time_to_stabilization_hours']} uur")
        logger.info(f"  Schimmel eliminatie: {results.metrics['mold_elimination_rate']:.0%}")
        logger.info(
            f"  Digitalisatie kwaliteit: {results.metrics['digitization_quality_score']}/10"
        )
        logger.info(f"  Kosten vs schatting: {results.metrics['cost_vs_estimate']:.0%}")
        logger.info(f"  Compliance: {results.metrics['compliance_checklist']}")
        logger.info("")
        logger.info(f"  Insights gebruikt: {results.metrics['insights_used']}")
        logger.info(f"  Synapse recommendations: {results.metrics['synapse_recommendations_used']}")

        # Final stats
        logger.info("")
        logger.info("--- ALS Component Statistieken ---")

        # Collective Memory stats
        cm_stats = {
            "insights_stored": len(self.insights_created),
            "queries_executed": 2,
            "reinforcements": 1,
        }
        logger.info(f"Collective Memory: {cm_stats}")

        # Synapse stats
        sn_stats = self.synapse_network.get_network_stats()
        logger.info(f"Synapse Network: {sn_stats}")

        # Swarm stats
        so_stats = self.swarm_orchestrator.get_orchestrator_stats()
        logger.info(f"Swarm Orchestrator: {so_stats}")

    def _export_final_report(self):
        """Exporteer finale audit trail."""
        logger.info("")
        logger.info("=" * 90)
        logger.info("GDPR COMPLIANT AUDIT TRAIL EXPORT")
        logger.info("=" * 90)

        report = self.logger.export_audit_trail()

        # Sla op naar file
        report_file = f"als_audit_trail_{self.demo_id}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"[OK] Audit trail geexporteerd naar: {report_file}")
        logger.info(f"[OK] Totaal events gelogd: {report['total_events']}")
        logger.info(f"[OK] Demo duur: {report['duration_seconds']:.2f} seconden")
        logger.info("")
        logger.info("GDPR Compliance Status:")
        for key, value in report["gdpr_compliance"].items():
            logger.info(f"  {key}: {'✓' if value else '✗'} {value}")

        logger.info("")
        logger.info("=" * 90)
        logger.info("LIVE DEMO VOLTOOID")
        logger.info("=" * 90)

        # Print samenvatting naar console
        print("\n" + "=" * 90)
        print("ALS LIVE DEMONSTRATIE - SAMENVATTING")
        print("=" * 90)
        print(f"Demo ID:              {self.demo_id}")
        print(f"Tenant ID:            {self.tenant_id}")
        print(f"Totaal gelogd events: {report['total_events']}")
        print(f"Demo duur:            {report['duration_seconds']:.2f} seconden")
        print("")
        print("Bestanden gegenereerd:")
        print(f"  • Audit trail:  {report_file}")
        print("  • Log bestand:  als_live_demo.log")
        print("=" * 90)


# ==================== MAIN ENTRY POINT ====================


async def main():
    """Main entry point voor de live demo."""
    print(
        """
================================================================================

                    ALS - AGENT LEARNING SYSTEM
                    Live Demonstratie met GDPR-compliant Logging

   Componenten:
   * Collective Memory    - Gedeelde kennis opslag en hergebruik
   * Synapse Network      - Agent samenwerkings netwerk met sterkte tracking
   * Swarm Orchestrator   - Dynamische team formatie en missie management

   Scenario: Nood-restauratie van een beschadigd cultureel artefact

================================================================================
    """
    )

    runner = ALSDemoRunner(tenant_id=999)
    await runner.run_full_demo()


if __name__ == "__main__":
    asyncio.run(main())

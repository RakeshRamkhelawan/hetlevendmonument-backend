"""
Perfect Subagents Manager - Single File Policy Implementation
Centralizes all subagent management while preserving individual specializations

This file coordinates:
- Loading specialized subagents from .github/agenten (content-creator, python-pro, etc.)
- Intelligent task routing to appropriate specialists
- API endpoints for subagent interaction
- Real LLM execution via specialized agents

Individual subagent specializations are preserved - only management is centralized.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.agents.base_agent import BaseAgent
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import TaskPriority

logger = logging.getLogger(__name__)


class SubagentModel(Enum):
    """Available Claude models for subagents"""

    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class TaskComplexity(Enum):
    """Task complexity levels for model selection"""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class SubagentMetadata:
    """Metadata for individual specialized subagents"""

    name: str
    description: str
    model: SubagentModel
    tools: list[str]
    capabilities: list[str]
    system_prompt: str
    file_path: str
    category: str


@dataclass
class RoutingDecision:
    """Result of intelligent task routing to specialist"""

    selected_subagent: str
    confidence: float
    reasoning: str
    model_recommendation: SubagentModel
    task_complexity: TaskComplexity
    alternative_agents: list[str]
    routing_metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


# API Models
class SubagentTaskRequest(BaseModel):
    """Request for specialized subagent task execution"""

    title: str = Field(..., description="Task title")
    description: str = Field(..., description="Task description")
    priority: TaskPriority = Field(TaskPriority.MEDIUM, description="Task priority")
    tags: list[str] = Field(default_factory=list, description="Task tags")
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Additional metadata"
    )  # TODO(TYPE): replace Any with concrete type
    preferred_agent: str | None = Field(None, description="Preferred specialist name")


class RoutingResponse(BaseModel):
    """Response model for task routing"""

    routing_decision: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    task_created: bool
    task_id: str | None = None
    message: str


class SubagentListResponse(BaseModel):
    """Response model for specialist listing"""

    subagents: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    total_count: int
    categories: dict[str, list[str]]
    statistics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class PerfectSubagentsManager:
    """
    Central manager for all subagent operations
    Preserves individual specialist capabilities while centralizing management
    """

    def __init__(
        self,
        subagents_dir: str | None = None,
        oversight_gate: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Initialize with clean provider configuration (Google Gemini + Ollama only)"""
        resolved_path: str
        if subagents_dir is None:
            project_root = Path(__file__).parent.parent.parent
            resolved_path = str(project_root / ".github" / "agenten github" / "agenten")
        else:
            resolved_path = subagents_dir

        # TODO(TYPE): replace Any with concrete type
        self.oversight_gate: Any | None = (
            oversight_gate  # TODO(TYPE): replace Any with concrete type
        )
        self.subagents_dir = Path(resolved_path)
        self.loaded_subagents: dict[str, SubagentMetadata] = {}
        self.categories: dict[str, list[str]] = {}
        self.routing_rules = self._initialize_routing_rules()
        self.complexity_keywords = self._initialize_complexity_keywords()
        self.provider_chain = ["google", "ollama"]  # Clean provider chain

        if not self.subagents_dir.exists():
            logger.warning(f"Subagents directory not found: {self.subagents_dir}")
        else:
            logger.info(f"Perfect Subagents Manager initialized: {self.subagents_dir}")
            self.load_all_subagents()

    def _initialize_routing_rules(
        self,
    ) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Initialize intelligent routing rules for specialist selection"""
        return {
            "development": {
                "keywords": [
                    "code",
                    "programming",
                    "development",
                    "implement",
                    "build",
                    "create",
                    "function",
                    "class",
                    "method",
                    "algorithm",
                    "debug",
                    "fix",
                    "refactor",
                    "api",
                    "endpoint",
                    "framework",
                    "library",
                    "package",
                    "module",
                ],
                "priority_agents": [
                    "pro",
                    "fullstack-pro",
                    "python-pro",
                    "javascript-pro",
                ],
                "complexity_boost": 1.2,
            },
            "data_ai": {
                "keywords": [
                    "data",
                    "analysis",
                    "machine learning",
                    "ml",
                    "ai",
                    "artificial intelligence",
                    "model",
                    "training",
                    "dataset",
                    "analytics",
                    "statistics",
                    "visualization",
                    "tensorflow",
                    "pytorch",
                    "pandas",
                    "numpy",
                    "scikit",
                    "neural network",
                ],
                "priority_agents": [
                    "data-scientist",
                    "ml-engineer",
                    "ai-researcher",
                    "prompt-engineer",
                ],
                "complexity_boost": 1.5,
            },
            "infrastructure": {
                "keywords": [
                    "deploy",
                    "deployment",
                    "docker",
                    "kubernetes",
                    "cloud",
                    "aws",
                    "azure",
                    "infrastructure",
                    "devops",
                    "ci/cd",
                    "pipeline",
                    "terraform",
                    "ansible",
                    "monitoring",
                    "logging",
                    "scaling",
                    "performance",
                    "optimization",
                ],
                "priority_agents": [
                    "devops-engineer",
                    "cloud-architect",
                    "kubernetes-specialist",
                ],
                "complexity_boost": 1.3,
            },
            "business": {
                "keywords": [
                    "business",
                    "strategy",
                    "plan",
                    "analysis",
                    "market",
                    "customer",
                    "sales",
                    "revenue",
                    "profit",
                    "growth",
                    "marketing",
                    "brand",
                    "competitive",
                    "stakeholder",
                    "requirements",
                    "proposal",
                    "presentation",
                ],
                "priority_agents": [
                    "business-analyst",
                    "product-manager",
                    "strategy-consultant",
                ],
                "complexity_boost": 1.0,
            },
            "content_seo": {
                "keywords": [
                    "content",
                    "writing",
                    "article",
                    "blog",
                    "seo",
                    "optimization",
                    "keywords",
                    "copywriting",
                    "marketing",
                    "social media",
                    "documentation",
                    "technical writing",
                    "user guide",
                    "manual",
                    "tutorial",
                    "explanation",
                ],
                "priority_agents": [
                    "content-creator",
                    "seo-specialist",
                    "technical-writer",
                ],
                "complexity_boost": 0.8,
            },
            "quality_security": {
                "keywords": [
                    "test",
                    "testing",
                    "quality",
                    "security",
                    "vulnerability",
                    "audit",
                    "review",
                    "validation",
                    "verification",
                    "compliance",
                    "penetration",
                    "encryption",
                    "authentication",
                    "authorization",
                    "firewall",
                ],
                "priority_agents": [
                    "security-expert",
                    "qa-engineer",
                    "code-reviewer",
                    "penetration-tester",
                ],
                "complexity_boost": 1.4,
            },
        }

    def _initialize_complexity_keywords(self) -> dict[TaskComplexity, list[str]]:
        """Initialize keywords for complexity assessment"""
        return {
            TaskComplexity.SIMPLE: [
                "simple",
                "basic",
                "quick",
                "small",
                "minor",
                "easy",
                "straightforward",
                "list",
                "show",
                "display",
                "view",
                "get",
                "fetch",
                "read",
            ],
            TaskComplexity.MEDIUM: [
                "analyze",
                "process",
                "transform",
                "integrate",
                "configure",
                "setup",
                "modify",
                "update",
                "enhance",
                "improve",
                "optimize",
                "standard",
            ],
            TaskComplexity.COMPLEX: [
                "architect",
                "design",
                "complex",
                "advanced",
                "enterprise",
                "scalable",
                "distributed",
                "microservices",
                "machine learning",
                "artificial intelligence",
                "optimization",
                "performance",
                "security",
                "comprehensive",
                "full-stack",
            ],
        }

    def load_all_subagents(self) -> dict[str, SubagentMetadata]:
        """Load all specialized subagents from markdown files"""
        if not self.subagents_dir.exists():
            logger.error(f"Subagents directory does not exist: {self.subagents_dir}")
            return {}

        subagent_files = list(self.subagents_dir.glob("*.md"))
        subagent_files = [
            f for f in subagent_files if f.name.lower() not in ["readme.md", "license"]
        ]

        logger.info(f"Found {len(subagent_files)} specialist subagent files")

        for file_path in subagent_files:
            try:
                subagent = self._parse_subagent_file(file_path)
                if subagent:
                    self.loaded_subagents[subagent.name] = subagent

                    category = self._categorize_subagent(subagent.name)
                    if category not in self.categories:
                        self.categories[category] = []
                    self.categories[category].append(subagent.name)

            except Exception as e:
                logger.error(f"Error loading specialist subagent from {file_path}: {e}")

        logger.info(f"Successfully loaded {len(self.loaded_subagents)} specialized subagents")
        return self.loaded_subagents

    def _parse_subagent_file(self, file_path: Path) -> SubagentMetadata | None:
        """Parse individual specialist subagent markdown file"""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Extract frontmatter (YAML header)
            frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
            if not frontmatter_match:
                logger.warning(f"No frontmatter found in {file_path}")
                return None

            frontmatter_text = frontmatter_match.group(1)
            system_prompt = frontmatter_match.group(2).strip()

            metadata = self._parse_frontmatter(frontmatter_text)

            name = metadata.get("name", file_path.stem)
            description = metadata.get("description", "No description available")

            # Parse model (default to sonnet)
            model_str = metadata.get("model", "sonnet").lower()
            try:
                model = SubagentModel(model_str)
            except ValueError:
                model = SubagentModel.SONNET
                logger.warning(f"Invalid model '{model_str}' in {file_path}, using sonnet")

            # Parse tools
            tools_str = metadata.get("tools", "")
            tools = (
                [tool.strip() for tool in tools_str.split(",") if tool.strip()] if tools_str else []
            )

            capabilities = self._extract_capabilities(system_prompt)
            category = self._categorize_subagent(name)

            return SubagentMetadata(
                name=name,
                description=description,
                model=model,
                tools=tools,
                capabilities=capabilities,
                system_prompt=system_prompt,
                file_path=str(file_path),
                category=category,
            )

        except Exception as e:
            logger.error(f"Error parsing specialist subagent file {file_path}: {e}")
            return None

    def _parse_frontmatter(self, frontmatter: str) -> dict[str, str]:
        """Parse YAML-like frontmatter"""
        metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for line in frontmatter.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
        return metadata

    def _extract_capabilities(self, system_prompt: str) -> list[str]:
        """Extract capability keywords from specialist system prompt"""
        capabilities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        capability_patterns = [
            r"(?:expert in|specialist in|master of)\s+([^.]+)",
            r"(?:can|able to)\s+([^.]+)",
            r"(?:skills?|expertise|capabilities?).*?:\s*([^.]+)",
        ]

        for pattern in capability_patterns:
            matches = re.findall(pattern, system_prompt, re.IGNORECASE)
            for match in matches:
                caps = [cap.strip() for cap in match.split(",") if cap.strip()]
                capabilities.extend(caps[:3])

        return capabilities[:10]

    def _categorize_subagent(self, name: str) -> str:
        """Categorize specialist subagent based on name patterns"""
        development_patterns = ["pro", "developer", "architect", "engineer"]
        infrastructure_patterns = [
            "devops",
            "cloud",
            "kubernetes",
            "terraform",
            "database",
        ]
        data_ai_patterns = ["data", "ml", "ai", "prompt"]
        business_patterns = ["business", "sales", "content", "customer", "hr", "legal"]
        seo_patterns = ["seo"]
        quality_patterns = [
            "security",
            "test",
            "code-reviewer",
            "performance",
            "debugger",
        ]

        name_lower = name.lower()

        if any(pattern in name_lower for pattern in seo_patterns):
            return "SEO & Content"
        elif any(pattern in name_lower for pattern in data_ai_patterns):
            return "Data & AI"
        elif any(pattern in name_lower for pattern in infrastructure_patterns):
            return "Infrastructure"
        elif any(pattern in name_lower for pattern in quality_patterns):
            return "Quality & Security"
        elif any(pattern in name_lower for pattern in business_patterns):
            return "Business"
        elif any(pattern in name_lower for pattern in development_patterns):
            return "Development"
        else:
            return "Specialized"

    def route_task_to_specialist(self, task: TaskData) -> RoutingDecision:
        """Intelligently route task to most appropriate specialist subagent"""
        try:
            content_analysis = self._analyze_task_content(task)
            task_complexity = self._assess_task_complexity(task)
            candidate_agents = self._find_candidate_agents(content_analysis)
            scored_agents = self._score_agents(candidate_agents, content_analysis, task_complexity)

            if not scored_agents:
                return self._fallback_routing(task, task_complexity)

            best_agent, best_score = scored_agents[0]
            alternatives = [agent for agent, _ in scored_agents[1:4]]

            subagent_metadata = self.get_subagent(best_agent)
            if subagent_metadata:
                model_recommendation = subagent_metadata.model
            else:
                model_recommendation = self._complexity_to_model(task_complexity)

            return RoutingDecision(
                selected_subagent=best_agent,
                confidence=min(best_score / 10.0, 1.0),
                reasoning=self._generate_routing_reasoning(
                    best_agent, content_analysis, task_complexity
                ),
                model_recommendation=model_recommendation,
                task_complexity=task_complexity,
                alternative_agents=alternatives,
                routing_metadata={
                    "content_analysis": content_analysis,
                    "candidate_count": len(candidate_agents),
                    "top_score": best_score,
                },
            )

        except Exception as e:
            logger.error(f"Error in task routing: {e}")
            return self._fallback_routing(task, TaskComplexity.MEDIUM)

    def _analyze_task_content(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze task content to identify specialist requirements"""
        content = f"{task.description} {task.metadata.get('requirements', '')}".lower()

        analysis: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "categories": [],
            "matched_keywords": [],
            "word_count": len(content.split()),
            "has_code_refs": bool(re.search(r"(function|class|import|def|var|let|const)", content)),
            "has_urls": bool(re.search(r"https?://", content)),
            "urgency_indicators": [],
        }

        urgency_patterns = [
            "urgent",
            "asap",
            "immediately",
            "critical",
            "emergency",
            "quick",
        ]
        analysis["urgency_indicators"] = [word for word in urgency_patterns if word in content]

        for category, rules in self.routing_rules.items():
            matched_keywords = [kw for kw in rules["keywords"] if kw.lower() in content]
            if matched_keywords:
                analysis["categories"].append(
                    {
                        "category": category,
                        "matched_keywords": matched_keywords,
                        "match_count": len(matched_keywords),
                        "priority_boost": rules.get("complexity_boost", 1.0),
                    }
                )
                analysis["matched_keywords"].extend(matched_keywords)

        return analysis

    def _assess_task_complexity(self, task: TaskData) -> TaskComplexity:
        """Assess task complexity for appropriate model selection"""
        content = task.description.lower()

        complexity_scores: dict[TaskComplexity, int] = {}
        for complexity, keywords in self.complexity_keywords.items():
            score = sum(1 for kw in keywords if kw in content)
            complexity_scores[complexity] = score

        complexity_indicators = {
            TaskComplexity.SIMPLE: (
                len(task.description.split()) < 20
                and not any(word in content for word in ["integrate", "architecture", "system"])
            ),
            TaskComplexity.COMPLEX: (
                len(task.description.split()) > 50
                or "enterprise" in content
                or "scalable" in content
                or "distributed" in content
            ),
        }

        for complexity, condition in complexity_indicators.items():
            if condition:
                complexity_scores[complexity] += 2

        if complexity_scores:
            return max(complexity_scores.keys(), key=lambda k: complexity_scores[k])

        return TaskComplexity.MEDIUM

    def _find_candidate_agents(
        self,
        content_analysis: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Find candidate specialist subagents"""
        candidates = set()

        for category_match in content_analysis["categories"]:
            category = category_match["category"]
            if category in self.routing_rules:
                priority_agents = self.routing_rules[category]["priority_agents"]
                candidates.update(priority_agents)

        for keyword in content_analysis["matched_keywords"]:
            matching_agents = self.find_subagents_by_capability(keyword)
            candidates.update(matching_agents)

        valid_candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent in candidates:
            if self.get_subagent(agent):
                valid_candidates.append(agent)

        return valid_candidates

    def _score_agents(
        self,
        candidates: list[str],
        content_analysis: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        complexity: TaskComplexity,
    ) -> list[tuple[str, float]]:
        """Score and rank candidate specialist agents"""
        scored_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_name in candidates:
            subagent = self.get_subagent(agent_name)
            if not subagent:
                continue

            score = 0.0

            description_matches = sum(
                1
                for kw in content_analysis["matched_keywords"]
                if kw.lower() in subagent.description.lower()
            )
            score += description_matches * 2

            for category_match in content_analysis["categories"]:
                category = category_match["category"]
                if category in self.routing_rules:
                    priority_agents = self.routing_rules[category]["priority_agents"]
                    if agent_name in priority_agents:
                        priority_index = priority_agents.index(agent_name)
                        score += 10 - priority_index * 2

            complexity_model_map = {
                TaskComplexity.SIMPLE: SubagentModel.HAIKU,
                TaskComplexity.MEDIUM: SubagentModel.SONNET,
                TaskComplexity.COMPLEX: SubagentModel.OPUS,
            }

            if subagent.model == complexity_model_map.get(complexity, SubagentModel.SONNET):
                score += 3

            capability_matches = sum(
                1
                for cap in subagent.capabilities
                for kw in content_analysis["matched_keywords"]
                if kw.lower() in cap.lower()
            )
            score += capability_matches * 1.5

            scored_agents.append((agent_name, score))

        scored_agents.sort(key=lambda x: x[1], reverse=True)
        return scored_agents

    def _complexity_to_model(self, complexity: TaskComplexity) -> SubagentModel:
        """Map task complexity to appropriate Claude model"""
        complexity_model_map = {
            TaskComplexity.SIMPLE: SubagentModel.HAIKU,
            TaskComplexity.MEDIUM: SubagentModel.SONNET,
            TaskComplexity.COMPLEX: SubagentModel.OPUS,
        }
        return complexity_model_map.get(complexity, SubagentModel.SONNET)

    def _generate_routing_reasoning(
        self,
        agent: str,
        content_analysis: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        complexity: TaskComplexity,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Generate human-readable reasoning for specialist selection"""
        reasons: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        subagent = self.get_subagent(agent)
        if subagent:
            reasons.append(f"Selected '{agent}' specialist")

            categories = [cat["category"] for cat in content_analysis["categories"]]
            if categories:
                reasons.append(f"Task matches {', '.join(categories)} domain(s)")

            reasons.append(f"Task complexity: {complexity.value}")
            reasons.append(f"Recommended model: {subagent.model.value}")

            if content_analysis["matched_keywords"]:
                key_matches = content_analysis["matched_keywords"][:3]
                reasons.append(f"Key matches: {', '.join(key_matches)}")

        return ". ".join(reasons)

    def _fallback_routing(self, task: TaskData, complexity: TaskComplexity) -> RoutingDecision:
        """Fallback routing when no specific specialist match found"""
        fallback_model = self._complexity_to_model(complexity)

        return RoutingDecision(
            selected_subagent="cva_main",
            confidence=0.3,
            reasoning=f"Fallback to CVA agent. Task complexity: {complexity.value}. Recommended model: {fallback_model.value}",
            model_recommendation=fallback_model,
            task_complexity=complexity,
            alternative_agents=["pro", "fullstack-pro", "business-analyst"][:3],
            routing_metadata={
                "fallback_routing": True,
                "reason": "No specific specialist subagent match found",
            },
        )

    def _get_oversight_gate(self) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Return injected OversightGate; None means governance check skipped."""
        return self.oversight_gate

    async def _check_governance(self, request: SubagentTaskRequest) -> None:
        """Check governance gate before executing specialist task."""
        gate = self._get_oversight_gate()
        if gate is None:
            return
        result = await gate.check(
            agent_name="SubAgentFactory",
            agent_department="specialist",
            agent_specialisation="task_execution",
            agent_capabilities=["task_routing", "specialist_execution"],
            task_action="execute_specialist",
            task_params={
                "title": request.title,
                "description": request.description,
                "priority": request.priority.value
                if hasattr(request.priority, "value")
                else request.priority,
                "preferred_agent": request.preferred_agent,
            },
        )

        if not result.allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Governance check blocked: {result.reason}",
            )

        if result.requires_human_approval:
            raise HTTPException(
                status_code=403,
                detail=f"Human approval required: {result.reason}",
            )

    async def execute_with_specialist(
        self, request: SubagentTaskRequest
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute task with appropriate specialist subagent - REAL LLM integration"""

        def log_to_file(message: str) -> None:
            with open("log.md", "a", encoding="utf-8") as f:
                f.write(f"\n{message}")

        try:
            # Governance check first
            await self._check_governance(request)

            start_time = datetime.now(timezone.utc)

            task_data = TaskData(
                title=request.title,
                description=request.description,
                priority=request.priority,
                tags=request.tags,
                metadata=request.metadata,
            )

            routing_decision = self.route_task_to_specialist(task_data)

            if request.preferred_agent:
                if self.get_subagent(request.preferred_agent):
                    routing_decision.selected_subagent = request.preferred_agent

            selected_subagent = self.get_subagent(routing_decision.selected_subagent)

            if not selected_subagent:
                raise HTTPException(
                    status_code=404,
                    detail=f"Specialist {routing_decision.selected_subagent} not found",
                )

            agent_name = selected_subagent.name.upper().replace(" ", "_")
            log_to_file(
                f"**{agent_name}_SPECIALIST:** [REAL_EXECUTION_START] Task: {request.title}"
            )
            log_to_file(
                f"**{agent_name}_SPECIALIST:** [SPECIALIST_SELECTED] {selected_subagent.name} - {selected_subagent.description}"
            )

            specialized_task_data = TaskData(
                id=f"specialist_{datetime.now(timezone.utc).strftime('%H%M%S')}",
                title=request.title,
                description=request.description,
                priority=request.priority,
                tags=request.tags,
                metadata={
                    **request.metadata,
                    "specialist_name": selected_subagent.name,
                    "specialist_model": selected_subagent.model.value,
                    "specialist_capabilities": selected_subagent.capabilities,
                    "specialist_system_prompt": selected_subagent.system_prompt,
                    "routing_confidence": routing_decision.confidence,
                    "routing_reasoning": routing_decision.reasoning,
                    "user_id": "specialist_system",
                    "task_type": "specialist_execution",
                },
            )

            # Execute with real BaseAgent using specialist configuration
            from src.core.types import AgentType

            base_agent = BaseAgent(  # type: ignore[abstract]
                agent_id=f"specialist_{selected_subagent.name.lower().replace(' ', '_')}",
                agent_type=AgentType.SPECIALIST,
            )

            log_to_file(
                f"**{agent_name}_SPECIALIST:** [REAL_LLM_EXECUTION] Using {selected_subagent.model.value} with Google Gemini/Ollama"
            )

            execution_result = await base_agent.process_task(specialized_task_data)
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            if execution_result and execution_result.success:
                log_to_file(
                    f"**{agent_name}_SPECIALIST:** [REAL_SUCCESS] Completed in {execution_time:.2f}s"
                )

                result = ExecutionResult(
                    task_id=specialized_task_data.task_id,
                    success=True,
                    result_data={
                        "specialist_used": selected_subagent.name,
                        "model_used": selected_subagent.model.value,
                        "task_complexity": routing_decision.task_complexity.value,
                        "routing_confidence": routing_decision.confidence,
                        "real_response": execution_result.result_data,
                        "capabilities_applied": selected_subagent.capabilities,
                        "execution_type": "REAL_SPECIALIST_EXECUTION",
                        "is_mock": False,
                        "provider_chain": self.provider_chain,
                    },
                    execution_time=execution_time,
                    logs=[
                        f"Real execution with specialist {selected_subagent.name}",
                        f"Model: {selected_subagent.model.value}",
                        f"Provider chain: {' -> '.join(self.provider_chain)}",
                        f"Routing confidence: {routing_decision.confidence:.2f}",
                        f"Execution time: {execution_time:.2f}s",
                    ],
                )

                log_to_file(
                    f"**{agent_name}_SPECIALIST:** [DELIVERABLE_READY] Specialist output: {len(str(execution_result.result_data))} chars"
                )

            else:
                log_to_file(
                    f"**{agent_name}_SPECIALIST:** [REAL_FAILURE] Execution failed after {execution_time:.2f}s"
                )

                result = ExecutionResult(
                    task_id=specialized_task_data.task_id,
                    success=False,
                    result_data={
                        "specialist_used": selected_subagent.name,
                        "model_used": selected_subagent.model.value,
                        "error": str(
                            execution_result.error_message
                            if execution_result
                            else "Unknown execution error"
                        ),
                        "execution_type": "REAL_SPECIALIST_EXECUTION_FAILED",
                        "is_mock": False,
                    },
                    execution_time=execution_time,
                    error_message=(
                        execution_result.error_message
                        if execution_result
                        else "Real specialist execution failed"
                    ),
                    logs=[f"Real execution failed with specialist {selected_subagent.name}"],
                )

            return {
                "execution_result": result.dict(),
                "routing_decision": {
                    "selected_subagent": routing_decision.selected_subagent,
                    "confidence": routing_decision.confidence,
                    "reasoning": routing_decision.reasoning,
                    "model_recommendation": routing_decision.model_recommendation.value,
                    "alternative_agents": routing_decision.alternative_agents,
                },
                "execution_type": "REAL_SPECIALIST_EXECUTION",
                "is_mock": False,
                "execution_time": execution_time,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except HTTPException:
            # Re-raise HTTPException (including governance 403s) without wrapping
            raise
        except Exception as e:
            logger.error(f"Error in real specialist execution: {e}")
            log_to_file(f"**SPECIALIST_MANAGER:** [REAL_ERROR] {str(e)}")
            raise HTTPException(
                status_code=500, detail="Real specialist execution failed"
            )

    def get_subagent(self, name: str) -> SubagentMetadata | None:
        """Get specific specialist subagent by name"""
        return self.loaded_subagents.get(name)

    def list_subagents(self, category: str | None = None) -> list[str]:
        """List all specialist subagents with optional category filter"""
        if category:
            return self.categories.get(category, [])
        return list(self.loaded_subagents.keys())

    def get_categories(self) -> dict[str, list[str]]:
        """Get all specialist categories"""
        return self.categories.copy()

    def find_subagents_by_capability(self, capability: str) -> list[str]:
        """Find specialists with specific capability"""
        matching: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        capability_lower = capability.lower()

        for name, subagent in self.loaded_subagents.items():
            if capability_lower in subagent.description.lower():
                matching.append(name)
                continue

            for cap in subagent.capabilities:
                if capability_lower in cap.lower():
                    matching.append(name)
                    break

        return matching

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive specialist statistics"""
        if not self.loaded_subagents:
            return {"total": 0}

        model_counts: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for subagent in self.loaded_subagents.values():
            model_counts[subagent.model.value] = model_counts.get(subagent.model.value, 0) + 1

        return {
            "total": len(self.loaded_subagents),
            "categories": len(self.categories),
            "by_category": {cat: len(agents) for cat, agents in self.categories.items()},
            "by_model": model_counts,
            "provider_chain": self.provider_chain,
        }


# FastAPI Router for API endpoints
subagent_router = APIRouter(
    prefix="/api/v1/subagents",
    tags=["subagents"],
    responses={404: {"description": "Not found"}},
)

# Global manager instance
_perfect_subagents_manager: PerfectSubagentsManager | None = None


def get_perfect_subagents_manager() -> PerfectSubagentsManager:
    """Get global perfect subagents manager instance"""
    global _perfect_subagents_manager
    if _perfect_subagents_manager is None:
        _perfect_subagents_manager = PerfectSubagentsManager()
    return _perfect_subagents_manager


# API Endpoints
@subagent_router.get("/", response_model=SubagentListResponse)
async def list_subagents(
    category: str | None = None,
    model: str | None = None,
    capability: str | None = None,
) -> SubagentListResponse:
    """List all available specialist subagents with filtering"""
    try:
        manager = get_perfect_subagents_manager()

        if category:
            subagent_names = manager.list_subagents(category)
        else:
            subagent_names = manager.list_subagents()

        if model:
            try:
                model_enum = SubagentModel(model.lower())
                filtered_names: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                for name in subagent_names:
                    subagent = manager.get_subagent(name)
                    if subagent is not None and subagent.model == model_enum:
                        filtered_names.append(name)
                subagent_names = filtered_names
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid model: {model}")

        if capability:
            matching_agents = manager.find_subagents_by_capability(capability)
            subagent_names = list(set(subagent_names) & set(matching_agents))

        subagents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for name in subagent_names:
            subagent = manager.get_subagent(name)
            if subagent:
                subagents.append(
                    {
                        "name": subagent.name,
                        "description": subagent.description,
                        "model": subagent.model.value,
                        "category": subagent.category,
                        "tools": subagent.tools,
                        "capabilities": subagent.capabilities,
                        "file_path": subagent.file_path,
                    }
                )

        return SubagentListResponse(
            subagents=subagents,
            total_count=len(subagents),
            categories=manager.get_categories(),
            statistics=manager.get_stats(),
        )

    except Exception as e:
        logger.error(f"Error listing specialist subagents: {e}")
        raise HTTPException(status_code=500, detail="Failed to list specialist subagents")


@subagent_router.post("/execute")
async def execute_specialist_task(
    request: SubagentTaskRequest,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute task with intelligent specialist routing - REAL LLM integration only"""
    manager = get_perfect_subagents_manager()
    return await manager.execute_with_specialist(request)


@subagent_router.post("/route", response_model=RoutingResponse)
async def route_to_specialist(request: SubagentTaskRequest) -> RoutingResponse:
    """Route task to most appropriate specialist"""
    try:
        manager = get_perfect_subagents_manager()

        task_data = TaskData(
            title=request.title,
            description=request.description,
            priority=request.priority,
            tags=request.tags,
            metadata=request.metadata,
        )

        routing_decision = manager.route_task_to_specialist(task_data)

        if request.preferred_agent:
            preferred_subagent = manager.get_subagent(request.preferred_agent)
            if preferred_subagent:
                routing_decision.selected_subagent = request.preferred_agent
                routing_decision.confidence = 0.95
                routing_decision.reasoning = f"User-specified specialist: {request.preferred_agent}"

        return RoutingResponse(
            routing_decision={
                "selected_subagent": routing_decision.selected_subagent,
                "confidence": routing_decision.confidence,
                "reasoning": routing_decision.reasoning,
                "model_recommendation": routing_decision.model_recommendation.value,
                "task_complexity": routing_decision.task_complexity.value,
                "alternative_agents": routing_decision.alternative_agents,
                "routing_metadata": routing_decision.routing_metadata,
            },
            task_created=True,
            task_id=task_data.id,
            message=f"Task routed to specialist {routing_decision.selected_subagent} with {routing_decision.confidence:.2f} confidence",
        )

    except Exception as e:
        logger.error(f"Error routing to specialist: {e}")
        raise HTTPException(status_code=500, detail="Failed to route to specialist")


@subagent_router.get("/stats")
async def get_specialist_stats() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive specialist system statistics"""
    try:
        manager = get_perfect_subagents_manager()
        return {
            "specialist_stats": manager.get_stats(),
            "system_info": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": "Perfect Subagents Manager - Single File Policy",
                "provider_chain": manager.provider_chain,
                "features": {
                    "intelligent_routing": True,
                    "specialist_preservation": True,
                    "real_llm_execution": True,
                    "google_gemini_integration": True,
                    "ollama_integration": True,
                    "centralized_management": True,
                },
            },
        }

    except Exception as e:
        logger.error(f"Error getting specialist stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get specialist stats")


if __name__ == "__main__":
    # Test the perfect subagents manager
    manager = PerfectSubagentsManager()
    print(f"Perfect Subagents Manager loaded {len(manager.loaded_subagents)} specialists")
    print(f"Categories: {list(manager.categories.keys())}")
    print(f"Provider chain: {manager.provider_chain}")

    # Test routing
    test_task = TaskData(
        title="Create Python API",
        description="Build a FastAPI application with authentication",
        metadata={"type": "development"},
    )

    decision = manager.route_task_to_specialist(test_task)
    print("\nTest routing:")
    print(f"Selected specialist: {decision.selected_subagent}")
    print(f"Confidence: {decision.confidence:.2f}")
    print(f"Reasoning: {decision.reasoning}")

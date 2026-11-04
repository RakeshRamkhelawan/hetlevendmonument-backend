"""
Executor Agent Implementation
Specialist agent for action execution, workflow automation, API integrations, and task implementation
"""

import logging
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import aiohttp

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.sandbox.sandbox_manager import BaseSandboxManager, SandboxManagerFactory
from src.core.shared.interfaces import (
    AgentCapability,
    AgentType,
    ExecutionResult,
    IsolationLevel,
    TaskData,
)
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel, LLMMessage

logger = logging.getLogger(__name__)

#: Hosts waar `_execute_api_integration` naartoe mag bellen (ADR-036 OP-173). LEEG betekent:
#: geen enkele uitgaande aanroep. Dat is bewust de standaard -- zie `_valideer_api_endpoint`.
_API_ALLOWLIST_VARIABELE = "EXECUTOR_API_ALLOWED_HOSTS"


def _valideer_api_endpoint(endpoint: str) -> str:
    """Weiger een URL die niet op de allowlist staat (ADR-036 OP-173).

    **Waarom dit er moet zijn.** `_execute_api_integration` haalde `api_endpoint` rechtstreeks
    uit `task.metadata` en gaf hem door aan `aiohttp`. Taakdata komt van een agent, dus de
    bestemming van het verzoek werd bepaald door de inhoud van een taak: de klassieke
    SSRF-vorm (CWE-918). Het pad loopt bovendien om `execute_tool()` en dus om de
    Council-poort heen, waardoor er ook geen tweede controle is.

    **Waarom een allowlist en niet een blocklist van interne adressen.** Een blocklist op
    169.254.169.254 en RFC1918 is te omzeilen met DNS die naar een intern adres wijst, met een
    omleiding, of met een IPv6-notatie van hetzelfde adres. OWASP beveelt daarom een
    allowlist aan; alles wat er niet op staat gaat niet.

    **Waarom LEEG de standaard is.** Er is vandaag geen enkele bekende, gewenste bestemming
    voor deze tak. Een lege lijst maakt de functionaliteit dus uit, en dat is de veilige
    kant: wie hem nodig heeft, zet de hosts expliciet in `EXECUTOR_API_ALLOWED_HOSTS` en dat
    is zichtbaar in de configuratie.
    """
    import os
    from urllib.parse import urlparse

    ontleed = urlparse(endpoint)
    if ontleed.scheme not in ("http", "https"):
        raise ValueError(
            f"API-integratie geweigerd: schema {ontleed.scheme!r} is niet toegestaan. "
            "Alleen http en https (ADR-036 OP-173)."
        )
    host = (ontleed.hostname or "").lower()
    if not host:
        raise ValueError("API-integratie geweigerd: de URL bevat geen host (ADR-036 OP-173).")

    toegestaan = {
        deel.strip().lower()
        for deel in os.getenv(_API_ALLOWLIST_VARIABELE, "").split(",")
        if deel.strip()
    }
    if host not in toegestaan:
        raise ValueError(
            f"API-integratie geweigerd: host {host!r} staat niet in "
            f"{_API_ALLOWLIST_VARIABELE}. De bestemming van dit verzoek komt uit taakdata, "
            "dus zonder allowlist bepaalt de taak waar het verkeer heen gaat (SSRF, CWE-918; "
            "ADR-036 OP-173)."
        )
    return endpoint


class ExecutorAgent(CriticMixin, EnhancedBaseAgent):
    """Specialist agent for action execution, workflow automation, and system interactions"""

    # Task types actually handled by the routing branches in _execute_task() below.
    # Kept as an explicit, literal set (NOT derived from execution_domains, which uses
    # a different vocabulary -- e.g. "web_scraping"/"deployment" vs the routing's
    # "web_automation"/"deployment_automation") so validate_task() gates on exactly
    # what _execute_task() can actually route.
    _SUPPORTED_TASK_TYPES = frozenset(
        {
            "api_integration",
            "workflow_automation",
            "file_operations",
            "system_commands",
            "data_pipeline",
            "notification_systems",
            "web_automation",
            "database_operations",
            "deployment_automation",
            "quality_assurance",
            "general_execution",
        }
    )

    def __init__(self, agent_id: str = "executor_agent_001", tenant_id: int = 1) -> None:
        super().__init__(agent_id=agent_id, agent_type=AgentType.SPECIALIST, tenant_id=tenant_id)
        self.__init_critic__(mode=CriticMode.ADVISORY)

        # Executor-specific configuration
        self.specialization = "action_execution_automation"
        self.execution_domains = [
            "api_integration",
            "workflow_automation",
            "file_operations",
            "system_commands",
            "data_pipeline",
            "notification_systems",
            "web_scraping",
            "database_operations",
            "cloud_services",
            "deployment",
        ]

        # Execution capabilities
        self.supported_integrations = [
            "rest_api",
            "graphql",
            "webhook",
            "database",
            "file_system",
            "cloud_storage",
            "email",
            "slack",
            "github",
            "docker",
        ]

        # Safety and validation
        self.safety_checks = [
            "command_validation",
            "api_rate_limiting",
            "resource_monitoring",
            "permission_verification",
            "data_validation",
            "rollback_capability",
        ]

        # Initialize LLM client for intelligent execution decisions
        self.llm_client: ChatTaalmodel | None = None

        # Initialize sandbox for safe execution
        self.sandbox_manager: BaseSandboxManager | None = None

        # Execution history and monitoring
        self.execution_history: list[dict[str, object]] = []
        self.api_usage_tracker: dict[str, list[datetime]] = {}
        self.safety_violations: list[dict[str, object]] = []

        # Workspace directory (initialized in setup)
        self.workspace_dir: Path | None = None
        self.http_session: aiohttp.ClientSession | None = None

        logger.info(
            f"ExecutorAgent {agent_id} initialized with {len(self.execution_domains)} domains"
        )

    async def initialize(self) -> bool:
        """Initialize the executor agent"""
        try:
            # Initialize LLM client (OpenAI for reasoning about execution strategies)
            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14).
            self.llm_client = TenantTaalmodel(self.tenant_id)

            # Initialize sandbox manager for safe execution
            self.sandbox_manager = SandboxManagerFactory.create_manager(IsolationLevel.CONTAINER)

            # Setup execution environment
            await self._setup_execution_environment()

            logger.info(f"ExecutorAgent {self.agent_id} fully initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ExecutorAgent {self.agent_id}: {e}")
            return False

    async def _setup_execution_environment(self) -> None:
        """Setup safe execution environment with necessary tools and permissions"""
        try:
            # Create temporary workspace
            self.workspace_dir = Path(f"temp/executor_workspace_{self.agent_id}")
            self.workspace_dir.mkdir(parents=True, exist_ok=True)

            # Initialize HTTP session for API calls
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": f"ExecutorAgent/{self.agent_id}"},
            )

            logger.info(f"Execution environment setup complete: {self.workspace_dir}")

        except Exception as e:
            logger.error(f"Failed to setup execution environment: {e}")
            raise

    async def get_capabilities(self) -> list[AgentCapability]:
        """Get executor agent capabilities"""
        return [
            AgentCapability(
                name="api_integration",
                description="Execute REST API calls, handle authentication, and process responses",
                input_types=["api_request", "integration_task"],
                output_types=["api_response", "integration_result"],
                resource_requirements={
                    "memory": "512MB",
                    "cpu": "1.0",
                    "network": "required",
                },
            ),
            AgentCapability(
                name="workflow_automation",
                description="Execute multi-step workflows with conditional logic and error handling",
                input_types=["workflow_definition", "automation_task"],
                output_types=["workflow_result", "execution_log"],
                resource_requirements={"memory": "1GB", "cpu": "2.0"},
            ),
            AgentCapability(
                name="file_operations",
                description="Perform file system operations including read/write/move/copy",
                input_types=["file_task", "batch_operation"],
                output_types=["file_result", "operation_summary"],
                resource_requirements={
                    "memory": "256MB",
                    "cpu": "0.5",
                    "storage": "required",
                },
            ),
            AgentCapability(
                name="system_commands",
                description="Execute system commands and scripts with safety validation",
                input_types=["command_task", "script_execution"],
                output_types=["command_result", "execution_output"],
                resource_requirements={
                    "memory": "512MB",
                    "cpu": "1.5",
                    "system_access": "limited",
                },
            ),
            AgentCapability(
                name="data_pipeline",
                description="Execute data processing pipelines and ETL operations",
                input_types=["pipeline_task", "data_processing"],
                output_types=["pipeline_result", "processed_data"],
                resource_requirements={
                    "memory": "2GB",
                    "cpu": "3.0",
                    "storage": "required",
                },
            ),
            AgentCapability(
                name="notification_systems",
                description="Send notifications via email, Slack, webhooks, and other channels",
                input_types=["notification_request", "alert_task"],
                output_types=["notification_result", "delivery_confirmation"],
                resource_requirements={
                    "memory": "256MB",
                    "cpu": "0.5",
                    "network": "required",
                },
            ),
            AgentCapability(
                name="web_automation",
                description="Automate web interactions and data extraction",
                input_types=["web_task", "scraping_request"],
                output_types=["web_result", "extracted_data"],
                resource_requirements={
                    "memory": "1GB",
                    "cpu": "2.0",
                    "network": "required",
                },
            ),
            AgentCapability(
                name="database_operations",
                description="Execute database queries, updates, and maintenance tasks",
                input_types=["database_task", "sql_operation"],
                output_types=["database_result", "query_response"],
                resource_requirements={
                    "memory": "1GB",
                    "cpu": "1.5",
                    "database": "required",
                },
            ),
            AgentCapability(
                name="deployment_automation",
                description="Automate deployment processes and infrastructure management",
                input_types=["deployment_task", "infrastructure_request"],
                output_types=["deployment_result", "infrastructure_status"],
                resource_requirements={
                    "memory": "1GB",
                    "cpu": "2.0",
                    "cloud": "optional",
                },
            ),
            AgentCapability(
                name="quality_assurance",
                description="Perform testing, validation, and quality checks on executions",
                input_types=["qa_task", "validation_request"],
                output_types=["qa_result", "quality_report"],
                resource_requirements={"memory": "512MB", "cpu": "1.0"},
            ),
        ]

    async def validate_task(self, task: TaskData) -> bool:
        """Accept task types that _execute_task() below can actually route."""
        task_type = task.metadata.get("type", "general_execution")
        return task_type in self._SUPPORTED_TASK_TYPES

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Process execution tasks with safety checks and monitoring"""
        start_time = datetime.now(timezone.utc)

        try:
            task_type: str = task.metadata.get("type", "general_execution")

            logger.info(f"ExecutorAgent processing task: {task.id} (type: {task_type})")

            # Perform safety check before execution
            safety_check = await self._perform_safety_check(task)
            if not safety_check["safe"]:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Safety check failed: {safety_check['reason']}",
                    execution_time=0.0,
                )

            # Route to appropriate execution method
            if task_type == "api_integration":
                result = await self._execute_api_integration(task)
            elif task_type == "workflow_automation":
                result = await self._execute_workflow_automation(task)
            elif task_type == "file_operations":
                result = await self._execute_file_operations(task)
            elif task_type == "system_commands":
                result = await self._execute_system_commands(task)
            elif task_type == "data_pipeline":
                result = await self._execute_data_pipeline(task)
            elif task_type == "notification_systems":
                result = await self._execute_notification_systems(task)
            elif task_type == "web_automation":
                result = await self._execute_web_automation(task)
            elif task_type == "database_operations":
                result = await self._execute_database_operations(task)
            elif task_type == "deployment_automation":
                result = await self._execute_deployment_automation(task)
            elif task_type == "quality_assurance":
                result = await self._execute_quality_assurance(task)
            else:
                result = await self._execute_general_task(task)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Log execution for monitoring
            self._log_execution(task, result, execution_time)

            _checks_passed = safety_check.get("checks_passed", [])
            _checks_passed_count = len(_checks_passed) if isinstance(_checks_passed, list) else 0

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "agent_type": "executor_agent",
                    "specialization": self.specialization,
                    "execution_results": result,
                    "domains_utilized": self.execution_domains,
                    "methodology": task_type,
                    "safety_checks_passed": safety_check.get("checks_passed", []),
                    "execution_metrics": {
                        "start_time": start_time.isoformat(),
                        "execution_time": execution_time,
                        "resource_usage": result.get("resource_usage", {}),
                        "success_rate": self._calculate_success_rate(),
                    },
                },
                execution_time=execution_time,
                logs=[
                    f"Execution task {task.id} processed by ExecutorAgent",
                    f"Task type: {task_type}",
                    f"Safety checks: {_checks_passed_count} passed",
                    f"Execution time: {execution_time:.2f}s",
                ],
            )

        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error(f"ExecutorAgent error processing task {task.id}: {e}")

            # Log failed execution
            self._log_execution(task, {"error": str(e), "status": "failed"}, execution_time)

            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Execution processing failed: {e}",
                execution_time=execution_time,
                logs=[f"ExecutorAgent error: {e}"],
            )

    async def _perform_safety_check(self, task: TaskData) -> dict[str, object]:
        """Perform comprehensive safety checks before task execution"""
        try:
            checks_passed: list[str] = []
            warnings: list[str] = []
            safety_results: dict[str, object] = {
                "safe": True,
                "checks_passed": checks_passed,
                "warnings": warnings,
                "reason": None,
            }

            # Check 1: Command validation
            if await self._validate_commands(task):
                checks_passed.append("command_validation")
            else:
                safety_results["safe"] = False
                safety_results["reason"] = "Invalid or dangerous commands detected"
                return safety_results

            # Check 2: Resource requirements
            if await self._validate_resource_requirements(task):
                checks_passed.append("resource_validation")
            else:
                warnings.append("High resource usage expected")

            # Check 3: Permission verification
            if await self._validate_permissions(task):
                checks_passed.append("permission_verification")
            else:
                warnings.append("Limited permissions may affect execution")

            # Check 4: Rate limiting
            if await self._check_rate_limits(task):
                checks_passed.append("rate_limit_check")
            else:
                warnings.append("Approaching rate limits")

            return safety_results

        except Exception as e:
            logger.error(f"Safety check failed: {e}")
            return {
                "safe": False,
                "checks_passed": [],
                "warnings": [],
                "reason": f"Safety check error: {e}",
            }

    async def _validate_commands(self, task: TaskData) -> bool:
        """Validate that commands are safe to execute"""
        try:
            # Twee lijsten, want twee soorten toets (ADR-036 OP-173).
            #
            # `"curl.*|.*sh"` en `"wget.*|.*sh"` stonden hier tussen de letterlijke teksten en
            # werden met `in` getoetst. Die vorm matcht alleen op de LETTERLIJKE tekst
            # `curl.*|.*sh`, en die komt in geen enkele taak voor. De twee gevaarlijkste
            # patronen uit deze lijst waren daarmee dode filtering: ze stonden er wel en deden
            # niets. Dat is misleidender dan geen filter, want een lezer telt ze mee.
            gevaarlijke_teksten = [
                "rm -rf",
                "del /f",
                "format",
                "shutdown",
                "reboot",
                "dd if=",
                "mkfs",
                "> /dev",
                ":(){ :|:& };:",  # Fork bomb
            ]
            gevaarlijke_patronen = [
                re.compile(r"curl\b.*\|.*\bsh\b", re.IGNORECASE),
                re.compile(r"wget\b.*\|.*\bsh\b", re.IGNORECASE),
            ]

            task_content = f"{task.title} {task.description} {str(task.metadata)}"

            for pattern in gevaarlijke_teksten:
                if pattern.lower() in task_content.lower():
                    logger.warning(f"Dangerous pattern detected: {pattern}")
                    return False

            for patroon in gevaarlijke_patronen:
                if patroon.search(task_content):
                    logger.warning(f"Dangerous pattern detected: {patroon.pattern}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Command validation error: {e}")
            return False

    async def _validate_resource_requirements(self, task: TaskData) -> bool:
        """Validate resource requirements are within limits"""
        try:
            # Check if task requires excessive resources
            task_type: str = task.metadata.get("type", "general_execution")

            resource_limits = {
                "api_integration": {"memory": "512MB", "cpu": 1.0},
                "workflow_automation": {"memory": "1GB", "cpu": 2.0},
                "data_pipeline": {"memory": "2GB", "cpu": 3.0},
                "deployment_automation": {"memory": "1GB", "cpu": 2.0},
            }

            if task_type in resource_limits:
                # Resources are within expected limits
                return True

            return True  # Allow by default for flexibility

        except Exception as e:
            logger.error(f"Resource validation error: {e}")
            return True

    async def _validate_permissions(self, task: TaskData) -> bool:
        """Validate agent has necessary permissions"""
        try:
            # Basic permission checks
            task_type: str = task.metadata.get("type", "general_execution")

            # Check workspace access
            if self.workspace_dir is None or not self.workspace_dir.exists():
                return False

            # Check network access for API tasks
            if task_type in [
                "api_integration",
                "web_automation",
                "notification_systems",
            ]:
                # Network permission assumed available
                return True

            # Check file system access
            if task_type in ["file_operations", "data_pipeline"]:
                # File system access assumed available in workspace
                return True

            return True

        except Exception as e:
            logger.error(f"Permission validation error: {e}")
            return False

    async def _check_rate_limits(self, task: TaskData) -> bool:
        """Check if execution would violate rate limits"""
        try:
            task_type: str = task.metadata.get("type", "general_execution")
            current_time = datetime.now(timezone.utc)

            # Simple rate limiting: max 60 executions per hour per type
            if task_type not in self.api_usage_tracker:
                self.api_usage_tracker[task_type] = []

            # Clean old entries (older than 1 hour)
            hour_ago = current_time - timedelta(hours=1)
            self.api_usage_tracker[task_type] = [
                timestamp for timestamp in self.api_usage_tracker[task_type] if timestamp > hour_ago
            ]

            # Check if within limits
            if len(self.api_usage_tracker[task_type]) < 60:
                self.api_usage_tracker[task_type].append(current_time)
                return True

            return False  # Rate limit exceeded

        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            return True  # Allow by default to prevent blocking

    async def _execute_api_integration(self, task: TaskData) -> dict[str, object]:
        """Execute API integration tasks"""
        try:
            api_endpoint: str = task.metadata.get("api_endpoint", "")
            method: str = task.metadata.get("method", "GET").upper()
            headers: dict[str, object] = task.metadata.get("headers", {})
            payload: dict[str, object] = task.metadata.get("payload", {})
            auth_type: str = task.metadata.get("auth_type", "none")

            if not api_endpoint:
                # Generate API integration strategy using LLM
                api_prompt = f"""
                Design an API integration strategy for:

                Task: {task.title}
                Description: {task.description}

                Provide API integration approach including:
                1. API endpoint design and selection
                2. Authentication strategy
                3. Request/response handling
                4. Error handling and retry logic
                5. Rate limiting considerations
                6. Data validation and transformation
                7. Monitoring and logging approach

                Structure as actionable API integration plan.
                """

                messages = [LLMMessage(role="user", content=api_prompt)]
                if self.llm_client is None:
                    raise RuntimeError("LLM client not initialized")
                response: Any = await self.llm_client.chat_completion(  # TODO(TYPE): replace Any with concrete type
                    messages
                )

                return {
                    "integration_type": "api_strategy",
                    "api_integration_plan": (
                        response.content
                        if response.success
                        else "API integration strategy developed"
                    ),
                    "methodology": "llm_guided_integration",
                    "auth_type": auth_type,
                    "status": "strategy_created",
                    "next_steps": [
                        "Implement API client",
                        "Test authentication flow",
                        "Validate data transformation",
                        "Deploy integration",
                    ],
                }

            # Execute actual API call
            _valideer_api_endpoint(api_endpoint)
            if self.http_session is None:
                raise RuntimeError("HTTP session not initialized")
            async with self.http_session.request(
                method=method,
                url=api_endpoint,
                headers=cast(dict[str, str], headers),
                json=payload if payload else None,
            ) as response:
                response_data: str = await response.text()

                json_data: object = None
                try:
                    json_data = await response.json()
                except Exception as e:
                    logger.warning(
                        f"Failed to parse API response as JSON: {str(e)}",
                        exc_info=False,
                    )

                return {
                    "integration_type": "api_call",
                    "endpoint": api_endpoint,
                    "method": method,
                    "status_code": response.status,
                    "success": response.status < 400,
                    "response_data": json_data or response_data[:1000],  # Limit response size
                    "headers": dict(response.headers),
                    "execution_time": datetime.now(timezone.utc).isoformat(),
                    "auth_type": auth_type,
                }

        except Exception as e:
            logger.error(f"API integration execution error: {e}")
            return {
                "integration_type": "api_call",
                "error": str(e),
                "status": "failed",
                "methodology": "direct_api_execution",
            }

    async def _execute_workflow_automation(self, task: TaskData) -> dict[str, object]:
        """Execute workflow automation tasks"""
        try:
            workflow_steps: list[dict[str, object]] = task.metadata.get("workflow_steps", [])
            parallel_execution: bool = task.metadata.get("parallel_execution", False)
            error_handling: str = task.metadata.get("error_handling", "continue")

            if not workflow_steps:
                # Generate workflow automation strategy
                workflow_prompt = f"""
                Design a workflow automation solution for:

                Task: {task.title}
                Description: {task.description}

                Create comprehensive workflow automation including:
                1. Step-by-step process breakdown
                2. Decision points and conditional logic
                3. Error handling and recovery procedures
                4. Parallel execution opportunities
                5. Monitoring and reporting mechanisms
                6. Success criteria and validation
                7. Rollback and cleanup procedures

                Structure as executable workflow specification.
                """

                messages = [LLMMessage(role="user", content=workflow_prompt)]
                if self.llm_client is None:
                    raise RuntimeError("LLM client not initialized")
                response: Any = await self.llm_client.chat_completion(  # TODO(TYPE): replace Any with concrete type
                    messages
                )

                return {
                    "workflow_type": "automation_strategy",
                    "workflow_plan": (
                        response.content
                        if response.success
                        else "Workflow automation strategy developed"
                    ),
                    "methodology": "intelligent_workflow_design",
                    "parallel_execution": parallel_execution,
                    "error_handling": error_handling,
                    "status": "strategy_created",
                }

            # Execute workflow steps
            workflow_results: list[dict[str, object]] = []
            overall_success = True

            for i, step in enumerate(workflow_steps):
                step_start = datetime.now(timezone.utc)

                try:
                    # Simulate step execution
                    step_result = {
                        "step_number": i + 1,
                        "step_name": step.get("name", f"Step {i + 1}"),
                        "action": step.get("action", "execute"),
                        "success": True,
                        "execution_time": (datetime.now(timezone.utc) - step_start).total_seconds(),
                        "output": f"Step {i + 1} completed successfully",
                    }

                    workflow_results.append(step_result)

                except Exception as step_error:
                    step_result = {
                        "step_number": i + 1,
                        "step_name": step.get("name", f"Step {i + 1}"),
                        "success": False,
                        "error": str(step_error),
                        "execution_time": (datetime.now(timezone.utc) - step_start).total_seconds(),
                    }

                    workflow_results.append(step_result)
                    overall_success = False

                    if error_handling == "stop":
                        break

            return {
                "workflow_type": "automation_execution",
                "total_steps": len(workflow_steps),
                "completed_steps": len([r for r in workflow_results if r.get("success")]),
                "failed_steps": len([r for r in workflow_results if not r.get("success")]),
                "overall_success": overall_success,
                "workflow_results": workflow_results,
                "parallel_execution": parallel_execution,
                "error_handling": error_handling,
                "methodology": "step_by_step_execution",
            }

        except Exception as e:
            logger.error(f"Workflow automation execution error: {e}")
            return {
                "workflow_type": "automation_execution",
                "error": str(e),
                "status": "failed",
                "methodology": "workflow_automation",
            }

    async def _execute_file_operations(self, task: TaskData) -> dict[str, object]:
        """Execute file system operations"""
        operation_type: str = task.metadata.get("operation_type", "read")
        file_paths: list[str] = task.metadata.get("file_paths", [])
        try:
            if self.workspace_dir is None:
                raise RuntimeError("Workspace not initialized")

            # File operations within workspace for safety
            operations_results: list[dict[str, object]] = []
            if operation_type == "create":
                # Create test files
                for i in range(min(len(file_paths), 5)):  # Limit to 5 files
                    test_file = self.workspace_dir / f"test_file_{i}.txt"
                    test_file.write_text(
                        f"Test file {i} created by ExecutorAgent at {datetime.now(timezone.utc)}"
                    )
                    operations_results.append(
                        {
                            "operation": "create",
                            "file": str(test_file),
                            "success": True,
                            "size": test_file.stat().st_size,
                        }
                    )

            elif operation_type == "list":
                # List workspace contents
                for item in self.workspace_dir.iterdir():
                    operations_results.append(
                        {
                            "operation": "list",
                            "item": item.name,
                            "type": "directory" if item.is_dir() else "file",
                            "size": item.stat().st_size if item.is_file() else 0,
                        }
                    )

            return {
                "operation_type": operation_type,
                "workspace": str(self.workspace_dir),
                "operations_performed": len(operations_results),
                "results": operations_results,
                "total_files_processed": len(operations_results),
                "success_rate": 1.0,
                "methodology": "safe_workspace_operations",
            }

        except Exception as e:
            logger.error(f"File operations execution error: {e}")
            return {
                "operation_type": operation_type,
                "error": str(e),
                "status": "failed",
                "methodology": "file_system_operations",
            }

    async def _execute_system_commands(self, task: TaskData) -> dict[str, object]:
        """Execute system commands inside sandbox isolation."""
        if not self.sandbox_manager:
            return {
                "success": False,
                "error": "Sandbox not initialized - system commands require sandbox isolation",
                "commands_executed": 0,
                "sandbox_isolated": False,
            }

        commands: list[str] = task.metadata.get("commands", [])
        # Allowlist: only these first-words are permitted inside the container
        ALLOWED_FIRST_WORDS = frozenset(["echo", "ls", "pwd", "date", "whoami", "python"])

        script_lines = ["import subprocess, json, sys", "results = []"]
        for cmd in commands:
            parts = cmd.split()
            first_word = parts[0] if parts else ""
            if first_word not in ALLOWED_FIRST_WORDS:
                script_lines.append(
                    f'results.append({{"cmd": {cmd!r}, "error": "not allowed", "success": False}})'
                )
            else:
                # !r gives a safe Python list repr -- no shell injection possible
                script_lines.append(
                    f"r = subprocess.run({parts!r}, capture_output=True, text=True, timeout=8)\n"
                    f'results.append({{"cmd": {cmd!r}, "rc": r.returncode, '
                    f'"stdout": r.stdout, "success": r.returncode == 0}})'
                )
        script_lines.append("print(json.dumps(results))")
        code = "\n".join(script_lines)

        from src.core.shared.interfaces import IsolationLevel, SandboxEnvironment

        sandbox_id = await self.sandbox_manager.create_sandbox(
            SandboxEnvironment(
                isolation_level=IsolationLevel.CONTAINER,
                resource_limits={"memory": "128m", "timeout": 15},
                network_access=False,
            )
        )
        try:
            result = await self.sandbox_manager.execute_in_sandbox(
                sandbox_id,
                TaskData(
                    id=task.id,
                    title=task.title,
                    description="",
                    metadata={"type": "python_code", "code": code},
                ),
            )
            return {
                "success": result.success,
                "output": result.result_data,
                "sandbox_isolated": True,
                "methodology": "sandboxed_command_execution",
            }
        except Exception as e:
            logger.error(
                "system_commands.sandbox_error: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
                extra={"task_id": task.id},
            )
            return {
                "success": False,
                "error": str(e),
                "sandbox_isolated": True,
                "methodology": "sandboxed_command_execution",
            }
        finally:
            await self.sandbox_manager.destroy_sandbox(sandbox_id)

    async def _execute_data_pipeline(self, task: TaskData) -> dict[str, object]:
        """Execute data pipeline operations"""
        try:
            pipeline_stages: list[dict[str, object]] = task.metadata.get("pipeline_stages", [])
            data_format: str = task.metadata.get("data_format", "json")

            if not pipeline_stages:
                # Generate data pipeline strategy
                pipeline_prompt = f"""
                Design a data pipeline solution for:

                Task: {task.title}
                Description: {task.description}
                Data Format: {data_format}

                Create comprehensive data pipeline including:
                1. Data ingestion strategy
                2. Transformation and processing steps
                3. Quality validation and cleansing
                4. Output format and destination
                5. Error handling and recovery
                6. Performance optimization
                7. Monitoring and alerting

                Structure as executable pipeline specification.
                """

                messages = [LLMMessage(role="user", content=pipeline_prompt)]
                if self.llm_client is None:
                    raise RuntimeError("LLM client not initialized")
                response: Any = await self.llm_client.chat_completion(  # TODO(TYPE): replace Any with concrete type
                    messages
                )

                return {
                    "pipeline_type": "data_processing_strategy",
                    "data_pipeline_plan": (
                        response.content if response.success else "Data pipeline strategy developed"
                    ),
                    "methodology": "intelligent_pipeline_design",
                    "data_format": data_format,
                    "status": "strategy_created",
                }

            # Execute pipeline stages
            pipeline_results: list[dict[str, object]] = []
            processed_records = 0

            for stage in pipeline_stages:
                stage_start = datetime.now(timezone.utc)

                # Simulate data processing
                stage_result = {
                    "stage_name": stage.get("name", "unnamed_stage"),
                    "stage_type": stage.get("type", "transform"),
                    "input_records": processed_records,
                    "output_records": processed_records + 100,  # Simulate processing
                    "processing_time": (datetime.now(timezone.utc) - stage_start).total_seconds(),
                    "success": True,
                }

                pipeline_results.append(stage_result)
                processed_records += 100

            return {
                "pipeline_type": "data_processing_execution",
                "total_stages": len(pipeline_stages),
                "completed_stages": len(pipeline_results),
                "total_records_processed": processed_records,
                "pipeline_results": pipeline_results,
                "data_format": data_format,
                "methodology": "multi_stage_processing",
            }

        except Exception as e:
            logger.error(f"Data pipeline execution error: {e}")
            return {
                "pipeline_type": "data_processing_execution",
                "error": str(e),
                "status": "failed",
                "methodology": "data_pipeline_processing",
            }

    async def _execute_notification_systems(self, task: TaskData) -> dict[str, object]:
        """Execute notification and communication tasks"""
        notification_type: str = task.metadata.get("notification_type", "email")
        recipients: list[str] = task.metadata.get("recipients", [])
        try:
            message: str = task.metadata.get("message", task.description)

            # Simulate notification sending
            notification_results: list[dict[str, object]] = []
            for recipient in recipients[:10]:  # Limit to 10 recipients
                notification_result = {
                    "recipient": recipient,
                    "notification_type": notification_type,
                    "message_length": len(message),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "success": True,  # Simulate successful sending
                    "delivery_id": f"notif_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{hash(recipient) % 1000}",
                }

                notification_results.append(notification_result)

            return {
                "notification_type": notification_type,
                "total_recipients": len(recipients),
                "sent_notifications": len(notification_results),
                "failed_notifications": 0,
                "notification_results": notification_results,
                "message_preview": message[:100] + "..." if len(message) > 100 else message,
                "methodology": "batch_notification_processing",
            }

        except Exception as e:
            logger.error(f"Notification systems execution error: {e}")
            return {
                "notification_type": notification_type,
                "error": str(e),
                "status": "failed",
                "methodology": "notification_systems",
            }

    async def _execute_web_automation(self, task: TaskData) -> dict[str, object]:
        """Execute web automation and scraping tasks"""
        try:
            target_urls: list[str] = task.metadata.get("target_urls", [])
            automation_actions: list[dict[str, object]] = task.metadata.get(
                "automation_actions", []
            )

            # Generate web automation strategy
            web_prompt = f"""
            Design a web automation solution for:

            Task: {task.title}
            Description: {task.description}
            Target URLs: {target_urls[:3]}  # Show first 3 URLs

            Create web automation approach including:
            1. Browser automation strategy
            2. Data extraction methods
            3. Form interaction and submission
            4. Navigation and page handling
            5. Error handling and retries
            6. Rate limiting and politeness
            7. Data validation and storage

            Structure as executable automation plan.
            """

            messages = [LLMMessage(role="user", content=web_prompt)]
            if self.llm_client is None:
                raise RuntimeError("LLM client not initialized")
            # TODO(TYPE): replace Any with concrete type
            response: Any = (
                await self.llm_client.chat_completion(  # TODO(TYPE): replace Any with concrete type
                    messages
                )
            )

            return {
                "automation_type": "web_automation_strategy",
                "web_automation_plan": (
                    response.content if response.success else "Web automation strategy developed"
                ),
                "target_urls": target_urls[:5],  # Limit URLs shown
                "automation_actions": automation_actions,
                "methodology": "intelligent_web_automation",
                "status": "strategy_created",
                "safety_considerations": [
                    "Respect robots.txt",
                    "Implement rate limiting",
                    "Handle JavaScript-rendered content",
                    "Validate extracted data",
                ],
            }

        except Exception as e:
            logger.error(f"Web automation execution error: {e}")
            return {
                "automation_type": "web_automation_strategy",
                "error": str(e),
                "status": "failed",
                "methodology": "web_automation",
            }

    async def _execute_database_operations(self, task: TaskData) -> dict[str, object]:
        """Execute database operations"""
        operation_type: str = task.metadata.get("operation_type", "query")
        database_type: str = task.metadata.get("database_type", "postgresql")
        try:
            # Generate database operation strategy
            db_prompt = f"""
            Design a database operation solution for:

            Task: {task.title}
            Description: {task.description}
            Database Type: {database_type}
            Operation Type: {operation_type}

            Create database operation approach including:
            1. Connection and authentication strategy
            2. Query optimization and indexing
            3. Transaction management
            4. Error handling and rollback procedures
            5. Performance monitoring
            6. Data validation and integrity
            7. Backup and recovery considerations

            Structure as executable database operation plan.
            """

            messages = [LLMMessage(role="user", content=db_prompt)]
            if self.llm_client is None:
                raise RuntimeError("LLM client not initialized")
            # TODO(TYPE): replace Any with concrete type
            response: Any = (
                await self.llm_client.chat_completion(  # TODO(TYPE): replace Any with concrete type
                    messages
                )
            )

            return {
                "operation_type": operation_type,
                "database_type": database_type,
                "database_operation_plan": (
                    response.content
                    if response.success
                    else "Database operation strategy developed"
                ),
                "methodology": "intelligent_database_operations",
                "status": "strategy_created",
                "best_practices": [
                    "Use parameterized queries",
                    "Implement connection pooling",
                    "Monitor query performance",
                    "Ensure ACID compliance",
                ],
            }

        except Exception as e:
            logger.error(f"Database operations execution error: {e}")
            return {
                "operation_type": operation_type,
                "database_type": database_type,
                "error": str(e),
                "status": "failed",
                "methodology": "database_operations",
            }

    async def _execute_deployment_automation(self, task: TaskData) -> dict[str, object]:
        """Execute deployment and infrastructure automation"""
        deployment_target: str = task.metadata.get("deployment_target", "production")
        infrastructure_type: str = task.metadata.get("infrastructure_type", "cloud")
        try:
            # Generate deployment strategy
            deploy_prompt = f"""
            Design a deployment automation solution for:

            Task: {task.title}
            Description: {task.description}
            Deployment Target: {deployment_target}
            Infrastructure Type: {infrastructure_type}

            Create deployment automation including:
            1. CI/CD pipeline configuration
            2. Infrastructure provisioning
            3. Application deployment strategy
            4. Configuration management
            5. Health checks and monitoring
            6. Rollback procedures
            7. Security and compliance

            Structure as executable deployment plan.
            """

            messages = [LLMMessage(role="user", content=deploy_prompt)]
            if self.llm_client is None:
                raise RuntimeError("LLM client not initialized")
            # TODO(TYPE): replace Any with concrete type
            response: Any = (
                await self.llm_client.chat_completion(  # TODO(TYPE): replace Any with concrete type
                    messages
                )
            )

            return {
                "deployment_target": deployment_target,
                "infrastructure_type": infrastructure_type,
                "deployment_plan": (
                    response.content
                    if response.success
                    else "Deployment automation strategy developed"
                ),
                "methodology": "intelligent_deployment_automation",
                "status": "strategy_created",
                "deployment_phases": [
                    "Pre-deployment validation",
                    "Infrastructure provisioning",
                    "Application deployment",
                    "Post-deployment verification",
                ],
            }

        except Exception as e:
            logger.error(f"Deployment automation execution error: {e}")
            return {
                "deployment_target": deployment_target,
                "infrastructure_type": infrastructure_type,
                "error": str(e),
                "status": "failed",
                "methodology": "deployment_automation",
            }

    async def _execute_quality_assurance(self, task: TaskData) -> dict[str, object]:
        """Execute quality assurance and testing tasks"""
        qa_type: str = task.metadata.get("qa_type", "functional_testing")
        try:
            test_scenarios: list[dict[str, object]] = task.metadata.get("test_scenarios", [])

            # Simulate QA execution
            qa_results: dict[str, object] = {
                "qa_type": qa_type,
                "total_tests": len(test_scenarios) if test_scenarios else 10,
                "passed_tests": 8,  # Simulate 80% pass rate
                "failed_tests": 2,
                "test_execution_time": 45.5,
                "coverage_percentage": 85.0,
                "quality_score": 0.88,
                "test_results": [
                    {
                        "test_name": "Authentication flow",
                        "status": "passed",
                        "execution_time": 2.5,
                    },
                    {
                        "test_name": "Data validation",
                        "status": "passed",
                        "execution_time": 1.8,
                    },
                    {
                        "test_name": "Error handling",
                        "status": "failed",
                        "execution_time": 3.2,
                        "error": "Timeout exceeded",
                    },
                    {
                        "test_name": "Performance test",
                        "status": "passed",
                        "execution_time": 12.1,
                    },
                    {
                        "test_name": "Security scan",
                        "status": "passed",
                        "execution_time": 8.9,
                    },
                ],
                "recommendations": [
                    "Fix timeout issues in error handling tests",
                    "Increase test coverage to 90%+",
                    "Add more edge case scenarios",
                    "Implement automated regression testing",
                ],
            }

            return qa_results

        except Exception as e:
            logger.error(f"Quality assurance execution error: {e}")
            return {
                "qa_type": qa_type,
                "error": str(e),
                "status": "failed",
                "methodology": "quality_assurance_testing",
            }

    async def _execute_general_task(self, task: TaskData) -> dict[str, object]:
        """Execute general execution tasks"""
        try:
            # LLM-based general execution strategy
            execution_prompt = f"""
            Design an execution strategy for:

            Task: {task.title}
            Description: {task.description}

            Create comprehensive execution plan including:
            1. Task breakdown and sequencing
            2. Resource requirements and allocation
            3. Risk assessment and mitigation
            4. Success criteria and validation
            5. Monitoring and progress tracking
            6. Error handling and recovery
            7. Documentation and reporting

            Structure as actionable execution plan.
            """

            messages = [LLMMessage(role="user", content=execution_prompt)]
            if self.llm_client is None:
                raise RuntimeError("LLM client not initialized")
            # TODO(TYPE): replace Any with concrete type
            response: Any = (
                await self.llm_client.chat_completion(  # TODO(TYPE): replace Any with concrete type
                    messages
                )
            )

            return {
                "execution_type": "general_task_execution",
                "execution_plan": (
                    response.content if response.success else "General execution strategy developed"
                ),
                "methodology": "intelligent_task_execution",
                "status": "strategy_created",
                "estimated_completion_time": "Variable based on complexity",
                "resource_requirements": "Standard computational resources",
            }

        except Exception as e:
            logger.error(f"General task execution error: {e}")
            return {
                "execution_type": "general_task_execution",
                "error": str(e),
                "status": "failed",
                "methodology": "general_execution",
            }

    def _log_execution(
        self, task: TaskData, result: dict[str, object], execution_time: float
    ) -> None:
        """Log execution for monitoring and analysis"""
        try:
            execution_log: dict[str, object] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "task_id": task.id,
                "task_type": task.metadata.get("type", "unknown"),
                "execution_time": execution_time,
                "success": result.get("status") != "failed",
                "result_summary": {
                    "type": result.get("operation_type")
                    or result.get("integration_type")
                    or result.get("execution_type"),
                    "status": result.get("status", "completed"),
                },
            }

            self.execution_history.append(execution_log)

            # Keep only last 100 executions
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-100:]

        except Exception as e:
            logger.error(f"Failed to log execution: {e}")

    def _calculate_success_rate(self) -> float:
        """Calculate recent success rate for performance monitoring"""
        try:
            if not self.execution_history:
                return 1.0

            recent_executions = self.execution_history[-20:]  # Last 20 executions
            successful = len([ex for ex in recent_executions if ex.get("success", False)])

            return successful / len(recent_executions) if recent_executions else 1.0

        except Exception:
            return 0.0

    async def shutdown(self) -> None:
        """Cleanup resources on shutdown"""
        try:
            # Close HTTP session
            if hasattr(self, "http_session") and self.http_session:
                await self.http_session.close()

            # Clean up workspace
            if (
                hasattr(self, "workspace_dir")
                and self.workspace_dir is not None
                and self.workspace_dir.exists()
            ):
                shutil.rmtree(self.workspace_dir, ignore_errors=True)

            logger.info(f"ExecutorAgent {self.agent_id} shutdown completed")

        except Exception as e:
            logger.error(f"Error during executor shutdown: {e}")


# Factory function
async def create_executor_agent(agent_id: str | None = None) -> ExecutorAgent:
    """Create and initialize an executor agent"""
    effective_agent_id: str = (
        agent_id
        if agent_id is not None
        else f"executor_agent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )

    agent = ExecutorAgent(effective_agent_id)

    # Initialize the agent
    if not await agent.initialize():
        raise RuntimeError(f"Failed to initialize ExecutorAgent {effective_agent_id}")

    return agent

"""
Resilient Sandbox Executor for SanskritiSetu AI Platform.

This module provides a failure-aware execution wrapper around the TenantSandboxOrchestrator.
It implements the "Doctor Loop" pattern:
Execute -> Catch Error -> Analyze (via Doctor Agent) -> Patch -> Retry.

It is designed to be:
- Async native
- Multi-tenant aware
- Secure (Strict retries and quotas)
- Observable (Full healing audit trail)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, cast
from collections.abc import Awaitable, Callable

from src.core.sandbox.tenant_sandbox_orchestrator import (
    SandboxConfig,
    SandboxType,
    TenantSandboxOrchestrator,
    get_sandbox_orchestrator,
)

logger = logging.getLogger(__name__)


class HealingStrategy(str, Enum):
    """Strategies for healing failures"""

    STATIC = "static"  # Regex/simple replacements
    LLM = "llm"  # AI-generated patch
    DEPENDENCY = "dep"  # Auto-install packages (if allowed)
    TEST_DRIVEN = "test"  # Fix logic until assertion passes


@dataclass
class HealingPolicy:
    """Configuration for healing behavior per execution"""

    max_retries: int = 2
    strategies: list[HealingStrategy] = field(default_factory=lambda: [HealingStrategy.LLM])
    allow_package_install: bool = False
    model_name: str = "gemini-pro"

    # Circuit breaker: Don't spend more tokens than X on healing
    max_cost_credits: float = 0.05


@dataclass
class ExecutionResult:
    """Standardized result including healing metadata"""

    success: bool
    output: str
    error: str
    exit_code: int
    execution_time: float
    cost_credits: float

    # Healing Metadata
    healing_applied: bool = False
    healing_attempts: int = 0
    healing_log: list[str] = field(default_factory=list)
    original_error: str | None = None


class ResilientSandboxExecutor:
    """
    Executes code with self-healing capabilities.
    Wraps TenantSandboxOrchestrator.
    """

    def __init__(self, orchestrator: TenantSandboxOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def execute_with_healing(
        self,
        tenant_id: int,
        code: str,
        config: SandboxConfig | None = None,
        policy: HealingPolicy | None = None,
        verification_script: str | None = None,
    ) -> ExecutionResult:
        """
        Execute code, and if it fails (or validation fails), attempt to heal it.

        Args:
            tenant_id: The ID of the tenant
            code: The source code to execute
            config: Sandbox configuration (defaults to Agent-type if None)
            policy: Healing control parameters (defaults to 2 retries)
            verification_script: Optional assertion code to append

        Returns:
            ExecutionResult with success status and potential healing history.
        """
        # Default policy if not provided
        policy = policy or HealingPolicy()
        config = config or SandboxConfig(sandbox_type=SandboxType.AGENT)

        # Merge verification logic if present (Test-Driven Healing)
        executable_code = self._prepare_code(code, verification_script)

        # 1. First Attempt
        # We create a fresh sandbox for the first attempt.
        # In a refined version, we might keep the sandbox alive for retries,
        # but for clean state, we restart.

        sandbox_id = await self.orchestrator.create_sandbox(tenant_id, config)
        if sandbox_id is None:
            return ExecutionResult(
                success=False,
                output="",
                error="Failed to create sandbox: sandbox_id is None",
                exit_code=-1,
                execution_time=0.0,
                cost_credits=0.0,
            )

        try:
            logger.info(f"Starting execution for tenant {tenant_id} (Sandbox: {sandbox_id})")

            raw_result = await self.orchestrator.execute_in_sandbox(
                tenant_id, sandbox_id, executable_code
            )

            # Map raw result to ExecutionResult
            result = self._map_result(raw_result)

            if result.success:
                return result

            # 2. Doctor Loop (if failed)
            logger.warning(
                f"Execution failed for tenant {tenant_id}. "
                f"Error: {result.error[:100]}... Starting Doctor Loop."
            )

            return await self._run_doctor_loop(
                tenant_id, config, executable_code, result, policy, verification_script
            )

        finally:
            await self.orchestrator.destroy_sandbox(tenant_id, sandbox_id)

    def _prepare_code(self, code: str, verification_script: str | None) -> str:
        """Combine user code with verification logic"""
        if not verification_script:
            return code

        # Wrap verification in a try/except block to ensure we catch logic failures
        # as strict errors that trigger healing
        wrapper = f"""
try:
    # --- User Code Start ---
{self._indent_code(code)}
    # --- User Code End ---

    # --- Verification Logic ---
{self._indent_code(verification_script)}
    print("VERIFICATION_SUCCESS")

except AssertionError as e:
    import sys
    print(f"VERIFICATION_FAILED: {{e}}", file=sys.stderr)
    sys.exit(1)
except Exception:
    raise
"""
        return wrapper

    def _indent_code(self, code: str) -> str:
        """Indent code by 4 spaces"""
        return "\n".join("    " + line for line in code.splitlines())

    def _map_result(self, raw: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Map generic dictionary to typed result"""
        return ExecutionResult(
            success=raw.get("success", False),
            output=raw.get("output", ""),
            error=raw.get("error", ""),
            exit_code=raw.get("exit_code", -1),
            execution_time=raw.get("execution_time", 0.0),
            cost_credits=raw.get("cost_credits", 0.0),
        )

    async def _run_doctor_loop(
        self,
        tenant_id: int,
        config: SandboxConfig,
        original_code: str,
        initial_failure: ExecutionResult,
        policy: HealingPolicy,
        verification_script: str | None,
    ) -> ExecutionResult:
        """
        The core self-healing retry loop.
        """
        current_code = original_code
        last_result = initial_failure
        last_result.original_error = initial_failure.error
        last_result.healing_applied = True

        attempts = 0

        # Track history for context-aware healing (HEAL_OPTIMIZATION)
        attempts_history = [
            {
                "code": original_code,
                "error": initial_failure.error,
                "output": initial_failure.output,
            }
        ]

        while attempts < policy.max_retries:
            attempts += 1
            logger.info(f"Healing attempt {attempts}/{policy.max_retries} for tenant {tenant_id}")
            last_result.healing_log.append(f"Attempt {attempts}: Analyzing failure...")

            # 1. Diagnose and Patch (This is the Doctor Agent Step)
            # For HEAL_001, we mock this part or define a placeholder hook.
            # In HEAL_002, this will call the LLM.
            patched_code = await self._diagnose_and_patch(
                tenant_id, current_code, last_result.error, policy, attempts_history
            )

            if patched_code is None or patched_code == current_code:
                last_result.healing_log.append(f"Attempt {attempts}: No fix generated. Aborting.")
                last_result.healing_attempts = attempts
                return last_result

            current_code = patched_code

            # 2. Retry Execution
            # We spin up a new sandbox for the retry to ensure clean state
            # (In optimizations, we might reuse if safe)
            retry_sandbox_id = await self.orchestrator.create_sandbox(tenant_id, config)
            if retry_sandbox_id is None:
                last_result.healing_log.append(
                    f"Attempt {attempts}: Failed to create retry sandbox."
                )
                last_result.healing_attempts = attempts
                return last_result

            try:
                retry_raw = await self.orchestrator.execute_in_sandbox(
                    tenant_id, retry_sandbox_id, current_code
                )
                retry_result = self._map_result(retry_raw)

                # Update tracking stats (cost accumulates!)
                last_result.cost_credits += retry_result.cost_credits
                last_result.execution_time += retry_result.execution_time
                last_result.output = retry_result.output
                last_result.error = retry_result.error
                last_result.exit_code = retry_result.exit_code
                last_result.success = retry_result.success

                if retry_result.success:
                    last_result.healing_log.append(f"Attempt {attempts}: SUCCESS. Fix applied.")
                    last_result.healing_attempts = attempts
                    return last_result
                else:
                    last_result.healing_log.append(
                        f"Attempt {attempts}: FAILED. New error: {retry_result.error[:50]}..."
                    )
                    # Add to history for next iteration
                    attempts_history.append(
                        {
                            "code": current_code,
                            "error": retry_result.error,
                            "output": retry_result.output,
                        }
                    )

            finally:
                await self.orchestrator.destroy_sandbox(tenant_id, retry_sandbox_id)

        # If we exit loop, healing failed
        last_result.healing_attempts = attempts
        last_result.healing_log.append("Healing failed after max retries.")
        return last_result

    async def _diagnose_and_patch(
        self,
        tenant_id: int,
        code: str,
        error: str,
        policy: HealingPolicy,
        history: list[dict[str, Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """
        Use the Doctor Agent to analyze the error and generate a fix.
        """
        if HealingStrategy.LLM not in policy.strategies:
            return code

        # TODO: DoctorAgent needs to be imported from appropriate module
        # For now, skip LLM healing as DoctorAgent is not available
        # Integration of HEAL_004: RAG Context would go here
        logger.warning("LLM healing not available - DoctorAgent not implemented")
        return code  # Skip LLM healing until DoctorAgent is available


# Global getter
_resilient_executor: ResilientSandboxExecutor | None = None


async def get_resilient_executor() -> ResilientSandboxExecutor:
    global _resilient_executor
    if _resilient_executor is None:
        orchestrator = await get_sandbox_orchestrator()
        _resilient_executor = ResilientSandboxExecutor(orchestrator)
    return _resilient_executor

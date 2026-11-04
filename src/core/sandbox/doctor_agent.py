"""
Doctor Agent - AI Error Diagnostician for the Self-Healing Sandbox.

This agent analyzes execution failures (stack traces, test failures)
and generates patched code to resolve them.

Architecture:
- Uses the platform's standard LLMProviderProtocol.
- Enforces strict JSON output for safe automation.
- Categorizes errors (Syntax, Logic, Timeout) for reporting.
"""

import ast
import json
import logging
import re
from typing import Any, Optional, cast

from src.core.llm.provider_factory import LLMProviderProtocol, get_llm_provider
from src.core.sandbox.resilient_executor import HealingPolicy

logger = logging.getLogger(__name__)

DOCTOR_SYSTEM_PROMPT = """
You are an expert Python Debugger and Code Healer.
Your task is to analyze a failed Python script execution and GENERATE A FIX.

INPUT:
1. Original Code (that failed)
2. Error Output (stack trace or assertion failure)
3. Additional Context (optional RAG search results)

OUTPUT RULES:
1. You must return VALID JSON only. Do not include markdown formatting like ```json ... ```.
2. The JSON structure must be:
{
    "analysis": "Brief explanation of why the code failed (max 1 sentence)",
    "error_type": "SYNTAX | IMPORT | LOGIC | TIMEOUT | HALLUCINATION",
    "fix_description": "What you changed",
    "patched_code": "The COMPLETE, FULLY WORKING Python script with the fix applied."
}
3. DO NOT return diffs. Return the FULL patched code.
4. If a module is missing (ModuleNotFoundError):
   - Check if it is a standard library module.
   - If it is a common PyPI package, you may try to import it (assuming environment has it),
     BUT prefer standard library alternatives if possible.
5. If it is a Logical Error (AssertionError):
   - Analyze the logic and fix it to satisfy the assertion.
6. PREVIOUS ATTEMPTS:
   - Review the provided history of previous failures.
   - DO NOT repeat the same fix if it failed before.
   - If a previous fix caused a new error, try a different strategy.
"""


class DoctorAgent:
    """
    AI Agent responsible for diagnosing and fixing code errors.
    """

    def __init__(self, llm_provider: LLMProviderProtocol | None = None) -> None:
        """
        Initialize the Doctor Agent.

        Args:
            llm_provider: Optional injected provider (for testing).
                          If None, gets default from factory.
        """
        self._llm_provider = llm_provider

    async def _get_provider(self) -> LLMProviderProtocol:
        """Lazy load the provider"""

        if self._llm_provider:
            return self._llm_provider
        return cast(LLMProviderProtocol, get_llm_provider())

    async def diagnose_and_fix(
        self,
        code: str,
        error_output: str,
        policy: HealingPolicy,
        context: str | None = None,
        history: list[dict[str, Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze error and generate a fix.

        Args:
            history: List[Any] of previous attempts [{'code':..., 'error':..., 'fix':...}]  # TODO(TYPE): replace Any with concrete type
        """
        provider = await self._get_provider()

        # Format History
        history_text = "No previous attempts."
        if history:
            history_text = "\n".join(
                [
                    f"Attempt {i + 1}: Output='{h.get('output', '')[:100]}...', Error='{h.get('error', '')}'"
                    for i, h in enumerate(history)
                ]
            )

        # Construct the User Prompt
        user_prompt = f"""
--- ORIGINAL CODE ---
{code}

--- ERROR OUTPUT ---
{error_output}

--- CONTEXT ---
{context or "No additional context provided."}

--- PREVIOUS ATTEMPTS (DO NOT REPEAT MISTAKES) ---
{history_text}
"""

        try:
            logger.info(f"Doctor Agent analyzing error via {policy.model_name}...")

            # Call LLM
            # Note: We use the provider's native generate method.
            # Adjust the temperature to be low (0.1) for deterministic fixes.
            response = await provider.generate_text(  # type: ignore[attr-defined]
                prompt=user_prompt,
                system_instruction=DOCTOR_SYSTEM_PROMPT,
                # We might need to pass model config here depending on provider implementation
                # validation skipped for MVP
            )

            # Parse Response
            result = self._parse_llm_response(response)

            if not result:
                logger.warning("Doctor Agent failed to produce valid JSON fix.")
                return {"patched_code": code, "error": "Invalid LLM format"}

            # Syntax Check (Self-Correction)
            patched_code = result.get("patched_code", "")
            syntax_error = self._validate_syntax(patched_code)
            if syntax_error:
                logger.warning(f"Doctor produced invalid syntax: {syntax_error}")
                # We could try to auto-fix syntax here or just fail.
                # For now, we return the error in the result so the executor knows.
                result["analysis"] += f" (Note: Generated code has Syntax Error: {syntax_error})"
                # We do NOT overwrite patched_code because maybe it's minor, but ideally we should reject.

            return result

        except Exception as e:
            logger.error(f"Doctor Agent crashed: {e}")
            return {"patched_code": code, "error": str(e)}

    def _validate_syntax(self, code: str) -> str | None:
        """Check if code is valid Python syntax"""
        try:
            ast.parse(code)
            return None
        except SyntaxError as e:
            return f"{e.msg} at line {e.lineno}"

    def _parse_llm_response(self, text: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Robustly extract JSON from LLM output.
        Handles Markdown code blocks, whitespace, etc.
        """
        text = text.strip()

        # Regex to find JSON code block anywhere in the text
        # Matches ```json { ... } ``` or ``` { ... } ```
        json_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_block_match:
            text = json_block_match.group(1).strip()
        else:
            # Fallback: maybe the whole text is JSON but has some noise?
            # Or maybe just { ... } without backticks?
            bracket_match = re.search(r"(\{.*\})", text, re.DOTALL)
            if bracket_match:
                text = bracket_match.group(1).strip()

        try:
            return cast(dict[str, Any], json.loads(text))  # TODO(TYPE): replace Any with concrete type
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from Doctor Agent: {text[:100]}...")
            return None

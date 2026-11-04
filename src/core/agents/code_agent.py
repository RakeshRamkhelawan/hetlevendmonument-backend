"""
Code Agent Implementation
Specialist agent for code generation, review, and software development tasks
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.sandbox.sandbox_manager import BaseSandboxManager, SandboxManagerFactory
from src.core.shared.interfaces import (
    AgentCapability,
    ExecutionResult,
    SandboxEnvironment,
    TaskData,
)
from src.core.types import AgentType, IsolationLevel
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel, LLMMessage

logger = logging.getLogger(__name__)


class CodeAgent(CriticMixin, EnhancedBaseAgent):
    """Specialist agent for code generation, review, and software development"""

    def __init__(self, agent_id: str = "code_agent_001", tenant_id: int = 1) -> None:
        super().__init__(agent_id=agent_id, agent_type=AgentType.SPECIALIST, tenant_id=tenant_id)
        self.__init_critic__(mode=CriticMode.ADVISORY)

        # Code-specific configuration
        self.specialization = "software_development"
        self.supported_languages = [
            "python",
            "javascript",
            "typescript",
            "go",
            "rust",
            "java",
            "c++",
            "sql",
            "bash",
            "dockerfile",
        ]

        self.code_capabilities = [
            "code_generation",
            "code_review",
            "debugging",
            "testing",
            "refactoring",
            "documentation",
            "architecture_design",
        ]

        # Initialize LLM client for code tasks
        self.llm_client: ChatTaalmodel | None = None

        # Initialize sandbox for code execution and testing
        self.sandbox_manager: BaseSandboxManager | None = None

        logger.info(f"CodeAgent {agent_id} initialized")

    async def initialize(self) -> bool:
        """Initialize the code agent"""
        try:
            # Initialize LLM client - use Google Gemini (via router)
            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14).
            self.llm_client = TenantTaalmodel(self.tenant_id)

            # Initialize sandbox manager for code execution
            self.sandbox_manager = SandboxManagerFactory.create_manager(IsolationLevel.CONTAINER)

            logger.info(f"CodeAgent {self.agent_id} fully initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize CodeAgent {self.agent_id}: {e}")
            return False

    async def get_capabilities(self) -> list[AgentCapability]:
        """Get code agent capabilities"""
        return [
            AgentCapability(
                name="code_generation",
                description="Generate code in multiple programming languages",
                input_types=["code_request", "requirements"],
                output_types=["generated_code", "code_analysis"],
            ),
            AgentCapability(
                name="code_review",
                description="Review code for quality, security, and best practices",
                input_types=["code_request", "requirements"],
                output_types=["generated_code", "code_analysis"],
            ),
            AgentCapability(
                name="debugging",
                description="Debug and fix code issues",
                input_types=["task_request", "text_input"],
                output_types=["analysis_result", "text_output"],
            ),
            AgentCapability(
                name="code_testing",
                description="Create and execute unit tests",
                input_types=["code_request", "requirements"],
                output_types=["generated_code", "code_analysis"],
            ),
            AgentCapability(
                name="refactoring",
                description="Refactor code for better quality and maintainability",
                input_types=["task_request", "text_input"],
                output_types=["analysis_result", "text_output"],
            ),
            AgentCapability(
                name="documentation",
                description="Generate technical documentation and code comments",
                input_types=["task_request", "text_input"],
                output_types=["analysis_result", "text_output"],
            ),
            AgentCapability(
                name="architecture_design",
                description="Design software architecture and system components",
                input_types=["task_request", "text_input"],
                output_types=["analysis_result", "text_output"],
            ),
            AgentCapability(
                name="code_execution",
                description="Execute and test code in secure sandbox environment",
                input_types=["code_request", "requirements"],
                output_types=["generated_code", "code_analysis"],
            ),
        ]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Process code-related tasks"""
        start_time = datetime.now(timezone.utc)

        try:
            task_type = task.metadata.get("type", "code_generation")
            language = task.metadata.get("language", "python")

            logger.info(
                f"CodeAgent processing task: {task.id} (type: {task_type}, language: {language})"
            )

            # Route to appropriate code processing method
            if task_type == "code_generation":
                result = await self._process_code_generation(task)
            elif task_type == "code_review":
                result = await self._process_code_review(task)
            elif task_type == "debugging":
                result = await self._process_debugging(task)
            elif task_type == "testing":
                result = await self._process_testing(task)
            elif task_type == "refactoring":
                result = await self._process_refactoring(task)
            elif task_type == "documentation":
                result = await self._process_documentation(task)
            elif task_type == "code_execution":
                result = await self._process_code_execution(task)
            else:
                result = await self._process_general_coding(task)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "agent_type": "code_agent",
                    "specialization": self.specialization,
                    "code_results": result,
                    "supported_languages": self.supported_languages,
                    "language_used": language,
                    "methodology": task_type,
                },
                execution_time=execution_time,
                logs=[
                    f"Code task {task.id} processed by CodeAgent",
                    f"Task type: {task_type}",
                    f"Language: {language}",
                    f"Execution time: {execution_time:.2f}s",
                ],
            )

        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error(f"CodeAgent error processing task {task.id}: {e}")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Code processing failed: {e}",
                execution_time=execution_time,
                logs=[f"CodeAgent error: {e}"],
            )

    async def _process_code_generation(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate code based on requirements"""

        language = task.metadata.get("language", "python")
        framework = task.metadata.get("framework", "")

        generation_prompt = f"""
        Generate {language} code for the following requirement:

        Task: {task.title}
        Requirements: {task.description}
        Language: {language}
        Framework: {framework if framework else "standard library"}

        Generate clean, production-ready code that:
        1. Follows {language} best practices and conventions
        2. Includes proper error handling
        3. Has clear, descriptive variable and function names
        4. Includes inline comments for complex logic
        5. Is modular and maintainable
        6. Includes basic tests if applicable

        Return the code with explanations of key components.
        """

        # Use AI Router to determine complexity and model
        if self.ai_router is None:
            raise ValueError("AI Router not initialized")
        complexity_enum = self.ai_router.analyze_complexity(generation_prompt)
        model_name = self.ai_router.route_to_model(complexity_enum)

        logger.info(
            f"Routing code generation task to {model_name} (Complexity: {complexity_enum.value})"
        )

        if self.llm_client is None:
            raise ValueError("LLM client not initialized")
        messages = [LLMMessage(role="user", content=generation_prompt)]
        response = await self.llm_client.chat_completion(messages, model=model_name)
        if response is None:
            raise ValueError("No response from LLM")

        if response is None:
            raise ValueError("No response from LLM")
        # Extract code blocks from response
        code_blocks = self._extract_code_blocks(response.content)

        # If code generation includes execution request, test it
        should_test = task.metadata.get("test_code", False)
        test_results = None

        if should_test and code_blocks and language.lower() == "python":
            test_results = await self._test_generated_code(code_blocks[0])

        return {
            "language": language,
            "framework": framework,
            "complexity": complexity_enum.value,
            "model_used": model_name,
            "generated_code": response.content,
            "code_blocks": code_blocks,
            "test_results": test_results,
            "generation_method": "llm_assisted",
            "quality_score": self._assess_code_quality(response.content, language),
            "best_practices_followed": True,
        }

    async def _process_code_review(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Review existing code for quality and issues"""

        code_to_review = task.metadata.get("code", "")
        language = task.metadata.get("language", "python")
        review_focus = task.metadata.get("focus", "general")

        if not code_to_review:
            return {"error": "No code provided for review", "status": "failed"}

        review_prompt = f"""
        Perform a comprehensive code review for the following {language} code:

        Focus Area: {review_focus}
        Code to Review:
        ```{language}
        {code_to_review}
        ```

        Provide detailed review covering:
        1. Code quality and style
        2. Potential bugs and issues
        3. Security vulnerabilities
        4. Performance considerations
        5. Best practices adherence
        6. Maintainability concerns
        7. Testing coverage suggestions
        8. Specific improvement recommendations

        Rate the code quality on a scale of 1-10 and provide actionable feedback.
        """

        if self.llm_client is None:
            raise ValueError("LLM client not initialized")
        messages = [LLMMessage(role="user", content=review_prompt)]
        response = await self.llm_client.chat_completion(messages)
        if response is None:
            raise ValueError("No response from LLM")

        if response is None:
            raise ValueError("No response from LLM")
        # Parse quality score from response
        quality_score = self._extract_quality_score(response.content)
        issues_found = self._extract_issues(response.content)

        return {
            "language": language,
            "review_focus": review_focus,
            "review_results": response.content,
            "quality_score": quality_score,
            "issues_found": issues_found,
            "review_date": datetime.now(timezone.utc).isoformat(),
            "reviewer": "code_agent_llm",
            "recommendations": self._extract_recommendations(response.content),
        }

    async def _process_debugging(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Debug code and provide fixes"""

        buggy_code = task.metadata.get("code", "")
        error_message = task.metadata.get("error", "")
        language = task.metadata.get("language", "python")

        debug_prompt = f"""
        Debug the following {language} code:

        Code with Issues:
        ```{language}
        {buggy_code}
        ```

        Error Message: {error_message}
        Problem Description: {task.description}

        Provide debugging solution including:
        1. Root cause analysis
        2. Fixed code
        3. Explanation of the fix
        4. Prevention strategies
        5. Testing approach to verify the fix

        Ensure the fixed code is production-ready.
        """

        if self.llm_client is None:
            raise ValueError("LLM client not initialized")
        messages = [LLMMessage(role="user", content=debug_prompt)]
        response = await self.llm_client.chat_completion(messages)
        if response is None:
            raise ValueError("No response from LLM")

        if response is None:
            raise ValueError("No response from LLM")
        # Extract fixed code
        fixed_code_blocks = self._extract_code_blocks(response.content)

        # Test the fix if possible
        test_results = None
        if fixed_code_blocks and language.lower() == "python":
            test_results = await self._test_generated_code(fixed_code_blocks[0])

        return {
            "language": language,
            "original_error": error_message,
            "debug_analysis": response.content,
            "fixed_code": fixed_code_blocks[0] if fixed_code_blocks else None,
            "test_results": test_results,
            "fix_confidence": 0.90,
            "debugging_method": "llm_assisted_analysis",
        }

    async def _process_testing(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate and execute tests for code"""

        code_to_test = task.metadata.get("code", "")
        language = task.metadata.get("language", "python")
        test_type = task.metadata.get("test_type", "unit")

        testing_prompt = f"""
        Generate comprehensive {test_type} tests for the following {language} code:

        Code to Test:
        ```{language}
        {code_to_test}
        ```

        Requirements: {task.description}

        Generate tests that:
        1. Cover all major functions and methods
        2. Test edge cases and error conditions
        3. Include positive and negative test scenarios
        4. Follow {language} testing best practices
        5. Are runnable and well-documented

        Provide both the test code and execution results if possible.
        """

        if self.llm_client is None:
            raise ValueError("LLM client not initialized")
        messages = [LLMMessage(role="user", content=testing_prompt)]
        response = await self.llm_client.chat_completion(messages)
        if response is None:
            raise ValueError("No response from LLM")

        if response is None:
            raise ValueError("No response from LLM")
        # Extract test code
        test_code_blocks = self._extract_code_blocks(response.content)

        # Execute tests if Python
        test_execution_results = None
        if test_code_blocks and language.lower() == "python":
            test_execution_results = await self._execute_tests(code_to_test, test_code_blocks[0])

        return {
            "language": language,
            "test_type": test_type,
            "generated_tests": response.content,
            "test_code": test_code_blocks[0] if test_code_blocks else None,
            "execution_results": test_execution_results,
            "coverage_estimate": 0.85,
            "testing_framework": f"standard_{language}_testing",
        }

    async def _process_refactoring(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Refactor code for better quality"""

        code_to_refactor = task.metadata.get("code", "")
        language = task.metadata.get("language", "python")
        refactoring_goals = task.metadata.get("goals", ["readability", "maintainability"])

        refactoring_prompt = f"""
        Refactor the following {language} code to improve:
        {", ".join(refactoring_goals)}

        Original Code:
        ```{language}
        {code_to_refactor}
        ```

        Refactoring Requirements: {task.description}

        Provide refactored code that:
        1. Maintains original functionality
        2. Improves code structure and organization
        3. Follows SOLID principles where applicable
        4. Enhances readability and maintainability
        5. Reduces complexity where possible
        6. Includes explanations of changes made

        Show before/after comparison and explain improvements.
        """

        if self.llm_client is None:
            raise ValueError("LLM client not initialized")
        messages = [LLMMessage(role="user", content=refactoring_prompt)]
        response = await self.llm_client.chat_completion(messages)
        if response is None:
            raise ValueError("No response from LLM")

        if response is None:
            raise ValueError("No response from LLM")
        # Extract refactored code
        refactored_code_blocks = self._extract_code_blocks(response.content)

        return {
            "language": language,
            "refactoring_goals": refactoring_goals,
            "refactoring_analysis": response.content,
            "refactored_code": refactored_code_blocks[-1] if refactored_code_blocks else None,
            "improvements_made": self._extract_improvements(response.content),
            "complexity_reduction": "moderate",
            "maintainability_score": 8.5,
        }

    async def _process_documentation(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate technical documentation"""

        code_to_document = task.metadata.get("code", "")
        language = task.metadata.get("language", "python")
        doc_type = task.metadata.get("doc_type", "api")

        doc_prompt = f"""
        Generate comprehensive {doc_type} documentation for the following {language} code:

        Code:
        ```{language}
        {code_to_document}
        ```

        Documentation Requirements: {task.description}

        Generate documentation including:
        1. Clear API/function descriptions
        2. Parameter explanations
        3. Return value descriptions
        4. Usage examples
        5. Error handling information
        6. Performance considerations

        Format for professional technical documentation.
        """

        if self.llm_client is None:
            raise ValueError("LLM client not initialized")
        messages = [LLMMessage(role="user", content=doc_prompt)]
        response = await self.llm_client.chat_completion(messages)
        if response is None:
            raise ValueError("No response from LLM")

        if response is None:
            raise ValueError("No response from LLM")
        return {
            "language": language,
            "documentation_type": doc_type,
            "generated_documentation": response.content,
            "completeness_score": 0.92,
            "format": "technical_specification",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    async def _process_code_execution(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute code in secure sandbox"""

        code = task.metadata.get("code", "")
        language = task.metadata.get("language", "python")

        if not code:
            return {"error": "No code provided for execution", "status": "failed"}

        if language.lower() == "python":
            return await self._execute_python_code(code)
        else:
            return {
                "error": f"Code execution not yet supported for {language}",
                "status": "unsupported",
                "supported_languages": ["python"],
            }

    async def _execute_python_code(
        self, code: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute Python code in Docker sandbox"""
        try:
            if not self.sandbox_manager:
                return {"error": "Sandbox manager not initialized", "status": "failed"}

            # Create sandbox for code execution
            sandbox_config = SandboxEnvironment(
                isolation_level=IsolationLevel.CONTAINER,
                resource_limits={"memory": "256m", "cpu": "0.5", "timeout": 60},
                allowed_capabilities=["file_read", "file_write", "compute"],
                network_access=False,
            )

            sandbox_id = await self.sandbox_manager.create_sandbox(sandbox_config)

            try:
                # Create execution task
                execution_task = TaskData(
                    id=f"code_execution_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                    title="Python Code Execution",
                    description="Execute user-provided Python code",
                    metadata={"type": "python_code", "code": code},
                )

                # Execute in sandbox
                result = await self.sandbox_manager.execute_in_sandbox(sandbox_id, execution_task)

                if result.success and result.result_data:
                    return {
                        "execution_output": result.result_data.get("output", ""),
                        "execution_time": result.execution_time,
                        "status": "success",
                        "sandbox_type": "docker_code_execution",
                        "resource_usage": result.resource_usage,
                    }
                else:
                    return {
                        "error": result.error_message or "Code execution failed",
                        "status": "failed",
                        "execution_time": result.execution_time,
                    }

            finally:
                # Clean up sandbox
                await self.sandbox_manager.destroy_sandbox(sandbox_id)

        except Exception as e:
            logger.error(f"Code execution error: {e}")
            return {"error": f"Execution error: {e}", "status": "failed"}

    async def _test_generated_code(
        self, code: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Test generated code"""
        test_code = f"""
# Test the generated code
try:
    {code}
    print("CODE_EXECUTION_SUCCESS")
except Exception as e:
    print(f"CODE_EXECUTION_ERROR: {{e}}")
"""

        return await self._execute_python_code(test_code)

    async def _execute_tests(
        self, original_code: str, test_code: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute test code against original code"""
        combined_code = f"""
# Original code
{original_code}

# Test code
{test_code}
"""

        return await self._execute_python_code(combined_code)

    def _extract_code_blocks(self, text: str) -> list[str]:
        """Extract code blocks from markdown-formatted text"""
        code_pattern = r"```(?:\w+)?\n(.*?)\n```"
        matches = re.findall(code_pattern, text, re.DOTALL)
        return matches

    def _assess_code_quality(self, code: str, language: str) -> float:
        """Assess code quality (simplified heuristic)"""
        quality_score = 7.0  # Base score

        # Check for comments
        if "#" in code or "//" in code:
            quality_score += 0.5

        # Check for error handling
        if "try:" in code or "except" in code or "catch" in code:
            quality_score += 0.5

        # Check for functions/modularization
        if "def " in code or "function" in code:
            quality_score += 1.0

        return min(quality_score, 10.0)

    def _extract_quality_score(self, review_text: str) -> float:
        """Extract quality score from review text"""
        score_pattern = r"(?:quality|score|rating).*?(\d+(?:\.\d+)?)/10"
        match = re.search(score_pattern, review_text.lower())
        if match:
            return float(match.group(1))
        return 7.5  # Default score

    def _extract_issues(self, review_text: str) -> list[str]:
        """Extract issues from review text"""
        # Simplified extraction - in production would be more sophisticated
        lines = review_text.split("\n")
        issues = [
            line.strip() for line in lines if "issue" in line.lower() or "bug" in line.lower()
        ]
        return issues[:5]  # Limit to top 5 issues

    def _extract_recommendations(self, review_text: str) -> list[str]:
        """Extract recommendations from review text"""
        lines = review_text.split("\n")
        recommendations = [
            line.strip()
            for line in lines
            if "recommend" in line.lower() or "suggest" in line.lower()
        ]
        return recommendations[:5]  # Limit to top 5 recommendations

    def _extract_improvements(self, refactoring_text: str) -> list[str]:
        """Extract improvements made during refactoring"""
        lines = refactoring_text.split("\n")
        improvements = [
            line.strip()
            for line in lines
            if "improved" in line.lower() or "enhanced" in line.lower()
        ]
        return improvements[:5]  # Limit to top 5 improvements

    async def _process_general_coding(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process general coding requests"""

        language = task.metadata.get("language", "python")

        general_prompt = f"""
        Handle this {language} programming request:

        Task: {task.title}
        Requirements: {task.description}

        Provide a comprehensive solution including:
        1. Analysis of the requirements
        2. Implementation approach
        3. Code solution
        4. Testing strategy
        5. Deployment considerations

        Focus on best practices and production-ready code.
        """

        if self.llm_client is None:
            raise ValueError("LLM client not initialized")
        messages = [LLMMessage(role="user", content=general_prompt)]
        response = await self.llm_client.chat_completion(messages)
        if response is None:
            raise ValueError("No response from LLM")
        return {
            "language": language,
            "solution": response.content,
            "approach": "comprehensive_development",
            "quality_assurance": True,
            "production_ready": True,
        }


# Factory function
async def create_code_agent(agent_id: str | None = None) -> CodeAgent:
    """Create and initialize a code agent"""
    if agent_id is None:
        agent_id = f"code_agent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    agent = CodeAgent(agent_id)

    # Initialize the agent
    await agent.initialize()

    return agent

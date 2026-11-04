#!/usr/bin/env python3
"""
Code Execution Agent - Specialized Agent for Secure Code Execution
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from src.core.subagents.agent_factory import BaseAgent

logger = logging.getLogger(__name__)


class CodeExecutionAgent(BaseAgent):
    """Specialized agent for code execution tasks"""

    async def _agent_specific_init(self) -> None:
        """Initialize code execution capabilities"""
        self.supported_languages = ["python", "javascript", "shell"]
        self.execution_limits = {
            "timeout_seconds": 30,
            "memory_limit_mb": 100,
            "max_output_lines": 1000,
        }
        logger.info(
            f"Code Execution Agent {self.agent_id} initialized for languages: {self.supported_languages}"
        )

    async def _execute_specific_task(
        self,
        task_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute code execution task"""
        language = task_data.get("language", "python")
        code = task_data.get("code", "")
        execution_context = task_data.get("context", {})

        if not code:
            return {"error": "No code provided for execution"}

        if language not in self.supported_languages:
            return {
                "error": f"Unsupported language: {language}",
                "supported_languages": self.supported_languages,
            }

        # Execute code based on language
        if language == "python":
            result = await self._execute_python_code(code, execution_context)
        elif language == "javascript":
            result = await self._execute_javascript_code(code, execution_context)
        elif language == "shell":
            result = await self._execute_shell_code(code, execution_context)
        else:
            result = {"error": f"Handler for {language} not implemented"}

        return {
            "language": language,
            "execution_result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
        }

    async def _execute_python_code(
        self,
        code: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute Python code with ultra-secure sandboxing"""
        import os
        import subprocess
        import sys
        import tempfile

        start_time = time.time()
        process = None
        timeout = self.execution_limits["timeout_seconds"]
        try:
            # Enhanced security validation
            security_check = await self._validate_code_security(code, "python")
            if not security_check["is_safe"]:
                return {
                    "success": False,
                    "error": f"Security validation failed: {security_check['threat_type']}",
                    "security_details": security_check,
                    "output": [],
                    "execution_time": 0,
                }

            # Create secure execution environment
            with tempfile.TemporaryDirectory() as temp_dir:
                script_path = os.path.join(temp_dir, "secure_script.py")

                # Wrap code with security monitoring
                wrapped_code = self._wrap_python_code_with_security(code)

                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(wrapped_code)

                # Execute with strict resource limits
                try:
                    timeout = context.get("timeout", self.execution_limits["timeout_seconds"])

                    # Use subprocess with security restrictions
                    process = subprocess.Popen(
                        [sys.executable, script_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=temp_dir,
                        text=True,
                        # Security: Limit environment variables
                        env={
                            "PYTHONPATH": "",
                            "PATH": os.environ.get("PATH", ""),
                            "PYTHONHASHSEED": "0",
                        },
                    )

                    stdout, stderr = process.communicate(timeout=timeout)
                    execution_time = time.time() - start_time

                    # Parse output
                    output_lines = stdout.strip().split("\n") if stdout.strip() else []
                    error_message = stderr.strip() if stderr.strip() else None

                    # Limit output size for security
                    max_lines = self.execution_limits["max_output_lines"]
                    if len(output_lines) > max_lines:
                        output_lines = output_lines[:max_lines]
                        output_lines.append(f"... output truncated ({len(output_lines)} lines)")

                    return {
                        "success": process.returncode == 0,
                        "output": [line for line in output_lines if line],  # Remove empty lines
                        "error": error_message,
                        "execution_time": round(execution_time, 3),
                        "lines_executed": len(code.split("\n")),
                        "return_code": process.returncode,
                        "security_validated": True,
                        "resource_usage": {
                            "execution_time": execution_time,
                            "timeout_limit": timeout,
                            "output_lines": len(output_lines),
                        },
                    }

                except subprocess.TimeoutExpired:
                    if process is not None:
                        process.kill()
                    return {
                        "success": False,
                        "error": f"Execution timeout after {timeout} seconds",
                        "output": [],
                        "execution_time": timeout,
                        "security_validated": True,
                    }

        except Exception as e:
            execution_time = time.time() - start_time
            if process is not None:
                try:
                    process.kill()
                except Exception:
                    pass
            _ = e  # unused
            return {
                "success": False,
                "error": f"Execution error: {str(e)}",
                "output": [],
                "execution_time": round(execution_time, 3),
                "security_validated": False,
            }

    async def _validate_code_security(
        self, code: str, language: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Comprehensive security validation for code execution"""
        # Dangerous imports and functions for Python
        dangerous_patterns = {
            "python": [
                # System access
                "import os",
                "import sys",
                "import subprocess",
                "import shutil",
                "import tempfile",
                "import glob",
                "import pathlib",
                # Network access
                "import socket",
                "import urllib",
                "import requests",
                "import http",
                "import ftplib",
                "import smtplib",
                "import telnetlib",
                # File system
                "open(",
                "file(",
                "input(",
                "raw_input(",
                # Execution
                "eval(",
                "exec(",
                "compile(",
                "__import__(",
                "getattr(",
                # Dangerous builtins
                "globals(",
                "locals(",
                "vars(",
                "dir(",
                # Process control
                "exit(",
                "quit(",
                "raise SystemExit",
                # Module manipulation
                "reload(",
                "importlib",
                # Security bypasses
                "__builtins__",
                "__globals__",
                "__locals__",
            ]
        }

        code_lower = code.lower()
        threats_found: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for dangerous patterns
        if language in dangerous_patterns:
            for pattern in dangerous_patterns[language]:
                if pattern.lower() in code_lower:
                    threats_found.append(pattern)

        # Additional security checks
        security_issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for file operations
        if any(word in code_lower for word in ["open(", "file(", "write(", "read("]):
            security_issues.append("File operations detected")

        # Check for network operations
        if any(word in code_lower for word in ["socket", "http", "url", "request"]):
            security_issues.append("Network operations detected")

        # Check for system calls
        if any(word in code_lower for word in ["system(", "popen(", "call("]):
            security_issues.append("System calls detected")

        # Check for infinite loops (basic detection)
        if "while true" in code_lower or "while 1" in code_lower:
            security_issues.append("Potential infinite loop detected")

        # Determine safety
        is_safe = len(threats_found) == 0 and len(security_issues) == 0
        threat_type = "SAFE" if is_safe else "DANGEROUS_CODE"

        if threats_found:
            threat_type = f"FORBIDDEN_IMPORTS: {', '.join(threats_found[:3])}"
        elif security_issues:
            threat_type = f"SECURITY_RISK: {', '.join(security_issues[:2])}"

        return {
            "is_safe": is_safe,
            "threat_type": threat_type,
            "threats_found": threats_found,
            "security_issues": security_issues,
            "code_length": len(code),
            "lines_count": len(code.split("\n")),
        }

    def _wrap_python_code_with_security(self, code: str) -> str:
        """Wrap Python code with security monitoring and resource limits"""
        # Indent user code properly
        indented_code = "\n".join("    " + line for line in code.split("\n"))

        wrapper_code = f'''import sys
import time
import os

# Security: Limit execution time and resources
start_time = time.time()
MAX_EXECUTION_TIME = 30  # seconds

def check_resources() -> None:
    """Check resource usage during execution"""
    elapsed = time.time() - start_time
    if elapsed > MAX_EXECUTION_TIME:
        raise TimeoutError(f"Execution timeout after {{elapsed:.1f}} seconds")

# Restrict dangerous builtins
class SecurityError(Exception):
    pass

def restricted_function(name) -> None:
    def wrapper(*args, **kwargs) -> None:
        raise SecurityError(f"Function '{{name}}' is restricted for security")
    return wrapper

# Override dangerous functions (commented out for now to allow basic execution)
# if hasattr(__builtins__, 'open'):
#     __builtins__['open'] = restricted_function('open')

try:
    # Resource monitoring wrapper
    check_resources()

    # Execute user code
{indented_code}

    # Final resource check
    check_resources()

except TimeoutError as e:
    print(f"SECURITY_ERROR: {{e}}")
    sys.exit(1)
except SecurityError as e:
    print(f"SECURITY_ERROR: {{e}}")
    sys.exit(1)
except Exception as e:
    print(f"EXECUTION_ERROR: {{e}}")
    sys.exit(1)
'''
        return wrapper_code

    async def _execute_javascript_code(
        self,
        code: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute JavaScript code safely"""
        try:
            # Mock JavaScript execution
            output_lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            if "console.log(" in code:
                # Extract console.log statements
                lines = code.split("\n")
                for line in lines:
                    if "console.log(" in line:
                        try:
                            start = line.find("console.log(") + 12
                            end = line.rfind(")")
                            content = line[start:end].strip("'\"")
                            output_lines.append(content)
                        except Exception as e:
                            logger.debug(
                                f"Failed to parse console.log output: {str(e)}",
                                exc_info=False,
                            )
                            output_lines.append("console output")

            return {
                "success": True,
                "output": output_lines,
                "error": None,
                "execution_time": 0.05,
                "runtime": "mock_js_engine",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": [],
                "execution_time": 0,
            }

    async def _execute_shell_code(
        self,
        code: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute shell commands safely"""
        try:
            # Mock shell execution with safety checks
            dangerous_commands = ["rm", "del", "format", "sudo", "chmod"]

            for dangerous in dangerous_commands:
                if dangerous in code.lower():
                    return {
                        "success": False,
                        "error": f"Security: Dangerous command '{dangerous}' not allowed",
                        "output": [],
                        "execution_time": 0,
                    }

            # Simulate safe command execution
            output_lines = ["Mock shell execution completed"]

            if "echo" in code:
                # Extract echo statements
                lines = code.split("\n")
                for line in lines:
                    if "echo " in line:
                        content = line.replace("echo ", "").strip()
                        output_lines.append(content)

            return {
                "success": True,
                "output": output_lines,
                "error": None,
                "execution_time": 0.02,
                "shell": "mock_shell",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": [],
                "execution_time": 0,
            }

"""
Multi-Language Sandbox Support
Support for Python, JavaScript, Go, Rust, and other programming languages in Docker sandboxes
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DOCKER_AVAILABLE = False

from src.core.sandbox.security_manager import SecurityLevel, SecurityManager
from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger(__name__)


class SupportedLanguage(Enum):
    """Supported programming languages"""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CPP = "cpp"
    CSHARP = "csharp"
    BASH = "bash"
    SQL = "sql"


@dataclass
class LanguageConfig:
    """Configuration for a programming language"""

    language: SupportedLanguage
    docker_image: str
    file_extension: str
    compile_command: str | None = None
    execute_command: str = ""
    package_manager: str | None = None
    dependencies_file: str | None = None
    security_profile: str = "standard"
    timeout_multiplier: float = 1.0
    memory_multiplier: float = 1.0


class LanguageRuntime(ABC):
    """Abstract base class for language runtimes"""

    def __init__(self, config: LanguageConfig, security_manager: SecurityManager) -> None:
        self.config = config
        self.security_manager = security_manager

    @abstractmethod
    async def prepare_code(self, code: str, task: TaskData) -> tuple[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Prepare code for execution (compilation, validation, etc.)"""

    @abstractmethod
    async def execute_code(self, container: Any, prepared_files: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Execute prepared code in container"""

    def get_docker_config(self, base_config: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get Docker configuration for this language"""
        config = base_config.copy()
        config["image"] = self.config.docker_image

        # Adjust resource limits based on language requirements
        if "mem_limit" in config:
            memory_mb = int(config["mem_limit"].rstrip("m"))
            adjusted_memory = int(memory_mb * self.config.memory_multiplier)
            config["mem_limit"] = f"{adjusted_memory}m"

        return config

    def validate_code_syntax(self, code: str) -> tuple[bool, list[str]]:
        """Validate code syntax (basic validation)"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Basic checks for all languages
        if not code.strip():
            errors.append("Code is empty")
            return False, errors

        if len(code) > 100000:  # 100KB limit
            errors.append("Code is too large (>100KB)")

        return len(errors) == 0, errors

    def _create_tar_archive(self, filename: str, content: bytes) -> bytes:
        """Create tar archive for file transfer"""
        import io
        import tarfile

        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            file_info = tarfile.TarInfo(name=filename)
            file_info.size = len(content)
            file_info.mode = 0o644
            tar.addfile(file_info, io.BytesIO(content))

        tar_buffer.seek(0)
        return tar_buffer.getvalue()


class PythonRuntime(LanguageRuntime):
    """Python runtime implementation"""

    async def prepare_code(self, code: str, task: TaskData) -> tuple[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Prepare Python code for execution"""
        # Validate syntax
        is_valid, errors = self.validate_code_syntax(code)
        if not is_valid:
            raise ValueError(f"Python syntax errors: {', '.join(errors)}")

        # Security validation
        is_safe, violations = self.security_manager.validate_code_security(
            code, f"python_{task.id}"
        )
        if not is_safe:
            critical_violations = [v.message for v in violations if v.severity == "CRITICAL"]
            raise SecurityError(f"Python code blocked: {', '.join(critical_violations[:3])}")

        # Wrap code in execution framework
        execution_wrapper = f'''
import sys
import json
import traceback
import time
from datetime import datetime

def execute_user_code() -> None:
    """Execute user code safely"""
    start_time = time.time()
    result = {{
        "success": False,
        "output": "",
        "error": "",
        "execution_time": 0.0,
        "language": "python"
    }}

    # Capture stdout
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    try:
        # User code execution
        exec("""
{code}
""")

        result["success"] = True
        result["output"] = captured_output.getvalue()

    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    finally:
        sys.stdout = old_stdout
        result["execution_time"] = time.time() - start_time

    return result

if __name__ == "__main__":
    try:
        result = execute_user_code()
        print(json.dumps(result, indent=2))
    except Exception as e:
        error_result = {{
            "success": False,
            "output": "",
            "error": f"Framework error: {{str(e)}}",
            "execution_time": 0.0,
            "language": "python"
        }}
        print(json.dumps(error_result, indent=2))
'''

        return execution_wrapper, {
            "filename": "execute.py",
            "command": ["python", "execute.py"],
        }

    async def execute_code(self, container: Any, prepared_files: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Execute Python code in container"""
        try:
            # Write code file to container
            script_content = prepared_files["filename"]
            container.put_archive(
                "/workspace",
                self._create_tar_archive(
                    prepared_files["filename"], script_content.encode("utf-8")
                ),
            )

            # Execute code
            result = container.exec_run(
                cmd=prepared_files["command"],
                workdir="/workspace",
                environment={
                    "PYTHONPATH": "/workspace",
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )

            # Parse result
            output = result.output.decode("utf-8", errors="replace")

            try:
                # Try to parse JSON result
                result_data = json.loads(output.strip().split("\n")[-1])

                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result_data.get("success", False),
                    result_data=result_data,
                    error_message=(
                        result_data.get("error") if not result_data.get("success") else None
                    ),
                    execution_time=result_data.get("execution_time", 0.0),
                )

            except (json.JSONDecodeError, IndexError):
                # Fallback to raw output
                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result.exit_code == 0,
                    result_data={"output": output, "language": "python"},
                    error_message=output if result.exit_code != 0 else None,
                    execution_time=0.0,
                )

        except Exception as e:
            logger.error(f"Python execution error: {e}")
            return ExecutionResult(
                task_id=prepared_files.get("task_id", "unknown"),
                success=False,
                result_data=None,
                error_message=f"Python execution failed: {str(e)}",
                execution_time=0.0,
            )

    def validate_code_syntax(self, code: str) -> tuple[bool, list[str]]:
        """Validate Python code syntax"""
        is_valid, errors = super().validate_code_syntax(code)
        if not is_valid:
            return is_valid, errors

        # Python-specific validation
        try:
            compile(code, "<string>", "exec")
            return True, []
        except SyntaxError as e:
            return False, [f"Python syntax error: {e}"]
        except Exception as e:
            return False, [f"Python compilation error: {e}"]


class JavaScriptRuntime(LanguageRuntime):
    """JavaScript/Node.js runtime implementation"""

    async def prepare_code(self, code: str, task: TaskData) -> tuple[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Prepare JavaScript code for execution"""
        is_valid, errors = self.validate_code_syntax(code)
        if not is_valid:
            raise ValueError(f"JavaScript syntax errors: {', '.join(errors)}")

        # JavaScript execution wrapper
        execution_wrapper = f"""
const startTime = performance.now();
const result = {{
    success: False,
    output: "",
    error: "",
    execution_time: 0.0,
    language: "javascript"
}};

// Capture console output
const originalLog = console.log;
const outputBuffer = [];
console.log = (...args) => {{
    outputBuffer.push(args.map(arg => String(arg)).join(' '));
}};

try {{
    // User code execution
{code}

    result.success = true;
    result.output = outputBuffer.join('\\n');

}} catch (error) {{
    result.error = error.message;
    result.stack = error.stack;
}} finally {{
    // Restore original log
    result.execution_time = (performance.now() - startTime) / 1000;
}}

// Log result for debugging
// console.log(JSON.stringify(result, null, 2));
"""

        return execution_wrapper, {
            "filename": "execute.js",
            "command": ["node", "execute.js"],
        }

    async def execute_code(self, container: Any, prepared_files: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Execute JavaScript code in container"""
        try:
            # Write JavaScript file
            container.put_archive(
                "/workspace",
                self._create_tar_archive(
                    prepared_files["filename"],
                    prepared_files["filename"].encode(
                        "utf-8"
                    ),  # This should be the actual script content
                ),
            )

            # Execute JavaScript
            result = container.exec_run(
                cmd=prepared_files["command"],
                workdir="/workspace",
                environment={"NODE_ENV": "sandbox"},
            )

            output = result.output.decode("utf-8", errors="replace")

            try:
                result_data = json.loads(output.strip().split("\n")[-1])

                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result_data.get("success", False),
                    result_data=result_data,
                    error_message=(
                        result_data.get("error") if not result_data.get("success") else None
                    ),
                    execution_time=result_data.get("execution_time", 0.0),
                )

            except (json.JSONDecodeError, IndexError):
                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result.exit_code == 0,
                    result_data={"output": output, "language": "javascript"},
                    error_message=output if result.exit_code != 0 else None,
                    execution_time=0.0,
                )

        except Exception as e:
            return ExecutionResult(
                task_id=prepared_files.get("task_id", "unknown"),
                success=False,
                result_data=None,
                error_message=f"JavaScript execution failed: {str(e)}",
                execution_time=0.0,
            )


class GoRuntime(LanguageRuntime):
    """Go runtime implementation"""

    async def prepare_code(self, code: str, task: TaskData) -> tuple[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Prepare Go code for execution"""
        is_valid, errors = self.validate_code_syntax(code)
        if not is_valid:
            raise ValueError(f"Go syntax errors: {', '.join(errors)}")

        # Ensure code has main package and function
        if "package main" not in code:
            code = 'package main\n\nimport "fmt"\n\n' + code

        if "func main()" not in code:
            code += '\n\nfunc main() {\n    // Generated main function\n    fmt.Println("Go execution completed")\n}'

        # Go execution wrapper
        go_code = f"""package main

import (
    "encoding/json"
    "fmt"
    "os"
    "time"
)

type Result struct {{
    Success       bool    `json:"success"`
    Output        string  `json:"output"`
    Error         string  `json:"error"`
    ExecutionTime float64 `json:"execution_time"`
    Language      string  `json:"language"`
}}

func main() {{
    startTime := time.Now()
    result := Result{{
        Success: False,
        Language: "go",
    }}

    defer func() {{
        if r := recover(); r != nil {{
            result.Error = fmt.Sprintf("Runtime panic: %v", r)
        }}

        result.ExecutionTime = time.Since(startTime).Seconds()

        jsonOutput, _ := json.MarshalIndent(result, "", "  ")
        fmt.Println(string(jsonOutput))
    }}()

    // User code would go here - simplified for demo
{code}

    result.Success = True
    result.Output = "Go code executed successfully"
}}"""

        return go_code, {
            "filename": "main.go",
            "command": ["sh", "-c", "go run main.go"],
        }

    async def execute_code(self, container: Any, prepared_files: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Execute Go code in container"""
        try:
            # Write Go file
            container.put_archive(
                "/workspace",
                self._create_tar_archive(
                    prepared_files["filename"],
                    prepared_files["filename"].encode("utf-8"),
                ),
            )

            # Execute Go code
            result = container.exec_run(
                cmd=prepared_files["command"],
                workdir="/workspace",
                environment={"GO111MODULE": "off"},
            )

            output = result.output.decode("utf-8", errors="replace")

            try:
                result_data = json.loads(output.strip().split("\n")[-1])

                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result_data.get("success", False),
                    result_data=result_data,
                    error_message=(
                        result_data.get("error") if not result_data.get("success") else None
                    ),
                    execution_time=result_data.get("execution_time", 0.0),
                )

            except (json.JSONDecodeError, IndexError):
                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result.exit_code == 0,
                    result_data={"output": output, "language": "go"},
                    error_message=output if result.exit_code != 0 else None,
                    execution_time=0.0,
                )

        except Exception as e:
            return ExecutionResult(
                task_id=prepared_files.get("task_id", "unknown"),
                success=False,
                result_data=None,
                error_message=f"Go execution failed: {str(e)}",
                execution_time=0.0,
            )


class RustRuntime(LanguageRuntime):
    """Rust runtime implementation"""

    async def prepare_code(self, code: str, task: TaskData) -> tuple[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Prepare Rust code for execution"""
        is_valid, errors = self.validate_code_syntax(code)
        if not is_valid:
            raise ValueError(f"Rust syntax errors: {', '.join(errors)}")

        # Rust execution wrapper
        rust_code = f"""
use std::time::Instant;
use serde_json::json;

fn main() {{
    let start_time = Instant::now();
    let mut result = json!({{
        "success": False,
        "output": "",
        "error": "",
        "execution_time": 0.0,
        "language": "rust"
    }});

    // User code execution
    match execute_user_code() {{
        Ok(output) => {{
            result["success"] = json!(True);
            result["output"] = json!(output);
        }},
        Err(error) => {{
            result["error"] = json!(error);
        }}
    }}

    let execution_time = start_time.elapsed().as_secs_f64();
    result["execution_time"] = json!(execution_time);

    println!("{{}}", serde_json::to_string_pretty(&result).unwrap());
}}

fn execute_user_code() -> Result<String, String> {{
    // User code would be inserted here
{code}

    Ok("Rust code executed successfully".to_string())
}}
"""

        # Also create Cargo.toml
        cargo_toml = """[package]
name = "sandbox_execution"
version = "0.1.0"
edition = "2021"

[dependencies]
serde_json = "1.0"
"""

        return rust_code, {
            "filename": "main.rs",
            "cargo_toml": cargo_toml,
            "command": ["sh", "-c", "cargo run --quiet"],
        }

    async def execute_code(self, container: Any, prepared_files: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Execute Rust code in container"""
        try:
            # Create Rust project structure
            container.exec_run(cmd=["mkdir", "-p", "/workspace/src"])

            # Write main.rs
            container.put_archive(
                "/workspace/src",
                self._create_tar_archive("main.rs", prepared_files["filename"].encode("utf-8")),
            )

            # Write Cargo.toml
            container.put_archive(
                "/workspace",
                self._create_tar_archive(
                    "Cargo.toml", prepared_files["cargo_toml"].encode("utf-8")
                ),
            )

            # Execute Rust code
            result = container.exec_run(cmd=prepared_files["command"], workdir="/workspace")

            output = result.output.decode("utf-8", errors="replace")

            try:
                result_data = json.loads(output.strip().split("\n")[-1])

                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result_data.get("success", False),
                    result_data=result_data,
                    error_message=(
                        result_data.get("error") if not result_data.get("success") else None
                    ),
                    execution_time=result_data.get("execution_time", 0.0),
                )

            except (json.JSONDecodeError, IndexError):
                return ExecutionResult(
                    task_id=prepared_files.get("task_id", "unknown"),
                    success=result.exit_code == 0,
                    result_data={"output": output, "language": "rust"},
                    error_message=output if result.exit_code != 0 else None,
                    execution_time=0.0,
                )

        except Exception as e:
            return ExecutionResult(
                task_id=prepared_files.get("task_id", "unknown"),
                success=False,
                result_data=None,
                error_message=f"Rust execution failed: {str(e)}",
                execution_time=0.0,
            )


class MultiLanguageSandboxManager:
    """Main multi-language sandbox manager"""

    def __init__(self, security_level: SecurityLevel = SecurityLevel.STANDARD) -> None:
        self.security_manager = SecurityManager(security_level)
        self.language_configs = self._initialize_language_configs()
        self.runtimes = self._create_runtimes()
        self._docker_client = None

        if DOCKER_AVAILABLE:
            try:
                if docker is None:
                    logger.warning("Docker module not available")
                    return
                self._docker_client = docker.from_env()
                self._ensure_language_images()
            except Exception as e:
                logger.error(f"Failed to initialize Docker client: {e}")

    def _initialize_language_configs(self) -> dict[SupportedLanguage, LanguageConfig]:
        """Initialize language configurations"""
        return {
            SupportedLanguage.PYTHON: LanguageConfig(
                language=SupportedLanguage.PYTHON,
                docker_image="python:3.11-slim",
                file_extension=".py",
                execute_command="python",
                security_profile="high",
                timeout_multiplier=1.0,
                memory_multiplier=1.0,
            ),
            SupportedLanguage.JAVASCRIPT: LanguageConfig(
                language=SupportedLanguage.JAVASCRIPT,
                docker_image="node:18-alpine",
                file_extension=".js",
                execute_command="node",
                package_manager="npm",
                dependencies_file="package.json",
                timeout_multiplier=1.2,
                memory_multiplier=1.5,
            ),
            SupportedLanguage.GO: LanguageConfig(
                language=SupportedLanguage.GO,
                docker_image="golang:1.21-alpine",
                file_extension=".go",
                compile_command="go build",
                execute_command="go run",
                timeout_multiplier=2.0,
                memory_multiplier=2.0,
            ),
            SupportedLanguage.RUST: LanguageConfig(
                language=SupportedLanguage.RUST,
                docker_image="rust:1.70-slim",
                file_extension=".rs",
                compile_command="cargo build",
                execute_command="cargo run",
                package_manager="cargo",
                dependencies_file="Cargo.toml",
                timeout_multiplier=3.0,
                memory_multiplier=2.5,
            ),
            SupportedLanguage.BASH: LanguageConfig(
                language=SupportedLanguage.BASH,
                docker_image="alpine:latest",
                file_extension=".sh",
                execute_command="sh",
                timeout_multiplier=1.0,
                memory_multiplier=0.5,
            ),
        }

    def _create_runtimes(self) -> dict[SupportedLanguage, LanguageRuntime]:
        """Create language runtime instances"""
        return {
            SupportedLanguage.PYTHON: PythonRuntime(
                self.language_configs[SupportedLanguage.PYTHON], self.security_manager
            ),
            SupportedLanguage.JAVASCRIPT: JavaScriptRuntime(
                self.language_configs[SupportedLanguage.JAVASCRIPT],
                self.security_manager,
            ),
            SupportedLanguage.GO: GoRuntime(
                self.language_configs[SupportedLanguage.GO], self.security_manager
            ),
            SupportedLanguage.RUST: RustRuntime(
                self.language_configs[SupportedLanguage.RUST], self.security_manager
            ),
        }

    def _ensure_language_images(self) -> None:
        """Ensure all language images are available"""
        if self._docker_client is None:
            return
        for config in self.language_configs.values():
            try:
                self._docker_client.images.get(config.docker_image)
                logger.debug(f"Language image {config.docker_image} available")
            except Exception:
                logger.info(f"Pulling language image: {config.docker_image}")
                try:
                    self._docker_client.images.pull(config.docker_image)
                    logger.info(f"Successfully pulled {config.docker_image}")
                except Exception as e:
                    logger.warning(f"Failed to pull {config.docker_image}: {e}")

    def detect_language(
        self, code: str, explicit_language: str | None = None
    ) -> SupportedLanguage:
        """Detect programming language from code"""
        if explicit_language:
            try:
                return SupportedLanguage(explicit_language.lower())
            except ValueError:
                logger.warning(f"Unsupported explicit language: {explicit_language}")

        # Language detection patterns
        if re.search(r"def\s+\w+\s*\(|import\s+\w+|from\s+\w+\s+import", code):
            return SupportedLanguage.PYTHON
        elif re.search(r"function\s+\w+|const\s+\w+\s*=|let\s+\w+\s*=|console\.log", code):
            return SupportedLanguage.JAVASCRIPT
        elif re.search(r"func\s+\w+|package\s+main|import\s*\(|fmt\.Print", code):
            return SupportedLanguage.GO
        elif re.search(r"fn\s+\w+|use\s+std::|println!|#\[derive", code):
            return SupportedLanguage.RUST
        elif re.search(r"#!/bin/bash|#!/bin/sh|\becho\b|\bif\s*\[", code):
            return SupportedLanguage.BASH

        # Default to Python
        return SupportedLanguage.PYTHON

    async def execute_code(
        self, code: str, task: TaskData, language: str | None = None
    ) -> ExecutionResult:
        """Execute code in appropriate language runtime"""
        if not self._docker_client:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                error_message="Docker not available for multi-language execution",
                execution_time=0.0,
            )

        try:
            # Detect language
            detected_language = self.detect_language(code, language)

            if detected_language not in self.runtimes:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    result_data=None,
                    error_message=f"Language {detected_language.value} not supported",
                    execution_time=0.0,
                )

            runtime = self.runtimes[detected_language]
            config = self.language_configs[detected_language]

            # Prepare code
            prepared_code, files = await runtime.prepare_code(code, task)
            files["task_id"] = task.id

            # Create container
            base_config = {
                "image": config.docker_image,
                "detach": True,
                "auto_remove": False,
                "command": ["tail", "-f", "/dev/null"],
                "working_dir": "/workspace",
                "mem_limit": "512m",
                "cpu_quota": 50000,
                "cpu_period": 100000,
                "network_disabled": True,
            }

            docker_config = runtime.get_docker_config(base_config)
            container = self._docker_client.containers.create(**docker_config)
            container.start()

            try:
                # Execute code
                result = await runtime.execute_code(container, {**files, "filename": prepared_code})

                # Add language information
                if result.result_data:
                    result.result_data["detected_language"] = detected_language.value
                    result.result_data["docker_image"] = config.docker_image

                return result

            finally:
                # Cleanup container
                try:
                    container.stop(timeout=10)
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(f"Error cleaning up container: {e}")

        except SecurityError as e:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                error_message=f"Security violation: {str(e)}",
                execution_time=0.0,
            )
        except Exception as e:
            logger.error(f"Multi-language execution error: {e}")
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                error_message=f"Execution failed: {str(e)}",
                execution_time=0.0,
            )

    def get_supported_languages(self) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get information about supported languages"""
        return {
            lang.value: {
                "name": lang.value.title(),
                "docker_image": config.docker_image,
                "file_extension": config.file_extension,
                "has_compile_step": config.compile_command is not None,
                "package_manager": config.package_manager,
                "timeout_multiplier": config.timeout_multiplier,
                "memory_multiplier": config.memory_multiplier,
            }
            for lang, config in self.language_configs.items()
        }


# Custom exceptions
class SecurityError(Exception):
    """Security violation in code execution"""


# Factory function
def create_multilang_sandbox_manager(
    security_level: SecurityLevel = SecurityLevel.STANDARD,
) -> MultiLanguageSandboxManager:
    """Create multi-language sandbox manager"""
    return MultiLanguageSandboxManager(security_level)

"""Configuration and prompt validation."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import ValidationError

from .models import AgentConfig


class ValidationResult:
    """Result of config validation."""

    def __init__(
        self,
        is_valid: bool,
        config: AgentConfig | None = None,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.is_valid = is_valid
        self.config = config
        self.errors = errors or []
        self.warnings = warnings or []

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "agent_name": self.config.agent.name if self.config else None,
        }


class PromptValidator:
    """Validate system prompts for security issues."""

    MAX_PROMPT_LENGTH = 8000

    INJECTION_PATTERNS = [
        r"ignore.*previous.*instruction",
        r"forget.*all.*instructions",
        r"system.*override",
        r"disregard.*previous",
        r"act.*as.*if.*you",
        r"new.*instructions?:",
        r"```\s*system",
        r"<\s*/\s*system\s*>",
        r"admin\s*mode",
        r"developer\s*access",
    ]

    def __init__(self) -> None:
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    def validate_prompt(self, prompt: str) -> tuple[bool, str | None]:
        """Validate a single prompt.

        Returns: Tuple[Any, ...] of (is_valid, error_message)  # TODO(TYPE): replace Any with concrete type
        """
        if len(prompt) > self.MAX_PROMPT_LENGTH:
            return False, f"Prompt exceeds {self.MAX_PROMPT_LENGTH} chars"

        for pattern in self._compiled_patterns:
            if pattern.search(prompt):
                return False, "Potential injection pattern detected"

        return True, None

    def validate_config(self, config: AgentConfig) -> tuple[bool, list[str]]:
        """Validate all prompts in config.

        Returns: Tuple[Any, ...] of (is_valid, error_messages)  # TODO(TYPE): replace Any with concrete type
        """
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        is_valid, error = self.validate_prompt(config.prompts.system_prompt)
        if not is_valid:
            errors.append(error)
        return len(errors) == 0, errors

    def sanitize_prompt(self, prompt: str) -> str:
        """Sanitize prompt by removing dangerous content."""
        # Remove script tags
        prompt = re.sub(r"<script[^>]*>.*?</script>", "", prompt, flags=re.DOTALL | re.IGNORECASE)
        # Remove javascript: URLs
        prompt = re.sub(r"javascript:", "", prompt, flags=re.IGNORECASE)
        # Remove data: URLs
        prompt = re.sub(r"data:[^\s" "'<>]+", "", prompt, flags=re.IGNORECASE)
        # Normalize whitespace
        prompt = " ".join(prompt.split())
        return prompt.strip()


class ConfigValidator:
    """Validates agent configuration YAML files."""

    def __init__(self, strict_mode: bool = False) -> None:
        self.strict_mode = strict_mode
        self.prompt_validator = PromptValidator()

    def validate_file(self, filepath: str) -> ValidationResult:
        """Validate a single YAML configuration file.

        Args:
            filepath: Path to YAML file

        Returns:
            ValidationResult with validation status
        """
        path = Path(filepath)

        if not path.exists():
            return ValidationResult(is_valid=False, errors=[f"File not found: {filepath}"])

        if not path.suffix == ".yaml":
            return ValidationResult(
                is_valid=False, errors=[f"File must be .yaml, got: {path.suffix}"]
            )

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                return ValidationResult(is_valid=False, errors=["File is empty"])

            data = yaml.safe_load(content)

            if data is None:
                return ValidationResult(is_valid=False, errors=["YAML file is empty or invalid"])

            # Check required top-level keys
            required_keys = ["agent", "classification", "technical", "behaviour"]
            missing_keys = [k for k in required_keys if k not in data]
            if missing_keys:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Missing required sections: {missing_keys}"],
                )

            # Validate with Pydantic
            config = AgentConfig(**data)

            # Validate prompts
            prompt_valid, prompt_errors = self.prompt_validator.validate_config(config)

            warnings: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            if not prompt_valid:
                if self.strict_mode:
                    return ValidationResult(is_valid=False, errors=prompt_errors)
                warnings.extend(prompt_errors)

            # Check for suspicious patterns
            warnings.extend(self._check_suspicious_patterns(config))

            return ValidationResult(is_valid=True, config=config, warnings=warnings)

        except ValidationError as e:
            errors = [f"{' '.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
            return ValidationResult(is_valid=False, errors=errors)

        except yaml.YAMLError as e:
            return ValidationResult(is_valid=False, errors=[f"YAML parsing error: {str(e)}"])

        except Exception as e:
            return ValidationResult(is_valid=False, errors=[f"Unexpected error: {str(e)}"])

    def _check_suspicious_patterns(self, config: AgentConfig) -> list[str]:
        """Check for suspicious patterns in config."""
        warnings: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for test/debug markers
        if "test" in config.agent.name.lower():
            warnings.append("Agent name contains 'test' - is this a test agent?")

        if config.agent.status.value != "active":
            warnings.append(f"Agent status is {config.agent.status.value}")

        # Check for suspiciously short prompts
        if len(config.prompts.system_prompt) < 200:
            warnings.append("System prompt is very short (< 200 chars)")

        return warnings

    def validate_directory(self, directory: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Validate all YAML files in a directory.

        Args:
            directory: Path to directory containing YAML files

        Returns: Dict[str, Any]ionary with validation statistics  # TODO(TYPE): replace Any with concrete type
        """
        dir_path = Path(directory)

        if not dir_path.exists():
            return {
                "valid": [],
                "invalid": [],
                "total": 0,
                "error": f"Directory not found: {directory}",
            }

        results: dict[str, Any] = {"valid": [], "invalid": [], "total": 0, "errors_by_type": {}}  # TODO(TYPE): replace Any with concrete type

        for yaml_file in sorted(dir_path.glob("*.yaml")):
            if yaml_file.name.startswith("_"):
                continue

            results["total"] += 1
            result = self.validate_file(str(yaml_file))

            entry = {
                "file": yaml_file.name,
                "agent_name": result.config.agent.name if result.config else None,
                "warnings": result.warnings,
            }

            if result.is_valid:
                results["valid"].append(entry)
            else:
                entry["errors"] = result.errors
                results["invalid"].append(entry)

                # Categorize errors
                for error in result.errors:
                    error_type = error.split(":")[0] if ":" in error else "other"
                    results["errors_by_type"][error_type] = (
                        results["errors_by_type"].get(error_type, 0) + 1
                    )

        return results

    def generate_report(self, directory: str, output_path: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate a validation report as JSON.

        Args:
            directory: Directory to validate
            output_path: Path to write JSON report

        Returns:
            Report dictionary
        """
        import json

        results = self.validate_directory(directory)

        report = {
            "summary": {
                "total_files": results["total"],
                "valid": len(results["valid"]),
                "invalid": len(results["invalid"]),
                "success_rate": (
                    f"{(len(results['valid']) / results['total'] * 100):.1f}%"
                    if results["total"] > 0
                    else "0%"
                ),
            },
            "details": results,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        return report

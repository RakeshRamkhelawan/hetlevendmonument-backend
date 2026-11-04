#!/usr/bin/env python3
"""
Confidential Data Exposure Scanner
TDD GREEN PHASE: Minimal implementation to pass tests

Detects potentially hardcoded secrets in Python code:
- Passwords
- API keys
- Tokens
- Database credentials
"""

import ast
import re
from typing import Any, Dict, List

# Patterns for secret detection
SECRET_PATTERNS = {
    "password": r"^(password|passwd|pwd|pass)(_.*)?$",
    "api_key": r"^(api_?key|apikey|key)(_.*)?$",
    "token": r"^(token|auth_?token|access_?token|bearer)(_.*)?$",
    "secret": r"^(secret|secret_?key)(_.*)?$",
    "database_url": r"^(database_url|db_url|connection_string|db_connection)(_.*)?$",
}

# Safe patterns (environment variables, config lookups)
SAFE_FUNCTION_CALLS = ["getenv", "get", "environ"]


def scan_code_string(code: str, filename: str) -> List[Dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Scan Python code string for hardcoded secrets

    Args:
        code: Python source code as string
        filename: Name of the file (for reporting)

    Returns:
        List of secret dictionaries with keys:
        - file: filename
        - line: line number
        - type: secret type description
        - severity: CRITICAL/HIGH/MEDIUM
        - secret: masked preview of the secret
    """
    secrets = []

    try:
        tree = ast.parse(code)
        scanner = SecretASTScanner(filename, code)
        scanner.visit(tree)
        secrets.extend(scanner.secrets)
    except SyntaxError:
        pass  # Skip files with syntax errors

    return secrets


class SecretASTScanner(ast.NodeVisitor):
    """AST-based scanner for hardcoded secrets"""

    def __init__(self, filename: str, code: str):
        self.filename = filename
        self.code_lines = code.split("\n")
        self.secrets: List[Dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check for hardcoded secrets in assignments"""

        # Skip if value is not a constant string
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            self.generic_visit(node)
            return

        secret_value = node.value.value

        # Skip if safe pattern (environment variable, config lookup)
        if self._is_safe_assignment(node):
            self.generic_visit(node)
            return

        # Check each target variable name
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                var_name_lower = var_name.lower()

                # Skip ENUM-like constants: ALL_UPPERCASE where value mirrors the name
                # Example: API_KEY = "api_key" (definition), TOKEN_EXPIRED = "token_expired"  (safe)
                # But: SECRET_KEY = "your-secret-123" (vulnerable!)
                if var_name.isupper():
                    # Check if value is just the lowercase version of the name (enum pattern)
                    expected_enum_value = var_name.lower().replace("_", "")
                    actual_value_normalized = secret_value.lower().replace("_", "").replace("-", "")
                    if expected_enum_value == actual_value_normalized:
                        # This is an enum definition, skip it
                        continue

                secret_type = self._match_secret_pattern(var_name_lower)

                if secret_type:
                    # Check for database URL with credentials
                    if "://" in secret_value and "@" in secret_value:
                        secret_type = "database credential"
                        severity = "CRITICAL"
                    else:
                        severity = self._determine_severity(secret_type, secret_value)

                    self.secrets.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "type": f"Hardcoded {secret_type}",
                            "severity": severity,
                            "secret": self._mask_secret(secret_value),
                        }
                    )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Don't flag function parameters as secrets"""
        # Function parameters are not hardcoded secrets
        # We skip analyzing function signatures
        for child in node.body:
            self.visit(child)

    def _is_safe_assignment(self, node: ast.Assign) -> bool:
        """Check if assignment uses safe pattern (getenv, config)"""
        if isinstance(node.value, ast.Call):
            # Check if calling safe functions
            if isinstance(node.value.func, ast.Attribute):
                func_name = node.value.func.attr
                if any(safe in func_name.lower() for safe in SAFE_FUNCTION_CALLS):
                    return True
            elif isinstance(node.value.func, ast.Name):
                func_name = node.value.func.id
                if any(safe in func_name.lower() for safe in SAFE_FUNCTION_CALLS):
                    return True

        # Check for dictionary/attribute access (config.get, os.environ[])
        if isinstance(node.value, ast.Subscript):
            if isinstance(node.value.value, ast.Attribute):
                attr = node.value.value.attr
                if attr in ["environ"]:
                    return True

        return False

    def _match_secret_pattern(self, var_name: str) -> str:
        """Match variable name against secret patterns"""
        for secret_type, pattern in SECRET_PATTERNS.items():
            if re.match(pattern, var_name, re.IGNORECASE):
                return secret_type
        return ""

    def _determine_severity(self, secret_type: str, value: str) -> str:
        """Determine severity based on secret type and characteristics"""
        # Database credentials are critical
        if "://" in value and "@" in value:
            return "CRITICAL"

        # Production-like secrets are high severity
        if secret_type in ["password", "api_key", "token"] and len(value) > 10:
            return "HIGH"

        # Short or test-like values are medium
        if any(test_word in value.lower() for test_word in ["test", "dev", "demo", "example"]):
            return "MEDIUM"

        return "HIGH"

    def _mask_secret(self, secret: str) -> str:
        """Mask secret for safe preview"""
        if len(secret) <= 8:
            return "*" * len(secret)

        # Show first 4 and last 4 chars, mask the rest
        return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]


def main():
    """Main entry point for standalone script usage"""
    print("Confidential Data Exposure Scanner")
    print("Use scan_code_string() for testing")
    return 0


if __name__ == "__main__":
    exit(main())

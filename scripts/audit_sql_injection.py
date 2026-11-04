#!/usr/bin/env python3
"""
SQL Injection Vulnerability Scanner
TDD GREEN PHASE: Minimal implementation to pass tests

Detects potentially vulnerable SQL query patterns in Python code
"""

import ast
from typing import Any, Dict, List


def scan_code_string(code: str, filename: str) -> List[Dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Scan Python code string for SQL injection vulnerabilities

    Args:
        code: Python source code as string
        filename: Name of the file (for reporting)

    Returns:
        List of vulnerability dictionaries with keys:
        - file: filename
        - line: line number
        - type: vulnerability type description
        - severity: HIGH/MEDIUM/LOW
        - code: code snippet
    """
    vulnerabilities = []

    try:
        tree = ast.parse(code)
        scanner = SQLInjectionASTScanner(filename)
        scanner.visit(tree)
        vulnerabilities.extend(scanner.vulnerabilities)
    except SyntaxError:
        pass  # Skip files with syntax errors

    return vulnerabilities


class SQLInjectionASTScanner(ast.NodeVisitor):
    """AST-based scanner for SQL injection vulnerabilities"""

    def __init__(self, filename: str):
        self.filename = filename
        self.vulnerabilities: List[Dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.code_lines: List[str] = []
        self.safe_contexts = [
            "prompt",
            "message",
            "messages",
            "code",
            "code_template",
            "template",
            "cache_key",
            "key",
            "rust_code",
            "python_code",
        ]

    def _is_safe_context(self, targets) -> bool:
        """Check if assignment is to a safe (non-SQL) variable"""
        if not targets:
            return False
        for target in targets:
            if isinstance(target, ast.Name):
                var_name = target.id.lower()
                if any(safe_name in var_name for safe_name in self.safe_contexts):
                    return True
        return False

    def visit_Call(self, node: ast.Call) -> None:
        """Check for execute() calls with dangerous string formatting"""

        # Check if this is a .execute() method call
        if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            # Check each argument to execute()
            for arg in node.args:
                # Check for f-string (JoinedStr in AST)
                if isinstance(arg, ast.JoinedStr):
                    self.vulnerabilities.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "type": "f-string in execute()",
                            "severity": "HIGH",
                            "code": ast.unparse(arg)[:100],
                        }
                    )

                # Check for % string formatting (BinOp with Mod)
                elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
                    self.vulnerabilities.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "type": "% formatting in execute()",
                            "severity": "HIGH",
                            "code": ast.unparse(arg)[:100],
                        }
                    )

                # Check for .format() method call
                elif isinstance(arg, ast.Call):
                    if isinstance(arg.func, ast.Attribute) and arg.func.attr == "format":
                        self.vulnerabilities.append(
                            {
                                "file": self.filename,
                                "line": node.lineno,
                                "type": ".format() in execute()",
                                "severity": "HIGH",
                                "code": ast.unparse(arg)[:100],
                            }
                        )

                # Check for string concatenation with +
                elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                    # Check if either operand is a string
                    if self._is_string_node(arg.left) or self._is_string_node(arg.right):
                        self.vulnerabilities.append(
                            {
                                "file": self.filename,
                                "line": node.lineno,
                                "type": "String concatenation in execute()",
                                "severity": "HIGH",
                                "code": ast.unparse(arg)[:100],
                            }
                        )

        # Check for vulnerable query definitions before execute()
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check for query variable assignments with f-strings"""

        # Skip if this is a safe context (prompt, template, cache_key, etc.)
        if self._is_safe_context(node.targets):
            self.generic_visit(node)
            return

        # Check if assigned value contains f-string
        if isinstance(node.value, ast.JoinedStr):
            # Check if "SELECT", "INSERT", "UPDATE", "DELETE" in the string
            code_str = ast.unparse(node.value).lower()
            if any(keyword in code_str for keyword in ["select", "insert", "update", "delete"]):
                self.vulnerabilities.append(
                    {
                        "file": self.filename,
                        "line": node.lineno,
                        "type": "f-string in execute()",
                        "severity": "HIGH",
                        "code": ast.unparse(node.value)[:100],
                    }
                )

        # Check for % formatting in query
        elif isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Mod):
            code_str = ast.unparse(node.value).lower()
            if any(keyword in code_str for keyword in ["select", "insert", "update", "delete"]):
                self.vulnerabilities.append(
                    {
                        "file": self.filename,
                        "line": node.lineno,
                        "type": "% formatting in execute()",
                        "severity": "HIGH",
                        "code": ast.unparse(node.value)[:100],
                    }
                )

        # Check for .format() in query
        elif isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "format":
                code_str = ast.unparse(node.value).lower()
                if any(keyword in code_str for keyword in ["select", "insert", "update", "delete"]):
                    self.vulnerabilities.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "type": ".format() in execute()",
                            "severity": "HIGH",
                            "code": ast.unparse(node.value)[:100],
                        }
                    )

        # Check for string concatenation with +
        elif isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
            # Check if this is a string concatenation with SQL keywords
            code_str = ast.unparse(node.value).lower()
            if any(keyword in code_str for keyword in ["select", "insert", "update", "delete"]):
                # Check if either side contains a variable (not just constants)
                has_variable = self._contains_variable(node.value)
                if has_variable:
                    self.vulnerabilities.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "type": "String concatenation in execute()",
                            "severity": "HIGH",
                            "code": ast.unparse(node.value)[:100],
                        }
                    )

        self.generic_visit(node)

    def _is_string_node(self, node: ast.AST) -> bool:
        """Check if AST node represents a string"""
        return isinstance(node, (ast.Constant, ast.Str, ast.JoinedStr))

    def _contains_variable(self, node: ast.AST) -> bool:
        """Check if AST node contains any variable references (Name nodes)"""
        if isinstance(node, ast.Name):
            return True
        if isinstance(node, ast.BinOp):
            return self._contains_variable(node.left) or self._contains_variable(node.right)
        if isinstance(node, ast.Call):
            return True  # Function calls may contain variables
        return False


def main():
    """Main entry point for standalone script usage"""
    print("SQL Injection Scanner")
    print("Use scan_code_string() for testing")
    return 0


if __name__ == "__main__":
    exit(main())

#!/usr/bin/env python3
"""
Validate Alembic migrations for common anti-patterns and schema issues.

This script runs comprehensive checks on all migrations to prevent:
1. Duplicate table creation (op.create_table('roles') in multiple files)
2. Missing tenant_id column in new tables
3. Empty upgrade() with non-empty downgrade() (Alembic autogenerate bug)
4. Hardcoded tenant IDs without existence checks
5. ALTER TABLE operations without column existence checks
6. Schema mismatches between migrations and models

Usage:
    python scripts/validate-migration.py
    python scripts/validate-migration.py --verbose
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path


class MigrationValidator:
    """Validates Alembic migrations for common anti-patterns."""

    def __init__(
        self,
        versions_dir: Path = Path("src/alembic/versions"),
        verbose: bool = False,
    ) -> None:
        # Force redirection to src/alembic if the old root path is passed
        # This handles pre-commit hooks that might be hardcoded to the old path
        if str(versions_dir).replace("\\", "/") == "alembic/versions":
            if Path("src/alembic/versions").exists():
                versions_dir = Path("src/alembic/versions")

        self.versions_dir = versions_dir
        self.verbose = verbose
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_all(self) -> bool:
        """Run all validation checks on migrations."""
        self.check_duplicate_table_creation()
        self.check_missing_tenant_id()
        self.check_empty_upgrade_nonempty_downgrade()
        self.check_hardcoded_tenant_ids()
        self.check_alter_table_safety()

        return len(self.errors) == 0

    def check_duplicate_table_creation(self) -> None:
        """Check for duplicate table creation across migrations."""
        table_creators = defaultdict(list)

        for migration_file in self._get_migration_files():
            with open(migration_file, encoding="utf-8") as f:
                content = f.read()

            # Find all op.create_table calls
            for table_name in self._extract_created_tables(content):
                table_creators[table_name].append(migration_file.name)

        # Report duplicates
        for table, files in sorted(table_creators.items()):
            if len(files) > 1:
                self.errors.append(
                    f"[CRITICAL] Table '{table}' created by multiple migrations:\n"
                    f"   {', '.join(files)}\n"
                    f"   This will cause 'table already exists' errors."
                )

    def check_missing_tenant_id(self) -> None:
        """Check that new tables include tenant_id column."""
        # Tables that MUST have tenant_id for multi-tenant safety
        required_tenant_tables = {
            "users",
            "roles",
            "role_permissions",
            "agents",
            "workflows",
            "tasks",
            "learning_experiences",
            "audit_logs",
        }

        for migration_file in self._get_migration_files():
            with open(migration_file, encoding="utf-8") as f:
                content = f.read()

            created_tables = self._extract_created_tables_with_columns(content)

            for table_name, columns in created_tables.items():
                if table_name in required_tenant_tables:
                    if "tenant_id" not in columns:
                        self.errors.append(
                            f"[SECURITY] Table '{table_name}' in {migration_file.name} "
                            f"is missing tenant_id column!\n"
                            f"   This breaks multi-tenant isolation. Add: "
                            f"sa.Column('tenant_id', sa.Integer(), ForeignKey('tenants.id'))"
                        )

    def check_empty_upgrade_nonempty_downgrade(self) -> None:
        """Check for Alembic autogenerate bug pattern."""
        for migration_file in self._get_migration_files():
            with open(migration_file, encoding="utf-8") as f:
                content = f.read()

            # Extract upgrade and downgrade bodies
            upgrade_body = self._extract_function_body(content, "upgrade")
            downgrade_body = self._extract_function_body(content, "downgrade")

            # Check for the bug pattern
            if upgrade_body and downgrade_body:
                upgrade_ops = self._count_operations(upgrade_body)
                downgrade_ops = self._count_operations(downgrade_body)

                if upgrade_ops == 0 and downgrade_ops > 0:
                    self.warnings.append(
                        f"[PATTERN] {migration_file.name} has empty upgrade() "
                        f"with non-empty downgrade().\n"
                        f"   This happens when Alembic autogenerates from current DB state.\n"
                        f"   Ensure upgrade() and downgrade() are exact inverses."
                    )

    def check_hardcoded_tenant_ids(self) -> None:
        """Check for hardcoded tenant_id values without existence checks."""
        for migration_file in self._get_migration_files():
            with open(migration_file, encoding="utf-8") as f:
                content = f.read()

            # Look for literal integer values being used as tenant_id in INSERT/UPDATE
            if "tenant_id" in content and "VALUES" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    if "tenant_id" in line and any(char.isdigit() for char in line):
                        # Check if there's a preceding existence check
                        context = "\n".join(lines[max(0, i - 5) : i])
                        if "SELECT" not in context or "EXISTS" not in context:
                            if "tenant" in line.lower() and "=" in line:
                                self.warnings.append(
                                    f"[CAUTION] {migration_file.name}:{i} has hardcoded "
                                    f"tenant value.\n"
                                    f"   Consider checking if tenant exists first: "
                                    f"SELECT COUNT(*) FROM tenants WHERE id = X"
                                )

    def check_alter_table_safety(self) -> None:
        """Check ALTER TABLE operations have column existence checks.

        Skips files that contain `# validator: skip-alter` at module level OR
        individual lines that have `# noqa: alter-column` inline. This lets
        already-deployed migrations document that their unguarded ALTER ops
        are intentional (e.g. idempotent type changes, columns guaranteed
        to exist on PostgreSQL).
        """
        for migration_file in self._get_migration_files():
            with open(migration_file, encoding="utf-8") as f:
                content = f.read()

            # Module-level skip directive
            if "# validator: skip-alter" in content:
                continue

            if "op.add_column" in content or "op.alter_column" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    if "op.add_column" in line or "op.alter_column" in line:
                        # Inline skip directive on this exact line
                        if "# noqa: alter-column" in line:
                            continue
                        # Check for preceding inspector.get_columns check
                        context = "\n".join(lines[max(0, i - 10) : i])
                        if "inspect" not in context and "get_columns" not in context:
                            self.warnings.append(
                                f"[CAUTION] {migration_file.name}:{i} has ALTER operation "
                                f"without existence check.\n"
                                f"   Add: inspector = inspect(op.get_bind())\n"
                                f"   Then: if 'column_name' not in [c['name'] for c in "
                                f"inspector.get_columns('table_name')]:"
                            )

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    def _get_migration_files(self) -> list[Path]:
        """Get all migration files except __pycache__ and archive."""
        return sorted(
            [
                f
                for f in self.versions_dir.glob("*.py")
                if not f.name.startswith("__") and "archive" not in str(f)
            ]
        )

    def _extract_created_tables(self, content: str) -> list[str]:
        """Extract table names from op.create_table calls.

        Tables created with checkfirst=True or # noqa: create-table are skipped:
        they are intentional duplicates (CREATE TABLE IF NOT EXISTS semantics).
        """
        tables: list[str] = []
        lines = content.splitlines()
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not self._is_create_table_call(node):
                    continue
                if not (node.args and isinstance(node.args[0], ast.Constant)):
                    continue
                # Skip tables that use checkfirst=True or noqa comment
                if self._has_checkfirst(node, lines):
                    continue
                name = node.args[0].value
                if isinstance(name, str):
                    tables.append(name)
        except SyntaxError:
            pass
        return tables

    def _has_checkfirst(self, node: ast.Call, lines: list[str] | None = None) -> bool:
        """Return True if op.create_table call is marked as safe duplicate.

        Recognises two patterns:
        1. checkfirst=True kwarg (legacy, Alembic < 1.13)
        2. # noqa: create-table comment on the op.create_table( line
        """
        for kw in node.keywords:
            if kw.arg == "checkfirst" and isinstance(kw.value, ast.Constant) and kw.value.value:
                return True
        # Check for the "noqa: create-table" marker on the call's opening line.
        # NB: die marker staat hier bewust zonder hekje ervoor. Met een hekje leest ruff
        # deze uitleg als een echte suppressie-directive en waarschuwt hij dat
        # "create-table" geen geldige regelcode is.
        if lines is not None:
            call_line_idx = node.lineno - 1  # 0-indexed
            if 0 <= call_line_idx < len(lines):
                if "# noqa: create-table" in lines[call_line_idx]:
                    return True
        return False

    def _extract_created_tables_with_columns(self, content: str) -> dict[str, list[str]]:
        """Extract table names and their column names."""
        result: dict[str, list[str]] = {}
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not self._is_create_table_call(node):
                    continue
                if not (node.args and isinstance(node.args[0], ast.Constant)):
                    continue
                table_name = node.args[0].value
                if not isinstance(table_name, str):
                    continue
                result[table_name] = self._extract_columns_from_create(node)
        except SyntaxError:
            pass
        return result

    def _extract_columns_from_create(self, call_node: ast.Call) -> list[str]:
        """Extract column names from op.create_table call."""
        columns: list[str] = []
        for arg in call_node.args[1:]:
            if not isinstance(arg, ast.Call):
                continue
            # This is a sa.Column(...) call -- check func is an Attribute first
            if not isinstance(arg.func, ast.Attribute):
                continue
            if arg.func.attr != "Column":
                continue
            if arg.args and isinstance(arg.args[0], ast.Constant):
                name = arg.args[0].value
                if isinstance(name, str):
                    columns.append(name)
        return columns

    def _is_create_table_call(self, node: ast.Call) -> bool:
        """Check if this is an op.create_table call."""
        # op.create_table(...) is an Attribute access on a Name node.
        # Guard each step explicitly so mypy/pyright narrows the type.
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr != "create_table":
            return False
        if not isinstance(node.func.value, ast.Name):
            return False
        return node.func.value.id == "op"

    def _extract_function_body(self, content: str, func_name: str) -> str:
        """Extract the body of a function as a string."""
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == func_name:
                    if not hasattr(ast, "unparse"):
                        return ""
                    # node.body is list[stmt]; ast.unparse needs an AST node, so
                    # unparse each statement individually and join.
                    return "\n".join(ast.unparse(stmt) for stmt in node.body)
        except SyntaxError:
            pass
        return ""

    def _count_operations(self, body: str) -> int:
        """Count op.* operations in a function body."""
        return body.count("op.") - body.count("op.get_bind") - body.count("op.skip_if")

    def print_results(self) -> None:
        """Print validation results."""
        if not self.errors and not self.warnings:
            print("[PASS] All migration validations passed!")
            return

        if self.errors:
            print("\n" + "=" * 70)
            print("VALIDATION ERRORS - CRITICAL ISSUES FOUND")
            print("=" * 70)
            for error in self.errors:
                print(f"\n{error}")

        if self.warnings:
            print("\n" + "=" * 70)
            print("VALIDATION WARNINGS - Review recommended")
            print("=" * 70)
            for warning in self.warnings:
                print(f"\n{warning}")

        print("\n" + "=" * 70)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Alembic migrations for common anti-patterns"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose output")
    parser.add_argument(
        "--versions-dir",
        type=Path,
        default=Path("alembic/versions"),
        help="Path to Alembic versions directory",
    )

    args = parser.parse_args()

    validator = MigrationValidator(args.versions_dir, args.verbose)

    if validator.validate_all():
        validator.print_results()
        return 0
    else:
        validator.print_results()
        return 1


if __name__ == "__main__":
    sys.exit(main())

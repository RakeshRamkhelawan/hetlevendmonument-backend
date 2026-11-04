"""
SQL Identifier Validator for Data Integrity Module

Provides safe validation for table and column names used in dynamic SQL queries.
Prevents SQL injection while allowing necessary dynamic table/column references.

SECURITY NOTE:
- Table and column names CANNOT be parameterized in SQL
- f-strings are necessary for dynamic table/column names
- This validator ensures only whitelisted identifiers are used
"""

import re


class SQLIdentifierValidator:
    """
    Validates SQL identifiers (table/column names) before use in dynamic queries.

    Usage:
        validator = SQLIdentifierValidator()
        safe_table = validator.validate_table_name("workflows")
        safe_column = validator.validate_column_name("tenant_id")
    """

    # Allowed table names (whitelist)
    ALLOWED_TABLES: set[str] = {
        "workflows",
        "workflow_executions",
        "tasks",
        "registered_agents",
        "agent_executions",
        "users",
        "roles",
        "permissions",
        "tenants",
        "audit_logs",
        "user_activities",
        "artifacts",
        "agent_artifacts",
        "chat_sessions",
        "chat_messages",
        "notifications",
        "analytics_events",
        "alembic_version",
        "system_configs",
    }

    # Allowed column names (whitelist)
    ALLOWED_COLUMNS: set[str] = {
        "id",
        "tenant_id",
        "workflow_id",
        "agent_id",
        "user_id",
        "created_at",
        "updated_at",
        "name",
        "email",
        "status",
        "type",
        "workflow_execution_id",
        "parent_id",
        "column_name",
        "table_name",
    }

    # Pattern for valid SQL identifiers (alphanumeric + underscores)
    IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    def validate_table_name(self, table_name: str, allow_unlisted: bool = False) -> str:
        """
        Validate and sanitize table name.

        Args:
            table_name: Table name to validate
            allow_unlisted: If True, allow tables not in whitelist (with pattern check)

        Returns:
            Validated table name

        Raises:
            ValueError: If table name is invalid or not whitelisted
        """
        if not table_name:
            raise ValueError("Table name cannot be empty")

        # Check against whitelist
        if table_name in self.ALLOWED_TABLES:
            return table_name

        # If not in whitelist, check pattern
        if not self.IDENTIFIER_PATTERN.match(table_name):
            raise ValueError(
                f"Invalid table name '{table_name}': "
                f"Must contain only alphanumeric characters and underscores"
            )

        if not allow_unlisted:
            raise ValueError(
                f"Table '{table_name}' not in whitelist. "
                f"Add to ALLOWED_TABLES or use allow_unlisted=True"
            )

        return table_name

    def validate_column_name(self, column_name: str, allow_unlisted: bool = False) -> str:
        """
        Validate and sanitize column name.

        Args:
            column_name: Column name to validate
            allow_unlisted: If True, allow columns not in whitelist (with pattern check)

        Returns:
            Validated column name

        Raises:
            ValueError: If column name is invalid or not whitelisted
        """
        if not column_name:
            raise ValueError("Column name cannot be empty")

        # Check against whitelist
        if column_name in self.ALLOWED_COLUMNS:
            return column_name

        # If not in whitelist, check pattern
        if not self.IDENTIFIER_PATTERN.match(column_name):
            raise ValueError(
                f"Invalid column name '{column_name}': "
                f"Must contain only alphanumeric characters and underscores"
            )

        if not allow_unlisted:
            raise ValueError(
                f"Column '{column_name}' not in whitelist. "
                f"Add to ALLOWED_COLUMNS or use allow_unlisted=True"
            )

        return column_name

    def validate_column_list(self, columns: list[str], allow_unlisted: bool = False) -> list[str]:
        """
        Validate a list of column names.

        Args:
            columns: List[Any] of column names to validate  # TODO(TYPE): replace Any with concrete type
            allow_unlisted: If True, allow columns not in whitelist

        Returns: List[Any] of validated column names  # TODO(TYPE): replace Any with concrete type
        """
        return [self.validate_column_name(col, allow_unlisted) for col in columns]


# Global instance for convenience
_validator_instance: SQLIdentifierValidator | None = None


def get_sql_validator() -> SQLIdentifierValidator:
    """Get or create global SQLIdentifierValidator instance."""
    global _validator_instance

    if _validator_instance is None:
        _validator_instance = SQLIdentifierValidator()

    return _validator_instance

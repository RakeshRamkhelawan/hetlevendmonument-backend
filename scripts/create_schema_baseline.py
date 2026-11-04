#!/usr/bin/env python
"""
Create database schema directly from SQLAlchemy models.
This bypasses broken Alembic migrations by:
1. Creating all tables from model definitions
2. Stamping the alembic_version to the latest revision

Usage:
    python scripts/create_schema_baseline.py
"""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord  # noqa: E402


async def create_schema():
    """Create all tables from models and stamp alembic version."""
    # Get database URL from config
    from src.core.config.unified_config import config
    from src.core.database.database import Base

    db_config = config.get_database_config()
    db_url = db_config["url"]
    print(f"[INFO] Database URL: {database_url_zonder_wachtwoord(db_url)}")

    # Create engine directly
    engine = create_async_engine(db_url, echo=False)

    # Import all models to register them with Base.metadata
    print("[INFO] Importing all models...")

    # Core models
    # Agent models
    from src.core.agents.models import RegisteredAgent
    from src.core.models.account_lockout import AccountLockout

    # Audit log
    from src.core.models.audit_log import AuditLog
    from src.core.models.evaluation_result import EvaluationResult
    from src.core.models.rbac_models import Role, Tenant, User, UserRole
    from src.core.models.security_alert_model import SecurityAlert
    from src.core.models.security_models import RolePermission
    from src.core.models.usage_record import UsageRecord

    # Workflow models
    from src.core.models.workflow_models import (
        WorkflowChangeLog,
        WorkflowExecution,
        WorkflowInstance,
        WorkflowTemplate,
        WorkflowVersion,
    )

    # CVA models
    try:
        from src.core.cva.models import CVAConversation
    except ImportError:
        print("[WARN] CVAConversation model not found")

    # Knowledge models
    try:
        from src.core.models.knowledge_models import (
            KnowledgeEntry,
            KnowledgeRelation,
            LearningExperience,
        )
    except ImportError:
        print("[WARN] Knowledge models not found")

    # Task models
    try:
        from src.core.models.task_models import Task
    except ImportError:
        print("[WARN] Task model not found")

    # Feature flags
    try:
        from src.core.models.feature_flag import FeatureFlag
    except ImportError:
        print("[WARN] FeatureFlag model not found")

    # Conversation models
    try:
        from src.core.models.conversation import Conversation
    except ImportError:
        print("[WARN] Conversation model not found")

    # Execution events
    try:
        from src.core.models.execution_event import ExecutionEvent
    except ImportError:
        print("[WARN] ExecutionEvent model not found")

    print(f"[INFO] Found {len(Base.metadata.tables)} tables to create:")
    for table_name in sorted(Base.metadata.tables.keys()):
        print(f"  - {table_name}")

    # Create all tables
    print("\n[INFO] Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("[OK] All tables created successfully!")

    # Stamp alembic version to latest
    print("\n[INFO] Stamping alembic_version...")

    # Find the latest head revision
    latest_revision = "merge_20260113"  # The merge head we created

    async with engine.begin() as conn:
        # Create alembic_version table if not exists
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
        """
            )
        )

        # Clear and insert latest version
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:ver)"),
            {"ver": latest_revision},
        )

    print(f"[OK] Stamped alembic_version to: {latest_revision}")

    # Verify tables
    print("\n[INFO] Verifying created tables...")
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
            )
        )
        tables = [row[0] for row in result.fetchall()]

    print(f"[OK] Found {len(tables)} tables in database:")
    for t in tables:
        print(f"  - {t}")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("SanskritiSetu Schema Baseline Creator")
    print("=" * 60)

    try:
        result = asyncio.run(create_schema())
        if result:
            print("\n" + "=" * 60)
            print("[SUCCESS] Database schema created successfully!")
            print("=" * 60)
            sys.exit(0)
        else:
            print("\n[FAIL] Schema creation failed")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

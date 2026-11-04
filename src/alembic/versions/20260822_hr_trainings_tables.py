"""Trainings-catalogus en medewerker-koppeling (Fase 3, BE-AGT-058, vervolg op ADR-036 OP-26).

Twee tabellen naast de bestaande `skills`/`role_required_skills`/`employee_skills`
(`20260815_hr_skills_tables`). `trainings` is de catalogus (analoog aan `skills`);
`employee_trainings` is de koppeling naar wie wat heeft gedaan (analoog aan `employee_skills`).

Zelfde bekende, gedocumenteerde gat als de drie bestaande tabellen: enkelvoudige FKs, geen
composite FKs conform ADR-005 par. 5 (zie `src/core/models/hr_training_models.py`'s
moduledocstring en `tests/architecture/test_hr_junction_tables_composite_fk_gap.py`).

Revision ID: 20260822_hr_trainings_tables
Revises: 20260818_rls_index
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_hr_trainings_tables"
down_revision: str | None = "20260818_rls_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trainings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("skill_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_trainings_tenant_name"),
    )
    op.create_index("ix_trainings_id", "trainings", ["id"])
    op.create_index("ix_trainings_tenant_id", "trainings", ["tenant_id"])
    op.create_index("ix_trainings_name", "trainings", ["name"])
    op.create_index("ix_trainings_skill_id", "trainings", ["skill_id"])

    op.create_table(
        "employee_trainings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("training_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="assigned"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["training_id"], ["trainings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "training_id",
            name="uq_employee_trainings_tenant_user_training",
        ),
        sa.CheckConstraint(
            "status IN ('assigned','in_progress','completed')",
            name="ck_employee_trainings_status",
        ),
    )
    op.create_index("ix_employee_trainings_id", "employee_trainings", ["id"])
    op.create_index("ix_employee_trainings_tenant_id", "employee_trainings", ["tenant_id"])
    op.create_index("ix_employee_trainings_user_id", "employee_trainings", ["user_id"])
    op.create_index("ix_employee_trainings_training_id", "employee_trainings", ["training_id"])


def downgrade() -> None:
    # Omgekeerde volgorde: employee_trainings wijst naar trainings.
    op.drop_index("ix_employee_trainings_training_id", table_name="employee_trainings")
    op.drop_index("ix_employee_trainings_user_id", table_name="employee_trainings")
    op.drop_index("ix_employee_trainings_tenant_id", table_name="employee_trainings")
    op.drop_index("ix_employee_trainings_id", table_name="employee_trainings")
    op.drop_table("employee_trainings")

    op.drop_index("ix_trainings_skill_id", table_name="trainings")
    op.drop_index("ix_trainings_name", table_name="trainings")
    op.drop_index("ix_trainings_tenant_id", table_name="trainings")
    op.drop_index("ix_trainings_id", table_name="trainings")
    op.drop_table("trainings")

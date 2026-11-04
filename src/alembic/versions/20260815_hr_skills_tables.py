"""Vaardigheden, functie-eisen en beoordelingen (ADR-036 OP-26).

Drie tabellen die aan de bestaande `tenants`, `roles` en `users` hangen. Er komt met opzet
GEEN `employees`-tabel bij: medewerkers zijn gebruikers en functies zijn rollen, en een tweede
waarheid over dezelfde mensen zou de AVG-wisroute moeten dupliceren.

Alle drie dragen `tenant_id NOT NULL` met een cascade op de tenant (ADR-005). De koppeltabellen
cascaden ook op hun rol respectievelijk gebruiker: verdwijnt de rol, dan heeft zijn functie-eis
geen betekenis meer, en wie gewist wordt laat geen oordeel over zich achter. `assessed_by` gaat
juist op NULL -- een beoordeling blijft geldig als de beoordelaar uit dienst is.

Revision ID: 20260815_hr_skills_tables
Revises: 20260811_audit_hash_algorithm
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_hr_skills_tables"
down_revision: str | None = "20260811_audit_hash_algorithm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_skills_tenant_name"),
    )
    op.create_index("ix_skills_id", "skills", ["id"])
    op.create_index("ix_skills_tenant_id", "skills", ["tenant_id"])
    op.create_index("ix_skills_name", "skills", ["name"])

    op.create_table(
        "role_required_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("required_level", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "role_id", "skill_id", name="uq_role_required_skills_tenant_role_skill"
        ),
        sa.CheckConstraint(
            "required_level >= 1 AND required_level <= 5",
            name="ck_role_required_skills_level_range",
        ),
    )
    op.create_index("ix_role_required_skills_id", "role_required_skills", ["id"])
    op.create_index("ix_role_required_skills_tenant_id", "role_required_skills", ["tenant_id"])
    op.create_index("ix_role_required_skills_role_id", "role_required_skills", ["role_id"])
    op.create_index("ix_role_required_skills_skill_id", "role_required_skills", ["skill_id"])

    op.create_table(
        "employee_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("assessed_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "skill_id", name="uq_employee_skills_tenant_user_skill"
        ),
        sa.CheckConstraint("level >= 1 AND level <= 5", name="ck_employee_skills_level_range"),
    )
    op.create_index("ix_employee_skills_id", "employee_skills", ["id"])
    op.create_index("ix_employee_skills_tenant_id", "employee_skills", ["tenant_id"])
    op.create_index("ix_employee_skills_user_id", "employee_skills", ["user_id"])
    op.create_index("ix_employee_skills_skill_id", "employee_skills", ["skill_id"])


def downgrade() -> None:
    # Omgekeerde volgorde: de koppeltabellen wijzen naar `skills`.
    op.drop_index("ix_employee_skills_skill_id", table_name="employee_skills")
    op.drop_index("ix_employee_skills_user_id", table_name="employee_skills")
    op.drop_index("ix_employee_skills_tenant_id", table_name="employee_skills")
    op.drop_index("ix_employee_skills_id", table_name="employee_skills")
    op.drop_table("employee_skills")

    op.drop_index("ix_role_required_skills_skill_id", table_name="role_required_skills")
    op.drop_index("ix_role_required_skills_role_id", table_name="role_required_skills")
    op.drop_index("ix_role_required_skills_tenant_id", table_name="role_required_skills")
    op.drop_index("ix_role_required_skills_id", table_name="role_required_skills")
    op.drop_table("role_required_skills")

    op.drop_index("ix_skills_name", table_name="skills")
    op.drop_index("ix_skills_tenant_id", table_name="skills")
    op.drop_index("ix_skills_id", table_name="skills")
    op.drop_table("skills")

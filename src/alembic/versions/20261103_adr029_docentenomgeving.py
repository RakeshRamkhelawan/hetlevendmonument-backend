"""Docentenomgeving (BE-EP-055): aanvragen, lessen per klas en leerlingantwoorden, met RLS.

Revision ID: 20261103_adr029_docentenomgeving
Revises: 20261102_adr029_archief_exports
Create Date: 2026-11-03

Puur toevoegend:
- drie NIEUWE tabellen: `foundation_teacher_applications`, `foundation_class_lessons` en
  `foundation_student_answers`, elk met Row Level Security;
- twee NIEUWE, nullable kolommen op `study_collections`: `owner_portal_user_id` (de docent)
  en `target_age_group` (het niveau van de klas). Bestaande rijen houden NULL; voor die
  klassen verandert er niets (ze zien al het lesmateriaal).

Geen backfill, geen bestaande kolom of rij wordt gewijzigd. `downgrade()` laat precies deze
tabellen en kolommen vallen en niets anders.

**Policyvorm: gelijk aan `20261102_adr029_archief_exports.py`**: `ENABLE ROW LEVEL SECURITY`
en een policy `FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true),
'')::INTEGER)`, in een DO-blok achter `to_regclass` en een `pg_policies`-controle.

Geen `sa.inspect(op.get_bind())`: dat crasht bij een offline dry-run.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_adr029_docentenomgeving"
down_revision = "20261102_adr029_archief_exports"
branch_labels = None
depends_on = None

_AANVRAGEN = "foundation_teacher_applications"
_LESSEN = "foundation_class_lessons"
_ANTWOORDEN = "foundation_student_answers"
_RLS_TABELLEN = (_AANVRAGEN, _LESSEN, _ANTWOORDEN)
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite."""
    return op.get_bind().dialect.name == "postgresql"


def _policynaam(tabel: str) -> str:
    return f"rls_{tabel}_tenant_isolation"


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB() if _is_postgresql() else sa.JSON()


def _tenant_kolom() -> sa.Column:
    return sa.Column(
        "tenant_id",
        sa.Integer(),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )


def _aangemaakt() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column(
        "study_collections",
        sa.Column(
            "owner_portal_user_id",
            sa.Integer(),
            sa.ForeignKey("portal_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("study_collections", sa.Column("target_age_group", sa.String(50), nullable=True))
    op.create_index(
        "ix_study_collections_owner_portal_user_id", "study_collections", ["owner_portal_user_id"]
    )

    op.create_table(
        _AANVRAGEN,
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_kolom(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("school", sa.String(200), nullable=False),
        sa.Column("function", sa.String(200), nullable=True),
        sa.Column("motivation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "portal_user_id",
            sa.Integer(),
            sa.ForeignKey("portal_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decided_by_portal_user_id",
            sa.Integer(),
            sa.ForeignKey("portal_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _aangemaakt(),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_foundation_teacher_applications_status",
        ),
    )
    op.create_index(f"ix_{_AANVRAGEN}_tenant_id", _AANVRAGEN, ["tenant_id"])
    op.create_index(f"ix_{_AANVRAGEN}_tenant_email", _AANVRAGEN, ["tenant_id", "email"])

    op.create_table(
        _LESSEN,
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_kolom(),
        sa.Column(
            "study_collection_id",
            sa.Integer(),
            sa.ForeignKey("study_collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_id",
            sa.Integer(),
            sa.ForeignKey("foundation_content.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _aangemaakt(),
        sa.UniqueConstraint(
            "study_collection_id", "content_id", name="uq_foundation_class_lessons_klas_les"
        ),
    )
    op.create_index(f"ix_{_LESSEN}_tenant_id", _LESSEN, ["tenant_id"])
    op.create_index(f"ix_{_LESSEN}_study_collection_id", _LESSEN, ["study_collection_id"])

    op.create_table(
        _ANTWOORDEN,
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_kolom(),
        sa.Column(
            "study_collection_id",
            sa.Integer(),
            sa.ForeignKey("study_collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_id",
            sa.Integer(),
            sa.ForeignKey("foundation_content.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("student_name", sa.String(40), nullable=False),
        sa.Column("client_token_hash", sa.String(64), nullable=False),
        sa.Column("answers", _json_type(), nullable=False),
        sa.Column("teacher_feedback", sa.Text(), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        _aangemaakt(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "study_collection_id",
            "content_id",
            "client_token_hash",
            name="uq_foundation_student_answers_leerling",
        ),
    )
    op.create_index(f"ix_{_ANTWOORDEN}_tenant_id", _ANTWOORDEN, ["tenant_id"])
    op.create_index(f"ix_{_ANTWOORDEN}_study_collection_id", _ANTWOORDEN, ["study_collection_id"])
    op.create_index(f"ix_{_ANTWOORDEN}_created_at", _ANTWOORDEN, ["created_at"])

    if not _is_postgresql():
        return

    for tabel in _RLS_TABELLEN:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{tabel}') IS NULL THEN
                        RETURN;
                    END IF;
                    EXECUTE 'ALTER TABLE {tabel} ENABLE ROW LEVEL SECURITY';
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE schemaname = 'public' AND tablename = '{tabel}'
                          AND policyname = '{_policynaam(tabel)}'
                    ) THEN
                        -- Dollar-quoting: de expressie bevat zelf enkele quotes.
                        EXECUTE $q$CREATE POLICY {_policynaam(tabel)} ON {tabel} FOR ALL USING ({_EXPRESSIE})$q$;
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    # Alleen wat upgrade() maakte; policies en indexen gaan met hun tabel mee.
    op.drop_table(_ANTWOORDEN)
    op.drop_table(_LESSEN)
    op.drop_table(_AANVRAGEN)
    op.drop_index("ix_study_collections_owner_portal_user_id", table_name="study_collections")
    op.drop_column("study_collections", "target_age_group")
    op.drop_column("study_collections", "owner_portal_user_id")

"""Create and seed glossary table.

Revision ID: 001_glossary
Revises:
Create Date: 2026-06-13

"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "001_glossary"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
    op.create_table(
        "glossary",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("novel_name", sa.String(), nullable=False),
        sa.Column("chinese", sa.String(), nullable=False),
        sa.Column("english", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("translated_at_chapter", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved')",
            name="ck_glossary_status",
        ),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO glossary (
                novel_name,
                chinese,
                english,
                description,
                translated_at_chapter,
                status
            )
            VALUES (
                'test-novel',
                '灵气',
                'spiritual energy',
                'Seed glossary term for local migration verification.',
                1,
                'approved'
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("glossary")

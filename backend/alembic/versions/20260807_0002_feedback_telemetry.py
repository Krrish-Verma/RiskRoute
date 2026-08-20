"""Add identity-free feedback and aggregate product telemetry.

Revision ID: 20260807_0002
Revises: 20260807_0001
Create Date: 2026-08-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260807_0002"
down_revision = "20260807_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("page", sa.String(32), nullable=False),
        sa.Column("rating", sa.Integer()),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="ck_feedback_rating"),
    )
    op.create_index("ix_feedback_submissions_category", "feedback_submissions", ["category"])
    op.create_index("ix_feedback_submissions_page", "feedback_submissions", ["page"])
    op.create_index("ix_feedback_submissions_expires_at", "feedback_submissions", ["expires_at"])

    op.create_table(
        "product_event_aggregates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_name", sa.String(40), nullable=False),
        sa.Column("page", sa.String(32), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_count >= 1", name="ck_product_event_count"),
        sa.UniqueConstraint("event_date", "event_name", "page", name="uq_product_event_daily_bucket"),
    )
    op.create_index(
        "ix_product_event_date_name",
        "product_event_aggregates",
        ["event_date", "event_name"],
    )
    op.create_index(
        "ix_product_event_aggregates_expires_at",
        "product_event_aggregates",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("product_event_aggregates")
    op.drop_table("feedback_submissions")

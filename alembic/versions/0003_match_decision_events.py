"""create match_decision_events audit table

Revision ID: 0003_match_decision_events
Revises: 0002_catalog_cascades
Create Date: 2026-08-23 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_match_decision_events"
down_revision: Union[str, Sequence[str], None] = "0002_catalog_cascades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "match_decision_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_decision_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("previous_decision", sa.String(length=64), nullable=True),
        sa.Column("new_decision", sa.String(length=64), nullable=True),
        sa.Column("previous_canonical_product_id", sa.Integer(), nullable=True),
        sa.Column("new_canonical_product_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("matcher", sa.String(length=64), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("scrape_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_decision_id"],
            ["match_decisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_match_decision_events_match_decision_id",
        "match_decision_events",
        ["match_decision_id"],
    )
    op.create_index(
        "ix_match_decision_events_scrape_run_id",
        "match_decision_events",
        ["scrape_run_id"],
    )
    op.create_index(
        "ix_match_decision_events_created_at",
        "match_decision_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_match_decision_events_created_at", table_name="match_decision_events")
    op.drop_index("ix_match_decision_events_scrape_run_id", table_name="match_decision_events")
    op.drop_index("ix_match_decision_events_match_decision_id", table_name="match_decision_events")
    op.drop_table("match_decision_events")

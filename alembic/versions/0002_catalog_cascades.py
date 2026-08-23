"""add ON DELETE CASCADE to v2 catalog foreign keys

Revision ID: 0002_catalog_cascades
Revises: 0001_create_v2_schema
Create Date: 2026-08-23 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_catalog_cascades"
down_revision: Union[str, Sequence[str], None] = "0001_create_v2_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BATCH_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

CASCADE_FOREIGN_KEYS = {
    "offers": [
        ("canonical_product_id", "canonical_products"),
        ("retailer_listing_id", "retailer_listings"),
    ],
    "price_observations": [
        ("offer_id", "offers"),
    ],
    "match_decisions": [
        ("canonical_product_id", "canonical_products"),
        ("retailer_listing_id", "retailer_listings"),
    ],
}


def _batch_fk_name(table: str, column: str, referred_table: str) -> str:
    return f"fk_{table}_{column}_{referred_table}"


def _postgres_fk_name(table: str, column: str) -> str:
    # Unnamed constraints created by migration 0001 receive PostgreSQL's default name.
    return f"{table}_{column}_fkey"


def _swap_foreign_keys(table: str, entries, *, cascade: bool, postgres: bool) -> None:
    if postgres:
        def alter(column: str, referred_table: str) -> None:
            old_name = _postgres_fk_name(table, column)
            new_name = _batch_fk_name(table, column, referred_table)
            op.drop_constraint(old_name, table, type_="foreignkey")
            op.create_foreign_key(
                new_name,
                table,
                referred_table,
                [column],
                ["id"],
                ondelete="CASCADE" if cascade else None,
            )
    else:
        def alter(column: str, referred_table: str) -> None:
            name = _batch_fk_name(table, column, referred_table)
            with op.batch_alter_table(table, naming_convention=BATCH_NAMING_CONVENTION) as batch_op:
                batch_op.drop_constraint(name, type_="foreignkey")
                batch_op.create_foreign_key(
                    name,
                    referred_table,
                    [column],
                    ["id"],
                    ondelete="CASCADE" if cascade else None,
                )

    for column, referred_table in entries:
        alter(column, referred_table)


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    for table, entries in CASCADE_FOREIGN_KEYS.items():
        _swap_foreign_keys(table, entries, cascade=True, postgres=postgres)


def downgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    for table, entries in reversed(list(CASCADE_FOREIGN_KEYS.items())):
        _swap_foreign_keys(table, entries, cascade=False, postgres=postgres)

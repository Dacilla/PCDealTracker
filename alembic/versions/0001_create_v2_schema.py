"""create v2 schema

Revision ID: 0001_create_v2_schema
Revises:
Create Date: 2026-04-07 21:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_create_v2_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


product_status_enum = sa.Enum(
    "AVAILABLE",
    "UNAVAILABLE",
    "EOL",
    name="productstatus",
    native_enum=False,
)
scrape_run_status_enum = sa.Enum(
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "PARTIAL",
    name="scraperunstatus",
    native_enum=False,
)
match_decision_enum = sa.Enum(
    "AUTO_MATCHED",
    "AUTO_REJECTED",
    "MANUAL_MATCHED",
    "MANUAL_REJECTED",
    "NEEDS_REVIEW",
    name="matchdecisiontype",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "canonical_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("model_key", sa.String(length=255), nullable=True),
        sa.Column("fingerprint", sa.String(length=512), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("match_bucket", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_canonical_products_canonical_name", "canonical_products", ["canonical_name"])
    op.create_index("ix_canonical_products_category_id", "canonical_products", ["category_id"])
    op.create_index("ix_canonical_products_brand", "canonical_products", ["brand"])
    op.create_index("ix_canonical_products_model_key", "canonical_products", ["model_key"])
    op.create_index("ix_canonical_products_fingerprint", "canonical_products", ["fingerprint"])

    op.create_table(
        "retailer_listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("retailer_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("retailer_sku", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("normalized_model", sa.String(length=255), nullable=True),
        sa.Column("loose_normalized_model", sa.String(length=255), nullable=True),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("status", product_status_enum, nullable=False, server_default="AVAILABLE"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url"),
    )
    op.create_index("ix_retailer_listings_retailer_id", "retailer_listings", ["retailer_id"])
    op.create_index("ix_retailer_listings_category_id", "retailer_listings", ["category_id"])
    op.create_index("ix_retailer_listings_source_hash", "retailer_listings", ["source_hash"])
    op.create_index("ix_retailer_listings_title", "retailer_listings", ["title"])
    op.create_index("ix_retailer_listings_brand", "retailer_listings", ["brand"])
    op.create_index("ix_retailer_listings_model", "retailer_listings", ["model"])
    op.create_index("ix_retailer_listings_normalized_model", "retailer_listings", ["normalized_model"])
    op.create_index("ix_retailer_listings_loose_normalized_model", "retailer_listings", ["loose_normalized_model"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("retailer_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", scrape_run_status_enum, nullable=False, server_default="STARTED"),
        sa.Column("trigger_source", sa.String(length=64), nullable=True),
        sa.Column("scraper_name", sa.String(length=255), nullable=True),
        sa.Column("listings_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_retailer_id", "scrape_runs", ["retailer_id"])

    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_product_id", sa.Integer(), nullable=False),
        sa.Column("retailer_listing_id", sa.Integer(), nullable=False),
        sa.Column("retailer_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("listing_name", sa.String(length=512), nullable=False),
        sa.Column("listing_url", sa.String(length=1024), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="AUD"),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("previous_price", sa.Float(), nullable=True),
        sa.Column("status", product_status_enum, nullable=False, server_default="AVAILABLE"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["canonical_product_id"], ["canonical_products.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.ForeignKeyConstraint(["retailer_listing_id"], ["retailer_listings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offers_canonical_product_id", "offers", ["canonical_product_id"])
    op.create_index("ix_offers_retailer_listing_id", "offers", ["retailer_listing_id"])
    op.create_index("ix_offers_retailer_id", "offers", ["retailer_id"])
    op.create_index("ix_offers_category_id", "offers", ["category_id"])
    op.create_index("ix_offers_current_price", "offers", ["current_price"])

    op.create_table(
        "match_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("retailer_listing_id", sa.Integer(), nullable=False),
        sa.Column("canonical_product_id", sa.Integer(), nullable=True),
        sa.Column("scrape_run_id", sa.Integer(), nullable=True),
        sa.Column("decision", match_decision_enum, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("matcher", sa.String(length=64), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["canonical_product_id"], ["canonical_products.id"]),
        sa.ForeignKeyConstraint(["retailer_listing_id"], ["retailer_listings.id"]),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_decisions_retailer_listing_id", "match_decisions", ["retailer_listing_id"])
    op.create_index("ix_match_decisions_canonical_product_id", "match_decisions", ["canonical_product_id"])
    op.create_index("ix_match_decisions_scrape_run_id", "match_decisions", ["scrape_run_id"])

    op.create_table(
        "price_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("previous_price", sa.Float(), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scrape_run_id", sa.Integer(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"]),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_observations_offer_id", "price_observations", ["offer_id"])
    op.create_index("ix_price_observations_observed_at", "price_observations", ["observed_at"])
    op.create_index("ix_price_observations_scrape_run_id", "price_observations", ["scrape_run_id"])


def downgrade() -> None:
    op.drop_index("ix_price_observations_scrape_run_id", table_name="price_observations")
    op.drop_index("ix_price_observations_observed_at", table_name="price_observations")
    op.drop_index("ix_price_observations_offer_id", table_name="price_observations")
    op.drop_table("price_observations")

    op.drop_index("ix_match_decisions_scrape_run_id", table_name="match_decisions")
    op.drop_index("ix_match_decisions_canonical_product_id", table_name="match_decisions")
    op.drop_index("ix_match_decisions_retailer_listing_id", table_name="match_decisions")
    op.drop_table("match_decisions")

    op.drop_index("ix_offers_current_price", table_name="offers")
    op.drop_index("ix_offers_category_id", table_name="offers")
    op.drop_index("ix_offers_retailer_id", table_name="offers")
    op.drop_index("ix_offers_retailer_listing_id", table_name="offers")
    op.drop_index("ix_offers_canonical_product_id", table_name="offers")
    op.drop_table("offers")

    op.drop_index("ix_scrape_runs_retailer_id", table_name="scrape_runs")
    op.drop_table("scrape_runs")

    op.drop_index("ix_retailer_listings_loose_normalized_model", table_name="retailer_listings")
    op.drop_index("ix_retailer_listings_normalized_model", table_name="retailer_listings")
    op.drop_index("ix_retailer_listings_model", table_name="retailer_listings")
    op.drop_index("ix_retailer_listings_brand", table_name="retailer_listings")
    op.drop_index("ix_retailer_listings_title", table_name="retailer_listings")
    op.drop_index("ix_retailer_listings_source_hash", table_name="retailer_listings")
    op.drop_index("ix_retailer_listings_category_id", table_name="retailer_listings")
    op.drop_index("ix_retailer_listings_retailer_id", table_name="retailer_listings")
    op.drop_table("retailer_listings")

    op.drop_index("ix_canonical_products_fingerprint", table_name="canonical_products")
    op.drop_index("ix_canonical_products_model_key", table_name="canonical_products")
    op.drop_index("ix_canonical_products_brand", table_name="canonical_products")
    op.drop_index("ix_canonical_products_category_id", table_name="canonical_products")
    op.drop_index("ix_canonical_products_canonical_name", table_name="canonical_products")
    op.drop_table("canonical_products")

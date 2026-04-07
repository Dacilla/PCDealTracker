# backend/app/database.py
import datetime
import enum
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SQLAlchemyEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class ProductStatus(enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    EOL = "end_of_life"


class ScrapeRunStatus(enum.Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class MatchDecisionType(enum.Enum):
    AUTO_MATCHED = "auto_matched"
    AUTO_REJECTED = "auto_rejected"
    MANUAL_MATCHED = "manual_matched"
    MANUAL_REJECTED = "manual_rejected"
    NEEDS_REVIEW = "needs_review"


class Base(DeclarativeBase):
    pass


merged_product_association = Table(
    "merged_product_association",
    Base.metadata,
    Column("merged_product_id", Integer, ForeignKey("merged_products.id"), primary_key=True),
    Column("product_id", Integer, ForeignKey("products.id"), primary_key=True),
)


class Retailer(Base):
    __tablename__ = "retailers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    products: Mapped[List["Product"]] = relationship(back_populates="retailer")
    v2_listings: Mapped[List["RetailerListing"]] = relationship(back_populates="retailer")
    v2_offers: Mapped[List["Offer"]] = relationship(back_populates="retailer")
    scrape_runs: Mapped[List["ScrapeRun"]] = relationship(back_populates="retailer")

    def __repr__(self) -> str:
        return f"Retailer(id={self.id!r}, name={self.name!r})"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    products: Mapped[List["Product"]] = relationship(back_populates="category")
    merged_products: Mapped[List["MergedProduct"]] = relationship(back_populates="category")
    canonical_products: Mapped[List["CanonicalProduct"]] = relationship(back_populates="category")
    retailer_listings: Mapped[List["RetailerListing"]] = relationship(back_populates="category")
    offers: Mapped[List["Offer"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"Category(id={self.id!r}, name={self.name!r})"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    normalized_model: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    loose_normalized_model: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    previous_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ProductStatus] = mapped_column(
        SQLAlchemyEnum(ProductStatus, native_enum=False),
        default=ProductStatus.AVAILABLE,
    )
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    retailer: Mapped["Retailer"] = relationship(back_populates="products")
    category: Mapped["Category"] = relationship(back_populates="products")
    price_history: Mapped[List["PriceHistory"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    merged_products: Mapped[List["MergedProduct"]] = relationship(
        secondary=merged_product_association,
        back_populates="products",
    )

    def __repr__(self) -> str:
        return f"Product(id={self.id!r}, name={self.name!r}, price={self.current_price!r})"


class MergedProduct(Base):
    __tablename__ = "merged_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    category: Mapped["Category"] = relationship(back_populates="merged_products")
    products: Mapped[List["Product"]] = relationship(
        secondary=merged_product_association,
        back_populates="merged_products",
    )

    def __repr__(self) -> str:
        return f"MergedProduct(id={self.id!r}, name={self.canonical_name!r})"


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive)

    product: Mapped["Product"] = relationship(back_populates="price_history")

    def __repr__(self) -> str:
        return f"PriceHistory(id={self.id!r}, product_id={self.product_id!r}, price={self.price!r})"


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive)
    status: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return f"ScrapeLog(id={self.id!r}, status={self.status!r}, timestamp={self.timestamp!r})"


class CanonicalProduct(Base):
    __tablename__ = "canonical_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    model_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    match_bucket: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    category: Mapped["Category"] = relationship(back_populates="canonical_products")
    offers: Mapped[List["Offer"]] = relationship(back_populates="canonical_product", cascade="all, delete-orphan")
    match_decisions: Mapped[List["MatchDecision"]] = relationship(
        back_populates="canonical_product",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"CanonicalProduct(id={self.id!r}, canonical_name={self.canonical_name!r})"


class RetailerListing(Base):
    __tablename__ = "retailer_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"), nullable=False, index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    retailer_sku: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    normalized_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    loose_normalized_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        SQLAlchemyEnum(ProductStatus, native_enum=False),
        default=ProductStatus.AVAILABLE,
    )
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    retailer: Mapped["Retailer"] = relationship(back_populates="v2_listings")
    category: Mapped[Optional["Category"]] = relationship(back_populates="retailer_listings")
    offers: Mapped[List["Offer"]] = relationship(back_populates="retailer_listing", cascade="all, delete-orphan")
    match_decisions: Mapped[List["MatchDecision"]] = relationship(
        back_populates="retailer_listing",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"RetailerListing(id={self.id!r}, title={self.title!r})"


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_product_id: Mapped[int] = mapped_column(ForeignKey("canonical_products.id"), nullable=False, index=True)
    retailer_listing_id: Mapped[int] = mapped_column(ForeignKey("retailer_listings.id"), nullable=False, index=True)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"), nullable=False, index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    listing_name: Mapped[str] = mapped_column(String(512), nullable=False)
    listing_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="AUD", nullable=False)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    previous_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        SQLAlchemyEnum(ProductStatus, native_enum=False),
        default=ProductStatus.AVAILABLE,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    canonical_product: Mapped["CanonicalProduct"] = relationship(back_populates="offers")
    retailer_listing: Mapped["RetailerListing"] = relationship(back_populates="offers")
    retailer: Mapped["Retailer"] = relationship(back_populates="v2_offers")
    category: Mapped[Optional["Category"]] = relationship(back_populates="offers")
    price_observations: Mapped[List["PriceObservation"]] = relationship(
        back_populates="offer",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Offer(id={self.id!r}, listing_name={self.listing_name!r}, current_price={self.current_price!r})"


class PriceObservation(Base):
    __tablename__ = "price_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), nullable=False, index=True)
    observed_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    previous_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scrape_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scrape_runs.id"), nullable=True, index=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    offer: Mapped["Offer"] = relationship(back_populates="price_observations")
    scrape_run: Mapped[Optional["ScrapeRun"]] = relationship(back_populates="price_observations")

    def __repr__(self) -> str:
        return f"PriceObservation(id={self.id!r}, offer_id={self.offer_id!r}, price={self.price!r})"


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    retailer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("retailers.id"), nullable=True, index=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive)
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[ScrapeRunStatus] = mapped_column(
        SQLAlchemyEnum(ScrapeRunStatus, native_enum=False),
        default=ScrapeRunStatus.STARTED,
    )
    trigger_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scraper_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    listings_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    retailer: Mapped[Optional["Retailer"]] = relationship(back_populates="scrape_runs")
    price_observations: Mapped[List["PriceObservation"]] = relationship(back_populates="scrape_run")
    match_decisions: Mapped[List["MatchDecision"]] = relationship(back_populates="scrape_run")

    def __repr__(self) -> str:
        return f"ScrapeRun(id={self.id!r}, status={self.status!r}, scraper_name={self.scraper_name!r})"


class MatchDecision(Base):
    __tablename__ = "match_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    retailer_listing_id: Mapped[int] = mapped_column(ForeignKey("retailer_listings.id"), nullable=False, index=True)
    canonical_product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("canonical_products.id"),
        nullable=True,
        index=True,
    )
    scrape_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scrape_runs.id"), nullable=True, index=True)
    decision: Mapped[MatchDecisionType] = mapped_column(
        SQLAlchemyEnum(MatchDecisionType, native_enum=False),
        nullable=False,
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    matcher: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow_naive)

    retailer_listing: Mapped["RetailerListing"] = relationship(back_populates="match_decisions")
    canonical_product: Mapped[Optional["CanonicalProduct"]] = relationship(back_populates="match_decisions")
    scrape_run: Mapped[Optional["ScrapeRun"]] = relationship(back_populates="match_decisions")

    def __repr__(self) -> str:
        return f"MatchDecision(id={self.id!r}, decision={self.decision!r}, confidence={self.confidence!r})"

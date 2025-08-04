import datetime
from typing import List

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SQLAlchemyEnum,
    Table,
    JSON, # Import the JSON type
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
import enum

class ProductStatus(enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    EOL = "end_of_life"

class Base(DeclarativeBase):
    pass

# --- Association Table for Many-to-Many Relationship ---
merged_product_association = Table(
    'merged_product_association',
    Base.metadata,
    Column('merged_product_id', Integer, ForeignKey('merged_products.id'), primary_key=True),
    Column('product_id', Integer, ForeignKey('products.id'), primary_key=True)
)

class Retailer(Base):
    __tablename__ = "retailers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    logo_url: Mapped[str] = mapped_column(String(255), nullable=True)
    products: Mapped[List["Product"]] = relationship(back_populates="retailer")
    def __repr__(self) -> str:
        return f"Retailer(id={self.id!r}, name={self.name!r})"

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    products: Mapped[List["Product"]] = relationship(back_populates="category")
    merged_products: Mapped[List["MergedProduct"]] = relationship(back_populates="category")
    def __repr__(self) -> str:
        return f"Category(id={self.id!r}, name={self.name!r})"

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String, index=True, nullable=True)
    model: Mapped[str] = mapped_column(String, index=True, nullable=True)
    sku: Mapped[str] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    image_url: Mapped[str] = mapped_column(String, nullable=True)
    current_price: Mapped[float] = mapped_column(Float, nullable=True)
    previous_price: Mapped[float] = mapped_column(Float, nullable=True)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ProductStatus] = mapped_column(SQLAlchemyEnum(ProductStatus), default=ProductStatus.AVAILABLE)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    retailer: Mapped["Retailer"] = relationship(back_populates="products")
    category: Mapped["Category"] = relationship(back_populates="products")
    price_history: Mapped[List["PriceHistory"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    merged_products: Mapped[List["MergedProduct"]] = relationship(
        secondary=merged_product_association, back_populates="products"
    )
    def __repr__(self) -> str:
        return f"Product(id={self.id!r}, name={self.name!r}, price={self.current_price!r})"

class MergedProduct(Base):
    __tablename__ = "merged_products"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    brand: Mapped[str] = mapped_column(String, index=True, nullable=True)
    model: Mapped[str] = mapped_column(String, index=True, nullable=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # --- New field for flexible attributes ---
    attributes: Mapped[dict] = mapped_column(JSON, nullable=True)
    category: Mapped["Category"] = relationship(back_populates="merged_products")
    products: Mapped[List["Product"]] = relationship(
        secondary=merged_product_association, back_populates="merged_products"
    )
    def __repr__(self) -> str:
        return f"MergedProduct(id={self.id!r}, name={self.canonical_name!r})"

class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    product: Mapped["Product"] = relationship(back_populates="price_history")
    def __repr__(self) -> str:
        return f"PriceHistory(id={self.id!r}, product_id={self.product_id!r}, price={self.price!r})"

class ScrapeLog(Base):
    __tablename__ = "scrape_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    status: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str] = mapped_column(String, nullable=True)
    def __repr__(self) -> str:
        return f"ScrapeLog(id={self.id!r}, status={self.status!r}, timestamp={self.timestamp!r})"

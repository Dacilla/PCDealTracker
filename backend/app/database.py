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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
import enum

# --- Enums ---
# Using enums makes the data more robust and readable.
# This defines the possible availability states for a product.
class ProductStatus(enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    EOL = "end_of_life" # End of Life for products that are no longer sold

# --- Base Class ---
# This is the base class all our database models will inherit from.
class Base(DeclarativeBase):
    pass

# --- Models ---
# These classes define the structure of our database tables.

class Retailer(Base):
    __tablename__ = "retailers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # This creates a link between a Retailer and all its Products.
    products: Mapped[List["Product"]] = relationship(back_populates="retailer")

    def __repr__(self) -> str:
        return f"Retailer(id={self.id!r}, name={self.name!r})"

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # This creates a link between a Category and all its Products.
    products: Mapped[List["Product"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"Category(id={self.id!r}, name={self.name!r})"

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # --- Amended Fields ---
    # We've expanded the 'name' field to be more specific for better tracking.
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String, index=True, nullable=True)
    model: Mapped[str] = mapped_column(String, index=True, nullable=True)
    sku: Mapped[str] = mapped_column(String, nullable=True) # Stock Keeping Unit from the retailer
    
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    
    current_price: Mapped[float] = mapped_column(Float, nullable=True)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # --- Amended Field ---
    # Using an Enum provides more status detail than a simple boolean.
    status: Mapped[ProductStatus] = mapped_column(SQLAlchemyEnum(ProductStatus), default=ProductStatus.AVAILABLE)

    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    # Establishes the many-to-one relationships.
    retailer: Mapped["Retailer"] = relationship(back_populates="products")
    category: Mapped["Category"] = relationship(back_populates="products")
    
    # --- Amended Relationship ---
    # cascade="all, delete-orphan" ensures that when a product is deleted,
    # all its associated price history records are also deleted automatically.
    price_history: Mapped[List["PriceHistory"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Product(id={self.id!r}, name={self.name!r}, price={self.current_price!r})"

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
    status: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "SUCCESS", "FAILURE"
    details: Mapped[str] = mapped_column(String, nullable=True) # e.g., error message or items scraped

    def __repr__(self) -> str:
        return f"ScrapeLog(id={self.id!r}, status={self.status!r}, timestamp={self.timestamp!r})"


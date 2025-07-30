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

class ProductStatus(enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    EOL = "end_of_life"

class Base(DeclarativeBase):
    pass

class Retailer(Base):
    __tablename__ = "retailers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    products: Mapped[List["Product"]] = relationship(back_populates="retailer")
    def __repr__(self) -> str:
        return f"Retailer(id={self.id!r}, name={self.name!r})"

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    products: Mapped[List["Product"]] = relationship(back_populates="category")
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
    previous_price: Mapped[float] = mapped_column(Float, nullable=True) # New column
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ProductStatus] = mapped_column(SQLAlchemyEnum(ProductStatus), default=ProductStatus.AVAILABLE)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    retailer: Mapped["Retailer"] = relationship(back_populates="products")
    category: Mapped["Category"] = relationship(back_populates="products")
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
    status: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str] = mapped_column(String, nullable=True)
    def __repr__(self) -> str:
        return f"ScrapeLog(id={self.id!r}, status={self.status!r}, timestamp={self.timestamp!r})"

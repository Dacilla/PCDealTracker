from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.config import settings

# Database setup
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Retailer(Base):
    __tablename__ = "retailers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    website_url = Column(String(255), nullable=False)
    logo_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    scraper_class = Column(String(100), nullable=False)  # Class name for the scraper
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    products = relationship("Product", back_populates="retailer")
    price_histories = relationship("PriceHistory", back_populates="retailer")

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Self-referential relationship for subcategories
    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    brand = Column(String(100), nullable=True, index=True)
    model = Column(String(100), nullable=True)
    sku = Column(String(100), nullable=True)
    
    # Retailer-specific data
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False)
    retailer_product_id = Column(String(100), nullable=False)  # Retailer's internal ID
    product_url = Column(String(500), nullable=False)
    image_url = Column(String(500), nullable=True)
    
    # Category
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    
    # Current pricing
    current_price = Column(Float, nullable=True)
    original_price = Column(Float, nullable=True)  # RRP or original price
    is_on_sale = Column(Boolean, default=False)
    sale_percentage = Column(Float, nullable=True)
    
    # Availability
    in_stock = Column(Boolean, default=True)
    stock_level = Column(String(50), nullable=True)  # "High", "Low", etc.
    
    # Deal detection
    is_deal = Column(Boolean, default=False)
    is_historical_low = Column(Boolean, default=False)
    deal_score = Column(Float, nullable=True)  # Algorithm-calculated deal quality score
    
    # Product details
    description = Column(Text, nullable=True)
    specifications = Column(Text, nullable=True)  # JSON string of specs
    
    # Metadata
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), onupdate=func.now())
    last_scraped = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    retailer = relationship("Retailer", back_populates="products")
    category = relationship("Category", back_populates="products")
    price_histories = relationship("PriceHistory", back_populates="product")
    
    # Indexes for better query performance
    __table_args__ = (
        Index('idx_retailer_product', 'retailer_id', 'retailer_product_id'),
        Index('idx_current_price', 'current_price'),
        Index('idx_is_deal', 'is_deal'),
        Index('idx_brand_category', 'brand', 'category_id'),
    )

class PriceHistory(Base):
    __tablename__ = "price_histories"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False)
    
    # Price data
    price = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)
    is_sale = Column(Boolean, default=False)
    sale_percentage = Column(Float, nullable=True)
    
    # Stock information
    in_stock = Column(Boolean, default=True)
    stock_level = Column(String(50), nullable=True)
    
    # Timestamp
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    scraped_at = Column(DateTime(timezone=True), nullable=False)
    
    # Relationships
    product = relationship("Product", back_populates="price_histories")
    retailer = relationship("Retailer", back_populates="price_histories")
    
    # Indexes
    __table_args__ = (
        Index('idx_product_date', 'product_id', 'recorded_at'),
        Index('idx_retailer_date', 'retailer_id', 'recorded_at'),
        Index('idx_price_date', 'price', 'recorded_at'),
    )

class ScrapeLog(Base):
    __tablename__ = "scrape_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False)
    
    # Scrape session info
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False)  # "running", "completed", "failed", "cancelled"
    
    # Results
    products_scraped = Column(Integer, default=0)
    products_updated = Column(Integer, default=0)
    products_added = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    
    # Error info
    error_message = Column(Text, nullable=True)
    error_details = Column(Text, nullable=True)  # JSON string of detailed errors
    
    # Performance metrics
    duration_seconds = Column(Float, nullable=True)
    pages_scraped = Column(Integer, default=0)
    requests_made = Column(Integer, default=0)
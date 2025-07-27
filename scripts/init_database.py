#!/usr/bin/env python3
"""
Database initialization script for PCDealTracker
This script creates the database schema and populates it with initial data.
"""

import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import create_engine
from app.database import Base, SessionLocal, Retailer, Category, Product, PriceHistory
from app.config import settings
from datetime import datetime, timedelta
import random

def create_retailers(db):
    """Create initial retailer data"""
    retailers_data = [
        {
            "name": "PC Case Gear",
            "website_url": "https://www.pccasegear.com",
            "scraper_class": "PCCaseGearScraper",
            "is_active": True
        },
        {
            "name": "Scorptec",
            "website_url": "https://www.scorptec.com.au",
            "scraper_class": "ScorptecScraper",
            "is_active": True
        },
        {
            "name": "Centre Com",
            "website_url": "https://www.centrecom.com.au",
            "scraper_class": "CentreComScraper",
            "is_active": True
        },
        {
            "name": "MSY Technology",
            "website_url": "https://www.msy.com.au",
            "scraper_class": "MSYScraper",
            "is_active": True
        },
        {
            "name": "Umart",
            "website_url": "https://www.umart.com.au",
            "scraper_class": "UmartScraper",
            "is_active": True
        },
        {
            "name": "Computer Alliance",
            "website_url": "https://www.computeralliance.com.au",
            "scraper_class": "ComputerAllianceScraper",
            "is_active": True
        }
    ]
    
    retailers = []
    for retailer_data in retailers_data:
        retailer = Retailer(**retailer_data)
        db.add(retailer)
        retailers.append(retailer)
    
    db.commit()
    print(f"Created {len(retailers)} retailers")
    return retailers

def create_categories(db):
    """Create initial category data"""
    categories_data = [
        {"name": "Graphics Cards", "slug": "graphics-cards"},
        {"name": "Processors", "slug": "processors"},
        {"name": "Motherboards", "slug": "motherboards"},
        {"name": "Memory", "slug": "memory"},
        {"name": "Storage", "slug": "storage"},
        {"name": "Power Supplies", "slug": "power-supplies"},
        {"name": "Cases", "slug": "cases"},
        {"name": "Cooling", "slug": "cooling"},
        {"name": "Monitors", "slug": "monitors"},
        {"name": "Keyboards", "slug": "keyboards"},
        {"name": "Mice", "slug": "mice"},
        {"name": "Headsets", "slug": "headsets"}
    ]
    
    categories = []
    for category_data in categories_data:
        category = Category(**category_data)
        db.add(category)
        categories.append(category)
    
    db.commit()
    print(f"Created {len(categories)} categories")
    return categories

def create_sample_products(db, retailers, categories):
    """Create sample product data"""
    sample_products = [
        # Graphics Cards
        {
            "name": "NVIDIA GeForce RTX 4080 16GB",
            "brand": "NVIDIA",
            "model": "RTX 4080",
            "category": "Graphics Cards",
            "base_price": 1599.00,
            "description": "High-performance gaming graphics card with 16GB GDDR6X memory"
        },
        {
            "name": "AMD Radeon RX 7900 XTX 24GB",
            "brand": "AMD",
            "model": "RX 7900 XTX",
            "category": "Graphics Cards",
            "base_price": 1399.00,
            "description": "Flagship AMD graphics card with 24GB GDDR6 memory"
        },
        # Processors
        {
            "name": "Intel Core i7-13700K",
            "brand": "Intel",
            "model": "i7-13700K",
            "category": "Processors",
            "base_price": 649.00,
            "description": "13th Gen Intel Core processor with 16 cores"
        },
        {
            "name": "AMD Ryzen 9 7950X",
            "brand": "AMD",
            "model": "7950X",
            "category": "Processors",
            "base_price": 799.00,
            "description": "High-performance AMD processor with 16 cores"
        },
        # Memory
        {
            "name": "Corsair Vengeance LPX 32GB DDR4-3200",
            "brand": "Corsair",
            "model": "Vengeance LPX",
            "category": "Memory",
            "base_price": 199.00,
            "description": "32GB DDR4 memory kit optimized for performance"
        },
        # Storage
        {
            "name": "Samsung 980 PRO 2TB NVMe SSD",
            "brand": "Samsung",
            "model": "980 PRO",
            "category": "Storage",
            "base_price": 299.00,
            "description": "High-speed NVMe SSD with 2TB capacity"
        },
        # Monitors
        {
            "name": "ASUS ROG Swift PG279QM 27\" 240Hz",
            "brand": "ASUS",
            "model": "PG279QM",
            "category": "Monitors",
            "base_price": 899.00,
            "description": "27-inch gaming monitor with 240Hz refresh rate"
        }
    ]
    
    # Create category lookup
    category_lookup = {cat.name: cat for cat in categories}
    
    products = []
    
    for product_data in sample_products:
        category = category_lookup[product_data["category"]]
        
        # Create this product for multiple retailers with price variations
        for retailer in retailers[:4]:  # Only use first 4 retailers for sample data
            # Add some price variation between retailers
            price_variation = random.uniform(0.9, 1.1)
            current_price = round(product_data["base_price"] * price_variation, 2)
            
            # Sometimes make it a deal
            is_deal = random.choice([True, False, False, False])  # 25% chance
            is_on_sale = is_deal
            sale_percentage = None
            original_price = current_price
            
            if is_on_sale:
                sale_percentage = random.uniform(10, 30)
                original_price = current_price / (1 - sale_percentage / 100)
                original_price = round(original_price, 2)
            
            product = Product(
                name=product_data["name"],
                brand=product_data["brand"],
                model=product_data["model"],
                retailer_id=retailer.id,
                retailer_product_id=f"{retailer.name.lower().replace(' ', '')}-{len(products)+1}",
                product_url=f"{retailer.website_url}/product/{product_data['name'].lower().replace(' ', '-')}",
                image_url=f"{retailer.website_url}/images/{product_data['name'].lower().replace(' ', '-')}.jpg",
                category_id=category.id,
                current_price=current_price,
                original_price=original_price if is_on_sale else None,
                is_on_sale=is_on_sale,
                sale_percentage=sale_percentage,
                in_stock=random.choice([True, True, True, False]),  # 75% in stock
                is_deal=is_deal,
                is_historical_low=random.choice([True, False, False, False]),  # 25% chance
                deal_score=random.uniform(70, 95) if is_deal else None,
                description=product_data["description"],
                is_active=True
            )
            
            db.add(product)
            products.append(product)
    
    db.commit()
    print(f"Created {len(products)} sample products")
    return products

def create_price_history(db, products):
    """Create sample price history data"""
    price_histories = []
    
    for product in products:
        # Generate 30 days of price history
        for i in range(30, 0, -1):
            date = datetime.utcnow() - timedelta(days=i)
            
            # Create some price variation over time
            base_price = product.current_price or 100.0
            price_variation = random.uniform(0.85, 1.15)
            historical_price = round(base_price * price_variation, 2)
            
            # Sometimes the product was on sale
            is_sale = random.choice([True, False, False, False, False])  # 20% chance
            sale_percentage = None
            original_price = historical_price
            
            if is_sale:
                sale_percentage = random.uniform(5, 25)
                original_price = historical_price / (1 - sale_percentage / 100)
                original_price = round(original_price, 2)
            
            price_history = PriceHistory(
                product_id=product.id,
                retailer_id=product.retailer_id,
                price=historical_price,
                original_price=original_price if is_sale else None,
                is_sale=is_sale,
                sale_percentage=sale_percentage,
                in_stock=random.choice([True, True, True, False]),  # 75% in stock
                recorded_at=date,
                scraped_at=date
            )
            
            db.add(price_history)
            price_histories.append(price_history)
    
    db.commit()
    print(f"Created {len(price_histories)} price history records")
    return price_histories

def main():
    """Initialize the database with sample data"""
    print("Initializing PCDealTracker database...")
    
    # Create database engine
    engine = create_engine(settings.database_url)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("Created database tables")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Check if data already exists
        existing_retailers = db.query(Retailer).count()
        if existing_retailers > 0:
            print(f"Database already contains {existing_retailers} retailers. Skipping initialization.")
            return
        
        # Create initial data
        print("\nCreating initial data...")
        retailers = create_retailers(db)
        categories = create_categories(db)
        products = create_sample_products(db, retailers, categories)
        price_histories = create_price_history(db, products)
        
        print(f"\nDatabase initialization complete!")
        print(f"- {len(retailers)} retailers")
        print(f"- {len(categories)} categories")
        print(f"- {len(products)} products")
        print(f"- {len(price_histories)} price history records")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
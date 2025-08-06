import os
import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import Base, Retailer, Category
from backend.app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_database():
    """
    Creates all database tables and populates the initial data for retailers and categories.
    """
    # Create tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # --- Populate Retailers with local logo paths ---
        retailers = [
            {"name": "PC Case Gear", "url": "https://www.pccasegear.com", "logo_url": "assets/logos/pccg.png"},
            {"name": "Scorptec", "url": "https://www.scorptec.com.au", "logo_url": "assets/logos/scorptec.png"},
            {"name": "Centre Com", "url": "https://www.centrecom.com.au", "logo_url": "assets/logos/centrecom.png"},
            {"name": "MSY Technology", "url": "https://www.msy.com.au", "logo_url": "assets/logos/msy.png"},
            {"name": "Umart", "url": "https://www.umart.com.au", "logo_url": "assets/logos/umart.png"},
            {"name": "Computer Alliance", "url": "https://www.computeralliance.com.au", "logo_url": "assets/logos/computeralliance.png"},
            {"name": "JW Computers", "url": "https://www.jw.com.au", "logo_url": "assets/logos/jw.png"},
            {"name": "Shopping Express", "url": "https://www.shoppingexpress.com.au", "logo_url": "assets/logos/shoppingexpress.png"},
            {"name": "Austin Computers", "url": "https://www.austin.net.au", "logo_url": "assets/logos/austin.png"},
        ]
        
        for retailer_data in retailers:
            # This will update existing retailers with the new logo_url if they already exist
            existing_retailer = db.execute(select(Retailer).where(Retailer.name == retailer_data["name"])).scalar_one_or_none()
            if existing_retailer:
                existing_retailer.logo_url = retailer_data["logo_url"]
            else:
                db.add(Retailer(**retailer_data))

        # --- Populate Categories ---
        categories = [
            "Graphics Cards", "CPUs", "Motherboards", "Memory (RAM)", 
            "Storage (SSD/HDD)", "Power Supplies", "PC Cases", "Monitors",
            "Cooling", "Fans & Accessories"
        ]
        for category_name in categories:
            exists = db.execute(select(Category).where(Category.name == category_name)).scalar_one_or_none()
            if not exists:
                db.add(Category(name=category_name))

        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    print("Setting up the database...")
    setup_database()
    print("Database setup complete.")

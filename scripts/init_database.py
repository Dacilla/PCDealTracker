import os
import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import Base, Retailer, Category
from backend.app.config import settings

RETAILERS = [
    {"name": "PC Case Gear", "url": "https://www.pccasegear.com", "logo_url": "https://files.pccasegear.com/images/pccg-logo.svg"},
    {"name": "Scorptec", "url": "https://www.scorptec.com.au", "logo_url": "https://www.scorptec.com.au/assets/images/logo_v5.png"},
    {"name": "Centre Com", "url": "https://www.centrecom.com.au", "logo_url": "https://www.centrecom.com.au/images/logo.png"},
    {"name": "MSY Technology", "url": "https://www.msy.com.au", "logo_url": "https://assets.msy.com.au/themes/msy/images/logo_lg.png"},
    {"name": "Umart", "url": "https://www.umart.com.au", "logo_url": "https://www.umart.com.au/images/logo_umart.png"},
    {"name": "Computer Alliance", "url": "https://www.computeralliance.com.au", "logo_url": "https://www.computeralliance.com.au/images/ca_logo.png"},
    {"name": "JW Computers", "url": "https://www.jw.com.au", "logo_url": "https://www.jw.com.au/static/version1753773075/frontend/JWC/base/en_AU/images/logo.svg"},
]

CATEGORIES = [
    {"name": "Graphics Cards"},
    {"name": "CPUs"}, 
    {"name": "Motherboards"},
    {"name": "Memory (RAM)"},
    {"name": "Storage (SSD/HDD)"},
    {"name": "Power Supplies"},
    {"name": "PC Cases"},
    {"name": "Monitors"},
    {"name": "Cooling"},
    {"name": "Fans & Accessories"},
]

def setup_database():
    print("Connecting to the database...")
    engine = create_engine(settings.database_url, echo=False)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully.")

        print("\nSeeding retailers...")
        for retailer_data in RETAILERS:
            exists = session.execute(
                select(Retailer).where(Retailer.name == retailer_data["name"])
            ).scalars().first()
            
            if not exists:
                retailer = Retailer(**retailer_data)
                session.add(retailer)
                print(f"  Added retailer: {retailer.name}")
            else:
                exists.url = retailer_data["url"]
                exists.logo_url = retailer_data["logo_url"]
                print(f"  Updated (already exists): {retailer_data['name']}")
        
        print("\nSeeding categories...")
        for category_data in CATEGORIES:
            exists = session.execute(
                select(Category).where(Category.name == category_data["name"])
            ).scalars().first()

            if not exists:
                category = Category(name=category_data["name"])
                session.add(category)
                print(f"  Added category: {category.name}")
            else:
                print(f"  Skipped (already exists): {category_data['name']}")

        session.commit()
        print("\nInitial data has been seeded successfully.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        session.rollback()
    finally:
        session.close()
        print("Database session closed.")


if __name__ == "__main__":
    print("--- Starting Database Initialization ---")
    setup_database()
    print("--- Database Initialization Complete ---")

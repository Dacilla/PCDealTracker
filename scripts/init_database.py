import os
import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# This is a bit of a hack to allow this script to import from the 'backend' directory.
# It adds the parent directory of 'scripts' to Python's path.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import Base, Retailer, Category
from backend.app.config import settings

# --- Initial Data ---
# This is the foundational data for the application.
# It can be easily expanded in the future.

RETAILERS = [
    {"name": "PC Case Gear", "url": "https://www.pccasegear.com"},
    {"name": "Scorptec", "url": "https://www.scorptec.com.au"},
    {"name": "Centre Com", "url": "https://www.centrecom.com.au"},
    {"name": "MSY Technology", "url": "https://www.msy.com.au"},
    {"name": "Umart", "url": "https://www.umart.com.au"},
    {"name": "Computer Alliance", "url": "https://www.computeralliance.com.au"},
]

CATEGORIES = [
    {"name": "Graphics Cards"},
    # --- CORRECTED NAME ---
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
    """
    Sets up the database by creating tables and seeding initial data.
    """
    print("Connecting to the database...")
    # Use the imported settings object directly.
    engine = create_engine(settings.database_url, echo=False)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully.")

        # --- Seed Retailers ---
        print("\nSeeding retailers...")
        for retailer_data in RETAILERS:
            exists = session.execute(
                select(Retailer).where(Retailer.name == retailer_data["name"])
            ).scalars().first()
            
            if not exists:
                retailer = Retailer(name=retailer_data["name"], url=retailer_data["url"])
                session.add(retailer)
                print(f"  Added retailer: {retailer.name}")
            else:
                print(f"  Skipped (already exists): {retailer_data['name']}")
        
        # --- Seed Categories ---
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

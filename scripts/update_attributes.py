import os
import sys
from sqlalchemy import select
from sqlalchemy.orm import joinedload

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.dependencies import SessionLocal, engine
from backend.app.database import MergedProduct, Base
from backend.app.utils.parsing import parse_product_attributes

def update_existing_attributes():
    """
    A one-time script to iterate through existing MergedProduct records
    and populate their 'attributes' field using the latest parsing logic,
    without deleting any data.
    """
    print("--- Starting One-Time Attribute Update Process ---")
    
    # Ensure the database schema is up-to-date (e.g., adds the 'attributes' column if missing)
    print("Verifying database schema...")
    Base.metadata.create_all(bind=engine)
    print("Schema verified.")

    db_session = SessionLocal()
    updated_count = 0

    try:
        # Select all merged products, loading their category relationship as well
        query = select(MergedProduct).options(joinedload(MergedProduct.category))
        all_merged_products = db_session.execute(query).scalars().unique().all()

        if not all_merged_products:
            print("No products found to update.")
            return

        print(f"Found {len(all_merged_products)} total products to check and update...")

        for product in all_merged_products:
            # Generate new attributes using the parser
            new_attributes = parse_product_attributes(product.canonical_name, product.category.name)
            
            # Check if the new attributes are different from the old ones to avoid unnecessary writes
            if product.attributes != new_attributes:
                product.attributes = new_attributes
                updated_count += 1
                if new_attributes:
                    print(f"  -> Updating '{product.canonical_name}' with attributes: {new_attributes}")

        if updated_count > 0:
            print(f"\nFound {updated_count} products to update. Committing changes...")
            db_session.commit()
            print("Successfully updated attributes for all products.")
        else:
            print("\nAll product attributes are already up-to-date. No changes needed.")

    except Exception as e:
        print(f"\nAn error occurred during the update process: {e}")
        db_session.rollback()
    finally:
        db_session.close()
        print("Database session closed.")


if __name__ == "__main__":
    update_existing_attributes()

import os
import sys
from sqlalchemy import select, delete, text, inspect
from sqlalchemy.orm import joinedload

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.dependencies import SessionLocal, engine
from backend.app.database import Product, MergedProduct, merged_product_association, Base
from backend.app.utils.parsing import normalize_model_strict, normalize_model_loose
from scripts.merge_products import group_products_by_model

def run_one_time_rebuild():
    """
    A one-time script to:
    1. Ensure all normalization columns exist.
    2. Populate the normalization fields for all existing products.
    3. Clear out all old merged products.
    4. Re-run the merging process with the new, two-pass logic.
    """
    print("--- Starting One-Time Product Rebuild Process ---")
    
    print("Verifying database schema...")
    Base.metadata.create_all(bind=engine)
    
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('products')]
    
    with engine.connect() as connection:
        if 'normalized_model' not in columns:
            print("  -> 'normalized_model' column not found. Adding it...")
            connection.execute(text('ALTER TABLE products ADD COLUMN normalized_model VARCHAR'))
        if 'loose_normalized_model' not in columns:
            print("  -> 'loose_normalized_model' column not found. Adding it...")
            connection.execute(text('ALTER TABLE products ADD COLUMN loose_normalized_model VARCHAR'))
        connection.commit()
    
    print("Schema verified.")

    db_session = SessionLocal()

    try:
        print("\n--- Step 1: Normalizing models for all existing products ---")
        all_products = db_session.execute(select(Product)).scalars().all()
        
        if not all_products:
            print("No products found in the database. Exiting.")
            return

        print(f"Found {len(all_products)} products to normalize...")
        for product in all_products:
            if product.model:
                product.normalized_model = normalize_model_strict(product.model)
                product.loose_normalized_model = normalize_model_loose(product.model)
        
        db_session.commit()
        print("Normalization complete.")

        print("\n--- Step 2: Clearing old merged product data ---")
        db_session.execute(delete(merged_product_association))
        db_session.execute(delete(MergedProduct))
        db_session.commit()
        print("Old merged data cleared.")

        print("\n--- Step 3: Re-running the merging process with new logic ---")
        db_session.close()
        group_products_by_model()
        
        print("\n--- One-Time Product Rebuild Process Complete ---")

    except Exception as e:
        print(f"\nAn error occurred during the rebuild process: {e}")
        db_session.rollback()
    finally:
        if db_session.is_active:
            db_session.close()
        print("Database session closed.")


if __name__ == "__main__":
    run_one_time_rebuild()

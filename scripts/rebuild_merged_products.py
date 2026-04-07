import os
import sys
from sqlalchemy import inspect, select, text

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import Base, Product
from backend.app.dependencies import SessionLocal, engine
from backend.app.utils.parsing import normalize_model_loose, normalize_model_strict
from scripts.merge_products import clear_existing_merged_products, merge_products_with_fuzzy_logic


def run_one_time_rebuild():
    """
    A one-time script to:
    1. Ensure all normalization columns exist.
    2. Populate the normalization fields for all existing products.
    3. Clear out all old merged products.
    4. Re-run the merging process with the current merge logic.
    """
    print("--- Starting One-Time Product Rebuild Process ---")

    print("Verifying database schema...")
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    columns = [column["name"] for column in inspector.get_columns("products")]

    with engine.connect() as connection:
        if "normalized_model" not in columns:
            print("  -> 'normalized_model' column not found. Adding it...")
            connection.execute(text("ALTER TABLE products ADD COLUMN normalized_model VARCHAR"))
        if "loose_normalized_model" not in columns:
            print("  -> 'loose_normalized_model' column not found. Adding it...")
            connection.execute(text("ALTER TABLE products ADD COLUMN loose_normalized_model VARCHAR"))
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
            if not product.model:
                continue
            product.normalized_model = normalize_model_strict(product.model)
            product.loose_normalized_model = normalize_model_loose(product.model)

        db_session.commit()
        print("Normalization complete.")

        print("\n--- Step 2: Clearing old merged product data ---")
        clear_existing_merged_products(db_session)
        print("Old merged data cleared.")
    except Exception as exc:
        print(f"\nAn error occurred during the rebuild preparation: {exc}")
        db_session.rollback()
        raise
    finally:
        db_session.close()

    print("\n--- Step 3: Re-running the merging process with current logic ---")
    merge_products_with_fuzzy_logic()
    print("\n--- One-Time Product Rebuild Process Complete ---")


if __name__ == "__main__":
    run_one_time_rebuild()

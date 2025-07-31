import os
import sys
from sqlalchemy import select, func
from collections import defaultdict

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.dependencies import SessionLocal, engine # Import engine
from backend.app.database import Product, MergedProduct, Base # Import Base

def group_products_by_model():
    """
    Groups individual products into merged products based on brand and model.
    This script is designed to be run after the scrapers have populated the database.
    """
    print("--- Starting Product Merging Process ---")
    
    # --- Ensure all tables are created before starting ---
    print("Verifying database schema...")
    Base.metadata.create_all(bind=engine)
    print("Schema verified.")

    db_session = SessionLocal()

    try:
        # Select all products that have a brand and model, and are not yet associated
        # with any merged product. This makes the script idempotent.
        products_to_merge_query = (
            select(Product)
            .where(
                Product.brand.isnot(None),
                Product.model.isnot(None),
                ~Product.merged_products.any() # Efficiently checks for no association
            )
        )
        products_to_merge = db_session.execute(products_to_merge_query).scalars().all()

        if not products_to_merge:
            print("No new products to merge.")
            return

        print(f"Found {len(products_to_merge)} products to process...")

        # Group products by a tuple of (brand, model, category_id)
        grouped_products = defaultdict(list)
        for product in products_to_merge:
            key = (product.brand.lower(), product.model.lower(), product.category_id)
            grouped_products[key].append(product)

        print(f"Grouped into {len(grouped_products)} unique models.")

        # Process each group
        for (brand_key, model_key, category_id), products_in_group in grouped_products.items():
            
            # Use the name from the first product in the group as the canonical name
            canonical_name = f"{products_in_group[0].brand} {products_in_group[0].model}"
            
            # Check if a MergedProduct already exists for this canonical name
            merged_product = db_session.execute(
                select(MergedProduct).where(MergedProduct.canonical_name == canonical_name)
            ).scalar_one_or_none()

            # If not, create a new one
            if not merged_product:
                print(f"  Creating new merged product: {canonical_name}")
                merged_product = MergedProduct(
                    canonical_name=canonical_name,
                    brand=products_in_group[0].brand,
                    model=products_in_group[0].model,
                    category_id=category_id
                )
                db_session.add(merged_product)
                # We need to flush to get the ID for the association
                db_session.flush()

            # Associate all products in the group with the MergedProduct
            print(f"  Associating {len(products_in_group)} listings with '{canonical_name}'")
            for product in products_in_group:
                merged_product.products.append(product)
        
        # Commit all changes at the end
        db_session.commit()
        print("\n--- Product Merging Process Complete ---")

    except Exception as e:
        print(f"\nAn error occurred during the merging process: {e}")
        db_session.rollback()
    finally:
        db_session.close()
        print("Database session closed.")


if __name__ == "__main__":
    group_products_by_model()

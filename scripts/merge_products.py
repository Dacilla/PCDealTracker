import os
import sys
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from collections import defaultdict

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.dependencies import SessionLocal, engine
from backend.app.database import Product, MergedProduct, Base
# Import the new, enhanced parser
from backend.app.utils.parsing import parse_product_attributes

def group_products_by_model():
    """
    Groups individual products and enriches them with parsed, category-specific attributes.
    """
    print("--- Starting Product Merging and Enrichment Process ---")
    
    print("Verifying database schema...")
    Base.metadata.create_all(bind=engine)
    print("Schema verified.")

    db_session = SessionLocal()

    try:
        # We need to load the category relationship to access the category name for parsing
        products_to_merge_query = (
            select(Product)
            .options(joinedload(Product.category)) # Eager load the category
            .where(
                Product.brand.isnot(None),
                Product.model.isnot(None),
                ~Product.merged_products.any()
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
            
            first_product = products_in_group[0]
            canonical_name = f"{first_product.brand} {first_product.model}"
            
            merged_product = db_session.execute(
                select(MergedProduct).where(MergedProduct.canonical_name == canonical_name)
            ).scalar_one_or_none()

            if not merged_product:
                print(f"  Creating new merged product: {canonical_name}")
                
                # --- Call the enhanced attribute parser ---
                attributes = parse_product_attributes(canonical_name, first_product.category.name)
                if attributes:
                    print(f"    -> Enriched with attributes: {attributes}")

                merged_product = MergedProduct(
                    canonical_name=canonical_name,
                    brand=first_product.brand,
                    model=first_product.model,
                    category_id=category_id,
                    attributes=attributes # Save the parsed attributes
                )
                db_session.add(merged_product)
                db_session.flush()

            print(f"  Associating {len(products_in_group)} listings with '{canonical_name}'")
            for product in products_in_group:
                merged_product.products.append(product)
        
        db_session.commit()
        print("\n--- Product Merging and Enrichment Process Complete ---")

    except Exception as e:
        print(f"\nAn error occurred during the merging process: {e}")
        db_session.rollback()
    finally:
        db_session.close()
        print("Database session closed.")


if __name__ == "__main__":
    group_products_by_model()

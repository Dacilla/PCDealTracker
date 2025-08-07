# scripts/merge_products.py
import os
import sys
from sqlalchemy import select, delete, func
from sqlalchemy.orm import joinedload
from collections import defaultdict
from thefuzz import fuzz

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.dependencies import SessionLocal
from backend.app.database import Product, MergedProduct, Base
from backend.app.utils.parsing import parse_product_attributes

# --- Configuration ---
# This threshold is now much stricter, only for catching minor typos or word order issues.
SIMILARITY_THRESHOLD = 96

def clear_existing_merged_products(db_session):
    """Wipes all data from MergedProduct and the association table."""
    print("--- Clearing all existing merged product data ---")
    from backend.app.database import merged_product_association
    db_session.execute(delete(merged_product_association))
    db_session.execute(delete(MergedProduct))
    db_session.commit()
    print("--- All old merged data has been cleared. ---")


def merge_products_with_fuzzy_logic():
    """
    Groups products using a two-pass system:
    1. High-confidence matching based on the pre-calculated normalized_model.
    2. A stricter fuzzy match for any remaining, ambiguous products.
    """
    print("--- Starting Two-Pass Product Merging Process ---")
    
    db_session = SessionLocal()

    try:
        # Get all products that haven't been merged yet.
        products_to_merge_query = (
            select(Product)
            .options(joinedload(Product.category))
            .where(~Product.merged_products.any())
        )
        all_unmerged_products = db_session.execute(products_to_merge_query).scalars().all()

        if not all_unmerged_products:
            print("No new products to merge.")
            db_session.close()
            return

        print(f"Found {len(all_unmerged_products)} unmerged products to process...")
        
        # --- PASS 1: High-Confidence Normalization Matching ---
        print("\n--- Pass 1: Matching based on normalized models ---")
        
        groups_by_normalized_model = defaultdict(list)
        products_left_over = []

        for product in all_unmerged_products:
            # We need a valid normalized_model to perform this pass
            if product.normalized_model and product.normalized_model.strip():
                key = (product.category_id, product.normalized_model)
                groups_by_normalized_model[key].append(product)
            else:
                # If no normalized_model, save it for the fuzzy pass
                products_left_over.append(product)

        # Process the high-confidence groups
        for (category_id, model_key), listings in groups_by_normalized_model.items():
            if len(listings) > 1:
                # More than one product shares this exact normalized model - a definite match.
                canonical_name = max([p.name for p in listings], key=len)
                first_product = listings[0]
                attributes = parse_product_attributes(canonical_name, first_product.category.name)
                
                new_merged_product = MergedProduct(
                    canonical_name=canonical_name,
                    brand=first_product.brand,
                    model=first_product.model,
                    category_id=category_id,
                    attributes=attributes,
                    products=listings
                )
                db_session.add(new_merged_product)
            else:
                # Only one product in this group, so it's not a match yet.
                products_left_over.extend(listings)
        
        print(f"  -> Committed {len(groups_by_normalized_model) - len(products_left_over)} high-confidence groups.")
        print(f"  -> {len(products_left_over)} products remaining for fuzzy matching.")
        db_session.commit()


        # --- PASS 2: Stricter Fuzzy Matching for Leftovers ---
        print("\n--- Pass 2: Fuzzy matching for remaining products ---")

        products_by_category = defaultdict(list)
        for p in products_left_over:
            if p.category:
                products_by_category[p.category_id].append(p)

        for category_id, products_in_category in products_by_category.items():
            cat_name = products_in_category[0].category.name if products_in_category else "N/A"
            print(f"\nProcessing category '{cat_name}' ({len(products_in_category)} products)...")

            for i, product in enumerate(products_in_category):
                print(f"  -> Sorting: {i + 1}/{len(products_in_category)}", end='\r')
                
                # Check if this product was already merged in this session
                db_product = db_session.get(Product, product.id, populate_existing=True)
                if db_product and db_product.merged_products:
                    continue

                # Get all merged products from the CURRENT category to check for fuzzy matches
                existing_in_category = db_session.execute(
                    select(MergedProduct).where(MergedProduct.category_id == category_id)
                ).scalars().all()

                best_match = None
                highest_score = 0

                for merged_product in existing_in_category:
                    score = fuzz.token_set_ratio(product.name, merged_product.canonical_name)
                    if score > highest_score:
                        highest_score = score
                        best_match = merged_product

                if highest_score >= SIMILARITY_THRESHOLD and best_match:
                    best_match.products.append(product)
                else:
                    # FINAL SAFEGUARD: Check the ENTIRE database for an exact name match
                    # that could have been created in a DIFFERENT category's transaction.
                    global_match = db_session.execute(
                        select(MergedProduct).where(MergedProduct.canonical_name == product.name)
                    ).scalar_one_or_none()

                    if global_match:
                        # A match exists from another category. Add to it.
                        global_match.products.append(product)
                    else:
                        # This product is truly unique across all categories. Create a new one.
                        attributes = parse_product_attributes(product.name, cat_name)
                        new_merged_product = MergedProduct(
                            canonical_name=product.name,
                            brand=product.brand,
                            model=product.model,
                            category_id=category_id,
                            attributes=attributes,
                            products=[product]
                        )
                        db_session.add(new_merged_product)

            print()
            # Commit all changes for this category before moving to the next.
            db_session.commit()

        print("\n--- Two-Pass Merging Process Complete ---")

    except Exception as e:
        print(f"\nAn error occurred during the merging process: {e}")
        import traceback
        traceback.print_exc()
        db_session.rollback()
    finally:
        if db_session.is_active:
            db_session.close()
            print("Database session closed.")

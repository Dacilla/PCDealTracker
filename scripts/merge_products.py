# scripts/merge_products.py
import os
import sys
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload
from thefuzz import fuzz

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import MergedProduct, Product
from backend.app.dependencies import SessionLocal
from backend.app.utils.parsing import parse_product_attributes

# This threshold is intentionally strict; it only catches near-identical leftovers.
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
    1. High-confidence matching based on normalized models.
    2. A strict fuzzy match for any remaining products.
    """
    print("--- Starting Two-Pass Product Merging Process ---")

    db_session = SessionLocal()
    try:
        products_to_merge_query = (
            select(Product)
            .options(joinedload(Product.category))
            .where(~Product.merged_products.any())
        )
        all_unmerged_products = db_session.execute(products_to_merge_query).scalars().all()

        if not all_unmerged_products:
            print("No new products to merge.")
            return

        print(f"Found {len(all_unmerged_products)} unmerged products to process...")

        print("\n--- Pass 1: Matching based on normalized models ---")
        groups_by_normalized_model = defaultdict(list)
        products_left_over = []

        for product in all_unmerged_products:
            if product.normalized_model and product.normalized_model.strip():
                key = (product.category_id, product.normalized_model)
                groups_by_normalized_model[key].append(product)
            else:
                products_left_over.append(product)

        created_groups = 0
        for (category_id, _model_key), listings in groups_by_normalized_model.items():
            if len(listings) <= 1:
                products_left_over.extend(listings)
                continue

            canonical_name = max((product.name for product in listings), key=len)
            first_product = listings[0]
            attributes = parse_product_attributes(canonical_name, first_product.category.name)

            db_session.add(
                MergedProduct(
                    canonical_name=canonical_name,
                    brand=first_product.brand,
                    model=first_product.model,
                    category_id=category_id,
                    attributes=attributes,
                    products=listings,
                )
            )
            created_groups += 1

        db_session.commit()
        print(f"  -> Committed {created_groups} high-confidence groups.")
        print(f"  -> {len(products_left_over)} products remaining for fuzzy matching.")

        print("\n--- Pass 2: Fuzzy matching for remaining products ---")
        products_by_category = defaultdict(list)
        for product in products_left_over:
            if product.category:
                products_by_category[product.category_id].append(product)

        for category_id, products_in_category in products_by_category.items():
            cat_name = products_in_category[0].category.name if products_in_category else "N/A"
            print(f"\nProcessing category '{cat_name}' ({len(products_in_category)} products)...")

            for index, product in enumerate(products_in_category, start=1):
                print(f"  -> Sorting: {index}/{len(products_in_category)}", end="\r")

                db_product = db_session.get(Product, product.id, populate_existing=True)
                if db_product and db_product.merged_products:
                    continue

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
                    continue

                global_match = db_session.execute(
                    select(MergedProduct).where(MergedProduct.canonical_name == product.name)
                ).scalar_one_or_none()

                if global_match:
                    global_match.products.append(product)
                    continue

                attributes = parse_product_attributes(product.name, cat_name)
                db_session.add(
                    MergedProduct(
                        canonical_name=product.name,
                        brand=product.brand,
                        model=product.model,
                        category_id=category_id,
                        attributes=attributes,
                        products=[product],
                    )
                )

            print()
            db_session.commit()

        print("\n--- Two-Pass Merging Process Complete ---")
    except Exception as exc:
        print(f"\nAn error occurred during the merging process: {exc}")
        import traceback

        traceback.print_exc()
        db_session.rollback()
        raise
    finally:
        if db_session.is_active:
            db_session.close()
            print("Database session closed.")


def group_products_by_model():
    """Backwards-compatible alias used by older scripts/docs."""
    merge_products_with_fuzzy_logic()

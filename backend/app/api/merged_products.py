# backend/app/api/merged_products.py
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select, func, asc, desc, cast, Float, and_

from ..dependencies import get_db
from ..database import MergedProduct, Product, PriceHistory, ProductStatus, merged_product_association
from .products import ProductSchema, CategorySchema, RetailerSchema
from ..redis_client import get_cache, set_cache

# --- Pydantic Schemas ---

class PriceHistoryWithRetailerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    price: float
    date: datetime.datetime
    retailer: RetailerSchema

class MergedProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    canonical_name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    category: CategorySchema
    attributes: Optional[dict] = None
    
    listings: List[ProductSchema] = []
    
    best_price: Optional[float] = None
    best_price_url: Optional[str] = None
    best_price_retailer: Optional[str] = None

    all_time_low_price: Optional[float] = None
    all_time_low_date: Optional[datetime.datetime] = None
    all_time_low_retailer_name: Optional[str] = None
    
    msrp: Optional[float] = None


class MergedProductPage(BaseModel):
    total: int
    products: List[MergedProductSchema]

# --- API Router ---
router = APIRouter(
    prefix="/api/v1/merged-products",
    tags=["Merged Products"],
    responses={404: {"description": "Not found"}},
)

def _process_merged_product(mp: MergedProduct, db: Session) -> dict:
    """Helper function to process a single MergedProduct object and return a dict."""
    merged_schema = MergedProductSchema.model_validate(mp)
    
    # The status needs to be accessed as a string for the schema
    validated_listings = []
    for p in mp.products:
        p_dict = ProductSchema.model_validate(p).model_dump()
        p_dict['status'] = p.status.value # Ensure status is the string value
        validated_listings.append(ProductSchema.model_validate(p_dict))
    
    merged_schema.listings = validated_listings
    
    available_listings = [p for p in mp.products if p.current_price is not None and p.status == ProductStatus.AVAILABLE]
    if available_listings:
        best_listing = min(available_listings, key=lambda p: p.current_price)
        merged_schema.best_price = best_listing.current_price
        merged_schema.best_price_url = best_listing.url
        merged_schema.best_price_retailer = best_listing.retailer.name
    
    product_ids = [p.id for p in mp.products]
    if product_ids:
        price_stats = db.query(
            func.min(PriceHistory.price),
            func.max(PriceHistory.price)
        ).filter(PriceHistory.product_id.in_(product_ids)).first()

        if price_stats and price_stats[0] is not None:
            merged_schema.msrp = price_stats[1]

            all_time_low_entry = db.query(PriceHistory)\
                .join(Product)\
                .options(joinedload(PriceHistory.product).joinedload(Product.retailer))\
                .filter(PriceHistory.product_id.in_(product_ids))\
                .order_by(PriceHistory.price.asc(), PriceHistory.date.desc())\
                .first()
            
            if all_time_low_entry:
                merged_schema.all_time_low_price = all_time_low_entry.price
                merged_schema.all_time_low_date = all_time_low_entry.date
                merged_schema.all_time_low_retailer_name = all_time_low_entry.product.retailer.name
    
    return merged_schema.model_dump(mode='json')


@router.get("/", response_model=MergedProductPage)
def read_merged_products(
    request: Request,
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = Query(None),
    search_mode: Optional[str] = Query("loose"),
    category_id: Optional[int] = Query(None),
    sort_by: Optional[str] = Query("name"),
    sort_order: Optional[str] = Query("asc"),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    hide_unavailable: bool = Query(False),
):
    """
    Retrieve a paginated list of merged products with caching.
    """
    cache_key = f"merged_products:{str(request.query_params)}"
    cached_result = get_cache(cache_key)
    if cached_result:
        # print(f"--- Serving merged products from cache: {cache_key} ---")
        return cached_result

    # print(f"--- Fetching merged products from DB: {cache_key} ---")
    
    min_price_subquery = (
        select(merged_product_association.c.merged_product_id, func.min(Product.current_price).label("min_price"))
        .join(Product, merged_product_association.c.product_id == Product.id)
        # FIX: Explicitly use the enum's string value in the query.
        .where(Product.status == ProductStatus.AVAILABLE)
        .group_by(merged_product_association.c.merged_product_id).subquery()
    )
    
    is_outer_join = not hide_unavailable
    query = (
        select(MergedProduct)
        .join(min_price_subquery, MergedProduct.id == min_price_subquery.c.merged_product_id, isouter=is_outer_join)
        .options(joinedload(MergedProduct.category), selectinload(MergedProduct.products).joinedload(Product.retailer))
    )
    
    filters = []
    if search:
        search_terms = search.split()
        search_conditions = [MergedProduct.canonical_name.ilike(f"%{term}%") for term in search_terms]
        filters.append(and_(*search_conditions) if search_mode == "loose" else MergedProduct.canonical_name.ilike(f"%{search}%"))

    if category_id: filters.append(MergedProduct.category_id == category_id)
    if min_price is not None: filters.append(min_price_subquery.c.min_price >= min_price)
    if max_price is not None: filters.append(min_price_subquery.c.min_price <= max_price)

    known_params = ['page', 'page_size', 'search', 'search_mode', 'category_id', 'sort_by', 'sort_order', 'min_price', 'max_price', 'hide_unavailable']
    for key, value in request.query_params.items():
        if key not in known_params and value:
            if key.startswith("min_"): filters.append(cast(MergedProduct.attributes[key[4:]], Float) >= float(value))
            elif key.startswith("max_"): filters.append(cast(MergedProduct.attributes[key[4:]], Float) <= float(value))
            else: filters.append(MergedProduct.attributes[key].as_string() == value)

    if filters:
        query = query.where(and_(*filters))

    count_query = select(func.count(MergedProduct.id.distinct())).join(min_price_subquery, MergedProduct.id == min_price_subquery.c.merged_product_id, isouter=is_outer_join)
    if filters:
        count_query = count_query.where(and_(*filters))
        
    total = db.execute(count_query).scalar_one()

    # --- Sorting Logic ---
    # FIX: Ensure only one order_by clause is applied.
    order_clause = None
    if sort_by == "price":
        order_clause = asc(min_price_subquery.c.min_price) if sort_order == "asc" else desc(min_price_subquery.c.min_price)
        query = query.order_by(order_clause.nulls_last())
    elif sort_by == "recent":
        most_recent_date_subquery = (
            select(
                merged_product_association.c.merged_product_id,
                func.max(PriceHistory.date).label("max_date"),
            )
            .join(Product, merged_product_association.c.product_id == Product.id)
            .join(PriceHistory, Product.id == PriceHistory.product_id)
            .group_by(merged_product_association.c.merged_product_id)
            .subquery()
        )
        query = query.join(
            most_recent_date_subquery,
            MergedProduct.id == most_recent_date_subquery.c.merged_product_id,
            isouter=True
        )
        order_clause = desc(most_recent_date_subquery.c.max_date)
        query = query.order_by(order_clause.nulls_last())
    elif sort_by == "discount" or sort_by == "discount_amount":
        max_price_subquery = (
            select(
                merged_product_association.c.merged_product_id,
                func.max(PriceHistory.price).label("max_price"),
            )
            .join(Product, merged_product_association.c.product_id == Product.id)
            .join(PriceHistory, Product.id == PriceHistory.product_id)
            .group_by(merged_product_association.c.merged_product_id)
            .subquery()
        )
        query = query.join(
            max_price_subquery,
            MergedProduct.id == max_price_subquery.c.merged_product_id,
            isouter=True
        )
        if sort_by == "discount":
            discount_calc = func.coalesce(
                (max_price_subquery.c.max_price - min_price_subquery.c.min_price) / func.nullif(max_price_subquery.c.max_price, 0),
                0
            )
        else: # discount_amount
            discount_calc = (max_price_subquery.c.max_price - min_price_subquery.c.min_price)
        
        order_clause = desc(discount_calc)
        query = query.order_by(order_clause.nulls_last())
    else: # Default sort by name
        order_clause = asc(MergedProduct.canonical_name) if sort_order == "asc" else desc(MergedProduct.canonical_name)
        query = query.order_by(order_clause)
    
    skip = (page - 1) * page_size
    results = db.execute(query.offset(skip).limit(page_size)).scalars().unique().all()

    processed_results = [_process_merged_product(mp, db) for mp in results]
    
    final_response = {"total": total, "products": processed_results}
    set_cache(cache_key, final_response, expiry_seconds=900) # Cache for 15 minutes
    return final_response

@router.get("/{merged_product_id}", response_model=MergedProductSchema)
def read_single_merged_product(merged_product_id: int, db: Session = Depends(get_db)):
    cache_key = f"merged_product:{merged_product_id}"
    cached_product = get_cache(cache_key)
    if cached_product:
        # print(f"--- Serving single product from cache: {cache_key} ---")
        return cached_product

    # print(f"--- Fetching single product from DB: {cache_key} ---")
    query = (
        select(MergedProduct)
        .options(joinedload(MergedProduct.category), selectinload(MergedProduct.products).joinedload(Product.retailer))
        .where(MergedProduct.id == merged_product_id)
    )
    result = db.execute(query).scalars().unique().first()
    if not result:
        raise HTTPException(status_code=404, detail="Merged product not found")
    
    processed_product = _process_merged_product(result, db)
    set_cache(cache_key, processed_product, expiry_seconds=900)
    return processed_product

# (The price history endpoint remains the same)
@router.get("/{merged_product_id}/price-history", response_model=List[PriceHistoryWithRetailerSchema])
def get_combined_price_history(merged_product_id: int, db: Session = Depends(get_db)):
    merged_product = db.get(MergedProduct, merged_product_id)
    if not merged_product:
        raise HTTPException(status_code=404, detail="Merged product not found")

    product_ids = [p.id for p in merged_product.products]
    if not product_ids: return []

    history_entries = (
        db.query(PriceHistory)
        .join(Product)
        .options(joinedload(PriceHistory.product).joinedload(Product.retailer))
        .filter(PriceHistory.product_id.in_(product_ids))
        .order_by(PriceHistory.date.asc())
        .all()
    )

    response = []
    for entry in history_entries:
        response.append({
            "price": entry.price,
            "date": entry.date,
            "retailer": entry.product.retailer
        })# scripts/merge_products.py
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
            if product.normalized_model and product.normalized_model.strip():
                key = (product.category_id, product.normalized_model)
                groups_by_normalized_model[key].append(product)
            else:
                products_left_over.append(product)

        for (category_id, model_key), listings in groups_by_normalized_model.items():
            if len(listings) > 1:
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
                products_left_over.extend(listings)
        
        # Commit after the first pass to make these new products available for the next pass
        db_session.commit()
        print(f"  -> Committed {len(groups_by_normalized_model) - len(products_left_over)} high-confidence groups.")
        print(f"  -> {len(products_left_over)} products remaining for fuzzy matching.")


        # --- PASS 2: Stricter Fuzzy Matching for Leftovers ---
        print("\n--- Pass 2: Fuzzy matching for remaining products ---")

        products_by_category = defaultdict(list)
        for p in products_left_over:
            if p.category:
                products_by_category[p.category_id].append(p)
        
        # A local cache to track merged products created *within this pass*
        # before they are committed to the DB. This prevents race conditions.
        newly_merged_cache = {}

        for category_id, products_in_category in products_by_category.items():
            cat_name = products_in_category[0].category.name if products_in_category else "N/A"
            print(f"\nProcessing category '{cat_name}' ({len(products_in_category)} products)...")

            # Get all merged products that already exist in the DB for this category
            existing_in_db_category = db_session.execute(
                select(MergedProduct).where(MergedProduct.category_id == category_id)
            ).scalars().all()

            for i, product in enumerate(products_in_category):
                print(f"  -> Sorting: {i + 1}/{len(products_in_category)}", end='\r')
                
                # Skip if already merged in Pass 1
                if any(product in mp.products for mp in db_session.new if isinstance(mp, MergedProduct)):
                    continue

                best_match = None
                highest_score = 0

                # Check against products already in the DB for this category
                for merged_product in existing_in_db_category:
                    score = fuzz.token_set_ratio(product.name, merged_product.canonical_name)
                    if score > highest_score:
                        highest_score = score
                        best_match = merged_product
                
                # Also check against products we've just created in this pass's cache
                for cached_name, cached_mp in newly_merged_cache.items():
                     score = fuzz.token_set_ratio(product.name, cached_name)
                     if score > highest_score:
                        highest_score = score
                        best_match = cached_mp

                if highest_score >= SIMILARITY_THRESHOLD and best_match:
                    # Found a suitable fuzzy match, add the listing to it.
                    best_match.products.append(product)
                else:
                    # No fuzzy match. Check for an exact match in the cache first.
                    if product.name in newly_merged_cache:
                        newly_merged_cache[product.name].products.append(product)
                    else:
                        # Not in the cache, now check the DB globally for an exact match.
                        global_match = db_session.execute(
                            select(MergedProduct).where(MergedProduct.canonical_name == product.name)
                        ).scalar_one_or_none()

                        if global_match:
                            global_match.products.append(product)
                        else:
                            # This product is truly unique. Create it, add to the session, and add to our local cache.
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
                            newly_merged_cache[product.name] = new_merged_product
            print() # Newline for cleaner logging

        # Commit all pending changes from Pass 2 at the very end.
        print("\nCommitting all Pass 2 changes...")
        db_session.commit()
        print("--- Two-Pass Merging Process Complete ---")

    except Exception as e:
        print(f"\nAn error occurred during the merging process: {e}")
        import traceback
        traceback.print_exc()
        db_session.rollback()
    finally:
        if db_session.is_active:
            db_session.close()
            print("Database session closed.")


    return response

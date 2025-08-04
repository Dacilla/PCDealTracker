import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select, func, asc, desc, cast, Float, and_

from ..dependencies import get_db
from ..database import MergedProduct, Product, PriceHistory, ProductStatus, merged_product_association
from .products import ProductSchema, CategorySchema, RetailerSchema

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

def _process_merged_product(mp: MergedProduct, db: Session) -> MergedProductSchema:
    """Helper function to process a single MergedProduct object."""
    merged_schema = MergedProductSchema.model_validate(mp)
    
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

        if price_stats:
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
    
    merged_schema.listings = [ProductSchema.model_validate(p) for p in mp.products]
    return merged_schema

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
    hide_unavailable: bool = Query(False), # New parameter
):
    """
    Retrieve a paginated list of merged products with dynamic attribute and range filtering.
    """
    min_price_subquery = (
        select(
            merged_product_association.c.merged_product_id,
            func.min(Product.current_price).label("min_price"),
        )
        .join(Product, merged_product_association.c.product_id == Product.id)
        .where(Product.status == ProductStatus.AVAILABLE)
        .group_by(merged_product_association.c.merged_product_id)
        .subquery()
    )
    
    # If hiding unavailable, we must have a match in the min_price_subquery (INNER JOIN)
    # Otherwise, we can include products with no available listings (LEFT JOIN)
    is_outer_join = not hide_unavailable

    query = (
        select(MergedProduct)
        .join(min_price_subquery, MergedProduct.id == min_price_subquery.c.merged_product_id, isouter=is_outer_join)
        .options(
            joinedload(MergedProduct.category),
            selectinload(MergedProduct.products).joinedload(Product.retailer)
        )
    )
    
    filters = []
    if search:
        if search_mode == "strict":
            filters.append(MergedProduct.canonical_name.ilike(f"%{search}%"))
        else:
            search_terms = search.split()
            search_conditions = [MergedProduct.canonical_name.ilike(f"%{term}%") for term in search_terms]
            filters.append(and_(*search_conditions))

    if category_id: filters.append(MergedProduct.category_id == category_id)
    if min_price is not None: filters.append(min_price_subquery.c.min_price >= min_price)
    if max_price is not None: filters.append(min_price_subquery.c.min_price <= max_price)

    known_params = ['page', 'page_size', 'search', 'search_mode', 'category_id', 'sort_by', 'sort_order', 'min_price', 'max_price', 'hide_unavailable']
    query_params = request.query_params
    
    for key in query_params.keys():
        if key not in known_params:
            if key.startswith("min_"):
                attr_key = key[4:]
                value = query_params.get(key)
                filters.append(cast(MergedProduct.attributes[attr_key], Float) >= float(value))
            elif key.startswith("max_"):
                attr_key = key[4:]
                value = query_params.get(key)
                filters.append(cast(MergedProduct.attributes[attr_key], Float) <= float(value))
            else:
                value = query_params.get(key)
                filters.append(MergedProduct.attributes[key].as_string() == value)

    if filters:
        query = query.where(*filters)

    count_query = select(func.count(MergedProduct.id.distinct())).join(
        min_price_subquery, MergedProduct.id == min_price_subquery.c.merged_product_id, isouter=is_outer_join
    ).where(*filters)
    total = db.execute(count_query).scalar_one()

    # --- Sorting Logic ---
    if sort_by == "price":
        order_column = asc(min_price_subquery.c.min_price) if sort_order == "asc" else desc(min_price_subquery.c.min_price)
        query = query.order_by(order_column.nulls_last())
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
        order_column = desc(most_recent_date_subquery.c.max_date)
        query = query.order_by(order_column.nulls_last())
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
        
        order_column = desc(discount_calc)
        query = query.order_by(order_column.nulls_last())
    else:
        order_column = asc(MergedProduct.canonical_name) if sort_order == "asc" else desc(MergedProduct.canonical_name)
        query = query.order_by(order_column)
    
    skip = (page - 1) * page_size
    results = db.execute(query.offset(skip).limit(page_size)).scalars().unique().all()

    processed_results = [_process_merged_product(mp, db) for mp in results]

    return {"total": total, "products": processed_results}

@router.get("/{merged_product_id}", response_model=MergedProductSchema)
def read_single_merged_product(merged_product_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single merged product by its ID.
    """
    query = (
        select(MergedProduct)
        .options(
            joinedload(MergedProduct.category),
            selectinload(MergedProduct.products).joinedload(Product.retailer)
        )
        .where(MergedProduct.id == merged_product_id)
    )
    result = db.execute(query).scalars().unique().first()
    if not result:
        raise HTTPException(status_code=404, detail="Merged product not found")
    
    return _process_merged_product(result, db)

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
        })

    return response

import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select, func, asc, desc

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
    
    listings: List[ProductSchema] = []
    
    best_price: Optional[float] = None
    best_price_url: Optional[str] = None
    best_price_retailer: Optional[str] = None

    all_time_low_price: Optional[float] = None
    all_time_low_date: Optional[datetime.datetime] = None
    all_time_low_retailer_name: Optional[str] = None


class MergedProductPage(BaseModel):
    total: int
    products: List[MergedProductSchema]

# --- API Router ---
router = APIRouter(
    prefix="/api/v1/merged-products",
    tags=["Merged Products"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=MergedProductPage)
def read_merged_products(
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = Query(None, description="Search by canonical name"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    sort_by: Optional[str] = Query("name", description="Sort by 'name' or 'price'"),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
):
    """
    Retrieve a paginated list of merged products, with sorting, filtering, and all-time low data.
    """
    query = (
        select(MergedProduct)
        .options(
            joinedload(MergedProduct.category),
            selectinload(MergedProduct.products).joinedload(Product.retailer)
        )
    )
    count_query = select(func.count()).select_from(MergedProduct)

    filters = []
    if search:
        filters.append(MergedProduct.canonical_name.ilike(f"%{search}%"))
    if category_id:
        filters.append(MergedProduct.category_id == category_id)
    
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.execute(count_query).scalar_one()

    # --- Sorting Logic ---
    if sort_by == "price":
        # Subquery to find the minimum price for each merged product
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
        query = query.join(
            min_price_subquery,
            MergedProduct.id == min_price_subquery.c.merged_product_id,
            isouter=True
        )
        order_column = asc(min_price_subquery.c.min_price) if sort_order == "asc" else desc(min_price_subquery.c.min_price)
        query = query.order_by(order_column.nulls_last())
    else: # Default to sorting by name
        order_column = asc(MergedProduct.canonical_name) if sort_order == "asc" else desc(MergedProduct.canonical_name)
        query = query.order_by(order_column)
    
    skip = (page - 1) * page_size
    results = db.execute(query.offset(skip).limit(page_size)).scalars().unique().all()

    processed_results = []
    for mp in results:
        merged_schema = MergedProductSchema.model_validate(mp)
        
        available_listings = [p for p in mp.products if p.current_price is not None and p.status == ProductStatus.AVAILABLE]
        if available_listings:
            best_listing = min(available_listings, key=lambda p: p.current_price)
            merged_schema.best_price = best_listing.current_price
            merged_schema.best_price_url = best_listing.url
            merged_schema.best_price_retailer = best_listing.retailer.name
        
        product_ids = [p.id for p in mp.products]
        if product_ids:
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
        processed_results.append(merged_schema)

    return {"total": total, "products": processed_results}

@router.get("/{merged_product_id}/price-history", response_model=List[PriceHistoryWithRetailerSchema])
def get_combined_price_history(merged_product_id: int, db: Session = Depends(get_db)):
    """
    Retrieve the combined price history for all listings of a merged product.
    """
    merged_product = db.get(MergedProduct, merged_product_id)
    if not merged_product:
        raise HTTPException(status_code=404, detail="Merged product not found")

    product_ids = [p.id for p in merged_product.products]

    if not product_ids:
        return []

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

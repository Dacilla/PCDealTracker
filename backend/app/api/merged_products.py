import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select, func

from ..dependencies import get_db
from ..database import MergedProduct, Product, PriceHistory, ProductStatus
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
):
    """
    Retrieve a paginated list of merged products.
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
    
    skip = (page - 1) * page_size
    results = db.execute(query.order_by(MergedProduct.canonical_name).offset(skip).limit(page_size)).scalars().unique().all()

    processed_results = []
    for mp in results:
        merged_schema = MergedProductSchema.model_validate(mp)
        
        available_listings = [p for p in mp.products if p.current_price is not None and p.status == ProductStatus.AVAILABLE]
        
        if available_listings:
            best_listing = min(available_listings, key=lambda p: p.current_price)
            merged_schema.best_price = best_listing.current_price
            merged_schema.best_price_url = best_listing.url
            merged_schema.best_price_retailer = best_listing.retailer.name
        
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

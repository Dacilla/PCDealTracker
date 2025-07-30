from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func

# Import schemas and dependencies from other modules
from ..dependencies import get_db
from ..database import Product, Category
from .products import ProductSchema # Re-use the ProductSchema from the products API

# --- Pydantic Schemas ---

class DealStats(BaseModel):
    """Defines the shape of the deal statistics response."""
    total_deals: int
    # We can add more stats here later, like average discount.

# --- API Router ---
router = APIRouter(
    prefix="/api/v1/deals",
    tags=["Deals"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[ProductSchema])
def read_deals(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 1000,
    category_name: Optional[str] = Query(None, description="Filter by category name")
):
    """
    Retrieve a list of products that are currently on sale.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.on_sale == True) # The core logic for finding deals
        .order_by(Product.id)
    )

    if category_name:
        query = query.join(Product.category).where(Category.name == category_name)

    deals = db.execute(query.offset(skip).limit(limit)).scalars().all()
    return deals

# --- NEW ENDPOINT ---
@router.get("/category/{category_id}", response_model=List[ProductSchema])
def read_deals_by_category(category_id: int, db: Session = Depends(get_db)):
    """
    Retrieve all deals belonging to a specific category ID.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.on_sale == True, Product.category_id == category_id)
        .order_by(Product.id)
    )
    deals = db.execute(query).scalars().all()
    return deals


@router.get("/stats", response_model=DealStats)
def get_deal_stats(db: Session = Depends(get_db)):
    """
    Get statistics about the current deals.
    """
    total_deals = db.query(func.count(Product.id)).filter(Product.on_sale == True).scalar()
    return {"total_deals": total_deals or 0}

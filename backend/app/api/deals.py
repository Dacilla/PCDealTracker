from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func

from ..dependencies import get_db
from ..database import Product, Category
from .products import ProductSchema

class DealStats(BaseModel):
    total_deals: int

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
    search: Optional[str] = Query(None, description="Search for deals by name")
):
    """
    Retrieve a list of products on sale, with an option to search.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.on_sale == True)
        .order_by(Product.id)
    )

    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))

    deals = db.execute(query.offset(skip).limit(limit)).scalars().all()
    return deals

@router.get("/category/{category_id}", response_model=List[ProductSchema])
def read_deals_by_category(
    category_id: int, 
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search for deals by name")
):
    """
    Retrieve deals for a specific category, with an option to search.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.on_sale == True, Product.category_id == category_id)
        .order_by(Product.id)
    )
    
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
        
    deals = db.execute(query).scalars().all()
    return deals

@router.get("/stats", response_model=DealStats)
def get_deal_stats(db: Session = Depends(get_db)):
    """
    Get statistics about the current deals.
    """
    total_deals = db.query(func.count(Product.id)).filter(Product.on_sale == True).scalar()
    return {"total_deals": total_deals or 0}

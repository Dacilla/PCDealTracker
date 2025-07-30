from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, asc, desc

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
    search: Optional[str] = Query(None, description="Search for deals by name"),
    sort_by: Optional[str] = Query(None, description="Sort by 'price'"),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
    retailer_id: Optional[int] = Query(None, description="Filter by retailer ID")
):
    """
    Retrieve a list of products on sale, with options for searching, sorting, and filtering.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.on_sale == True)
    )

    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))

    if retailer_id:
        query = query.where(Product.retailer_id == retailer_id)

    if sort_by == "price":
        order_column = asc(Product.current_price) if sort_order == "asc" else desc(Product.current_price)
        query = query.order_by(order_column)
    else:
        query = query.order_by(Product.id)

    deals = db.execute(query.offset(skip).limit(limit)).scalars().all()
    return deals

@router.get("/category/{category_id}", response_model=List[ProductSchema])
def read_deals_by_category(
    category_id: int, 
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search for deals by name"),
    sort_by: Optional[str] = Query(None, description="Sort by 'price'"),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
    retailer_id: Optional[int] = Query(None, description="Filter by retailer ID")
):
    """
    Retrieve deals for a specific category, with options for searching, sorting, and filtering.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.on_sale == True, Product.category_id == category_id)
    )
    
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
        
    if retailer_id:
        query = query.where(Product.retailer_id == retailer_id)

    if sort_by == "price":
        order_column = asc(Product.current_price) if sort_order == "asc" else desc(Product.current_price)
        query = query.order_by(order_column)
    else:
        query = query.order_by(Product.id)

    deals = db.execute(query).scalars().all()
    return deals

@router.get("/stats", response_model=DealStats)
def get_deal_stats(db: Session = Depends(get_db)):
    """
    Get statistics about the current deals.
    """
    total_deals = db.query(func.count(Product.id)).filter(Product.on_sale == True).scalar()
    return {"total_deals": total_deals or 0}

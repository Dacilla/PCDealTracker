from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, asc, desc, func

from ..database import Product, Category, Retailer
from ..dependencies import get_db
from .price_history import PriceHistorySchema # Import the correct schema

class RetailerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    logo_url: Optional[str] = None

class CategorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

class ProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    sku: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    current_price: Optional[float] = None
    on_sale: bool
    retailer: RetailerSchema
    category: CategorySchema

class ProductPage(BaseModel):
    total: int
    products: List[ProductSchema]


router = APIRouter(
    prefix="/api/v1/products",
    tags=["Products"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=ProductPage)
def read_products(
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = Query(None, description="Search for products by name"),
    sort_by: Optional[str] = Query(None, description="Sort by 'price'"),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
    retailer_id: Optional[int] = Query(None, description="Filter by retailer ID")
):
    """
    Retrieve a paginated list of all products, with options for searching, sorting, and filtering.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
    )
    count_query = select(func.count()).select_from(Product)
    
    base_filters = []
    if search:
        base_filters.append(Product.name.ilike(f"%{search}%"))
    if retailer_id:
        base_filters.append(Product.retailer_id == retailer_id)

    if base_filters:
        query = query.where(*base_filters)
        count_query = count_query.where(*base_filters)

    total = db.execute(count_query).scalar_one()

    if sort_by == "price":
        order_column = asc(Product.current_price) if sort_order == "asc" else desc(Product.current_price)
        query = query.order_by(order_column)
    else:
        query = query.order_by(Product.id)
        
    skip = (page - 1) * page_size
    query = query.offset(skip).limit(page_size)
    products = db.execute(query).scalars().all()
    return {"total": total, "products": products}

@router.get("/category/{category_id}", response_model=ProductPage)
def read_products_by_category(
    category_id: int, 
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = Query(None, description="Search for products by name"),
    sort_by: Optional[str] = Query(None, description="Sort by 'price'"),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
    retailer_id: Optional[int] = Query(None, description="Filter by retailer ID")
):
    """
    Retrieve paginated products for a specific category, with options for searching, sorting, and filtering.
    """
    base_filters = [Product.category_id == category_id]
    if search:
        base_filters.append(Product.name.ilike(f"%{search}%"))
    if retailer_id:
        base_filters.append(Product.retailer_id == retailer_id)
    
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(*base_filters)
    )
    count_query = select(func.count()).select_from(Product).where(*base_filters)
    
    total = db.execute(count_query).scalar_one()

    if sort_by == "price":
        order_column = asc(Product.current_price) if sort_order == "asc" else desc(Product.current_price)
        query = query.order_by(order_column)
    else:
        query = query.order_by(Product.id)

    skip = (page - 1) * page_size
    products = db.execute(query.offset(skip).limit(page_size)).scalars().all()
    return {"total": total, "products": products}


@router.get("/{product_id}", response_model=ProductSchema)
def read_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).options(
        joinedload(Product.retailer), 
        joinedload(Product.category)
    ).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

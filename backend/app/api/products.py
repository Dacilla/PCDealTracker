from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from ..database import Product, Category, Retailer
from ..dependencies import get_db

class RetailerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str

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

router = APIRouter(
    prefix="/api/v1/products",
    tags=["Products"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[ProductSchema])
def read_products(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 1000,
    category_name: Optional[str] = Query(None, description="Filter by category name"),
    retailer_name: Optional[str] = Query(None, description="Filter by retailer name"),
    on_sale: Optional[bool] = Query(None, description="Filter for products that are on sale")
):
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .order_by(Product.id)
    )
    if category_name:
        query = query.join(Product.category).where(Category.name == category_name)
    if retailer_name:
        query = query.join(Product.retailer).where(Retailer.name == retailer_name)
    if on_sale is not None:
        query = query.where(Product.on_sale == on_sale)
        
    query = query.offset(skip).limit(limit)
    products = db.execute(query).scalars().all()
    return products

@router.get("/{product_id}", response_model=ProductSchema)
def read_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).options(
        joinedload(Product.retailer), 
        joinedload(Product.category)
    ).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

# --- NEW ENDPOINT ---
@router.get("/category/{category_id}", response_model=List[ProductSchema])
def read_products_by_category(category_id: int, db: Session = Depends(get_db)):
    """
    Retrieve all products belonging to a specific category ID.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.category_id == category_id)
        .order_by(Product.id)
    )
    products = db.execute(query).scalars().all()
    return products

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
    search: Optional[str] = Query(None, description="Search for products by name")
):
    """
    Retrieve a list of all products, with an option to search by name.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .order_by(Product.id)
    )
    
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
        
    query = query.offset(skip).limit(limit)
    products = db.execute(query).scalars().all()
    return products

@router.get("/category/{category_id}", response_model=List[ProductSchema])
def read_products_by_category(
    category_id: int, 
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search for products by name")
):
    """
    Retrieve products for a specific category, with an option to search.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .where(Product.category_id == category_id)
        .order_by(Product.id)
    )

    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))

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

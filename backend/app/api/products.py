from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

# Import database models and the session dependency
from ..database import Product, Category, Retailer
from ..dependencies import get_db

# --- Pydantic Schemas ---
# These models define the shape of the data for API requests and responses.
# They ensure that the data is valid and provide serialization.

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
    # This tells Pydantic to read the data even if it is not a dict, but an ORM model.
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    sku: Optional[str] = None
    url: str
    current_price: Optional[float] = None
    on_sale: bool
    
    # These will be populated with the nested schema data
    retailer: RetailerSchema
    category: CategorySchema

# --- API Router ---
# We create a router to group all the product-related endpoints.
router = APIRouter(
    prefix="/api/v1/products",
    tags=["Products"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[ProductSchema])
def read_products(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    category_name: Optional[str] = Query(None, description="Filter by category name, e.g., 'Graphics Cards'"),
    on_sale: Optional[bool] = Query(None, description="Filter for products that are on sale")
):
    """
    Retrieve a list of products with optional filtering and pagination.
    """
    query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category))
        .order_by(Product.id)
    )

    # Apply filters conditionally
    if category_name:
        query = query.join(Category).where(Category.name == category_name)
    
    if on_sale is not None:
        query = query.where(Product.on_sale == on_sale)

    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    products = db.execute(query).scalars().all()
    return products


@router.get("/{product_id}", response_model=ProductSchema)
def read_product(product_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single product by its ID.
    """
    # We use joinedload to efficiently fetch the related retailer and category in the same query.
    product = db.query(Product).options(
        joinedload(Product.retailer), 
        joinedload(Product.category)
    ).filter(Product.id == product_id).first()

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product


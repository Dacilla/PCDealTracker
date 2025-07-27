from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db, Product, Category, Retailer

router = APIRouter()

# Pydantic models for API responses
class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    
    class Config:
        from_attributes = True

class RetailerResponse(BaseModel):
    id: int
    name: str
    website_url: str
    
    class Config:
        from_attributes = True

class ProductResponse(BaseModel):
    id: int
    name: str
    brand: Optional[str]
    model: Optional[str]
    current_price: Optional[float]
    original_price: Optional[float]
    is_on_sale: bool
    sale_percentage: Optional[float]
    in_stock: bool
    is_deal: bool
    is_historical_low: bool
    deal_score: Optional[float]
    product_url: str
    image_url: Optional[str]
    retailer: RetailerResponse
    category: CategoryResponse
    last_updated: Optional[datetime]
    
    class Config:
        from_attributes = True

class ProductListResponse(BaseModel):
    products: List[ProductResponse]
    total: int
    page: int
    per_page: int
    total_pages: int

@router.get("/products", response_model=ProductListResponse)
async def get_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = Query(None),
    retailer_id: Optional[int] = Query(None),
    brand: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    on_sale: Optional[bool] = Query(None),
    deals_only: Optional[bool] = Query(None),
    in_stock_only: bool = Query(True),
    search: Optional[str] = Query(None)
):
    """Get products with filtering and pagination"""
    
    query = db.query(Product).filter(Product.is_active == True)
    
    # Apply filters
    if category_id:
        query = query.filter(Product.category_id == category_id)
    
    if retailer_id:
        query = query.filter(Product.retailer_id == retailer_id)
    
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    
    if min_price is not None:
        query = query.filter(Product.current_price >= min_price)
    
    if max_price is not None:
        query = query.filter(Product.current_price <= max_price)
    
    if on_sale is not None:
        query = query.filter(Product.is_on_sale == on_sale)
    
    if deals_only:
        query = query.filter(Product.is_deal == True)
    
    if in_stock_only:
        query = query.filter(Product.in_stock == True)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            Product.name.ilike(search_term) | 
            Product.brand.ilike(search_term) |
            Product.model.ilike(search_term)
        )
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * per_page
    products = query.offset(offset).limit(per_page).all()
    
    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    
    return ProductListResponse(
        products=products,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages
    )

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get a specific product by ID"""
    
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product

@router.get("/categories", response_model=List[CategoryResponse])
async def get_categories(db: Session = Depends(get_db)):
    """Get all product categories"""
    
    categories = db.query(Category).all()
    return categories

@router.get("/retailers", response_model=List[RetailerResponse])
async def get_retailers(db: Session = Depends(get_db)):
    """Get all retailers"""
    
    retailers = db.query(Retailer).filter(Retailer.is_active == True).all()
    return retailers

@router.get("/products/{product_id}/similar")
async def get_similar_products(
    product_id: int, 
    db: Session = Depends(get_db),
    limit: int = Query(5, ge=1, le=20)
):
    """Get similar products based on category and brand"""
    
    # Get the original product
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Find similar products (same category, preferably same brand)
    similar_query = db.query(Product).filter(
        Product.id != product_id,
        Product.category_id == product.category_id,
        Product.is_active == True,
        Product.in_stock == True
    )
    
    # Prioritize same brand
    if product.brand:
        same_brand = similar_query.filter(Product.brand == product.brand).limit(limit//2).all()
        different_brand = similar_query.filter(Product.brand != product.brand).limit(limit - len(same_brand)).all()
        similar_products = same_brand + different_brand
    else:
        similar_products = similar_query.limit(limit).all()
    
    return {"similar_products": similar_products[:limit]}
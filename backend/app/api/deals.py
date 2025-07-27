from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.database import get_db, Product, Category, Retailer

router = APIRouter()

# Pydantic models
class DealResponse(BaseModel):
    id: int
    name: str
    brand: Optional[str]
    current_price: Optional[float]
    original_price: Optional[float]
    sale_percentage: Optional[float]
    deal_score: Optional[float]
    is_historical_low: bool
    product_url: str
    image_url: Optional[str]
    retailer_name: str
    retailer_id: int
    category_name: str
    last_updated: Optional[datetime]
    
    class Config:
        from_attributes = True

class DealStats(BaseModel):
    total_deals: int
    historical_lows: int
    average_discount: float
    top_categories: List[dict]
    top_retailers: List[dict]

@router.get("/deals", response_model=List[DealResponse])
async def get_deals(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    category_id: Optional[int] = Query(None),
    retailer_id: Optional[int] = Query(None),
    min_discount: float = Query(0, ge=0, le=100),
    historical_lows_only: bool = Query(False),
    sort_by: str = Query("deal_score", regex="^(deal_score|discount|price|updated)$")
):
    """Get current deals with filtering options"""
    
    query = db.query(Product).join(Retailer).join(Category).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_deal == True
    )
    
    # Apply filters
    if category_id:
        query = query.filter(Product.category_id == category_id)
    
    if retailer_id:
        query = query.filter(Product.retailer_id == retailer_id)
    
    if min_discount > 0:
        query = query.filter(Product.sale_percentage >= min_discount)
    
    if historical_lows_only:
        query = query.filter(Product.is_historical_low == True)
    
    # Apply sorting
    if sort_by == "deal_score":
        query = query.order_by(desc(Product.deal_score))
    elif sort_by == "discount":
        query = query.order_by(desc(Product.sale_percentage))
    elif sort_by == "price":
        query = query.order_by(Product.current_price)
    elif sort_by == "updated":
        query = query.order_by(desc(Product.last_updated))
    
    deals = query.limit(limit).all()
    
    # Format response
    deal_responses = []
    for product in deals:
        deal_responses.append(DealResponse(
            id=product.id,
            name=product.name,
            brand=product.brand,
            current_price=product.current_price,
            original_price=product.original_price,
            sale_percentage=product.sale_percentage,
            deal_score=product.deal_score,
            is_historical_low=product.is_historical_low,
            product_url=product.product_url,
            image_url=product.image_url,
            retailer_name=product.retailer.name,
            retailer_id=product.retailer_id,
            category_name=product.category.name,
            last_updated=product.last_updated
        ))
    
    return deal_responses

@router.get("/deals/stats", response_model=DealStats)
async def get_deal_stats(db: Session = Depends(get_db)):
    """Get statistics about current deals"""
    
    # Total deals
    total_deals = db.query(Product).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_deal == True
    ).count()
    
    # Historical lows
    historical_lows = db.query(Product).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_historical_low == True
    ).count()
    
    # Average discount
    avg_result = db.query(Product).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_deal == True,
        Product.sale_percentage.isnot(None)
    ).all()
    
    if avg_result:
        average_discount = sum(p.sale_percentage for p in avg_result if p.sale_percentage) / len(avg_result)
    else:
        average_discount = 0.0
    
    # Top categories by deal count
    top_categories_query = db.query(
        Category.name,
        Category.id
    ).join(Product).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_deal == True
    ).group_by(Category.id, Category.name).all()
    
    category_counts = {}
    for cat_name, cat_id in top_categories_query:
        count = db.query(Product).filter(
            Product.category_id == cat_id,
            Product.is_active == True,
            Product.in_stock == True,
            Product.is_deal == True
        ).count()
        category_counts[cat_name] = count
    
    top_categories = [
        {"name": name, "deal_count": count}
        for name, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]
    
    # Top retailers by deal count
    top_retailers_query = db.query(
        Retailer.name,
        Retailer.id
    ).join(Product).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_deal == True
    ).group_by(Retailer.id, Retailer.name).all()
    
    retailer_counts = {}
    for ret_name, ret_id in top_retailers_query:
        count = db.query(Product).filter(
            Product.retailer_id == ret_id,
            Product.is_active == True,
            Product.in_stock == True,
            Product.is_deal == True
        ).count()
        retailer_counts[ret_name] = count
    
    top_retailers = [
        {"name": name, "deal_count": count}
        for name, count in sorted(retailer_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]
    
    return DealStats(
        total_deals=total_deals,
        historical_lows=historical_lows,
        average_discount=round(average_discount, 2),
        top_categories=top_categories,
        top_retailers=top_retailers
    )

@router.get("/deals/trending")
async def get_trending_deals(
    db: Session = Depends(get_db),
    hours: int = Query(24, ge=1, le=168),  # Last 1-168 hours (1 week)
    limit: int = Query(20, ge=1, le=100)
):
    """Get deals that were recently added or had significant price drops"""
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Recently added deals
    new_deals = db.query(Product).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_deal == True,
        Product.first_seen >= cutoff_time
    ).order_by(desc(Product.deal_score)).limit(limit//2).all()
    
    # Recently updated deals with significant changes
    updated_deals = db.query(Product).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_deal == True,
        Product.last_updated >= cutoff_time,
        Product.first_seen < cutoff_time  # Exclude new deals already captured above
    ).order_by(desc(Product.deal_score)).limit(limit//2).all()
    
    # Combine and format
    all_trending = new_deals + updated_deals
    trending_deals = []
    
    for product in all_trending[:limit]:
        trending_deals.append({
            "id": product.id,
            "name": product.name,
            "brand": product.brand,
            "current_price": product.current_price,
            "original_price": product.original_price,
            "sale_percentage": product.sale_percentage,
            "deal_score": product.deal_score,
            "is_historical_low": product.is_historical_low,
            "product_url": product.product_url,
            "image_url": product.image_url,
            "retailer_name": product.retailer.name,
            "category_name": product.category.name,
            "is_new": product.first_seen >= cutoff_time,
            "last_updated": product.last_updated
        })
    
    return {"trending_deals": trending_deals}

@router.get("/deals/historical-lows")
async def get_historical_lows(
    db: Session = Depends(get_db),
    category_id: Optional[int] = Query(None),
    limit: int = Query(30, ge=1, le=100)
):
    """Get products currently at their historical low prices"""
    
    query = db.query(Product).join(Retailer).join(Category).filter(
        Product.is_active == True,
        Product.in_stock == True,
        Product.is_historical_low == True
    )
    
    if category_id:
        query = query.filter(Product.category_id == category_id)
    
    products = query.order_by(desc(Product.deal_score)).limit(limit).all()
    
    historical_low_deals = []
    for product in products:
        historical_low_deals.append({
            "id": product.id,
            "name": product.name,
            "brand": product.brand,
            "current_price": product.current_price,
            "deal_score": product.deal_score,
            "product_url": product.product_url,
            "image_url": product.image_url,
            "retailer_name": product.retailer.name,
            "category_name": product.category.name,
            "last_updated": product.last_updated
        })
    
    return {"historical_lows": historical_low_deals}
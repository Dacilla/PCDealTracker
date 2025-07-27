from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.database import get_db, Product, PriceHistory, Retailer

router = APIRouter()

# Pydantic models
class PricePoint(BaseModel):
    price: float
    original_price: Optional[float]
    is_sale: bool
    sale_percentage: Optional[float]
    in_stock: bool
    recorded_at: datetime
    retailer_name: str
    
    class Config:
        from_attributes = True

class PriceHistoryResponse(BaseModel):
    product_id: int
    product_name: str
    current_price: Optional[float]
    lowest_price: float
    highest_price: float
    average_price: float
    price_points: List[PricePoint]
    
class PriceStatistics(BaseModel):
    lowest_price: float
    highest_price: float
    average_price: float
    current_price: Optional[float]
    price_change_7d: Optional[float]
    price_change_30d: Optional[float]
    discount_frequency: float  # Percentage of time product was on sale
    last_sale_date: Optional[datetime]
    times_at_current_price: int

@router.get("/products/{product_id}/price-history", response_model=PriceHistoryResponse)
async def get_product_price_history(
    product_id: int,
    db: Session = Depends(get_db),
    days: int = Query(90, ge=1, le=365),
    retailer_id: Optional[int] = Query(None)
):
    """Get price history for a specific product"""
    
    # Verify product exists
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Calculate date range
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Build query
    query = db.query(PriceHistory).join(Retailer).filter(
        PriceHistory.product_id == product_id,
        PriceHistory.recorded_at >= cutoff_date
    )
    
    if retailer_id:
        query = query.filter(PriceHistory.retailer_id == retailer_id)
    
    price_records = query.order_by(PriceHistory.recorded_at).all()
    
    if not price_records:
        raise HTTPException(status_code=404, detail="No price history found for this product")
    
    # Calculate statistics
    prices = [record.price for record in price_records]
    lowest_price = min(prices)
    highest_price = max(prices)
    average_price = sum(prices) / len(prices)
    
    # Format price points
    price_points = []
    for record in price_records:
        price_points.append(PricePoint(
            price=record.price,
            original_price=record.original_price,
            is_sale=record.is_sale,
            sale_percentage=record.sale_percentage,
            in_stock=record.in_stock,
            recorded_at=record.recorded_at,
            retailer_name=record.retailer.name
        ))
    
    return PriceHistoryResponse(
        product_id=product_id,
        product_name=product.name,
        current_price=product.current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=round(average_price, 2),
        price_points=price_points
    )

@router.get("/products/{product_id}/price-stats", response_model=PriceStatistics)
async def get_product_price_statistics(
    product_id: int,
    db: Session = Depends(get_db),
    days: int = Query(90, ge=1, le=365)
):
    """Get detailed price statistics for a product"""
    
    # Verify product exists
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Calculate date ranges
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    month_ago = datetime.utcnow() - timedelta(days=30)
    
    # Get all price records in range
    price_records = db.query(PriceHistory).filter(
        PriceHistory.product_id == product_id,
        PriceHistory.recorded_at >= cutoff_date
    ).order_by(PriceHistory.recorded_at).all()
    
    if not price_records:
        raise HTTPException(status_code=404, detail="No price history found")
    
    prices = [record.price for record in price_records]
    lowest_price = min(prices)
    highest_price = max(prices)
    average_price = sum(prices) / len(prices)
    
    # Calculate price changes
    price_change_7d = None
    price_change_30d = None
    
    if product.current_price:
        # Find price 7 days ago
        week_record = db.query(PriceHistory).filter(
            PriceHistory.product_id == product_id,
            PriceHistory.recorded_at >= week_ago
        ).order_by(PriceHistory.recorded_at).first()
        
        if week_record:
            price_change_7d = product.current_price - week_record.price
        
        # Find price 30 days ago
        month_record = db.query(PriceHistory).filter(
            PriceHistory.product_id == product_id,
            PriceHistory.recorded_at >= month_ago
        ).order_by(PriceHistory.recorded_at).first()
        
        if month_record:
            price_change_30d = product.current_price - month_record.price
    
    # Calculate discount frequency
    sale_records = [record for record in price_records if record.is_sale]
    discount_frequency = (len(sale_records) / len(price_records)) * 100 if price_records else 0
    
    # Find last sale date
    last_sale_record = db.query(PriceHistory).filter(
        PriceHistory.product_id == product_id,
        PriceHistory.is_sale == True
    ).order_by(desc(PriceHistory.recorded_at)).first()
    
    last_sale_date = last_sale_record.recorded_at if last_sale_record else None
    
    # Count times at current price
    times_at_current_price = 0
    if product.current_price:
        times_at_current_price = db.query(PriceHistory).filter(
            PriceHistory.product_id == product_id,
            PriceHistory.price == product.current_price
        ).count()
    
    return PriceStatistics(
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=round(average_price, 2),
        current_price=product.current_price,
        price_change_7d=round(price_change_7d, 2) if price_change_7d else None,
        price_change_30d=round(price_change_30d, 2) if price_change_30d else None,
        discount_frequency=round(discount_frequency, 2),
        last_sale_date=last_sale_date,
        times_at_current_price=times_at_current_price
    )

@router.get("/price-alerts")
async def get_price_alerts(
    db: Session = Depends(get_db),
    alert_type: str = Query("drops", regex="^(drops|increases|deals)$"),
    hours: int = Query(24, ge=1, le=168),
    min_change_percentage: float = Query(10.0, ge=1.0, le=100.0)
):
    """Get price alerts based on recent changes"""
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Get recent price changes
    recent_records = db.query(PriceHistory).join(Product).join(Retailer).filter(
        PriceHistory.recorded_at >= cutoff_time,
        Product.is_active == True
    ).all()
    
    alerts = []
    
    for record in recent_records:
        product = record.product
        
        # Get previous price (before this record)
        previous_record = db.query(PriceHistory).filter(
            PriceHistory.product_id == record.product_id,
            PriceHistory.recorded_at < record.recorded_at
        ).order_by(desc(PriceHistory.recorded_at)).first()
        
        if not previous_record:
            continue
        
        # Calculate percentage change
        price_change = record.price - previous_record.price
        percentage_change = (price_change / previous_record.price) * 100
        
        # Check if it meets our criteria
        should_alert = False
        
        if alert_type == "drops" and percentage_change <= -min_change_percentage:
            should_alert = True
        elif alert_type == "increases" and percentage_change >= min_change_percentage:
            should_alert = True
        elif alert_type == "deals" and record.is_sale and abs(percentage_change) >= min_change_percentage:
            should_alert = True
        
        if should_alert:
            alerts.append({
                "product_id": product.id,
                "product_name": product.name,
                "brand": product.brand,
                "retailer_name": record.retailer.name,
                "previous_price": previous_record.price,
                "current_price": record.price,
                "price_change": round(price_change, 2),
                "percentage_change": round(percentage_change, 2),
                "is_sale": record.is_sale,
                "recorded_at": record.recorded_at,
                "product_url": product.product_url
            })
    
    # Sort by percentage change (biggest changes first)
    if alert_type == "drops":
        alerts.sort(key=lambda x: x["percentage_change"])
    else:
        alerts.sort(key=lambda x: x["percentage_change"], reverse=True)
    
    return {"alerts": alerts[:50]}  # Limit to 50 alerts

@router.get("/retailers/{retailer_id}/price-comparison")
async def compare_retailer_prices(
    retailer_id: int,
    db: Session = Depends(get_db),
    category_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """Compare prices from one retailer against others for the same products"""
    
    # Verify retailer exists
    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    # Get products from this retailer
    query = db.query(Product).filter(
        Product.retailer_id == retailer_id,
        Product.is_active == True,
        Product.in_stock == True
    )
    
    if category_id:
        query = query.filter(Product.category_id == category_id)
    
    products = query.limit(limit).all()
    
    comparisons = []
    
    for product in products:
        # Find similar products from other retailers
        # This is a simplified comparison - in practice, you'd want more sophisticated matching
        similar_products = db.query(Product).filter(
            Product.retailer_id != retailer_id,
            Product.name.ilike(f"%{product.name}%"),
            Product.is_active == True,
            Product.in_stock == True
        ).all()
        
        if similar_products:
            competitor_prices = [p.current_price for p in similar_products if p.current_price]
            
            if competitor_prices:
                min_competitor_price = min(competitor_prices)
                avg_competitor_price = sum(competitor_prices) / len(competitor_prices)
                
                price_difference = product.current_price - min_competitor_price if product.current_price else None
                
                comparisons.append({
                    "product": {
                        "id": product.id,
                        "name": product.name,
                        "brand": product.brand,
                        "price": product.current_price,
                        "url": product.product_url
                    },
                    "competitor_analysis": {
                        "min_competitor_price": min_competitor_price,
                        "avg_competitor_price": round(avg_competitor_price, 2),
                        "price_difference": round(price_difference, 2) if price_difference else None,
                        "is_cheapest": product.current_price <= min_competitor_price if product.current_price else False,
                        "competitor_count": len(similar_products)
                    }
                })
    
    return {
        "retailer": retailer.name,
        "comparisons": comparisons
    }
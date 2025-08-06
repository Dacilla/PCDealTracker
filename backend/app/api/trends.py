import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, and_, desc

from ..dependencies import get_db
from ..database import MergedProduct, Product, PriceHistory
# FIX: Import the helper function from merged_products
from .merged_products import MergedProductSchema, _process_merged_product

# --- Pydantic Schemas ---

class PriceDropSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    product: MergedProductSchema
    initial_price: float
    latest_price: float
    price_drop_amount: float
    price_drop_percentage: float

# --- API Router ---
router = APIRouter(
    prefix="/api/v1/trends",
    tags=["Trends"],
    responses={404: {"description": "Not found"}},
)

@router.get("/biggest-drops", response_model=List[PriceDropSchema])
def get_biggest_price_drops(db: Session = Depends(get_db)):
    """
    Calculates and returns the products with the biggest price drops over the last 7 days.
    """
    seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    # Subquery to find the earliest price for each product in the last 7 days
    initial_price_sq = (
        select(
            PriceHistory.product_id,
            PriceHistory.price.label("initial_price")
        )
        .where(PriceHistory.date >= seven_days_ago)
        .distinct(PriceHistory.product_id)
        .order_by(PriceHistory.product_id, PriceHistory.date.asc())
        .subquery()
    )

    # Subquery to find the latest price for each product
    latest_price_sq = (
        select(
            PriceHistory.product_id,
            PriceHistory.price.label("latest_price")
        )
        .distinct(PriceHistory.product_id)
        .order_by(PriceHistory.product_id, PriceHistory.date.desc())
        .subquery()
    )
    
    # Define the calculation for the percentage drop
    price_drop_percentage_calc = (((initial_price_sq.c.initial_price - latest_price_sq.c.latest_price) / initial_price_sq.c.initial_price) * 100)

    # Main query to join the data and calculate the drops
    query = (
        select(
            MergedProduct,
            initial_price_sq.c.initial_price,
            latest_price_sq.c.latest_price,
            (initial_price_sq.c.initial_price - latest_price_sq.c.latest_price).label("price_drop_amount"),
            price_drop_percentage_calc.label("price_drop_percentage")
        )
        .join(MergedProduct.products)
        .join(initial_price_sq, Product.id == initial_price_sq.c.product_id)
        .join(latest_price_sq, Product.id == latest_price_sq.c.product_id)
        .where(
            initial_price_sq.c.initial_price > latest_price_sq.c.latest_price
        )
        .options(
            joinedload(MergedProduct.category),
            joinedload(MergedProduct.products).joinedload(Product.retailer)
        )
        .order_by(desc(func.coalesce(price_drop_percentage_calc, 0)))
        .limit(20) # Limit to the top 20 biggest drops
    )

    results = db.execute(query).unique().all()

    # Format the results into the Pydantic schema
    response = []
    for row in results:
        mp, initial, latest, drop_amount, drop_percent = row
        
        # FIX: Use the centralized helper function to ensure consistent data structure
        product_data = _process_merged_product(mp, db)
        
        response.append(
            PriceDropSchema(
                product=product_data,
                initial_price=initial,
                latest_price=latest,
                price_drop_amount=drop_amount,
                price_drop_percentage=drop_percent
            )
        )

    return response

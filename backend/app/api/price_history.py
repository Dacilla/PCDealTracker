import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..database import PriceHistory, Product

# --- Pydantic Schemas ---

class PriceHistorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    price: float
    date: datetime.datetime

# --- API Router ---
router = APIRouter(
    prefix="/api/v1/products", # Note: We attach this to the /products prefix
    tags=["Price History"],
    responses={404: {"description": "Not found"}},
)

@router.get("/{product_id}/price-history", response_model=List[PriceHistorySchema])
def read_price_history(product_id: int, db: Session = Depends(get_db)):
    """
    Retrieve the price history for a specific product.
    """
    # First, check if the product actually exists.
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Query for the price history, ordered by date.
    history = (
        db.query(PriceHistory)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.date.asc())
        .all()
    )
    
    return history

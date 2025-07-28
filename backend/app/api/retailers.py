from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..dependencies import get_db
from ..database import Retailer
# We can reuse the schema defined in the products API
from .products import RetailerSchema

router = APIRouter(
    prefix="/api/v1/retailers",
    tags=["Retailers"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[RetailerSchema])
def read_retailers(db: Session = Depends(get_db)):
    """
    Retrieve a list of all retailers.
    """
    retailers = db.execute(select(Retailer).order_by(Retailer.name)).scalars().all()
    return retailers

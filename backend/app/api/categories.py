from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..dependencies import get_db
from ..database import Category
# We can reuse the schema defined in the products API
from .products import CategorySchema

router = APIRouter(
    prefix="/api/v1/categories",
    tags=["Categories"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[CategorySchema])
def read_categories(db: Session = Depends(get_db)):
    """
    Retrieve a list of all product categories.
    """
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    return categories

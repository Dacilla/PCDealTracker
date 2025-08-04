from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..dependencies import get_db
from ..database import Category
from .products import CategorySchema
from ..redis_client import get_cache, set_cache

router = APIRouter(
    prefix="/api/v1/categories",
    tags=["Categories"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[CategorySchema])
def read_categories(db: Session = Depends(get_db)):
    """
    Retrieve a list of all product categories, using a cache.
    """
    cache_key = "all_categories"
    cached_categories = get_cache(cache_key)
    if cached_categories:
        print("--- Serving categories from cache ---")
        return cached_categories

    print("--- Fetching categories from DB ---")
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    
    # Pydantic models need to be converted to dicts for JSON serialization
    categories_dict = [CategorySchema.model_validate(c).model_dump() for c in categories]
    set_cache(cache_key, categories_dict, expiry_seconds=86400) # Cache for 24 hours

    return categories

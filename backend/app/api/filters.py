from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from collections import defaultdict

from ..dependencies import get_db
from ..database import MergedProduct, Category
from ..redis_client import get_cache, set_cache

router = APIRouter(
    prefix="/api/v1/filters",
    tags=["Filters"],
    responses={404: {"description": "Not found"}},
)

@router.get("/{category_id}")
def get_available_filters(category_id: int, db: Session = Depends(get_db)):
    """
    Dynamically generates a list of available filters for a given category, using a cache.
    """
    cache_key = f"filters:{category_id}"
    cached_filters = get_cache(cache_key)
    if cached_filters:
        print(f"--- Serving filters for category {category_id} from cache ---")
        return cached_filters

    print(f"--- Fetching filters for category {category_id} from DB ---")
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    query = select(MergedProduct.attributes).where(
        MergedProduct.category_id == category_id,
        MergedProduct.attributes.isnot(None)
    )
    results = db.execute(query).scalars().all()

    if not results:
        return {}

    filter_data = defaultdict(lambda: {'type': None, 'values': set()})
    
    for attr_dict in results:
        for key, value in attr_dict.items():
            if value is None:
                continue
            is_numerical = isinstance(value, (int, float))
            if filter_data[key]['type'] is None:
                filter_data[key]['type'] = 'numerical' if is_numerical else 'categorical'
            filter_data[key]['values'].add(value)

    final_filters = {}
    for key, data in filter_data.items():
        if data['type'] == 'numerical':
            numeric_values = [v for v in data['values'] if isinstance(v, (int, float))]
            if not numeric_values or len(numeric_values) < 2: continue
            final_filters[key] = {
                'type': 'numerical',
                'min': min(numeric_values),
                'max': max(numeric_values)
            }
        else:
            final_filters[key] = {
                'type': 'categorical',
                'values': sorted(list(data['values']))
            }
    
    set_cache(cache_key, final_filters, expiry_seconds=86400) # Cache for 24 hours
    return final_filters

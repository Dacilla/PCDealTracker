from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, cast, JSON
from collections import defaultdict

from ..dependencies import get_db
from ..database import MergedProduct, Category

router = APIRouter(
    prefix="/api/v1/filters",
    tags=["Filters"],
    responses={404: {"description": "Not found"}},
)

@router.get("/{category_id}")
def get_available_filters(category_id: int, db: Session = Depends(get_db)):
    """
    Dynamically generates a list of available filters for a given category,
    distinguishing between categorical and numerical data.
    """
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

    # --- Process all attributes to determine their type and values ---
    filter_data = defaultdict(lambda: {'type': None, 'values': set()})
    
    for attr_dict in results:
        for key, value in attr_dict.items():
            if value is None:
                continue

            # Attempt to determine if the value is numerical
            is_numerical = isinstance(value, (int, float))
            
            # If type is not set, set it now
            if filter_data[key]['type'] is None:
                filter_data[key]['type'] = 'numerical' if is_numerical else 'categorical'
            
            # Add the value to the set
            filter_data[key]['values'].add(value)

    # --- Finalize the response structure ---
    final_filters = {}
    for key, data in filter_data.items():
        if data['type'] == 'numerical':
            # For numerical, find the min and max
            numeric_values = [v for v in data['values'] if isinstance(v, (int, float))]
            if not numeric_values: continue
            final_filters[key] = {
                'type': 'numerical',
                'min': min(numeric_values),
                'max': max(numeric_values)
            }
        else:
            # For categorical, return the sorted list of unique values
            final_filters[key] = {
                'type': 'categorical',
                'values': sorted(list(data['values']))
            }

    return final_filters

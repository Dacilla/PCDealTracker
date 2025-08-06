from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class RetailerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    logo_url: Optional[str] = None # Add the new field

class CategorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

class ProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    current_price: Optional[float] = None
    previous_price: Optional[float] = None
    on_sale: bool
    status: str
    retailer_id: int
    category_id: int
    retailer: RetailerSchema
    category: CategorySchema

class PriceHistorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    price: float
    date: datetime

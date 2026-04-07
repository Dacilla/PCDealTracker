import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Float, and_, asc, cast, desc, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import MergedProduct, PriceHistory, Product, ProductStatus, merged_product_association
from ..dependencies import get_db
from ..redis_client import get_cache, set_cache
from .products import CategorySchema, ProductSchema, RetailerSchema


class PriceHistoryWithRetailerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price: float
    date: datetime.datetime
    retailer: RetailerSchema


class MergedProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    category: CategorySchema
    attributes: Optional[dict] = None

    listings: List[ProductSchema] = []

    best_price: Optional[float] = None
    best_price_url: Optional[str] = None
    best_price_retailer: Optional[str] = None

    all_time_low_price: Optional[float] = None
    all_time_low_date: Optional[datetime.datetime] = None
    all_time_low_retailer_name: Optional[str] = None

    msrp: Optional[float] = None


class MergedProductPage(BaseModel):
    total: int
    products: List[MergedProductSchema]


router = APIRouter(
    prefix="/api/v1/merged-products",
    tags=["Merged Products"],
    responses={404: {"description": "Not found"}},
)


def _process_merged_product(mp: MergedProduct, db: Session) -> dict:
    merged_schema = MergedProductSchema.model_validate(mp)

    validated_listings = []
    for listing in mp.products:
        listing_payload = ProductSchema.model_validate(listing).model_dump()
        listing_payload["status"] = listing.status.value
        validated_listings.append(ProductSchema.model_validate(listing_payload))

    merged_schema.listings = validated_listings

    available_listings = [
        listing
        for listing in mp.products
        if listing.current_price is not None and listing.status == ProductStatus.AVAILABLE
    ]
    if available_listings:
        best_listing = min(available_listings, key=lambda listing: listing.current_price)
        merged_schema.best_price = best_listing.current_price
        merged_schema.best_price_url = best_listing.url
        merged_schema.best_price_retailer = best_listing.retailer.name

    product_ids = [listing.id for listing in mp.products]
    if product_ids:
        price_stats = (
            db.query(func.min(PriceHistory.price), func.max(PriceHistory.price))
            .filter(PriceHistory.product_id.in_(product_ids))
            .first()
        )

        if price_stats and price_stats[0] is not None:
            merged_schema.msrp = price_stats[1]

            all_time_low_entry = (
                db.query(PriceHistory)
                .join(Product)
                .options(joinedload(PriceHistory.product).joinedload(Product.retailer))
                .filter(PriceHistory.product_id.in_(product_ids))
                .order_by(PriceHistory.price.asc(), PriceHistory.date.desc())
                .first()
            )

            if all_time_low_entry:
                merged_schema.all_time_low_price = all_time_low_entry.price
                merged_schema.all_time_low_date = all_time_low_entry.date
                merged_schema.all_time_low_retailer_name = all_time_low_entry.product.retailer.name

    return merged_schema.model_dump(mode="json")


@router.get("/", response_model=MergedProductPage)
def read_merged_products(
    request: Request,
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = Query(None),
    search_mode: Optional[str] = Query("loose"),
    category_id: Optional[int] = Query(None),
    sort_by: Optional[str] = Query("name"),
    sort_order: Optional[str] = Query("asc"),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    hide_unavailable: bool = Query(False),
):
    cache_key = f"merged_products:{str(request.query_params)}"
    cached_result = get_cache(cache_key)
    if cached_result:
        return cached_result

    min_price_subquery = (
        select(
            merged_product_association.c.merged_product_id,
            func.min(Product.current_price).label("min_price"),
        )
        .join(Product, merged_product_association.c.product_id == Product.id)
        .where(Product.status == ProductStatus.AVAILABLE)
        .group_by(merged_product_association.c.merged_product_id)
        .subquery()
    )

    is_outer_join = not hide_unavailable
    query = (
        select(MergedProduct)
        .join(
            min_price_subquery,
            MergedProduct.id == min_price_subquery.c.merged_product_id,
            isouter=is_outer_join,
        )
        .options(
            joinedload(MergedProduct.category),
            selectinload(MergedProduct.products).joinedload(Product.retailer),
            selectinload(MergedProduct.products).joinedload(Product.category),
        )
    )

    filters = []
    if search:
        search_terms = search.split()
        search_conditions = [MergedProduct.canonical_name.ilike(f"%{term}%") for term in search_terms]
        if search_mode == "strict":
            filters.append(MergedProduct.canonical_name.ilike(f"%{search}%"))
        else:
            filters.append(and_(*search_conditions))

    if category_id:
        filters.append(MergedProduct.category_id == category_id)
    if min_price is not None:
        filters.append(min_price_subquery.c.min_price >= min_price)
    if max_price is not None:
        filters.append(min_price_subquery.c.min_price <= max_price)

    known_params = {
        "page",
        "page_size",
        "search",
        "search_mode",
        "category_id",
        "sort_by",
        "sort_order",
        "min_price",
        "max_price",
        "hide_unavailable",
    }
    for key, value in request.query_params.items():
        if key in known_params or not value:
            continue
        if key.startswith("min_"):
            filters.append(cast(MergedProduct.attributes[key[4:]], Float) >= float(value))
        elif key.startswith("max_"):
            filters.append(cast(MergedProduct.attributes[key[4:]], Float) <= float(value))
        else:
            filters.append(MergedProduct.attributes[key].as_string() == value)

    if filters:
        predicate = and_(*filters)
        query = query.where(predicate)
    else:
        predicate = None

    count_query = select(func.count(MergedProduct.id.distinct())).select_from(MergedProduct).join(
        min_price_subquery,
        MergedProduct.id == min_price_subquery.c.merged_product_id,
        isouter=is_outer_join,
    )
    if predicate is not None:
        count_query = count_query.where(predicate)

    total = db.execute(count_query).scalar_one()

    if sort_by == "price":
        order_clause = asc(min_price_subquery.c.min_price) if sort_order == "asc" else desc(min_price_subquery.c.min_price)
        query = query.order_by(order_clause.nulls_last())
    elif sort_by == "recent":
        most_recent_date_subquery = (
            select(
                merged_product_association.c.merged_product_id,
                func.max(PriceHistory.date).label("max_date"),
            )
            .join(Product, merged_product_association.c.product_id == Product.id)
            .join(PriceHistory, Product.id == PriceHistory.product_id)
            .group_by(merged_product_association.c.merged_product_id)
            .subquery()
        )
        query = query.join(
            most_recent_date_subquery,
            MergedProduct.id == most_recent_date_subquery.c.merged_product_id,
            isouter=True,
        ).order_by(desc(most_recent_date_subquery.c.max_date).nulls_last())
    elif sort_by in {"discount", "discount_amount"}:
        max_price_subquery = (
            select(
                merged_product_association.c.merged_product_id,
                func.max(PriceHistory.price).label("max_price"),
            )
            .join(Product, merged_product_association.c.product_id == Product.id)
            .join(PriceHistory, Product.id == PriceHistory.product_id)
            .group_by(merged_product_association.c.merged_product_id)
            .subquery()
        )
        query = query.join(
            max_price_subquery,
            MergedProduct.id == max_price_subquery.c.merged_product_id,
            isouter=True,
        )
        if sort_by == "discount":
            discount_calc = func.coalesce(
                (max_price_subquery.c.max_price - min_price_subquery.c.min_price)
                / func.nullif(max_price_subquery.c.max_price, 0),
                0,
            )
        else:
            discount_calc = max_price_subquery.c.max_price - min_price_subquery.c.min_price
        query = query.order_by(desc(discount_calc).nulls_last())
    else:
        name_order = asc(MergedProduct.canonical_name) if sort_order == "asc" else desc(MergedProduct.canonical_name)
        query = query.order_by(name_order)

    skip = (page - 1) * page_size
    results = db.execute(query.offset(skip).limit(page_size)).scalars().unique().all()
    processed_results = [_process_merged_product(result, db) for result in results]

    response = {"total": total, "products": processed_results}
    set_cache(cache_key, response, expiry_seconds=900)
    return response


@router.get("/{merged_product_id}", response_model=MergedProductSchema)
def read_single_merged_product(merged_product_id: int, db: Session = Depends(get_db)):
    cache_key = f"merged_product:{merged_product_id}"
    cached_product = get_cache(cache_key)
    if cached_product:
        return cached_product

    query = (
        select(MergedProduct)
        .options(
            joinedload(MergedProduct.category),
            selectinload(MergedProduct.products).joinedload(Product.retailer),
            selectinload(MergedProduct.products).joinedload(Product.category),
        )
        .where(MergedProduct.id == merged_product_id)
    )
    result = db.execute(query).scalars().unique().first()
    if not result:
        raise HTTPException(status_code=404, detail="Merged product not found")

    processed_product = _process_merged_product(result, db)
    set_cache(cache_key, processed_product, expiry_seconds=900)
    return processed_product


@router.get("/{merged_product_id}/price-history", response_model=List[PriceHistoryWithRetailerSchema])
def get_combined_price_history(merged_product_id: int, db: Session = Depends(get_db)):
    merged_product = db.get(MergedProduct, merged_product_id)
    if not merged_product:
        raise HTTPException(status_code=404, detail="Merged product not found")

    product_ids = [listing.id for listing in merged_product.products]
    if not product_ids:
        return []

    history_entries = (
        db.query(PriceHistory)
        .join(Product)
        .options(joinedload(PriceHistory.product).joinedload(Product.retailer))
        .filter(PriceHistory.product_id.in_(product_ids))
        .order_by(PriceHistory.date.asc())
        .all()
    )

    response = []
    for entry in history_entries:
        response.append(
            {
                "price": entry.price,
                "date": entry.date,
                "retailer": entry.product.retailer,
            }
        )
    return response

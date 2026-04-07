import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import CanonicalProduct, Category, Offer, PriceObservation, ProductStatus
from ..dependencies import get_db


class V2RetailerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    logo_url: Optional[str] = None


class V2CategorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class V2OfferSchema(BaseModel):
    id: int
    name: str
    url: str
    image_url: Optional[str] = None
    current_price: Optional[float] = None
    previous_price: Optional[float] = None
    status: str
    on_sale: bool
    retailer: V2RetailerSchema


class V2ProductSummarySchema(BaseModel):
    id: str
    canonical_name: str
    category: V2CategorySchema
    brand: Optional[str] = None
    fingerprint: str
    attributes: dict
    offer_count: int
    available_offer_count: int
    best_price: Optional[float] = None
    best_price_retailer: Optional[str] = None
    price_range_min: Optional[float] = None
    price_range_max: Optional[float] = None
    retailers: List[str]


class V2ProductDetailSchema(V2ProductSummarySchema):
    listings: List[V2OfferSchema]


class V2ProductPageSchema(BaseModel):
    total: int
    products: List[V2ProductSummarySchema]


class V2HistorySeriesSchema(BaseModel):
    retailer: V2RetailerSchema
    points: List[dict]


class V2HistoryResponseSchema(BaseModel):
    product_id: str
    series: List[V2HistorySeriesSchema]


class V2FiltersResponseSchema(BaseModel):
    categories: List[V2CategorySchema]
    brands: List[str]
    min_price: Optional[float] = None
    max_price: Optional[float] = None


class V2TrendSchema(BaseModel):
    product: V2ProductSummarySchema
    initial_price: float
    latest_price: float
    price_drop_amount: float
    price_drop_percentage: float


router = APIRouter(prefix="/api/v2", tags=["V2"])


def _serialize_offer(offer: Offer) -> dict:
    return {
        "id": offer.id,
        "name": offer.listing_name,
        "url": offer.listing_url,
        "image_url": offer.image_url,
        "current_price": offer.current_price,
        "previous_price": offer.previous_price,
        "status": offer.status.value,
        "on_sale": (
            offer.previous_price is not None
            and offer.current_price is not None
            and offer.current_price < offer.previous_price
        ),
        "retailer": V2RetailerSchema.model_validate(offer.retailer).model_dump(),
    }


def _serialize_product(canonical_product: CanonicalProduct, *, hide_unavailable: bool = True) -> dict:
    offers = canonical_product.offers
    if hide_unavailable:
        offers = [offer for offer in offers if offer.status == ProductStatus.AVAILABLE and offer.is_active]

    available_offers = [offer for offer in offers if offer.current_price is not None]
    all_priced_offers = [offer for offer in canonical_product.offers if offer.current_price is not None]
    best_offer = min(available_offers, key=lambda offer: offer.current_price) if available_offers else None

    return {
        "id": str(canonical_product.id),
        "canonical_name": canonical_product.canonical_name,
        "category": V2CategorySchema.model_validate(canonical_product.category).model_dump(),
        "brand": canonical_product.brand,
        "fingerprint": canonical_product.fingerprint,
        "attributes": canonical_product.attributes or {},
        "offer_count": len(canonical_product.offers),
        "available_offer_count": len(available_offers),
        "best_price": best_offer.current_price if best_offer else None,
        "best_price_retailer": best_offer.retailer.name if best_offer else None,
        "price_range_min": min((offer.current_price for offer in all_priced_offers), default=None),
        "price_range_max": max((offer.current_price for offer in all_priced_offers), default=None),
        "retailers": sorted({offer.retailer.name for offer in canonical_product.offers}),
        "listings": sorted(
            [_serialize_offer(offer) for offer in canonical_product.offers],
            key=lambda offer: (
                offer["current_price"] is None,
                offer["current_price"] if offer["current_price"] is not None else float("inf"),
                offer["retailer"]["name"],
            ),
        ),
    }


def _load_canonical_products(
    db: Session,
    *,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
) -> List[CanonicalProduct]:
    query = (
        select(CanonicalProduct)
        .options(
            joinedload(CanonicalProduct.category),
            selectinload(CanonicalProduct.offers).joinedload(Offer.retailer),
            selectinload(CanonicalProduct.offers).joinedload(Offer.category),
            selectinload(CanonicalProduct.offers).selectinload(Offer.price_observations),
        )
        .where(CanonicalProduct.is_active.is_(True))
    )

    filters = []
    if search:
        filters.append(CanonicalProduct.canonical_name.ilike(f"%{search}%"))
    if category_id:
        filters.append(CanonicalProduct.category_id == category_id)
    if filters:
        query = query.where(and_(*filters))

    return db.execute(query.order_by(CanonicalProduct.canonical_name.asc())).scalars().unique().all()


def _require_persisted_catalog(db: Session) -> None:
    exists = db.execute(select(CanonicalProduct.id).limit(1)).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=503,
            detail="Persisted v2 catalog is empty. Run scripts/backfill_v2_catalog.py or a v2 ingest job first.",
        )


def _sort_products(products: List[dict], sort_by: str, sort_order: str) -> List[dict]:
    reverse = sort_order == "desc"
    if sort_by == "price":
        return sorted(
            products,
            key=lambda product: (
                product["best_price"] is None,
                product["best_price"] if product["best_price"] is not None else float("inf"),
            ),
            reverse=reverse,
        )
    if sort_by == "offers":
        return sorted(products, key=lambda product: product["available_offer_count"], reverse=reverse)
    return sorted(products, key=lambda product: product["canonical_name"].lower(), reverse=reverse)


def _get_product_or_404(db: Session, product_id: str) -> CanonicalProduct:
    product = db.execute(
        select(CanonicalProduct)
        .options(
            joinedload(CanonicalProduct.category),
            selectinload(CanonicalProduct.offers).joinedload(Offer.retailer),
            selectinload(CanonicalProduct.offers).selectinload(Offer.price_observations),
        )
        .where(CanonicalProduct.id == int(product_id))
    ).scalars().unique().first()
    if not product:
        raise HTTPException(status_code=404, detail="Canonical product not found")
    return product


@router.get("/products", response_model=V2ProductPageSchema)
def list_products(
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 24,
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    hide_unavailable: bool = Query(True),
):
    _require_persisted_catalog(db)
    products = [_serialize_product(product, hide_unavailable=hide_unavailable) for product in _load_canonical_products(db, search=search, category_id=category_id)]
    if hide_unavailable:
        products = [product for product in products if product["available_offer_count"] > 0]

    products = _sort_products(products, sort_by, sort_order)
    start = max(page - 1, 0) * page_size
    end = start + page_size
    summaries = [V2ProductSummarySchema(**{key: value for key, value in product.items() if key != "listings"}) for product in products[start:end]]
    return {"total": len(products), "products": summaries}


@router.get("/products/{product_id}", response_model=V2ProductDetailSchema)
def get_product(product_id: str, db: Session = Depends(get_db)):
    _require_persisted_catalog(db)
    product = _get_product_or_404(db, product_id)
    return V2ProductDetailSchema(**_serialize_product(product, hide_unavailable=False))


@router.get("/offers", response_model=List[V2OfferSchema])
def list_offers(
    db: Session = Depends(get_db),
    product_id: Optional[str] = Query(None),
    hide_unavailable: bool = Query(True),
):
    _require_persisted_catalog(db)

    if product_id:
        product = _get_product_or_404(db, product_id)
        offers = [_serialize_offer(offer) for offer in product.offers]
    else:
        query = select(Offer).options(joinedload(Offer.retailer)).order_by(Offer.current_price.asc().nullslast(), Offer.listing_name.asc())
        offers = [_serialize_offer(offer) for offer in db.execute(query).scalars().all()]

    if hide_unavailable:
        offers = [offer for offer in offers if offer["status"] == ProductStatus.AVAILABLE.value]
    return [V2OfferSchema(**offer) for offer in offers]


@router.get("/history", response_model=V2HistoryResponseSchema)
def get_history(product_id: str, db: Session = Depends(get_db)):
    _require_persisted_catalog(db)
    product = _get_product_or_404(db, product_id)

    series: Dict[int, dict] = {}
    for offer in product.offers:
        retailer = offer.retailer
        bucket = series.get(retailer.id)
        if bucket is None:
            bucket = {
                "retailer": V2RetailerSchema.model_validate(retailer).model_dump(),
                "points": [],
            }
            series[retailer.id] = bucket

        for observation in sorted(offer.price_observations, key=lambda item: item.observed_at):
            bucket["points"].append(
                {
                    "date": observation.observed_at,
                    "price": observation.price,
                    "listing_id": offer.id,
                }
            )

    return {"product_id": product_id, "series": list(series.values())}


@router.get("/filters", response_model=V2FiltersResponseSchema)
def get_filters(
    db: Session = Depends(get_db),
    category_id: Optional[int] = Query(None),
):
    _require_persisted_catalog(db)

    categories = db.execute(select(Category).order_by(Category.name.asc())).scalars().all()
    products = [_serialize_product(product) for product in _load_canonical_products(db, category_id=category_id)]
    products = [product for product in products if product["available_offer_count"] > 0]

    brands = sorted({product["brand"] for product in products if product["brand"]})
    prices = [product["best_price"] for product in products if product["best_price"] is not None]
    return {
        "categories": [V2CategorySchema.model_validate(category).model_dump() for category in categories],
        "brands": brands,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
    }


@router.get("/trends", response_model=List[V2TrendSchema])
def get_trends(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    _require_persisted_catalog(db)

    since = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(days=days)
    trends = []

    for product in _load_canonical_products(db):
        observations = []
        for offer in product.offers:
            observations.extend(
                [
                    observation
                    for observation in offer.price_observations
                    if observation.observed_at >= since
                ]
            )

        observations.sort(key=lambda item: item.observed_at)
        if len(observations) < 2:
            continue

        initial_price = observations[0].price
        latest_price = observations[-1].price
        if initial_price <= latest_price:
            continue

        drop_amount = initial_price - latest_price
        drop_percentage = (drop_amount / initial_price) * 100
        trends.append(
            {
                "product": V2ProductSummarySchema(**{key: value for key, value in _serialize_product(product).items() if key != "listings"}),
                "initial_price": initial_price,
                "latest_price": latest_price,
                "price_drop_amount": drop_amount,
                "price_drop_percentage": drop_percentage,
            }
        )

    trends.sort(key=lambda item: item["price_drop_percentage"], reverse=True)
    return trends[:limit]

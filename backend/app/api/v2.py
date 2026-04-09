import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import (
    CanonicalProduct,
    Category,
    MatchDecision,
    MatchDecisionType,
    Offer,
    PriceObservation,
    ProductStatus,
    RetailerListing,
    ScrapeRun,
    ScrapeRunStatus,
)
from ..dependencies import get_db, require_review_api_key
from ..services.v2_catalog import rank_match_candidates, resolve_match_decision


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


class V2ListingReferenceSchema(BaseModel):
    id: int
    title: str
    source_url: str
    status: str
    retailer: V2RetailerSchema
    category: Optional[V2CategorySchema] = None


class V2CanonicalReferenceSchema(BaseModel):
    id: str
    canonical_name: str
    fingerprint: str


class V2ScrapeRunSchema(BaseModel):
    id: int
    retailer: Optional[V2RetailerSchema] = None
    started_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    status: str
    trigger_source: Optional[str] = None
    scraper_name: Optional[str] = None
    listings_seen: int
    listings_created: int
    listings_updated: int
    error_summary: Optional[str] = None
    meta: Optional[dict] = None


class V2MatchDecisionSchema(BaseModel):
    id: int
    decision: str
    confidence: Optional[float] = None
    matcher: Optional[str] = None
    rationale: Optional[str] = None
    fingerprint: Optional[str] = None
    created_at: datetime.datetime
    retailer_listing: V2ListingReferenceSchema
    canonical_product: Optional[V2CanonicalReferenceSchema] = None
    scrape_run_id: Optional[int] = None


class V2MatchDecisionResolutionRequest(BaseModel):
    decision: MatchDecisionType
    canonical_product_id: Optional[str] = None
    rationale: Optional[str] = None


class V2MatchCandidateSchema(BaseModel):
    canonical_product: V2CanonicalReferenceSchema
    category: V2CategorySchema
    brand: Optional[str] = None
    best_price: Optional[float] = None
    retailer_count: int
    score: float
    reasons: List[str]


router = APIRouter(prefix="/api/v2", tags=["V2"])


def _canonical_product_load_options():
    return (
        joinedload(CanonicalProduct.category),
        selectinload(CanonicalProduct.offers).joinedload(Offer.retailer),
        selectinload(CanonicalProduct.offers).joinedload(Offer.category),
        selectinload(CanonicalProduct.offers).selectinload(Offer.price_observations),
    )


def _offer_stats_subquery():
    available_with_price = and_(
        Offer.status == ProductStatus.AVAILABLE,
        Offer.is_active.is_(True),
        Offer.current_price.is_not(None),
    )
    return (
        select(
            Offer.canonical_product_id.label("canonical_product_id"),
            func.count(Offer.id).label("offer_count"),
            func.sum(case((Offer.current_price.is_not(None), 1), else_=0)).label("priced_offer_count"),
            func.sum(case((available_with_price, 1), else_=0)).label("available_offer_count"),
            func.min(case((Offer.current_price.is_not(None), Offer.current_price), else_=None)).label("min_any_price"),
            func.min(case((available_with_price, Offer.current_price), else_=None)).label("min_available_price"),
        )
        .group_by(Offer.canonical_product_id)
        .subquery()
    )


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


def _serialize_scrape_run(scrape_run: ScrapeRun) -> dict:
    return {
        "id": scrape_run.id,
        "retailer": (
            V2RetailerSchema.model_validate(scrape_run.retailer).model_dump()
            if scrape_run.retailer is not None
            else None
        ),
        "started_at": scrape_run.started_at,
        "finished_at": scrape_run.finished_at,
        "status": scrape_run.status.value,
        "trigger_source": scrape_run.trigger_source,
        "scraper_name": scrape_run.scraper_name,
        "listings_seen": scrape_run.listings_seen,
        "listings_created": scrape_run.listings_created,
        "listings_updated": scrape_run.listings_updated,
        "error_summary": scrape_run.error_summary,
        "meta": scrape_run.meta,
    }


def _serialize_match_decision(match_decision: MatchDecision) -> dict:
    listing: RetailerListing = match_decision.retailer_listing
    return {
        "id": match_decision.id,
        "decision": match_decision.decision.value,
        "confidence": match_decision.confidence,
        "matcher": match_decision.matcher,
        "rationale": match_decision.rationale,
        "fingerprint": match_decision.fingerprint,
        "created_at": match_decision.created_at,
        "retailer_listing": {
            "id": listing.id,
            "title": listing.title,
            "source_url": listing.source_url,
            "status": listing.status.value,
            "retailer": V2RetailerSchema.model_validate(listing.retailer).model_dump(),
            "category": (
                V2CategorySchema.model_validate(listing.category).model_dump()
                if listing.category is not None
                else None
            ),
        },
        "canonical_product": (
            {
                "id": str(match_decision.canonical_product.id),
                "canonical_name": match_decision.canonical_product.canonical_name,
                "fingerprint": match_decision.canonical_product.fingerprint,
            }
            if match_decision.canonical_product is not None
            else None
        ),
        "scrape_run_id": match_decision.scrape_run_id,
    }


def _serialize_match_candidate(candidate) -> dict:
    priced_offers = [offer for offer in candidate.canonical_product.offers if offer.current_price is not None]
    best_price = min((offer.current_price for offer in priced_offers), default=None)
    return {
        "canonical_product": {
            "id": str(candidate.canonical_product.id),
            "canonical_name": candidate.canonical_product.canonical_name,
            "fingerprint": candidate.canonical_product.fingerprint,
        },
        "category": V2CategorySchema.model_validate(candidate.canonical_product.category).model_dump(),
        "brand": candidate.canonical_product.brand,
        "best_price": best_price,
        "retailer_count": len({offer.retailer_id for offer in candidate.canonical_product.offers}),
        "score": candidate.score,
        "reasons": candidate.reasons,
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


def _load_canonical_products_by_ids(db: Session, product_ids: List[int]) -> List[CanonicalProduct]:
    if not product_ids:
        return []

    products = db.execute(
        select(CanonicalProduct)
        .options(*_canonical_product_load_options())
        .where(CanonicalProduct.id.in_(product_ids))
    ).scalars().unique().all()
    products_by_id = {product.id: product for product in products}
    return [products_by_id[product_id] for product_id in product_ids if product_id in products_by_id]


def _product_id_query(
    *,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    hide_unavailable: bool = True,
):
    offer_stats = _offer_stats_subquery()
    query = (
        select(CanonicalProduct.id)
        .outerjoin(offer_stats, offer_stats.c.canonical_product_id == CanonicalProduct.id)
        .where(CanonicalProduct.is_active.is_(True))
    )

    if search:
        query = query.where(CanonicalProduct.canonical_name.ilike(f"%{search}%"))
    if category_id is not None:
        query = query.where(CanonicalProduct.category_id == category_id)
    if hide_unavailable:
        query = query.where(func.coalesce(offer_stats.c.available_offer_count, 0) > 0)

    return query, offer_stats


def _product_sort_expressions(*, sort_by: str, sort_order: str, hide_unavailable: bool, offer_stats):
    if sort_by == "price":
        price_column = (
            offer_stats.c.min_available_price if hide_unavailable else offer_stats.c.min_any_price
        )
        ordered_price = price_column.desc().nullslast() if sort_order == "desc" else price_column.asc().nullslast()
        return [ordered_price, CanonicalProduct.canonical_name.asc()]
    if sort_by == "offers":
        count_column = (
            offer_stats.c.available_offer_count if hide_unavailable else offer_stats.c.priced_offer_count
        )
        ordered_count = count_column.desc().nullslast() if sort_order == "desc" else count_column.asc().nullslast()
        return [ordered_count, CanonicalProduct.canonical_name.asc()]

    ordered_name = (
        CanonicalProduct.canonical_name.desc() if sort_order == "desc" else CanonicalProduct.canonical_name.asc()
    )
    return [ordered_name]


def _load_product_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: Optional[str],
    category_id: Optional[int],
    sort_by: str,
    sort_order: str,
    hide_unavailable: bool,
) -> tuple[int, List[CanonicalProduct]]:
    product_id_query, offer_stats = _product_id_query(
        search=search,
        category_id=category_id,
        hide_unavailable=hide_unavailable,
    )
    total = db.execute(
        select(func.count()).select_from(product_id_query.order_by(None).subquery())
    ).scalar_one()

    offset = max(page - 1, 0) * page_size
    ordered_product_ids = db.execute(
        product_id_query
        .order_by(*_product_sort_expressions(
            sort_by=sort_by,
            sort_order=sort_order,
            hide_unavailable=hide_unavailable,
            offer_stats=offer_stats,
        ))
        .offset(offset)
        .limit(page_size)
    ).scalars().all()

    return total, _load_canonical_products_by_ids(db, ordered_product_ids)


def _require_persisted_catalog(db: Session) -> None:
    exists = db.execute(select(CanonicalProduct.id).limit(1)).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=503,
            detail="Persisted v2 catalog is empty. Run scripts/run_scraper.py or a v2 ingest job first.",
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
        .options(*_canonical_product_load_options())
        .where(CanonicalProduct.id == int(product_id))
    ).scalars().unique().first()
    if not product:
        raise HTTPException(status_code=404, detail="Canonical product not found")
    return product


def _get_match_decision_or_404(db: Session, decision_id: int) -> MatchDecision:
    match_decision = db.execute(
        select(MatchDecision)
        .options(
            joinedload(MatchDecision.retailer_listing).joinedload(RetailerListing.retailer),
            joinedload(MatchDecision.retailer_listing).joinedload(RetailerListing.category),
            joinedload(MatchDecision.canonical_product),
        )
        .where(MatchDecision.id == decision_id)
    ).scalars().first()
    if not match_decision:
        raise HTTPException(status_code=404, detail="Match decision not found")
    return match_decision


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
    total, products = _load_product_page(
        db,
        page=page,
        page_size=page_size,
        search=search,
        category_id=category_id,
        sort_by=sort_by,
        sort_order=sort_order,
        hide_unavailable=hide_unavailable,
    )
    summaries = [
        V2ProductSummarySchema(**{key: value for key, value in _serialize_product(product, hide_unavailable=hide_unavailable).items() if key != "listings"})
        for product in products
    ]
    return {"total": total, "products": summaries}


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
    limit: Optional[int] = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _require_persisted_catalog(db)

    if product_id:
        product = _get_product_or_404(db, product_id)
        offers = [_serialize_offer(offer) for offer in product.offers]
    else:
        query = select(Offer).options(joinedload(Offer.retailer))
        if hide_unavailable:
            query = query.where(Offer.status == ProductStatus.AVAILABLE)
        query = query.order_by(Offer.current_price.asc().nullslast(), Offer.listing_name.asc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)
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
    product_id_query, offer_stats = _product_id_query(category_id=category_id, hide_unavailable=True)
    filtered_products = product_id_query.order_by(None).subquery()

    brands = db.execute(
        select(CanonicalProduct.brand)
        .join(filtered_products, filtered_products.c.id == CanonicalProduct.id)
        .where(CanonicalProduct.brand.is_not(None))
        .distinct()
        .order_by(CanonicalProduct.brand.asc())
    ).scalars().all()
    min_price, max_price = db.execute(
        select(
            func.min(offer_stats.c.min_available_price),
            func.max(offer_stats.c.min_available_price),
        )
        .select_from(CanonicalProduct)
        .join(filtered_products, filtered_products.c.id == CanonicalProduct.id)
        .outerjoin(offer_stats, offer_stats.c.canonical_product_id == CanonicalProduct.id)
    ).one()
    return {
        "categories": [V2CategorySchema.model_validate(category).model_dump() for category in categories],
        "brands": brands,
        "min_price": min_price,
        "max_price": max_price,
    }


@router.get("/trends", response_model=List[V2TrendSchema])
def get_trends(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    _require_persisted_catalog(db)

    since = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(days=days)
    observation_rankings = (
        select(
            Offer.canonical_product_id.label("canonical_product_id"),
            PriceObservation.price.label("price"),
            func.row_number().over(
                partition_by=Offer.canonical_product_id,
                order_by=(PriceObservation.observed_at.asc(), PriceObservation.id.asc()),
            ).label("first_rank"),
            func.row_number().over(
                partition_by=Offer.canonical_product_id,
                order_by=(PriceObservation.observed_at.desc(), PriceObservation.id.desc()),
            ).label("last_rank"),
        )
        .join(Offer, Offer.id == PriceObservation.offer_id)
        .join(CanonicalProduct, CanonicalProduct.id == Offer.canonical_product_id)
        .where(
            CanonicalProduct.is_active.is_(True),
            PriceObservation.observed_at >= since,
        )
        .subquery()
    )
    first_prices = (
        select(
            observation_rankings.c.canonical_product_id,
            observation_rankings.c.price.label("initial_price"),
        )
        .where(observation_rankings.c.first_rank == 1)
        .subquery()
    )
    last_prices = (
        select(
            observation_rankings.c.canonical_product_id,
            observation_rankings.c.price.label("latest_price"),
        )
        .where(observation_rankings.c.last_rank == 1)
        .subquery()
    )

    trend_rows = db.execute(
        select(
            CanonicalProduct.id,
            first_prices.c.initial_price,
            last_prices.c.latest_price,
            (first_prices.c.initial_price - last_prices.c.latest_price).label("price_drop_amount"),
            (
                ((first_prices.c.initial_price - last_prices.c.latest_price) * 100.0)
                / first_prices.c.initial_price
            ).label("price_drop_percentage"),
        )
        .join(first_prices, first_prices.c.canonical_product_id == CanonicalProduct.id)
        .join(last_prices, last_prices.c.canonical_product_id == CanonicalProduct.id)
        .where(
            CanonicalProduct.is_active.is_(True),
            first_prices.c.initial_price > last_prices.c.latest_price,
        )
        .order_by(
            (((first_prices.c.initial_price - last_prices.c.latest_price) * 100.0) / first_prices.c.initial_price).desc(),
            CanonicalProduct.canonical_name.asc(),
        )
        .limit(limit)
    ).all()

    products = _load_canonical_products_by_ids(db, [row.id for row in trend_rows])
    products_by_id = {product.id: product for product in products}
    trends = []
    for row in trend_rows:
        product = products_by_id.get(row.id)
        if product is None:
            continue
        trends.append(
            {
                "product": V2ProductSummarySchema(**{key: value for key, value in _serialize_product(product).items() if key != "listings"}),
                "initial_price": row.initial_price,
                "latest_price": row.latest_price,
                "price_drop_amount": row.price_drop_amount,
                "price_drop_percentage": row.price_drop_percentage,
            }
        )
    return trends


@router.get("/scrape-runs", response_model=List[V2ScrapeRunSchema])
def list_scrape_runs(
    db: Session = Depends(get_db),
    retailer_id: Optional[int] = Query(None),
    status: Optional[ScrapeRunStatus] = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    query = (
        select(ScrapeRun)
        .options(joinedload(ScrapeRun.retailer))
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(limit)
    )
    filters = []
    if retailer_id is not None:
        filters.append(ScrapeRun.retailer_id == retailer_id)
    if status is not None:
        filters.append(ScrapeRun.status == status)
    if filters:
        query = query.where(and_(*filters))

    runs = db.execute(query).scalars().all()
    return [V2ScrapeRunSchema(**_serialize_scrape_run(run)) for run in runs]


@router.get("/match-decisions", response_model=List[V2MatchDecisionSchema])
def list_match_decisions(
    db: Session = Depends(get_db),
    decision: Optional[MatchDecisionType] = Query(None),
    retailer_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    query = (
        select(MatchDecision)
        .options(
            joinedload(MatchDecision.retailer_listing).joinedload(RetailerListing.retailer),
            joinedload(MatchDecision.retailer_listing).joinedload(RetailerListing.category),
            joinedload(MatchDecision.canonical_product),
        )
        .order_by(MatchDecision.created_at.desc(), MatchDecision.id.desc())
        .limit(limit)
    )
    filters = []
    if decision is not None:
        filters.append(MatchDecision.decision == decision)
    if retailer_id is not None:
        filters.append(MatchDecision.retailer_listing.has(RetailerListing.retailer_id == retailer_id))
    if filters:
        query = query.where(and_(*filters))

    decisions = db.execute(query).scalars().all()
    return [V2MatchDecisionSchema(**_serialize_match_decision(item)) for item in decisions]


@router.get("/match-decisions/{decision_id}/candidates", response_model=List[V2MatchCandidateSchema])
def list_match_candidates(
    decision_id: int,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    limit: int = Query(8, ge=1, le=25),
):
    match_decision = _get_match_decision_or_404(db, decision_id)
    ranked_candidates = rank_match_candidates(
        db,
        listing=match_decision.retailer_listing,
        search=search,
        limit=limit,
    )
    return [V2MatchCandidateSchema(**_serialize_match_candidate(candidate)) for candidate in ranked_candidates]


@router.patch("/match-decisions/{decision_id}", response_model=V2MatchDecisionSchema)
def patch_match_decision(
    decision_id: int,
    payload: V2MatchDecisionResolutionRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_review_api_key),
):
    if payload.decision not in (MatchDecisionType.MANUAL_MATCHED, MatchDecisionType.MANUAL_REJECTED):
        raise HTTPException(
            status_code=400,
            detail="Only manual_matched and manual_rejected are supported by this endpoint.",
        )

    match_decision = _get_match_decision_or_404(db, decision_id)

    canonical_product = None
    if payload.decision == MatchDecisionType.MANUAL_MATCHED:
        if not payload.canonical_product_id:
            raise HTTPException(status_code=400, detail="canonical_product_id is required for manual matches.")
        canonical_product = db.get(CanonicalProduct, int(payload.canonical_product_id))
        if canonical_product is None:
            raise HTTPException(status_code=404, detail="Canonical product not found")
        if (
            match_decision.retailer_listing.category_id is not None
            and canonical_product.category_id != match_decision.retailer_listing.category_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Canonical product category must match the listing category.",
            )

    try:
        resolve_match_decision(
            db,
            match_decision=match_decision,
            decision=payload.decision,
            canonical_product=canonical_product,
            rationale=payload.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    refreshed = _get_match_decision_or_404(db, decision_id)
    return V2MatchDecisionSchema(**_serialize_match_decision(refreshed))

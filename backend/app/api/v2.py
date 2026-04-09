import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
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
from ..dependencies import get_db
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

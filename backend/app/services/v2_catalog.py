import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload
from thefuzz import fuzz

from ..database import (
    CanonicalProduct,
    MatchDecision,
    MatchDecisionType,
    Offer,
    PriceObservation,
    ProductStatus,
    RetailerListing,
    ScrapeRun,
    ScrapeRunStatus,
    utcnow_naive,
)
from ..utils.parsing import normalize_model_loose, normalize_model_strict, parse_product_attributes, parse_product_name


CATEGORY_FINGERPRINT_ATTRS = {
    "graphics cards": ("series", "vram_gb"),
    "cpus": ("socket", "intel_series", "amd_series"),
    "motherboards": ("socket", "intel_chipset", "amd_chipset", "form_factor"),
    "memory (ram)": ("type", "capacity_gb", "speed_mhz", "form_factor", "ecc"),
    "storage (ssd/hdd)": ("type", "capacity_gb", "form_factor"),
    "power supplies": ("wattage", "rating", "modularity"),
    "pc cases": ("size",),
    "monitors": ("screen_size_inch", "resolution", "panel_type", "refresh_rate_hz"),
    "cooling": ("type",),
}

AUTO_MATCH_SCORE_THRESHOLD = 96.0
REVIEW_QUEUE_SCORE_THRESHOLD = 75.0
MAX_VALID_SNAPSHOT_PRICE = 50_000.0
MODEL_SCORE_WEIGHT = 0.45
NAME_SCORE_WEIGHT = 0.30
BRAND_SCORE_WEIGHT = 0.15
ATTRIBUTE_SCORE_WEIGHT = 0.10
FINGERPRINT_BONUS_POINTS = 18.0

@dataclass
class V2ListingSnapshot:
    name: str
    url: str
    price: Optional[float]
    status: ProductStatus
    image_url: Optional[str] = None
    previous_price: Optional[float] = None
    retailer_sku: Optional[str] = None
    raw_payload: Optional[dict] = None


@dataclass
class UpsertResult:
    listing_created: bool
    offer_created: bool
    observation_created: bool
    canonical_created: bool


@dataclass
class CandidateRankResult:
    canonical_product: CanonicalProduct
    score: float
    reasons: list[str]


@dataclass
class MatchResolutionPlan:
    canonical_product: Optional[CanonicalProduct]
    decision: MatchDecisionType
    confidence: Optional[float]
    matcher: str
    rationale: str
    preserve_manual_state: bool = False
    force_offer_inactive: bool = False


def normalize_brand(name: str, brand: Optional[str]) -> Optional[str]:
    if brand:
        return brand
    return parse_product_name(name).get("brand")


def extract_attributes(name: str, category_name: str) -> dict:
    return parse_product_attributes(name, category_name)


def fallback_fingerprint(model: Optional[str], normalized_model: Optional[str], loose_normalized_model: Optional[str], name: str) -> str:
    base = loose_normalized_model or normalized_model or model or name
    base = base.lower()
    base = re.sub(r"[^a-z0-9\s-]", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def category_attr_keys(category_name: str) -> tuple:
    return CATEGORY_FINGERPRINT_ATTRS.get(category_name.lower(), ())


def build_catalog_identity(
    *,
    category_id: int,
    category_name: str,
    name: str,
    brand: Optional[str],
    model: Optional[str],
    normalized_model: Optional[str],
    loose_normalized_model: Optional[str],
):
    attrs = extract_attributes(name, category_name)
    normalized_brand = (normalize_brand(name, brand) or "").lower()
    fingerprint_base = fallback_fingerprint(model, normalized_model, loose_normalized_model, name)
    fingerprint_attrs = tuple(
        (key, attrs.get(key))
        for key in category_attr_keys(category_name)
        if attrs.get(key) is not None
    )
    identity = (category_id, normalized_brand, fingerprint_base, fingerprint_attrs)
    return identity, attrs, normalized_brand


def identity_to_fingerprint(identity: tuple) -> str:
    encoded = repr(identity).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:24]


def clear_v2_catalog(db: Session) -> None:
    db.execute(delete(PriceObservation))
    db.execute(delete(MatchDecision))
    db.execute(delete(Offer))
    db.execute(delete(RetailerListing))
    db.execute(delete(CanonicalProduct))
    db.commit()


def start_scrape_run(
    db: Session,
    *,
    retailer_id: Optional[int],
    scraper_name: str,
    trigger_source: str = "scraper",
) -> ScrapeRun:
    scrape_run = ScrapeRun(
        retailer_id=retailer_id,
        status=ScrapeRunStatus.STARTED,
        scraper_name=scraper_name,
        trigger_source=trigger_source,
        started_at=utcnow_naive(),
    )
    db.add(scrape_run)
    db.flush()
    return scrape_run


def finish_scrape_run(
    db: Session,
    scrape_run: ScrapeRun,
    *,
    status: ScrapeRunStatus,
    listings_seen: int,
    listings_created: int,
    listings_updated: int,
    error_summary: Optional[str] = None,
) -> ScrapeRun:
    scrape_run.status = status
    scrape_run.finished_at = utcnow_naive()
    scrape_run.listings_seen = listings_seen
    scrape_run.listings_created = listings_created
    scrape_run.listings_updated = listings_updated
    scrape_run.error_summary = error_summary
    db.flush()
    return scrape_run


def validate_listing_snapshot(snapshot: V2ListingSnapshot) -> V2ListingSnapshot:
    snapshot.name = snapshot.name.strip()
    if not snapshot.name:
        raise ValueError("Snapshot name cannot be blank")
    if snapshot.price is not None and (snapshot.price <= 0 or snapshot.price > MAX_VALID_SNAPSHOT_PRICE):
        raise ValueError(f"Suspicious snapshot price {snapshot.price} for {snapshot.url}")
    return snapshot


def _sync_offer_denormalized_fields(
    offer: Offer,
    *,
    canonical_product: CanonicalProduct,
    category_id: int,
    previous_price: Optional[float],
) -> None:
    # category_id is a query-time denormalization and must always mirror the canonical product.
    offer.category_id = canonical_product.category_id
    if offer.category_id != category_id:
        raise ValueError(
            f"Offer category {category_id} does not match canonical product category {canonical_product.category_id}"
        )

    # previous_price is duplicated onto Offer for fast UI access to "was $X" without scanning history.
    offer.previous_price = previous_price


def _get_latest_match_decision(db: Session, retailer_listing_id: int) -> MatchDecision | None:
    return db.execute(
        select(MatchDecision)
        .where(MatchDecision.retailer_listing_id == retailer_listing_id)
        .order_by(MatchDecision.created_at.desc(), MatchDecision.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _rank_candidates_for_listing(
    db: Session,
    *,
    listing: RetailerListing,
    category_name: str,
) -> list[CandidateRankResult]:
    query = (
        select(CanonicalProduct)
        .options(selectinload(CanonicalProduct.offers))
        .where(CanonicalProduct.is_active.is_(True))
    )
    if listing.category_id is not None:
        query = query.where(CanonicalProduct.category_id == listing.category_id)

    candidates = db.execute(query).scalars().unique().all()
    ranked = [
        _score_canonical_candidate(listing=listing, category_name=category_name, canonical_product=candidate)
        for candidate in candidates
    ]
    ranked.sort(
        key=lambda item: (
            item.score,
            len(item.canonical_product.offers),
            item.canonical_product.canonical_name.lower(),
        ),
        reverse=True,
    )
    return ranked


def _plan_match_resolution(
    db: Session,
    *,
    listing: RetailerListing,
    category_name: str,
    exact_canonical: Optional[CanonicalProduct],
    latest_decision: Optional[MatchDecision],
) -> MatchResolutionPlan:
    if latest_decision is not None:
        if latest_decision.decision == MatchDecisionType.MANUAL_MATCHED and latest_decision.canonical_product_id is not None:
            manual_canonical = db.get(CanonicalProduct, latest_decision.canonical_product_id)
            if manual_canonical is not None:
                return MatchResolutionPlan(
                    canonical_product=manual_canonical,
                    decision=MatchDecisionType.MANUAL_MATCHED,
                    confidence=1.0,
                    matcher="manual_review",
                    rationale=latest_decision.rationale or "Preserved manual canonical assignment during ingestion",
                    preserve_manual_state=True,
                )
        if latest_decision.decision == MatchDecisionType.MANUAL_REJECTED:
            return MatchResolutionPlan(
                canonical_product=exact_canonical,
                decision=MatchDecisionType.MANUAL_REJECTED,
                confidence=1.0,
                matcher="manual_review",
                rationale=latest_decision.rationale or "Preserved manual rejection during ingestion",
                preserve_manual_state=True,
                force_offer_inactive=True,
            )
        if latest_decision.decision == MatchDecisionType.NEEDS_REVIEW:
            return MatchResolutionPlan(
                canonical_product=exact_canonical,
                decision=MatchDecisionType.NEEDS_REVIEW,
                confidence=latest_decision.confidence,
                matcher=latest_decision.matcher or "candidate_rank",
                rationale=latest_decision.rationale or "Awaiting manual review",
            )

    if exact_canonical is not None:
        return MatchResolutionPlan(
            canonical_product=exact_canonical,
            decision=MatchDecisionType.AUTO_MATCHED,
            confidence=1.0,
            matcher="fingerprint",
            rationale="Matched during native v2 ingestion using deterministic fingerprint grouping",
        )

    ranked_candidates = _rank_candidates_for_listing(db, listing=listing, category_name=category_name)
    best_candidate = ranked_candidates[0] if ranked_candidates else None
    if best_candidate is not None and best_candidate.score >= AUTO_MATCH_SCORE_THRESHOLD:
        return MatchResolutionPlan(
            canonical_product=best_candidate.canonical_product,
            decision=MatchDecisionType.AUTO_MATCHED,
            confidence=round(best_candidate.score / 100.0, 3),
            matcher="candidate_rank",
            rationale=f"Automatically matched using ranked candidate score {best_candidate.score}",
        )
    if best_candidate is not None and best_candidate.score >= REVIEW_QUEUE_SCORE_THRESHOLD:
        return MatchResolutionPlan(
            canonical_product=None,
            decision=MatchDecisionType.NEEDS_REVIEW,
            confidence=round(best_candidate.score / 100.0, 3),
            matcher="candidate_rank",
            rationale=f"Queued for manual review after candidate score {best_candidate.score}",
        )

    return MatchResolutionPlan(
        canonical_product=None,
        decision=MatchDecisionType.AUTO_MATCHED,
        confidence=1.0,
        matcher="fingerprint",
        rationale="Created a new canonical product because no sufficiently similar candidate existed",
    )


def _persist_match_decision(
    db: Session,
    *,
    scrape_run: ScrapeRun,
    listing: RetailerListing,
    canonical_product: Optional[CanonicalProduct],
    decision: MatchDecisionType,
    confidence: Optional[float],
    matcher: str,
    rationale: str,
    fingerprint: str,
) -> MatchDecision:
    existing_decision = _get_latest_match_decision(db, listing.id)
    canonical_product_id = canonical_product.id if canonical_product is not None else None

    if existing_decision is not None and existing_decision.decision in (
        MatchDecisionType.MANUAL_MATCHED,
        MatchDecisionType.MANUAL_REJECTED,
    ):
        existing_decision.scrape_run_id = scrape_run.id
        existing_decision.fingerprint = fingerprint
        return existing_decision

    if (
        existing_decision is not None
        and existing_decision.decision == decision
        and existing_decision.canonical_product_id == canonical_product_id
    ):
        existing_decision.scrape_run_id = scrape_run.id
        existing_decision.confidence = confidence
        existing_decision.matcher = matcher
        existing_decision.rationale = rationale
        existing_decision.fingerprint = fingerprint
        return existing_decision

    decision_row = MatchDecision(
        retailer_listing_id=listing.id,
        canonical_product_id=canonical_product_id,
        scrape_run_id=scrape_run.id,
        decision=decision,
        confidence=confidence,
        matcher=matcher,
        rationale=rationale,
        fingerprint=fingerprint,
    )
    db.add(decision_row)
    return decision_row


def upsert_v2_listing_snapshot(
    db: Session,
    *,
    scrape_run: ScrapeRun,
    retailer_id: int,
    category_id: int,
    category_name: str,
    snapshot: V2ListingSnapshot,
) -> UpsertResult:
    snapshot = validate_listing_snapshot(snapshot)
    parsed_name = parse_product_name(snapshot.name)
    brand = normalize_brand(snapshot.name, parsed_name.get("brand"))
    model = parsed_name.get("model") or snapshot.name
    strict_model = normalize_model_strict(model)
    loose_model = normalize_model_loose(model)

    identity, attrs, normalized_brand = build_catalog_identity(
        category_id=category_id,
        category_name=category_name,
        name=snapshot.name,
        brand=brand,
        model=model,
        normalized_model=strict_model,
        loose_normalized_model=loose_model,
    )
    fingerprint = identity_to_fingerprint(identity)

    listing = db.execute(
        select(RetailerListing).where(RetailerListing.source_url == snapshot.url)
    ).scalar_one_or_none()
    listing_created = listing is None
    if listing is None:
        listing = RetailerListing(
            retailer_id=retailer_id,
            category_id=category_id,
            retailer_sku=snapshot.retailer_sku,
            source_url=snapshot.url,
            source_hash=hashlib.sha1(snapshot.url.encode("utf-8")).hexdigest()[:24],
            title=snapshot.name,
            brand=brand,
            model=model,
            normalized_model=strict_model,
            loose_normalized_model=loose_model,
            image_url=snapshot.image_url,
            raw_payload=snapshot.raw_payload,
            status=snapshot.status,
        )
        db.add(listing)
        db.flush()
    else:
        listing.retailer_id = retailer_id
        listing.category_id = category_id
        listing.retailer_sku = snapshot.retailer_sku
        listing.title = snapshot.name
        listing.brand = brand
        listing.model = model
        listing.normalized_model = strict_model
        listing.loose_normalized_model = loose_model
        listing.image_url = snapshot.image_url
        listing.raw_payload = snapshot.raw_payload
        listing.status = snapshot.status
        listing.last_seen_at = utcnow_naive()

    latest_decision = _get_latest_match_decision(db, listing.id)
    exact_canonical = db.execute(
        select(CanonicalProduct).where(
            CanonicalProduct.category_id == category_id,
            CanonicalProduct.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()
    resolution_plan = _plan_match_resolution(
        db,
        listing=listing,
        category_name=category_name,
        exact_canonical=exact_canonical,
        latest_decision=latest_decision,
    )

    canonical_product = resolution_plan.canonical_product
    canonical_created = canonical_product is None
    if canonical_product is None:
        canonical_product = CanonicalProduct(
            canonical_name=snapshot.name,
            category_id=category_id,
            brand=brand,
            model_key=loose_model or strict_model or model,
            fingerprint=fingerprint,
            attributes=attrs,
            match_bucket=category_name.lower().replace(" ", "_"),
        )
        db.add(canonical_product)
        db.flush()
    else:
        if len(snapshot.name) > len(canonical_product.canonical_name):
            canonical_product.canonical_name = snapshot.name
        if not canonical_product.brand and brand:
            canonical_product.brand = brand
        if not canonical_product.attributes:
            canonical_product.attributes = attrs

    offer = db.execute(
        select(Offer).where(Offer.retailer_listing_id == listing.id)
    ).scalar_one_or_none()
    previous_current_price = offer.current_price if offer else None
    previous_status = offer.status if offer else None
    offer_created = offer is None
    if offer is None:
        offer = Offer(
            canonical_product_id=canonical_product.id,
            retailer_listing_id=listing.id,
            retailer_id=retailer_id,
            category_id=canonical_product.category_id,
            listing_name=snapshot.name,
            listing_url=snapshot.url,
            image_url=snapshot.image_url,
            current_price=snapshot.price,
            previous_price=None,
            status=snapshot.status,
            is_active=snapshot.status == ProductStatus.AVAILABLE,
        )
        _sync_offer_denormalized_fields(
            offer,
            canonical_product=canonical_product,
            category_id=category_id,
            previous_price=snapshot.previous_price,
        )
        db.add(offer)
        db.flush()
    else:
        offer.canonical_product_id = canonical_product.id
        offer.retailer_id = retailer_id
        offer.listing_name = snapshot.name
        offer.listing_url = snapshot.url
        offer.image_url = snapshot.image_url
        offer.current_price = snapshot.price
        offer.status = snapshot.status
        offer.is_active = snapshot.status == ProductStatus.AVAILABLE
        offer.last_seen_at = utcnow_naive()
        _sync_offer_denormalized_fields(
            offer,
            canonical_product=canonical_product,
            category_id=category_id,
            previous_price=previous_current_price,
        )

    if resolution_plan.force_offer_inactive:
        offer.is_active = False

    observation_created = False
    latest_observation = db.execute(
        select(PriceObservation)
        .where(PriceObservation.offer_id == offer.id)
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    should_create_observation = (
        snapshot.price is not None
        and (
            latest_observation is None
            or latest_observation.price != snapshot.price
            or previous_status != snapshot.status
        )
    )
    if should_create_observation:
        db.add(
            PriceObservation(
                offer_id=offer.id,
                observed_at=utcnow_naive(),
                price=snapshot.price,
                previous_price=previous_current_price,
                in_stock=snapshot.status == ProductStatus.AVAILABLE,
                scrape_run_id=scrape_run.id,
                raw_payload=snapshot.raw_payload,
            )
        )
        observation_created = True

    _persist_match_decision(
        db,
        scrape_run=scrape_run,
        listing=listing,
        canonical_product=(
            canonical_product
            if resolution_plan.decision != MatchDecisionType.NEEDS_REVIEW
            else None
        ),
        decision=resolution_plan.decision,
        confidence=resolution_plan.confidence,
        matcher=resolution_plan.matcher,
        rationale=resolution_plan.rationale,
        fingerprint=fingerprint,
    )

    db.flush()
    return UpsertResult(
        listing_created=listing_created,
        offer_created=offer_created,
        observation_created=observation_created,
        canonical_created=canonical_created,
    )


def mark_missing_retailer_urls_unavailable(
    db: Session,
    *,
    retailer_id: int,
    seen_urls: set[str],
    scrape_run: ScrapeRun,
) -> int:
    listings = db.execute(
        select(RetailerListing)
        .options(joinedload(RetailerListing.offers))
        .where(RetailerListing.retailer_id == retailer_id)
    ).scalars().unique().all()

    updated = 0
    for listing in listings:
        if listing.source_url in seen_urls or listing.status == ProductStatus.UNAVAILABLE:
            continue

        listing.status = ProductStatus.UNAVAILABLE
        listing.last_seen_at = utcnow_naive()

        for offer in listing.offers:
            if offer.status == ProductStatus.UNAVAILABLE and not offer.is_active:
                continue
            offer.status = ProductStatus.UNAVAILABLE
            offer.is_active = False
            offer.last_seen_at = utcnow_naive()
            if offer.current_price is not None:
                db.add(
                    PriceObservation(
                        offer_id=offer.id,
                        observed_at=utcnow_naive(),
                        price=offer.current_price,
                        previous_price=offer.previous_price,
                        in_stock=False,
                        scrape_run_id=scrape_run.id,
                        raw_payload={"unavailable_marked": True},
                    )
                )
        updated += 1

    db.flush()
    return updated


def resolve_match_decision(
    db: Session,
    *,
    match_decision: MatchDecision,
    decision: MatchDecisionType,
    canonical_product: Optional[CanonicalProduct] = None,
    rationale: Optional[str] = None,
) -> MatchDecision:
    if decision not in (MatchDecisionType.MANUAL_MATCHED, MatchDecisionType.MANUAL_REJECTED):
        raise ValueError("Only manual match decisions can be resolved through this workflow")
    if decision == MatchDecisionType.MANUAL_MATCHED and canonical_product is None:
        raise ValueError("Manual matches require a target canonical product")

    offers = db.execute(
        select(Offer).where(Offer.retailer_listing_id == match_decision.retailer_listing_id)
    ).scalars().all()

    if decision == MatchDecisionType.MANUAL_MATCHED:
        assert canonical_product is not None
        canonical_product.is_active = True
        for offer in offers:
            offer.canonical_product_id = canonical_product.id
            offer.is_active = offer.status == ProductStatus.AVAILABLE
            _sync_offer_denormalized_fields(
                offer,
                canonical_product=canonical_product,
                category_id=canonical_product.category_id,
                previous_price=offer.previous_price,
            )
        match_decision.canonical_product_id = canonical_product.id
    else:
        for offer in offers:
            offer.is_active = False
        match_decision.canonical_product_id = None

    match_decision.decision = decision
    match_decision.matcher = "manual_review"
    match_decision.confidence = 1.0
    if rationale is not None:
        match_decision.rationale = rationale

    db.flush()
    return match_decision


def _score_canonical_candidate(
    *,
    listing: RetailerListing,
    category_name: str,
    canonical_product: CanonicalProduct,
) -> CandidateRankResult:
    listing_name = listing.title or ""
    listing_brand = (listing.brand or normalize_brand(listing_name, None) or "").lower()
    listing_model = listing.loose_normalized_model or listing.normalized_model or listing.model or listing_name
    listing_attributes = extract_attributes(listing_name, category_name) if category_name else {}

    candidate_name = canonical_product.canonical_name or ""
    candidate_brand = (canonical_product.brand or "").lower()
    candidate_model = canonical_product.model_key or candidate_name
    candidate_attributes = canonical_product.attributes or {}

    name_score = fuzz.token_set_ratio(listing_name, candidate_name)
    model_score = fuzz.token_set_ratio(listing_model, candidate_model)

    if listing_brand and candidate_brand:
        brand_score = 100.0 if listing_brand == candidate_brand else 15.0
    else:
        brand_score = 55.0

    shared_attribute_keys = sorted(set(listing_attributes) & set(candidate_attributes))
    matched_attribute_keys = [
        key for key in shared_attribute_keys if listing_attributes.get(key) == candidate_attributes.get(key)
    ]
    attribute_score = (
        (len(matched_attribute_keys) / len(shared_attribute_keys)) * 100.0 if shared_attribute_keys else 50.0
    )

    review_fingerprint = ""
    if listing.category_id is not None and category_name:
        identity, _, _ = build_catalog_identity(
            category_id=listing.category_id,
            category_name=category_name,
            name=listing_name,
            brand=listing.brand,
            model=listing.model,
            normalized_model=listing.normalized_model,
            loose_normalized_model=listing.loose_normalized_model,
        )
        review_fingerprint = identity_to_fingerprint(identity)

    fingerprint_bonus = (
        FINGERPRINT_BONUS_POINTS if review_fingerprint and review_fingerprint == canonical_product.fingerprint else 0.0
    )
    final_score = min(
        100.0,
        (model_score * MODEL_SCORE_WEIGHT)
        + (name_score * NAME_SCORE_WEIGHT)
        + (brand_score * BRAND_SCORE_WEIGHT)
        + (attribute_score * ATTRIBUTE_SCORE_WEIGHT)
        + fingerprint_bonus,
    )

    reasons: list[str] = []
    if fingerprint_bonus:
        reasons.append("Exact deterministic fingerprint match")
    if listing_brand and candidate_brand and listing_brand == candidate_brand:
        reasons.append(f"Brand match: {canonical_product.brand}")
    if matched_attribute_keys:
        reasons.append(f"Matched attributes: {', '.join(key.replace('_', ' ') for key in matched_attribute_keys[:3])}")
    if model_score >= 70:
        reasons.append(f"Model similarity {model_score}")
    if name_score >= 70:
        reasons.append(f"Name similarity {name_score}")
    if not reasons:
        reasons.append("Weak fallback candidate based on title similarity")

    return CandidateRankResult(
        canonical_product=canonical_product,
        score=round(final_score, 1),
        reasons=reasons,
    )


def rank_match_candidates(
    db: Session,
    *,
    listing: RetailerListing,
    limit: int = 8,
    search: Optional[str] = None,
) -> list[CandidateRankResult]:
    query = (
        select(CanonicalProduct)
        .options(
            joinedload(CanonicalProduct.category),
            selectinload(CanonicalProduct.offers),
        )
        .where(CanonicalProduct.is_active.is_(True))
    )

    if listing.category_id is not None:
        query = query.where(CanonicalProduct.category_id == listing.category_id)
    if search:
        query = query.where(CanonicalProduct.canonical_name.ilike(f"%{search}%"))

    candidates = db.execute(query).scalars().unique().all()
    category_name = listing.category.name if listing.category is not None else ""
    ranked = [
        _score_canonical_candidate(listing=listing, category_name=category_name, canonical_product=candidate)
        for candidate in candidates
    ]
    ranked.sort(
        key=lambda item: (
            item.score,
            len(item.canonical_product.offers),
            item.canonical_product.canonical_name.lower(),
        ),
        reverse=True,
    )
    return ranked[:limit]

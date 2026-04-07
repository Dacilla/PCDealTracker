import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from ..database import (
    CanonicalProduct,
    MatchDecision,
    MatchDecisionType,
    Offer,
    PriceHistory,
    PriceObservation,
    Product,
    ProductStatus,
    Retailer,
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

NATIVE_V2_RETAILER_NAMES = (
    "Centre Com",
    "Computer Alliance",
    "Shopping Express",
    "Scorptec",
    "JW Computers",
)


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


def upsert_v2_listing_snapshot(
    db: Session,
    *,
    scrape_run: ScrapeRun,
    retailer_id: int,
    category_id: int,
    category_name: str,
    snapshot: V2ListingSnapshot,
) -> UpsertResult:
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

    canonical_product = db.execute(
        select(CanonicalProduct).where(
            CanonicalProduct.category_id == category_id,
            CanonicalProduct.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()
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
            category_id=category_id,
            listing_name=snapshot.name,
            listing_url=snapshot.url,
            image_url=snapshot.image_url,
            current_price=snapshot.price,
            previous_price=snapshot.previous_price,
            status=snapshot.status,
            is_active=snapshot.status == ProductStatus.AVAILABLE,
        )
        db.add(offer)
        db.flush()
    else:
        offer.canonical_product_id = canonical_product.id
        offer.retailer_id = retailer_id
        offer.category_id = category_id
        offer.listing_name = snapshot.name
        offer.listing_url = snapshot.url
        offer.image_url = snapshot.image_url
        offer.previous_price = offer.current_price
        offer.current_price = snapshot.price
        offer.status = snapshot.status
        offer.is_active = snapshot.status == ProductStatus.AVAILABLE
        offer.last_seen_at = utcnow_naive()

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

    db.add(
        MatchDecision(
            retailer_listing_id=listing.id,
            canonical_product_id=canonical_product.id,
            scrape_run_id=scrape_run.id,
            decision=MatchDecisionType.AUTO_MATCHED,
            confidence=1.0,
            matcher="fingerprint",
            rationale="Matched during native v2 ingestion using deterministic fingerprint grouping",
            fingerprint=fingerprint,
        )
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


def rebuild_v2_catalog_from_legacy(
    db: Session,
    *,
    retailer_name: Optional[str] = None,
    exclude_retailer_names: Optional[tuple[str, ...] | list[str] | set[str]] = None,
    clear_existing: bool = True,
) -> ScrapeRun:
    if clear_existing:
        clear_v2_catalog(db)

    excluded_names = tuple(sorted(set(exclude_retailer_names or ())))

    product_query = (
        select(Product)
        .options(joinedload(Product.retailer), joinedload(Product.category), joinedload(Product.price_history))
        .where(Product.category_id.isnot(None))
        .order_by(Product.id.asc())
    )
    if retailer_name:
        product_query = product_query.join(Product.retailer).where(Product.retailer.has(name=retailer_name))
    if excluded_names:
        product_query = product_query.join(Product.retailer).where(Retailer.name.not_in(excluded_names))

    products = db.execute(product_query).scalars().unique().all()

    scrape_run = ScrapeRun(
        retailer_id=None,
        status=ScrapeRunStatus.SUCCEEDED,
        scraper_name="legacy_backfill",
        trigger_source="script",
        listings_seen=len(products),
        listings_created=len(products),
        finished_at=utcnow_naive(),
        meta={
            "retailer_name": retailer_name,
            "exclude_retailer_names": list(excluded_names),
            "clear_existing": clear_existing,
        },
    )
    db.add(scrape_run)
    db.flush()

    canonical_cache = {}
    listing_count = 0

    for product in products:
        if not product.category or not product.retailer:
            continue

        identity, attrs, normalized_brand = build_catalog_identity(
            category_id=product.category_id,
            category_name=product.category.name,
            name=product.name,
            brand=product.brand,
            model=product.model,
            normalized_model=product.normalized_model,
            loose_normalized_model=product.loose_normalized_model,
        )
        fingerprint = identity_to_fingerprint(identity)
        cache_key = (product.category_id, normalized_brand, fingerprint)

        canonical_product = canonical_cache.get(cache_key)
        if canonical_product is None:
            canonical_product = CanonicalProduct(
                canonical_name=product.name,
                category_id=product.category_id,
                brand=product.brand or normalized_brand or None,
                model_key=product.loose_normalized_model or product.normalized_model or product.model,
                fingerprint=fingerprint,
                attributes=attrs,
                match_bucket=product.category.name.lower().replace(" ", "_"),
            )
            db.add(canonical_product)
            db.flush()
            canonical_cache[cache_key] = canonical_product
        elif len(product.name) > len(canonical_product.canonical_name):
            canonical_product.canonical_name = product.name

        listing = RetailerListing(
            retailer_id=product.retailer_id,
            category_id=product.category_id,
            retailer_sku=product.sku,
            source_url=product.url,
            source_hash=hashlib.sha1(product.url.encode("utf-8")).hexdigest()[:24],
            title=product.name,
            brand=product.brand,
            model=product.model,
            normalized_model=product.normalized_model,
            loose_normalized_model=product.loose_normalized_model,
            image_url=product.image_url,
            raw_payload={"legacy_product_id": product.id, "on_sale": product.on_sale},
            status=product.status,
        )
        db.add(listing)
        db.flush()

        offer = Offer(
            canonical_product_id=canonical_product.id,
            retailer_listing_id=listing.id,
            retailer_id=product.retailer_id,
            category_id=product.category_id,
            listing_name=product.name,
            listing_url=product.url,
            image_url=product.image_url,
            current_price=product.current_price,
            previous_price=product.previous_price,
            status=product.status,
            is_active=product.status == ProductStatus.AVAILABLE,
        )
        db.add(offer)
        db.flush()

        db.add(
            MatchDecision(
                retailer_listing_id=listing.id,
                canonical_product_id=canonical_product.id,
                scrape_run_id=scrape_run.id,
                decision=MatchDecisionType.AUTO_MATCHED,
                confidence=1.0,
                matcher="legacy_backfill",
                rationale="Migrated from legacy Product row using deterministic fingerprint grouping",
                fingerprint=fingerprint,
            )
        )

        history_entries = sorted(product.price_history, key=lambda item: item.date)
        if history_entries:
            for entry in history_entries:
                db.add(
                    PriceObservation(
                        offer_id=offer.id,
                        observed_at=entry.date,
                        price=entry.price,
                        previous_price=None,
                        in_stock=product.status == ProductStatus.AVAILABLE,
                        scrape_run_id=scrape_run.id,
                        raw_payload={"legacy_price_history_id": entry.id},
                    )
                )
        elif product.current_price is not None:
            db.add(
                PriceObservation(
                    offer_id=offer.id,
                    observed_at=utcnow_naive(),
                    price=product.current_price,
                    previous_price=product.previous_price,
                    in_stock=product.status == ProductStatus.AVAILABLE,
                    scrape_run_id=scrape_run.id,
                    raw_payload={"legacy_product_id": product.id, "synthetic_observation": True},
                )
            )

        listing_count += 1

    scrape_run.listings_seen = len(products)
    scrape_run.listings_created = listing_count
    scrape_run.listings_updated = 0
    scrape_run.finished_at = utcnow_naive()

    db.commit()
    return scrape_run

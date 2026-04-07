from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from backend.app.database import (
    Base,
    CanonicalProduct,
    Category,
    MatchDecision,
    MatchDecisionType,
    Offer,
    PriceObservation,
    ProductStatus,
    Retailer,
    RetailerListing,
    ScrapeRun,
    ScrapeRunStatus,
    Product,
    PriceHistory,
)
from backend.app.services.v2_catalog import NATIVE_V2_RETAILER_NAMES, rebuild_v2_catalog_from_legacy


def test_v2_schema_relationships_roundtrip(tmp_path):
    database_path = tmp_path / "v2_schema.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="Retailer One", url="https://example.com")
        category = Category(name="Graphics Cards")
        session.add_all([retailer, category])
        session.commit()

        canonical = CanonicalProduct(
            canonical_name="ASUS RTX 5070 12GB",
            category_id=category.id,
            brand="ASUS",
            model_key="rtx-5070",
            fingerprint="graphics-cards|asus|rtx-5070|12gb",
            attributes={"vram_gb": 12, "series": "RTX"},
        )
        session.add(canonical)
        session.commit()

        listing = RetailerListing(
            retailer_id=retailer.id,
            category_id=category.id,
            source_url="https://example.com/asus-5070",
            title="ASUS RTX 5070 12GB OC",
            brand="ASUS",
            model="RTX 5070",
            normalized_model="rtx 5070 12",
            loose_normalized_model="rtx 5070",
            status=ProductStatus.AVAILABLE,
        )
        session.add(listing)
        session.commit()

        scrape_run = ScrapeRun(
            retailer_id=retailer.id,
            status=ScrapeRunStatus.SUCCEEDED,
            scraper_name="example_scraper",
            listings_seen=1,
            listings_created=1,
        )
        session.add(scrape_run)
        session.commit()

        offer = Offer(
            canonical_product_id=canonical.id,
            retailer_listing_id=listing.id,
            retailer_id=retailer.id,
            category_id=category.id,
            listing_name=listing.title,
            listing_url=listing.source_url,
            current_price=1299.0,
            previous_price=1399.0,
            status=ProductStatus.AVAILABLE,
        )
        session.add(offer)
        session.commit()

        observation = PriceObservation(
            offer_id=offer.id,
            price=1299.0,
            previous_price=1399.0,
            scrape_run_id=scrape_run.id,
        )
        decision = MatchDecision(
            retailer_listing_id=listing.id,
            canonical_product_id=canonical.id,
            scrape_run_id=scrape_run.id,
            decision=MatchDecisionType.AUTO_MATCHED,
            confidence=0.98,
            matcher="fingerprint",
            fingerprint=canonical.fingerprint,
        )
        session.add_all([observation, decision])
        session.commit()

        session.refresh(canonical)
        session.refresh(listing)
        session.refresh(scrape_run)

        assert canonical.offers[0].listing_name == "ASUS RTX 5070 12GB OC"
        assert listing.offers[0].current_price == 1299.0
        assert scrape_run.price_observations[0].price == 1299.0
        assert canonical.match_decisions[0].decision == MatchDecisionType.AUTO_MATCHED
    finally:
        session.close()
        engine.dispose()


def test_alembic_upgrade_creates_v2_tables(tmp_path):
    database_path = tmp_path / "alembic_v2.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE retailers (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    url VARCHAR(255) UNIQUE NOT NULL,
                    logo_url VARCHAR(255)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE categories (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL
                )
                """
            )
        )
    engine.dispose()

    alembic_cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(alembic_cfg, "head")

    inspector = inspect(create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False}))
    tables = set(inspector.get_table_names())
    assert "canonical_products" in tables
    assert "retailer_listings" in tables
    assert "offers" in tables
    assert "price_observations" in tables
    assert "scrape_runs" in tables
    assert "match_decisions" in tables


def test_legacy_backfill_populates_v2_catalog(tmp_path):
    database_path = tmp_path / "legacy_backfill.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="Retailer Two", url="https://retailer-two.example")
        category = Category(name="CPUs")
        session.add_all([retailer, category])
        session.commit()

        legacy_product = Product(
            name="AMD Ryzen 7 7800X3D",
            brand="AMD",
            model="Ryzen 7 7800X3D",
            normalized_model="ryzen 7 7800x3d",
            loose_normalized_model="amd ryzen 7 7800x3d am5",
            url="https://retailer-two.example/7800x3d",
            current_price=599.0,
            previous_price=649.0,
            on_sale=True,
            status=ProductStatus.AVAILABLE,
            retailer_id=retailer.id,
            category_id=category.id,
        )
        session.add(legacy_product)
        session.commit()

        session.add_all(
            [
                PriceHistory(product_id=legacy_product.id, price=649.0),
                PriceHistory(product_id=legacy_product.id, price=599.0),
            ]
        )
        session.commit()

        scrape_run = rebuild_v2_catalog_from_legacy(session, clear_existing=True)

        canonical = session.execute(select(CanonicalProduct)).scalar_one()
        listing = session.execute(select(RetailerListing)).scalar_one()
        offer = session.execute(select(Offer)).scalar_one()
        observations = session.execute(select(PriceObservation)).scalars().all()
        decision = session.execute(select(MatchDecision)).scalar_one()

        assert scrape_run.listings_created == 1
        assert canonical.canonical_name == "AMD Ryzen 7 7800X3D"
        assert listing.source_url == legacy_product.url
        assert offer.canonical_product_id == canonical.id
        assert len(observations) == 2
        assert decision.decision == MatchDecisionType.AUTO_MATCHED
    finally:
        session.close()
        engine.dispose()


def test_legacy_backfill_can_exclude_native_v2_retailers(tmp_path):
    database_path = tmp_path / "legacy_backfill_excluded.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        native_retailer = Retailer(name="Scorptec", url="https://www.scorptec.com.au")
        legacy_retailer = Retailer(name="MSY", url="https://www.msy.com.au")
        category = Category(name="Graphics Cards")
        session.add_all([native_retailer, legacy_retailer, category])
        session.commit()

        session.add_all(
            [
                Product(
                    name="ASUS GeForce RTX 5070 PRIME OC 12GB",
                    brand="ASUS",
                    model="RTX 5070 PRIME OC 12GB",
                    normalized_model="rtx 5070 prime oc 12",
                    loose_normalized_model="rtx 5070 12",
                    url="https://www.scorptec.com.au/product/graphics-cards/asus/5070-prime",
                    current_price=1299.0,
                    status=ProductStatus.AVAILABLE,
                    retailer_id=native_retailer.id,
                    category_id=category.id,
                ),
                Product(
                    name="MSI GeForce RTX 5070 VENTUS 2X OC 12GB",
                    brand="MSI",
                    model="RTX 5070 VENTUS 2X OC 12GB",
                    normalized_model="rtx 5070 ventus 2x oc 12",
                    loose_normalized_model="rtx 5070 12",
                    url="https://www.msy.com.au/msi-rtx-5070-ventus",
                    current_price=1249.0,
                    status=ProductStatus.AVAILABLE,
                    retailer_id=legacy_retailer.id,
                    category_id=category.id,
                ),
            ]
        )
        session.commit()

        scrape_run = rebuild_v2_catalog_from_legacy(
            session,
            clear_existing=True,
            exclude_retailer_names=NATIVE_V2_RETAILER_NAMES,
        )

        listings = session.execute(select(RetailerListing)).scalars().all()
        offers = session.execute(select(Offer)).scalars().all()

        assert scrape_run.listings_created == 1
        assert len(listings) == 1
        assert listings[0].source_url == "https://www.msy.com.au/msi-rtx-5070-ventus"
        assert len(offers) == 1
        assert scrape_run.meta["exclude_retailer_names"] == sorted(NATIVE_V2_RETAILER_NAMES)
    finally:
        session.close()
        engine.dispose()

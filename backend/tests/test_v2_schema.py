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
)
from backend.app.services.v2_catalog import clear_v2_catalog
from scripts.init_database import setup_database


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


def test_clear_v2_catalog_removes_catalog_rows_only(tmp_path):
    database_path = tmp_path / "clear_v2_catalog.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="Retailer Two", url="https://retailer-two.example")
        category = Category(name="CPUs")
        session.add_all([retailer, category])
        session.commit()

        canonical = CanonicalProduct(
            canonical_name="AMD Ryzen 7 7800X3D",
            category_id=category.id,
            brand="AMD",
            model_key="ryzen 7 7800x3d",
            fingerprint="cpu-amd-7800x3d",
        )
        session.add(canonical)
        session.commit()

        listing = RetailerListing(
            retailer_id=retailer.id,
            category_id=category.id,
            source_url="https://retailer-two.example/7800x3d",
            title="AMD Ryzen 7 7800X3D",
            status=ProductStatus.AVAILABLE,
        )
        session.add(listing)
        session.commit()

        scrape_run = ScrapeRun(
            retailer_id=retailer.id,
            status=ScrapeRunStatus.SUCCEEDED,
            scraper_name="seed",
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
            current_price=599.0,
            status=ProductStatus.AVAILABLE,
        )
        observation = PriceObservation(
            offer=offer,
            price=599.0,
            scrape_run_id=scrape_run.id,
        )
        decision = MatchDecision(
            retailer_listing_id=listing.id,
            canonical_product_id=canonical.id,
            scrape_run_id=scrape_run.id,
            decision=MatchDecisionType.AUTO_MATCHED,
        )
        session.add_all([offer, observation, decision])
        session.commit()

        clear_v2_catalog(session)

        assert session.execute(select(CanonicalProduct)).scalars().all() == []
        assert session.execute(select(RetailerListing)).scalars().all() == []
        assert session.execute(select(Offer)).scalars().all() == []
        assert session.execute(select(PriceObservation)).scalars().all() == []
        assert session.execute(select(MatchDecision)).scalars().all() == []
        assert session.execute(select(Retailer)).scalars().all()
        assert session.execute(select(Category)).scalars().all()
    finally:
        session.close()
        engine.dispose()


def test_setup_database_bootstraps_empty_sqlite_with_migrations_and_seed_data(tmp_path):
    database_path = tmp_path / "bootstrap.sqlite3"
    database_url = f"sqlite:///{database_path}"

    setup_database(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "alembic_version" in tables
    assert "retailers" in tables
    assert "categories" in tables
    assert "canonical_products" in tables
    assert "retailer_listings" in tables
    assert "offers" in tables
    assert "price_observations" in tables
    assert "scrape_runs" in tables
    assert "match_decisions" in tables

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        retailers = session.execute(select(Retailer).order_by(Retailer.name.asc())).scalars().all()
        categories = session.execute(select(Category).order_by(Category.name.asc())).scalars().all()

        assert len(retailers) == 8
        assert len(categories) == 10
        centre_com = next(retailer for retailer in retailers if retailer.name == "Centre Com")
        assert centre_com.logo_url is None
    finally:
        session.close()
        engine.dispose()

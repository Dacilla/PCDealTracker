from bs4 import BeautifulSoup
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import (
    Base,
    CanonicalProduct,
    Category,
    MatchDecision,
    Offer,
    PriceObservation,
    ProductStatus,
    Retailer,
)
from backend.app.scrapers.computeralliance_v2_scraper import parse_computeralliance_listing
from backend.app.scrapers.centrecom_v2_scraper import parse_centrecom_listing
from backend.app.scrapers.jw_v2_scraper import parse_jw_listing
from backend.app.scrapers.scorptec_v2_scraper import parse_scorptec_listing
from backend.app.scrapers.shoppingexpress_v2_scraper import parse_shoppingexpress_listing
from backend.app.services.v2_catalog import (
    V2ListingSnapshot,
    finish_scrape_run,
    mark_missing_retailer_urls_unavailable,
    start_scrape_run,
    upsert_v2_listing_snapshot,
)
from backend.app.database import ScrapeRunStatus


def test_parse_computeralliance_listing_extracts_snapshot():
    html = """
    <div class="product">
      <a data-pjax href="/example-product">
        <div class="img-container"><img src="/images/product.jpg" /></div>
        <h2 class="equalize">ASUS GeForce RTX 5070 PRIME OC 12GB</h2>
        <div class="price">$1,299.00</div>
      </a>
    </div>
    """
    item = BeautifulSoup(html, "html.parser").select_one(".product")
    snapshot = parse_computeralliance_listing(item, "https://www.computeralliance.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 PRIME OC 12GB"
    assert snapshot.url == "https://www.computeralliance.com.au/example-product"
    assert snapshot.image_url == "https://www.computeralliance.com.au/images/product.jpg"
    assert snapshot.price == 1299.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_parse_shoppingexpress_listing_extracts_snapshot():
    html = """
    <div class="wrapper-thumbnail">
      <div class="thumbnail-image"><img src="/img/example.jpg" /></div>
      <div class="caption">
        <a href="/shop/asus-5070" title="ASUS GeForce RTX 5070 DUAL OC 12GB">ASUS GeForce RTX 5070 DUAL OC 12GB</a>
      </div>
      <p class="price"><span>$1,249.00</span></p>
    </div>
    """
    item = BeautifulSoup(html, "html.parser").select_one(".wrapper-thumbnail")
    snapshot = parse_shoppingexpress_listing(item, "https://www.shoppingexpress.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.shoppingexpress.com.au/shop/asus-5070"
    assert snapshot.image_url == "https://www.shoppingexpress.com.au/img/example.jpg"
    assert snapshot.price == 1249.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_parse_scorptec_listing_extracts_snapshot():
    html = """
    <div class="product-list-detail">
      <div class="detail-image-wrapper"><img data-src="/img/scorptec.jpg" /></div>
      <div class="detail-product-title">
        <a href="/product/graphics-cards/nvidia/12345-asus-prime-5070">ASUS GeForce RTX 5070 PRIME OC 12GB</a>
      </div>
      <div class="detail-product-price">$1,279.00</div>
    </div>
    """
    item = BeautifulSoup(html, "html.parser").select_one(".product-list-detail")
    snapshot = parse_scorptec_listing(item, "https://www.scorptec.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 PRIME OC 12GB"
    assert snapshot.url == "https://www.scorptec.com.au/product/graphics-cards/nvidia/12345-asus-prime-5070"
    assert snapshot.image_url == "https://www.scorptec.com.au/img/scorptec.jpg"
    assert snapshot.price == 1279.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_parse_jw_listing_extracts_snapshot():
    html = """
    <div class="ais-InfiniteHits-item">
      <a class="result" href="/product/asus-rtx5070-dual-oc">
        <div class="result-thumbnail"><img src="/images/jw-5070.jpg" /></div>
        <div class="result-title">ASUS GeForce RTX 5070 DUAL OC 12GB</div>
      </a>
      <div class="after_special">$1,259.00</div>
    </div>
    """
    item = BeautifulSoup(html, "html.parser").select_one(".ais-InfiniteHits-item")
    snapshot = parse_jw_listing(item, "https://www.jw.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.jw.com.au/product/asus-rtx5070-dual-oc"
    assert snapshot.image_url == "https://www.jw.com.au/images/jw-5070.jpg"
    assert snapshot.price == 1259.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_parse_centrecom_listing_extracts_snapshot():
    html = """
    <div class="prbox_box" style="background-image:url(&quot;https://www.centrecom.com.au/images/5070.jpg&quot;);">
      <a class="prbox_link" href="/asus-geforce-rtx-5070-dual-oc-12gb"></a>
      <div class="prbox_name">ASUS GeForce RTX 5070 DUAL OC 12GB</div>
      <div class="saleprice">$1,239.00</div>
    </div>
    """
    item = BeautifulSoup(html, "html.parser").select_one(".prbox_box")
    snapshot = parse_centrecom_listing(item, "https://www.centrecom.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.centrecom.com.au/asus-geforce-rtx-5070-dual-oc-12gb"
    assert snapshot.image_url == "https://www.centrecom.com.au/images/5070.jpg"
    assert snapshot.price == 1239.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_native_v2_upsert_and_unavailable_marking(tmp_path):
    database_path = tmp_path / "v2_ingestion.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="Computer Alliance", url="https://www.computeralliance.com.au")
        category = Category(name="Graphics Cards")
        session.add_all([retailer, category])
        session.commit()

        scrape_run = start_scrape_run(
            session,
            retailer_id=retailer.id,
            scraper_name="computer_alliance_v2",
        )

        first = upsert_v2_listing_snapshot(
            session,
            scrape_run=scrape_run,
            retailer_id=retailer.id,
            category_id=category.id,
            category_name=category.name,
            snapshot=V2ListingSnapshot(
                name="ASUS GeForce RTX 5070 PRIME OC 12GB",
                url="https://www.computeralliance.com.au/example-product",
                price=1299.0,
                status=ProductStatus.AVAILABLE,
                image_url="https://www.computeralliance.com.au/images/product.jpg",
            ),
        )
        second = upsert_v2_listing_snapshot(
            session,
            scrape_run=scrape_run,
            retailer_id=retailer.id,
            category_id=category.id,
            category_name=category.name,
            snapshot=V2ListingSnapshot(
                name="ASUS GeForce RTX 5070 PRIME OC 12GB",
                url="https://www.computeralliance.com.au/example-product",
                price=1249.0,
                status=ProductStatus.AVAILABLE,
                image_url="https://www.computeralliance.com.au/images/product.jpg",
            ),
        )

        finish_scrape_run(
            session,
            scrape_run,
            status=ScrapeRunStatus.SUCCEEDED,
            listings_seen=2,
            listings_created=1,
            listings_updated=1,
        )
        session.commit()

        canonical = session.execute(select(CanonicalProduct)).scalar_one()
        offer = session.execute(select(Offer)).scalar_one()
        observations = session.execute(select(PriceObservation).order_by(PriceObservation.id.asc())).scalars().all()
        decisions = session.execute(select(MatchDecision)).scalars().all()

        assert first.listing_created is True
        assert second.listing_created is False
        assert canonical.canonical_name == "ASUS GeForce RTX 5070 PRIME OC 12GB"
        assert offer.current_price == 1249.0
        assert len(observations) == 2
        assert len(decisions) == 2

        missing_run = start_scrape_run(
            session,
            retailer_id=retailer.id,
            scraper_name="computer_alliance_v2",
        )
        updated = mark_missing_retailer_urls_unavailable(
            session,
            retailer_id=retailer.id,
            seen_urls=set(),
            scrape_run=missing_run,
        )
        finish_scrape_run(
            session,
            missing_run,
            status=ScrapeRunStatus.SUCCEEDED,
            listings_seen=0,
            listings_created=0,
            listings_updated=updated,
        )
        session.commit()

        refreshed_offer = session.execute(select(Offer)).scalar_one()
        assert updated == 1
        assert refreshed_offer.status == ProductStatus.UNAVAILABLE
        assert refreshed_offer.is_active is False
    finally:
        session.close()
        engine.dispose()


def test_native_v2_upsert_for_shoppingexpress_snapshot(tmp_path):
    database_path = tmp_path / "v2_shoppingexpress.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="Shopping Express", url="https://www.shoppingexpress.com.au")
        category = Category(name="Power Supplies")
        session.add_all([retailer, category])
        session.commit()

        scrape_run = start_scrape_run(
            session,
            retailer_id=retailer.id,
            scraper_name="shopping_express_v2",
        )

        result = upsert_v2_listing_snapshot(
            session,
            scrape_run=scrape_run,
            retailer_id=retailer.id,
            category_id=category.id,
            category_name=category.name,
            snapshot=V2ListingSnapshot(
                name="Corsair RM850x Shift 850W 80 Plus Gold Modular Power Supply",
                url="https://www.shoppingexpress.com.au/shop/rm850x-shift",
                price=249.0,
                status=ProductStatus.AVAILABLE,
                image_url="https://www.shoppingexpress.com.au/img/rm850x.jpg",
            ),
        )
        finish_scrape_run(
            session,
            scrape_run,
            status=ScrapeRunStatus.SUCCEEDED,
            listings_seen=1,
            listings_created=1,
            listings_updated=0,
        )
        session.commit()

        canonical = session.execute(select(CanonicalProduct)).scalar_one()
        offer = session.execute(select(Offer)).scalar_one()
        decision = session.execute(select(MatchDecision)).scalar_one()

        assert result.listing_created is True
        assert canonical.attributes["wattage"] == 850
        assert canonical.attributes["rating"] == "80+ Gold"
        assert offer.current_price == 249.0
        assert decision.matcher == "fingerprint"
    finally:
        session.close()
        engine.dispose()


def test_native_v2_upsert_for_scorptec_snapshot(tmp_path):
    database_path = tmp_path / "v2_scorptec.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="Scorptec", url="https://www.scorptec.com.au")
        category = Category(name="Monitors")
        session.add_all([retailer, category])
        session.commit()

        scrape_run = start_scrape_run(
            session,
            retailer_id=retailer.id,
            scraper_name="scorptec_v2",
        )

        result = upsert_v2_listing_snapshot(
            session,
            scrape_run=scrape_run,
            retailer_id=retailer.id,
            category_id=category.id,
            category_name=category.name,
            snapshot=V2ListingSnapshot(
                name='AOC Q27G4N 27" QHD 180Hz IPS Gaming Monitor',
                url="https://www.scorptec.com.au/product/monitors/27-inch/123456-q27g4n",
                price=399.0,
                status=ProductStatus.AVAILABLE,
                image_url="https://www.scorptec.com.au/images/q27g4n.jpg",
            ),
        )
        finish_scrape_run(
            session,
            scrape_run,
            status=ScrapeRunStatus.SUCCEEDED,
            listings_seen=1,
            listings_created=1,
            listings_updated=0,
        )
        session.commit()

        canonical = session.execute(select(CanonicalProduct)).scalar_one()
        offer = session.execute(select(Offer)).scalar_one()
        observation = session.execute(select(PriceObservation)).scalar_one()

        assert result.listing_created is True
        assert canonical.attributes["screen_size_inch"] == 27.0
        assert canonical.attributes["resolution"] == "1440p"
        assert canonical.attributes["refresh_rate_hz"] == 180
        assert offer.current_price == 399.0
        assert observation.in_stock is True
    finally:
        session.close()
        engine.dispose()


def test_native_v2_upsert_for_jw_snapshot(tmp_path):
    database_path = tmp_path / "v2_jw.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="JW Computers", url="https://www.jw.com.au")
        category = Category(name="Power Supplies")
        session.add_all([retailer, category])
        session.commit()

        scrape_run = start_scrape_run(
            session,
            retailer_id=retailer.id,
            scraper_name="jw_v2",
        )

        result = upsert_v2_listing_snapshot(
            session,
            scrape_run=scrape_run,
            retailer_id=retailer.id,
            category_id=category.id,
            category_name=category.name,
            snapshot=V2ListingSnapshot(
                name="be quiet! Straight Power 12 850W 80 Plus Platinum Modular PSU",
                url="https://www.jw.com.au/product/straight-power-12-850w",
                price=289.0,
                status=ProductStatus.AVAILABLE,
                image_url="https://www.jw.com.au/images/straight-power-12.jpg",
            ),
        )
        finish_scrape_run(
            session,
            scrape_run,
            status=ScrapeRunStatus.SUCCEEDED,
            listings_seen=1,
            listings_created=1,
            listings_updated=0,
        )
        session.commit()

        canonical = session.execute(select(CanonicalProduct)).scalar_one()
        offer = session.execute(select(Offer)).scalar_one()
        decision = session.execute(select(MatchDecision)).scalar_one()

        assert result.listing_created is True
        assert canonical.attributes["wattage"] == 850
        assert canonical.attributes["rating"] == "80+ Platinum"
        assert offer.current_price == 289.0
        assert decision.matcher == "fingerprint"
    finally:
        session.close()
        engine.dispose()


def test_native_v2_upsert_for_centrecom_snapshot(tmp_path):
    database_path = tmp_path / "v2_centrecom.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        retailer = Retailer(name="Centre Com", url="https://www.centrecom.com.au")
        category = Category(name="Storage (SSD/HDD)")
        session.add_all([retailer, category])
        session.commit()

        scrape_run = start_scrape_run(
            session,
            retailer_id=retailer.id,
            scraper_name="centrecom_v2",
        )

        result = upsert_v2_listing_snapshot(
            session,
            scrape_run=scrape_run,
            retailer_id=retailer.id,
            category_id=category.id,
            category_name=category.name,
            snapshot=V2ListingSnapshot(
                name="Samsung 990 PRO 2TB PCIe 4.0 NVMe SSD",
                url="https://www.centrecom.com.au/samsung-990-pro-2tb",
                price=249.0,
                status=ProductStatus.AVAILABLE,
                image_url="https://www.centrecom.com.au/images/990-pro.jpg",
            ),
        )
        finish_scrape_run(
            session,
            scrape_run,
            status=ScrapeRunStatus.SUCCEEDED,
            listings_seen=1,
            listings_created=1,
            listings_updated=0,
        )
        session.commit()

        canonical = session.execute(select(CanonicalProduct)).scalar_one()
        offer = session.execute(select(Offer)).scalar_one()
        decision = session.execute(select(MatchDecision)).scalar_one()

        assert result.listing_created is True
        assert canonical.attributes["type"] == "NVMe SSD"
        assert canonical.attributes["capacity_gb"] == 2000
        assert offer.current_price == 249.0
        assert decision.matcher == "fingerprint"
    finally:
        session.close()
        engine.dispose()

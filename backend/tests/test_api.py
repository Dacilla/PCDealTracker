import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
from backend.app.dependencies import get_db
from backend.app.main import app


@pytest.fixture(scope="function")
def session_factory(tmp_path):
    database_path = tmp_path / "test_api.sqlite3"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    yield testing_session_local

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def populate_db(session_factory):
    db_session = session_factory()
    try:
        retailer_a = Retailer(name="TestRetailer A", url="http://test.com/a", logo_url="assets/logos/a.png")
        retailer_b = Retailer(name="TestRetailer B", url="http://test.com/b", logo_url="assets/logos/b.png")
        db_session.add_all([retailer_a, retailer_b])
        db_session.commit()

        cat_gpu = Category(name="Graphics Cards")
        cat_cpu = Category(name="CPUs")
        db_session.add_all([cat_gpu, cat_cpu])
        db_session.commit()

        gpu_product = CanonicalProduct(
            canonical_name="ASUS RTX 4070 SUPER 12GB",
            category_id=cat_gpu.id,
            brand="ASUS",
            model_key="rtx 4070 super 12",
            fingerprint="gpu-asus-4070-super-12",
            attributes={"series": "RTX", "vram_gb": 12},
        )
        cpu_product = CanonicalProduct(
            canonical_name="AMD Ryzen 7 7800X3D",
            category_id=cat_cpu.id,
            brand="AMD",
            model_key="ryzen 7 7800x3d",
            fingerprint="cpu-amd-7800x3d",
            attributes={"socket": "AM5", "amd_series": "Ryzen 7"},
        )
        unavailable_gpu = CanonicalProduct(
            canonical_name="Legacy GPU",
            category_id=cat_gpu.id,
            brand="Legacy",
            model_key="legacy gpu",
            fingerprint="gpu-legacy",
            attributes={},
        )
        db_session.add_all([gpu_product, cpu_product, unavailable_gpu])
        db_session.commit()

        listing_1 = RetailerListing(
            retailer_id=retailer_a.id,
            category_id=cat_gpu.id,
            source_url="http://test.com/p1",
            source_hash="p1",
            title="ASUS RTX 4070 SUPER 12GB",
            brand="ASUS",
            model="RTX 4070 SUPER 12GB",
            normalized_model="rtx 4070 super 12",
            loose_normalized_model="rtx 4070 super 12",
            status=ProductStatus.AVAILABLE,
        )
        listing_2 = RetailerListing(
            retailer_id=retailer_b.id,
            category_id=cat_gpu.id,
            source_url="http://test.com/p2",
            source_hash="p2",
            title="ASUS RTX 4070 SUPER 12GB OC",
            brand="ASUS",
            model="RTX 4070 SUPER 12GB OC",
            normalized_model="rtx 4070 super 12",
            loose_normalized_model="rtx 4070 super 12",
            status=ProductStatus.AVAILABLE,
        )
        listing_3 = RetailerListing(
            retailer_id=retailer_a.id,
            category_id=cat_cpu.id,
            source_url="http://test.com/p3",
            source_hash="p3",
            title="AMD Ryzen 7 7800X3D",
            brand="AMD",
            model="Ryzen 7 7800X3D",
            normalized_model="ryzen 7 7800x3d",
            loose_normalized_model="amd ryzen 7 7800x3d am5",
            status=ProductStatus.AVAILABLE,
        )
        listing_4 = RetailerListing(
            retailer_id=retailer_a.id,
            category_id=cat_gpu.id,
            source_url="http://test.com/p4",
            source_hash="p4",
            title="Legacy GPU",
            brand="Legacy",
            model="GPU",
            normalized_model="legacy gpu",
            loose_normalized_model="legacy gpu",
            status=ProductStatus.UNAVAILABLE,
        )
        db_session.add_all([listing_1, listing_2, listing_3, listing_4])
        db_session.commit()

        offer_1 = Offer(
            canonical_product_id=gpu_product.id,
            retailer_listing_id=listing_1.id,
            retailer_id=retailer_a.id,
            category_id=cat_gpu.id,
            listing_name=listing_1.title,
            listing_url=listing_1.source_url,
            current_price=1000.0,
            previous_price=1100.0,
            status=ProductStatus.AVAILABLE,
            is_active=True,
        )
        offer_2 = Offer(
            canonical_product_id=gpu_product.id,
            retailer_listing_id=listing_2.id,
            retailer_id=retailer_b.id,
            category_id=cat_gpu.id,
            listing_name=listing_2.title,
            listing_url=listing_2.source_url,
            current_price=950.0,
            previous_price=1050.0,
            status=ProductStatus.AVAILABLE,
            is_active=True,
        )
        offer_3 = Offer(
            canonical_product_id=cpu_product.id,
            retailer_listing_id=listing_3.id,
            retailer_id=retailer_a.id,
            category_id=cat_cpu.id,
            listing_name=listing_3.title,
            listing_url=listing_3.source_url,
            current_price=600.0,
            previous_price=650.0,
            status=ProductStatus.AVAILABLE,
            is_active=True,
        )
        offer_4 = Offer(
            canonical_product_id=unavailable_gpu.id,
            retailer_listing_id=listing_4.id,
            retailer_id=retailer_a.id,
            category_id=cat_gpu.id,
            listing_name=listing_4.title,
            listing_url=listing_4.source_url,
            current_price=300.0,
            previous_price=300.0,
            status=ProductStatus.UNAVAILABLE,
            is_active=False,
        )
        db_session.add_all([offer_1, offer_2, offer_3, offer_4])
        db_session.commit()

        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        success_run = ScrapeRun(
            retailer_id=retailer_a.id,
            status=ScrapeRunStatus.SUCCEEDED,
            scraper_name="native_seed",
            trigger_source="test",
            listings_seen=4,
            listings_created=4,
            listings_updated=0,
        )
        failed_run = ScrapeRun(
            retailer_id=retailer_a.id,
            status=ScrapeRunStatus.FAILED,
            scraper_name="manual_review_probe",
            trigger_source="test",
            listings_seen=1,
            listings_created=0,
            listings_updated=0,
            error_summary="Simulated scrape failure",
        )
        db_session.add_all([success_run, failed_run])
        db_session.commit()

        db_session.add_all(
            [
                PriceObservation(
                    offer_id=offer_1.id,
                    price=1100.0,
                    observed_at=now - datetime.timedelta(days=7),
                    previous_price=None,
                    in_stock=True,
                    scrape_run_id=success_run.id,
                ),
                PriceObservation(
                    offer_id=offer_1.id,
                    price=1000.0,
                    observed_at=now - datetime.timedelta(days=1),
                    previous_price=1100.0,
                    in_stock=True,
                    scrape_run_id=success_run.id,
                ),
                PriceObservation(
                    offer_id=offer_2.id,
                    price=1050.0,
                    observed_at=now - datetime.timedelta(days=7),
                    previous_price=None,
                    in_stock=True,
                    scrape_run_id=success_run.id,
                ),
                PriceObservation(
                    offer_id=offer_2.id,
                    price=950.0,
                    observed_at=now - datetime.timedelta(hours=12),
                    previous_price=1050.0,
                    in_stock=True,
                    scrape_run_id=success_run.id,
                ),
                PriceObservation(
                    offer_id=offer_3.id,
                    price=650.0,
                    observed_at=now - datetime.timedelta(days=3),
                    previous_price=None,
                    in_stock=True,
                    scrape_run_id=success_run.id,
                ),
                PriceObservation(
                    offer_id=offer_3.id,
                    price=600.0,
                    observed_at=now - datetime.timedelta(hours=4),
                    previous_price=650.0,
                    in_stock=True,
                    scrape_run_id=success_run.id,
                ),
            ]
        )
        review_decision = MatchDecision(
            retailer_listing_id=listing_1.id,
            canonical_product_id=None,
            scrape_run_id=failed_run.id,
            decision=MatchDecisionType.NEEDS_REVIEW,
            confidence=0.42,
            matcher="test",
            rationale="Synthetic review case for API coverage",
            fingerprint="test-fingerprint-review",
        )
        db_session.add(review_decision)
        db_session.commit()

        return {
            "cat_gpu_id": cat_gpu.id,
            "cat_cpu_id": cat_cpu.id,
            "gpu_product_id": str(gpu_product.id),
            "cpu_product_id": str(cpu_product.id),
            "retailer_one_id": retailer_a.id,
            "review_decision_id": review_decision.id,
            "listing_one_id": listing_1.id,
        }
    finally:
        db_session.close()


def test_v2_products_list_basic(client, populate_db):
    response = client.get("/api/v2/products")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2

    gpu_product = next(product for product in data["products"] if product["category"]["name"] == "Graphics Cards")
    assert gpu_product["offer_count"] == 2
    assert gpu_product["available_offer_count"] == 2
    assert gpu_product["best_price"] == 950.0
    assert sorted(gpu_product["retailers"]) == ["TestRetailer A", "TestRetailer B"]


def test_v2_products_filter_by_category(client, populate_db):
    gpu_id = populate_db["cat_gpu_id"]
    response = client.get("/api/v2/products", params={"category_id": gpu_id})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert all(product["category"]["id"] == gpu_id for product in data["products"])


def test_v2_products_search(client, populate_db):
    response = client.get("/api/v2/products", params={"search": "Ryzen"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["products"][0]["canonical_name"] == "AMD Ryzen 7 7800X3D"


def test_v2_products_sort_by_price_desc(client, populate_db):
    response = client.get("/api/v2/products", params={"sort_by": "price", "sort_order": "desc"})
    assert response.status_code == 200
    data = response.json()
    prices = [product["best_price"] for product in data["products"] if product["best_price"] is not None]
    assert prices == [950.0, 600.0]


def test_v2_products_can_show_unavailable_entries(client, populate_db):
    gpu_id = populate_db["cat_gpu_id"]
    response = client.get("/api/v2/products", params={"category_id": gpu_id, "hide_unavailable": "false"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert any(product["canonical_name"] == "Legacy GPU" for product in data["products"])


def test_v2_product_detail_and_history(client, populate_db):
    detail = client.get(f"/api/v2/products/{populate_db['gpu_product_id']}")
    assert detail.status_code == 200
    assert len(detail.json()["listings"]) == 2

    history = client.get("/api/v2/history", params={"product_id": populate_db["gpu_product_id"]})
    assert history.status_code == 200
    assert len(history.json()["series"]) == 2


def test_v2_filters(client, populate_db):
    response = client.get("/api/v2/filters")
    assert response.status_code == 200
    data = response.json()
    assert {category["name"] for category in data["categories"]} == {"Graphics Cards", "CPUs"}
    assert data["min_price"] == 600.0
    assert data["max_price"] == 950.0


def test_v2_trends(client, populate_db):
    response = client.get("/api/v2/trends", params={"days": 30, "limit": 5})
    assert response.status_code == 200
    trends = response.json()
    assert len(trends) == 2
    assert trends[0]["price_drop_percentage"] >= trends[1]["price_drop_percentage"]


def test_v2_scrape_runs(client, populate_db):
    response = client.get("/api/v2/scrape-runs")
    assert response.status_code == 200
    runs = response.json()
    assert runs
    assert any(run["scraper_name"] == "manual_review_probe" for run in runs)
    assert any(run["status"] == "failed" for run in runs)


def test_v2_match_decisions_filters_review_items(client, populate_db):
    response = client.get(
        "/api/v2/match-decisions",
        params={"decision": "needs_review", "retailer_id": populate_db["retailer_one_id"]},
    )
    assert response.status_code == 200
    decisions = response.json()
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "needs_review"
    assert decisions[0]["retailer_listing"]["retailer"]["name"] == "TestRetailer A"
    assert decisions[0]["canonical_product"] is None
    assert decisions[0]["retailer_listing"]["category"]["name"] == "Graphics Cards"


def test_v2_match_decision_candidates_rank_best_match_first(client, populate_db):
    response = client.get(f"/api/v2/match-decisions/{populate_db['review_decision_id']}/candidates")
    assert response.status_code == 200
    candidates = response.json()
    assert len(candidates) == 2
    assert candidates[0]["canonical_product"]["id"] == populate_db["gpu_product_id"]
    assert candidates[0]["score"] > candidates[1]["score"]
    assert any("Brand match" in reason or "Model similarity" in reason for reason in candidates[0]["reasons"])


def test_v2_match_decision_candidates_support_search(client, populate_db):
    response = client.get(
        f"/api/v2/match-decisions/{populate_db['review_decision_id']}/candidates",
        params={"search": "Legacy"},
    )
    assert response.status_code == 200
    candidates = response.json()
    assert len(candidates) == 1
    assert candidates[0]["canonical_product"]["canonical_name"] == "Legacy GPU"


def test_v2_match_decision_manual_match_updates_offer_assignment(client, populate_db, session_factory):
    response = client.patch(
        f"/api/v2/match-decisions/{populate_db['review_decision_id']}",
        json={
            "decision": "manual_matched",
            "canonical_product_id": populate_db["gpu_product_id"],
            "rationale": "Reviewed and matched manually",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "manual_matched"
    assert data["canonical_product"]["id"] == populate_db["gpu_product_id"]
    assert data["matcher"] == "manual_review"

    session = session_factory()
    try:
        offer = session.execute(
            select(Offer).where(Offer.retailer_listing_id == populate_db["listing_one_id"])
        ).scalar_one()
        decision = session.get(MatchDecision, populate_db["review_decision_id"])
        assert offer.canonical_product_id == int(populate_db["gpu_product_id"])
        assert offer.is_active is True
        assert decision.decision == MatchDecisionType.MANUAL_MATCHED
    finally:
        session.close()


def test_v2_match_decision_manual_reject_deactivates_offer(client, populate_db, session_factory):
    response = client.patch(
        f"/api/v2/match-decisions/{populate_db['review_decision_id']}",
        json={
            "decision": "manual_rejected",
            "rationale": "Reviewed and rejected manually",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "manual_rejected"
    assert data["canonical_product"] is None

    session = session_factory()
    try:
        offer = session.execute(
            select(Offer).where(Offer.retailer_listing_id == populate_db["listing_one_id"])
        ).scalar_one()
        decision = session.get(MatchDecision, populate_db["review_decision_id"])
        assert offer.is_active is False
        assert decision.decision == MatchDecisionType.MANUAL_REJECTED
    finally:
        session.close()


def test_v2_match_decision_manual_match_rejects_mismatched_category(client, populate_db):
    response = client.patch(
        f"/api/v2/match-decisions/{populate_db['review_decision_id']}",
        json={
            "decision": "manual_matched",
            "canonical_product_id": populate_db["cpu_product_id"],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Canonical product category must match the listing category."

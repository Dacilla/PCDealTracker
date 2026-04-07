import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base, Category, MergedProduct, PriceHistory, Product, ProductStatus, Retailer
from backend.app.dependencies import get_db
from backend.app.main import app
from backend.app.services.v2_catalog import rebuild_v2_catalog_from_legacy


@pytest.fixture(scope="function")
def session_factory(tmp_path):
    database_path = tmp_path / "test_api.sqlite3"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    yield TestingSessionLocal

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
        r1 = Retailer(name="TestRetailer A", url="http://test.com/a", logo_url="assets/logos/a.png")
        r2 = Retailer(name="TestRetailer B", url="http://test.com/b", logo_url="assets/logos/b.png")
        db_session.add_all([r1, r2])
        db_session.commit()

        cat_gpu = Category(name="Graphics Cards")
        cat_cpu = Category(name="CPUs")
        db_session.add_all([cat_gpu, cat_cpu])
        db_session.commit()

        p1 = Product(
            name="ASUS RTX 4070 SUPER 12GB",
            brand="ASUS",
            model="RTX 4070 SUPER 12GB",
            normalized_model="rtx 4070 super 12",
            loose_normalized_model="rtx 4070 super 12",
            url="http://test.com/p1",
            current_price=1000.0,
            retailer_id=r1.id,
            category_id=cat_gpu.id,
            on_sale=True,
            status=ProductStatus.AVAILABLE,
        )
        p2 = Product(
            name="ASUS RTX 4070 SUPER 12GB OC",
            brand="ASUS",
            model="RTX 4070 SUPER 12GB OC",
            normalized_model="rtx 4070 super 12",
            loose_normalized_model="rtx 4070 super 12",
            url="http://test.com/p2",
            current_price=950.0,
            previous_price=1050.0,
            retailer_id=r2.id,
            category_id=cat_gpu.id,
            on_sale=True,
            status=ProductStatus.AVAILABLE,
        )
        p3 = Product(
            name="AMD Ryzen 7 7800X3D",
            brand="AMD",
            model="Ryzen 7 7800X3D",
            normalized_model="ryzen 7 7800x3d",
            loose_normalized_model="amd ryzen 7 7800x3d am5",
            url="http://test.com/p3",
            current_price=600.0,
            retailer_id=r1.id,
            category_id=cat_cpu.id,
            on_sale=True,
            status=ProductStatus.AVAILABLE,
        )
        p4 = Product(
            name="Legacy GPU",
            brand="Legacy",
            model="GPU",
            normalized_model="legacy gpu",
            loose_normalized_model="legacy gpu",
            url="http://test.com/p4",
            current_price=300.0,
            retailer_id=r1.id,
            category_id=cat_gpu.id,
            on_sale=False,
            status=ProductStatus.UNAVAILABLE,
        )
        db_session.add_all([p1, p2, p3, p4])
        db_session.commit()

        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        db_session.add_all(
            [
                PriceHistory(product_id=p1.id, price=1100.0, date=now - datetime.timedelta(days=7)),
                PriceHistory(product_id=p1.id, price=1000.0, date=now - datetime.timedelta(days=1)),
                PriceHistory(product_id=p2.id, price=1050.0, date=now - datetime.timedelta(days=7)),
                PriceHistory(product_id=p2.id, price=950.0, date=now - datetime.timedelta(hours=12)),
                PriceHistory(product_id=p3.id, price=650.0, date=now - datetime.timedelta(days=3)),
                PriceHistory(product_id=p3.id, price=600.0, date=now - datetime.timedelta(hours=4)),
            ]
        )

        mp1 = MergedProduct(canonical_name="ASUS RTX 4070 SUPER 12GB", category_id=cat_gpu.id, products=[p1, p2])
        mp2 = MergedProduct(canonical_name="AMD Ryzen 7 7800X3D", category_id=cat_cpu.id, products=[p3])
        mp3 = MergedProduct(canonical_name="Legacy GPU", category_id=cat_gpu.id, products=[p4])
        db_session.add_all([mp1, mp2, mp3])
        db_session.commit()

        rebuild_v2_catalog_from_legacy(db_session, clear_existing=True)

        return {
            "cat_gpu_id": cat_gpu.id,
            "cat_cpu_id": cat_cpu.id,
            "product_one_id": p1.id,
            "merged_gpu_id": mp1.id,
        }
    finally:
        db_session.close()


def test_read_merged_products_basic(client, populate_db):
    response = client.get("/api/v1/merged-products/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["products"]) == 3


def test_filter_by_category(client, populate_db):
    gpu_id = populate_db["cat_gpu_id"]
    response = client.get(f"/api/v1/merged-products/?category_id={gpu_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(product["category"]["id"] == gpu_id for product in data["products"])


def test_search_functionality(client, populate_db):
    response = client.get("/api/v1/merged-products/?search=Ryzen")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["products"][0]["canonical_name"] == "AMD Ryzen 7 7800X3D"


def test_sort_by_price_desc(client, populate_db):
    response = client.get("/api/v1/merged-products/?sort_by=price&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    prices = [product["best_price"] for product in data["products"] if product["best_price"] is not None]
    assert prices == [950.0, 600.0]


def test_hide_unavailable(client, populate_db):
    gpu_id = populate_db["cat_gpu_id"]
    response = client.get(f"/api/v1/merged-products/?category_id={gpu_id}")
    assert response.status_code == 200
    assert response.json()["total"] == 2

    hidden = client.get(f"/api/v1/merged-products/?category_id={gpu_id}&hide_unavailable=true")
    assert hidden.status_code == 200
    data_hidden = hidden.json()
    assert data_hidden["total"] == 1
    assert data_hidden["products"][0]["best_price"] == 950.0


def test_v2_products_group_raw_listings(client, populate_db):
    response = client.get("/api/v2/products")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2

    gpu_product = next(product for product in data["products"] if product["category"]["name"] == "Graphics Cards")
    assert gpu_product["offer_count"] == 2
    assert gpu_product["best_price"] == 950.0
    assert sorted(gpu_product["retailers"]) == ["TestRetailer A", "TestRetailer B"]


def test_v2_product_detail_and_history(client, populate_db):
    list_response = client.get("/api/v2/products")
    product_id = list_response.json()["products"][0]["id"]

    detail = client.get(f"/api/v2/products/{product_id}")
    assert detail.status_code == 200
    assert detail.json()["listings"]

    history = client.get("/api/v2/history", params={"product_id": product_id})
    assert history.status_code == 200
    assert history.json()["series"]


def test_v2_filters(client, populate_db):
    response = client.get("/api/v2/filters")
    assert response.status_code == 200
    data = response.json()
    assert {category["name"] for category in data["categories"]} == {"Graphics Cards", "CPUs"}
    assert data["min_price"] == 600.0
    assert data["max_price"] == 950.0

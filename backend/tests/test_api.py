# backend/tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# FIX: Changed relative imports to absolute imports
from backend.app.main import app
# FIX: Import the ProductStatus enum to use it in test data
from backend.app.database import Base, Product, Retailer, Category, MergedProduct, ProductStatus
from backend.app.dependencies import get_db

# --- Test Database Setup ---
# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Fixture to set up and tear down the database ---
@pytest.fixture(scope="function")
def db_session():
    """
    Creates a new database session for each test, rolling back changes afterward.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

# --- Fixture to override the 'get_db' dependency ---
@pytest.fixture(scope="function")
def client(db_session):
    """
    Creates a TestClient with the database dependency overridden.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Fixture to populate the database with test data ---
@pytest.fixture(scope="function")
def populate_db(db_session):
    """Populates the database with a controlled set of data for testing."""
    # Create Retailers
    r1 = Retailer(name="TestRetailer A", url="http://test.com/a")
    r2 = Retailer(name="TestRetailer B", url="http://test.com/b")
    db_session.add_all([r1, r2])
    db_session.commit()

    # Create Categories
    cat_gpu = Category(name="Graphics Cards")
    cat_cpu = Category(name="CPUs")
    db_session.add_all([cat_gpu, cat_cpu])
    db_session.commit()

    # Create Products
    # FIX: Use the ProductStatus enum members instead of raw strings
    p1 = Product(name="Cheap GPU Model", url="http://test.com/p1", current_price=100.0, retailer_id=r1.id, category_id=cat_gpu.id, on_sale=True, status=ProductStatus.AVAILABLE)
    p2 = Product(name="Expensive GPU Model", url="http://test.com/p2", current_price=500.0, retailer_id=r2.id, category_id=cat_gpu.id, on_sale=True, status=ProductStatus.AVAILABLE)
    p3 = Product(name="Mid-Range CPU", url="http://test.com/p3", current_price=250.0, retailer_id=r1.id, category_id=cat_cpu.id, on_sale=True, status=ProductStatus.AVAILABLE)
    p4 = Product(name="Unavailable GPU", url="http://test.com/p4", current_price=300.0, retailer_id=r1.id, category_id=cat_gpu.id, on_sale=False, status=ProductStatus.UNAVAILABLE)
    db_session.add_all([p1, p2, p3, p4])
    db_session.commit()

    # Create Merged Products
    mp1 = MergedProduct(canonical_name="Cheap GPU Model", category_id=cat_gpu.id, products=[p1])
    mp2 = MergedProduct(canonical_name="Expensive GPU Model", category_id=cat_gpu.id, products=[p2])
    mp3 = MergedProduct(canonical_name="Mid-Range CPU", category_id=cat_cpu.id, products=[p3])
    mp4 = MergedProduct(canonical_name="Unavailable GPU", category_id=cat_gpu.id, products=[p4])
    db_session.add_all([mp1, mp2, mp3, mp4])
    db_session.commit()
    
    return {"cat_gpu_id": cat_gpu.id, "cat_cpu_id": cat_cpu.id}


# --- API Tests ---

def test_read_merged_products_basic(client, populate_db):
    """Tests the basic functionality of the merged products endpoint."""
    response = client.get("/api/v1/merged-products/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert len(data["products"]) == 4

def test_filter_by_category(client, populate_db):
    """Tests that filtering by category_id works correctly."""
    gpu_id = populate_db["cat_gpu_id"]
    response = client.get(f"/api/v1/merged-products/?category_id={gpu_id}")
    assert response.status_code == 200
    data = response.json()
    # Should find the Cheap, Expensive, and Unavailable GPUs
    assert data["total"] == 3
    assert all(p["category"]["id"] == gpu_id for p in data["products"])

def test_search_functionality(client, populate_db):
    """Tests that the search parameter filters results."""
    response = client.get("/api/v1/merged-products/?search=Cheap")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["products"][0]["canonical_name"] == "Cheap GPU Model"

def test_sort_by_price_asc(client, populate_db):
    """Tests sorting by price in ascending order."""
    response = client.get("/api/v1/merged-products/?sort_by=price&sort_order=asc")
    assert response.status_code == 200
    data = response.json()
    prices = [p["best_price"] for p in data["products"] if p["best_price"] is not None]
    assert prices == [100.0, 250.0, 500.0]

def test_sort_by_price_desc(client, populate_db):
    """Tests sorting by price in descending order."""
    response = client.get("/api/v1/merged-products/?sort_by=price&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    prices = [p["best_price"] for p in data["products"] if p["best_price"] is not None]
    assert prices == [500.0, 250.0, 100.0]

def test_hide_unavailable(client, populate_db):
    """Tests that the hide_unavailable flag works."""
    gpu_id = populate_db["cat_gpu_id"]
    # First, check without the flag
    response = client.get(f"/api/v1/merged-products/?category_id={gpu_id}")
    assert response.json()["total"] == 3

    # Now, check with the flag
    response_hidden = client.get(f"/api/v1/merged-products/?category_id={gpu_id}&hide_unavailable=true")
    assert response_hidden.status_code == 200
    data_hidden = response_hidden.json()
    # Should only find the two available GPUs
    assert data_hidden["total"] == 2
    assert all(p["best_price"] is not None for p in data_hidden["products"])

from fastapi import FastAPI

# All the database connection logic is now handled via dependencies.
from .api import deals, products, price_history
from .database import Base
from .dependencies import engine

# This line ensures that if the script is run directly, 
# the tables are created. It's good practice, though our
# init_database.py script is the primary way to do this.
Base.metadata.create_all(bind=engine)


# --- FastAPI App Instance ---
app = FastAPI(
    title="PC Deal Tracker API",
    description="An API to track prices of PC hardware from various Australian retailers.",
    version="0.1.0",
)

# --- Include API Routers ---
# The endpoints in these routers will use the `get_db` dependency
# to get a database session.
app.include_router(products.router)
app.include_router(deals.router)
app.include_router(price_history.router)


# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {
        "message": "Welcome to the PC Deal Tracker API!",
        "docs_url": "/docs"
    }

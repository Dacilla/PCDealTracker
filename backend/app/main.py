from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# --- Import all API routers ---
from .api import deals, products, price_history, categories, retailers, merged_products, filters, trends
from .database import Base
from .dependencies import engine
# Import the cache clearing utility
from .redis_client import clear_all_cache

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    This function runs when the FastAPI application starts up.
    It clears the Redis cache to ensure fresh data on every reload during development.
    """
    print("--- Application starting up, clearing Redis cache... ---")
    clear_all_cache()
    print("--- Cache cleared successfully. ---")
    yield
    # Code here would run on shutdown
    print("--- Application shutting down. ---")


app = FastAPI(
    title="PC Deal Tracker API",
    description="An API to track prices of PC hardware from various Australian retailers.",
    version="0.1.0",
    lifespan=lifespan # Use the new lifespan manager
)


origins = [
    "http://localhost",
    "http://localhost:8080",
    "null",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include all API routers ---
app.include_router(products.router)
app.include_router(deals.router)
app.include_router(price_history.router)
app.include_router(categories.router)
app.include_router(retailers.router)
app.include_router(merged_products.router)
app.include_router(filters.router)
app.include_router(trends.router) # <-- Add the new trends router

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the PC Deal Tracker API!",
        "docs_url": "/docs"
    }

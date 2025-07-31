from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- Import all API routers ---
from .api import deals, products, price_history, categories, retailers, merged_products
from .database import Base
from .dependencies import engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PC Deal Tracker API",
    description="An API to track prices of PC hardware from various Australian retailers.",
    version="0.1.0",
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
# This makes the endpoints from each file available in the application.
app.include_router(products.router)
app.include_router(deals.router)
app.include_router(price_history.router)
app.include_router(categories.router)
app.include_router(retailers.router)
app.include_router(merged_products.router) # <-- Add the new router

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the PC Deal Tracker API!",
        "docs_url": "/docs"
    }

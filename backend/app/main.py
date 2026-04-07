from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import categories, deals, filters, merged_products, price_history, retailers, trends, v2
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="PC Deal Tracker API",
    description="APIs for tracking Australian PC hardware listings and derived product views.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(deals.router)
app.include_router(price_history.router)
app.include_router(categories.router)
app.include_router(retailers.router)
app.include_router(merged_products.router)
app.include_router(filters.router)
app.include_router(trends.router)
app.include_router(v2.router)


@app.get("/")
def read_root():
    return {
        "message": "Welcome to the PC Deal Tracker API!",
        "docs_url": "/docs",
        "v2_docs_hint": "/api/v2/products",
    }

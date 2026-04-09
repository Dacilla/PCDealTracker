from contextlib import asynccontextmanager
import threading

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import v2
from .config import settings
from scripts.run_scraper import run_native_v2_pipeline


_scheduled_scrape_lock = threading.Lock()


def run_scheduled_scrape() -> None:
    if not _scheduled_scrape_lock.acquire(blocking=False):
        return
    try:
        run_native_v2_pipeline()
    finally:
        _scheduled_scrape_lock.release()


def build_scrape_scheduler() -> AsyncIOScheduler | None:
    if not settings.scrape_scheduler_enabled:
        return None

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_scheduled_scrape,
        "interval",
        hours=settings.scrape_interval_hours,
        id="native_v2_scrape",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scrape_scheduler()
    if scheduler is not None:
        scheduler.start()

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


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

app.include_router(v2.router)


@app.get("/")
def read_root():
    return {
        "message": "Welcome to the PC Deal Tracker API!",
        "docs_url": "/docs",
        "v2_docs_hint": "/api/v2/products",
    }

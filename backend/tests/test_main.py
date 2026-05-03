import datetime

from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app, build_scrape_scheduler


def test_build_scrape_scheduler_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "scrape_scheduler_enabled", False)

    assert build_scrape_scheduler() is None


def test_build_scrape_scheduler_uses_configured_interval(monkeypatch):
    monkeypatch.setattr(settings, "scrape_scheduler_enabled", True)
    monkeypatch.setattr(settings, "scrape_interval_hours", 4)

    scheduler = build_scrape_scheduler()

    assert scheduler is not None
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "native_v2_scrape"
    assert jobs[0].trigger.interval == datetime.timedelta(hours=4)


def test_cors_allows_vite_preview_origin():
    client = TestClient(app)

    response = client.options(
        "/",
        headers={
            "Origin": "http://127.0.0.1:4173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4173"

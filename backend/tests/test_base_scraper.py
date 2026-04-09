import datetime
import threading

from backend.app.scrapers.base_scraper import BaseScraper


class _FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 4, 9, 17, 17, 0, tzinfo=tz)


class _ExplodingDriver:
    def __init__(self):
        self.page_source = "<html>debug</html>"
        self.screenshot_filename = None

    def get(self, url: str):
        raise RuntimeError("boom")

    def save_screenshot(self, filename: str):
        self.screenshot_filename = filename
        return True


def test_get_page_content_uses_month_in_debug_timestamp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("backend.app.scrapers.base_scraper.datetime.datetime", _FixedDateTime)

    scraper = object.__new__(BaseScraper)
    scraper.driver = _ExplodingDriver()
    scraper.shutdown_event = threading.Event()

    result = scraper.get_page_content("https://example.com", ".content")

    assert result is None
    assert scraper.driver.screenshot_filename == "debug_screenshot_20260409_171700.png"
    assert (tmp_path / "debug_page_content_20260409_171700.html").exists()


def test_base_scraper_reports_partial_status_and_error_summary():
    scraper = object.__new__(BaseScraper)
    scraper.item_errors = 2
    scraper.category_errors = 1

    assert scraper.completed_status().value == "partial"
    assert scraper.error_summary() == "1 category/page failures; 2 item failures"
    assert scraper.combine_error_summary("top-level failure") == "top-level failure; 1 category/page failures; 2 item failures"

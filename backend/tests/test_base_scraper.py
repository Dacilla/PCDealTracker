import datetime
import threading
from pathlib import Path

from backend.app.config import settings
from backend.app.scrapers.base_scraper import (
    BaseScraper,
    build_chrome_launch_kwargs,
    build_chrome_options,
    detect_browser_major_version,
    parse_browser_major_version,
)


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
    scraper.gate_waits = 0
    scraper.gate_clears = 0
    scraper.gate_failures = 0
    scraper.gate_waits_by_type = {}
    scraper.gate_clears_by_type = {}
    scraper.gate_failures_by_type = {}

    assert scraper.completed_status().value == "partial"
    assert scraper.error_summary() == "1 category/page failures; 2 item failures"
    assert scraper.combine_error_summary("top-level failure") == "top-level failure; 1 category/page failures; 2 item failures"


def test_base_scraper_gate_summary_is_included_in_error_summary():
    scraper = object.__new__(BaseScraper)
    scraper.item_errors = 0
    scraper.category_errors = 0
    scraper.gate_waits = 2
    scraper.gate_clears = 1
    scraper.gate_failures = 1
    scraper.gate_waits_by_type = {"cloudflare_challenge": 2}
    scraper.gate_clears_by_type = {"cloudflare_challenge": 1}
    scraper.gate_failures_by_type = {"http_403": 1}

    assert scraper.gate_summary() == (
        "2 gate waits (cloudflare_challenge:2); "
        "1 gates auto-cleared (cloudflare_challenge:1); "
        "1 gates failed to clear (http_403:1)"
    )
    assert scraper.error_summary() == (
        "2 gate waits (cloudflare_challenge:2); "
        "1 gates auto-cleared (cloudflare_challenge:1); "
        "1 gates failed to clear (http_403:1)"
    )


def test_build_chrome_options_applies_profile_headless_and_binary(monkeypatch, tmp_path):
    profile_dir = tmp_path / "chrome-profile"
    executable_path = tmp_path / "chrome.exe"
    executable_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(settings, "scraper_headless", True)
    monkeypatch.setattr(settings, "scraper_user_data_dir", str(profile_dir))
    monkeypatch.setattr(settings, "scraper_browser_executable", str(executable_path))

    options = build_chrome_options()

    assert "--headless=new" in options.arguments
    assert f"--user-data-dir={Path(profile_dir).resolve()}" in options.arguments
    assert options.binary_location == str(executable_path)
    assert profile_dir.exists()


def test_parse_browser_major_version_extracts_major_number():
    assert parse_browser_major_version("Google Chrome 147.0.7727.138") == 147
    assert parse_browser_major_version("Microsoft Edge 126.0.2592.113") == 126
    assert parse_browser_major_version("not-a-version") is None


def test_build_chrome_launch_kwargs_uses_detected_browser_major_version(monkeypatch, tmp_path):
    executable_path = tmp_path / "chrome.exe"
    executable_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(settings, "scraper_headless", False)
    monkeypatch.setattr(settings, "scraper_user_data_dir", None)
    monkeypatch.setattr(settings, "scraper_browser_executable", str(executable_path))
    monkeypatch.setattr(settings, "scraper_browser_major_version", None)
    monkeypatch.setattr(
        "backend.app.scrapers.base_scraper.detect_browser_major_version",
        lambda browser_executable=None: 147,
    )

    launch_kwargs = build_chrome_launch_kwargs()

    assert launch_kwargs["version_main"] == 147
    assert launch_kwargs["browser_executable_path"] == str(executable_path)


def test_detect_browser_major_version_uses_windows_file_version_fallback(monkeypatch, tmp_path):
    executable_path = tmp_path / "chrome.exe"
    executable_path.write_text("", encoding="utf-8")

    calls = []

    class _Result:
        def __init__(self, stdout: str = "", stderr: str = ""):
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == str(executable_path):
            return _Result()
        return _Result(stdout="147.0.7727.138")

    monkeypatch.setattr("backend.app.scrapers.base_scraper.os.name", "nt")
    monkeypatch.setattr("backend.app.scrapers.base_scraper.subprocess.run", fake_run)

    detected = detect_browser_major_version(str(executable_path))

    assert detected == 147
    assert calls[1][:3] == ["powershell", "-NoProfile", "-Command"]

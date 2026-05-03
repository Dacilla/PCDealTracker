import datetime
import os
import re
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from ..config import settings
from ..database import ScrapeRunStatus
from ..utils.browser_gate import detect_browser_gate

# A lock to prevent race conditions during driver initialization
_driver_lock = threading.Lock()


def patch_uc_destructor() -> None:
    if getattr(uc.Chrome, "_pcdealtracker_safe_del", False):
        return

    original_del = getattr(uc.Chrome, "__del__", None)
    if original_del is None:
        return

    def _safe_del(self):
        try:
            original_del(self)
        except OSError:
            pass

    uc.Chrome.__del__ = _safe_del
    uc.Chrome._pcdealtracker_safe_del = True


patch_uc_destructor()


def parse_browser_major_version(version_output: str) -> int | None:
    match = re.search(r"(\d+)\.\d+\.\d+\.\d+", version_output)
    if match is None:
        return None
    return int(match.group(1))


def detect_browser_major_version(browser_executable: str | None = None) -> int | None:
    executable = browser_executable or settings.scraper_browser_executable or uc.find_chrome_executable()
    if not executable:
        return None

    version_output = ""
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )
        version_output = result.stdout.strip() or result.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        version_output = ""

    detected_version = parse_browser_major_version(version_output)
    if detected_version is not None:
        return detected_version

    if os.name != "nt":
        return None

    escaped_executable = str(executable).replace("'", "''")
    powershell_command = f"(Get-Item '{escaped_executable}').VersionInfo.ProductVersion"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", powershell_command],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    return parse_browser_major_version(result.stdout.strip())


def build_chrome_options(
    *,
    headless: bool | None = None,
    user_data_dir: str | None = None,
    browser_executable: str | None = None,
) -> uc.ChromeOptions:
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")

    resolved_headless = settings.scraper_headless if headless is None else headless
    resolved_user_data_dir = settings.scraper_user_data_dir if user_data_dir is None else user_data_dir
    resolved_browser_executable = settings.scraper_browser_executable if browser_executable is None else browser_executable

    if resolved_headless:
        options.add_argument("--headless=new")
    if resolved_user_data_dir:
        user_data_dir_path = Path(resolved_user_data_dir).expanduser().resolve()
        user_data_dir_path.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir_path}")
    if resolved_browser_executable:
        options.binary_location = str(Path(resolved_browser_executable))

    return options


def build_chrome_launch_kwargs(
    *,
    headless: bool | None = None,
    user_data_dir: str | None = None,
    browser_executable: str | None = None,
    browser_major_version: int | None = None,
) -> dict:
    resolved_browser_executable = settings.scraper_browser_executable if browser_executable is None else browser_executable
    resolved_browser_major_version = (
        settings.scraper_browser_major_version
        if browser_major_version is None
        else browser_major_version
    )
    resolved_browser_major_version = (
        resolved_browser_major_version
        if resolved_browser_major_version is not None
        else detect_browser_major_version(resolved_browser_executable)
    )

    launch_kwargs = {
        "options": build_chrome_options(
            headless=headless,
            user_data_dir=user_data_dir,
            browser_executable=resolved_browser_executable,
        ),
        "use_subprocess": True,
    }
    if resolved_browser_executable:
        launch_kwargs["browser_executable_path"] = str(Path(resolved_browser_executable))
    if resolved_browser_major_version is not None:
        launch_kwargs["version_main"] = resolved_browser_major_version
    return launch_kwargs

class BaseScraper:
    """
    A base class for Selenium-driven scrapers with explicit waiting and light
    debugging support for failed page loads.
    """
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        self.db_session = db_session
        self.driver = None
        self.shutdown_event = shutdown_event
        self.item_errors = 0
        self.category_errors = 0
        self.gate_waits = 0
        self.gate_clears = 0
        self.gate_failures = 0
        self.gate_waits_by_type: Counter[str] = Counter()
        self.gate_clears_by_type: Counter[str] = Counter()
        self.gate_failures_by_type: Counter[str] = Counter()
        self.max_pages = 100
        
        try:
            # Use a lock to ensure only one thread initializes a driver at a time
            with _driver_lock:
                print("Initializing undetected-chromedriver...")
                launch_kwargs = build_chrome_launch_kwargs()
                self.driver = uc.Chrome(**launch_kwargs)
                self.driver.set_page_load_timeout(settings.scraper_page_timeout_seconds)
                print("Driver initialized.")

        except Exception as e:
            print(f"Error setting up undetected-chromedriver: {e}")
            print("Please ensure Google Chrome is installed.")

    def get_page_content(self, url: str, wait_for_selector: str) -> BeautifulSoup | None:
        """
        Fetches page content, explicitly waiting for a key element to be present.
        If the wait times out, it logs a warning but proceeds with parsing.
        """
        if self.shutdown_event.is_set():
            print("Shutdown signal received, stopping navigation.")
            return None

        if not self.driver:
            return None
            
        try:
            if url:
                print(f"Navigating to {url}...")
                self.driver.get(url)

            self._wait_for_selector_or_gate_clear(wait_for_selector)
            print("Selector found. Page is ready.")
            time.sleep(1)
            return BeautifulSoup(self.driver.page_source, 'html.parser')

        except TimeoutException:
            print(f"  -- WARNING: Timed out waiting for '{wait_for_selector}' at {url or self.driver.current_url}.")
            print("  -- Proceeding to parse the page content that has loaded so far.")
            return BeautifulSoup(self.driver.page_source, 'html.parser')

        except Exception as e:
            print(f"Error fetching or waiting for content at {url or self.driver.current_url}.")
            print(f"Underlying error: {e}")
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_filename = f"debug_screenshot_{timestamp}.png"
            html_filename = f"debug_page_content_{timestamp}.html"
            
            try:
                self.driver.save_screenshot(screenshot_filename)
                print(f"Saved a screenshot to {screenshot_filename} for inspection.")
                
                with open(html_filename, "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                print(f"Saved the page HTML to {html_filename} for inspection.")

            except Exception as se:
                print(f"Could not save debug files: {se}")
            return None

    def _wait_for_selector_or_gate_clear(self, wait_for_selector: str) -> None:
        print(f"Waiting for selector '{wait_for_selector}' to be present...")
        wait = WebDriverWait(self.driver, settings.scraper_page_timeout_seconds)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector)))
            return
        except TimeoutException:
            gate = detect_browser_gate(self.driver.title, self.driver.page_source)
            if gate:
                challenge_timeout = settings.scraper_challenge_timeout_seconds
                self.record_gate_wait(gate, self.driver.current_url)
                print(
                    f"Detected {gate} at {self.driver.current_url}. "
                    f"Waiting up to {challenge_timeout}s for the page to clear automatically..."
                )
                try:
                    challenge_wait = WebDriverWait(self.driver, challenge_timeout, poll_frequency=1)
                    challenge_wait.until(
                        lambda driver: bool(driver.find_elements(By.CSS_SELECTOR, wait_for_selector))
                        or detect_browser_gate(driver.title, driver.page_source) is None
                    )
                    follow_up_wait = WebDriverWait(self.driver, settings.scraper_page_timeout_seconds)
                    follow_up_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector)))
                    self.record_gate_clear(gate, self.driver.current_url)
                    return
                except TimeoutException:
                    self.record_gate_failure(gate, self.driver.current_url)
                    raise
            raise

    def record_item_error(self, detail: str) -> None:
        self.item_errors = getattr(self, "item_errors", 0) + 1
        print(f"  Could not ingest an item into v2. Error: {detail}")

    def record_category_error(self, detail: str) -> None:
        self.category_errors = getattr(self, "category_errors", 0) + 1
        print(f"  Category/page scrape issue: {detail}")

    def record_gate_wait(self, gate: str, url: str) -> None:
        self.gate_waits += 1
        self.gate_waits_by_type[gate] += 1
        print(f"  Gate detected ({gate}) at {url}. Waiting for auto-clear.")

    def record_gate_clear(self, gate: str, url: str) -> None:
        self.gate_clears += 1
        self.gate_clears_by_type[gate] += 1
        print(f"  Gate cleared ({gate}) at {url}.")

    def record_gate_failure(self, gate: str, url: str) -> None:
        self.gate_failures += 1
        self.gate_failures_by_type[gate] += 1
        print(f"  Gate did not clear ({gate}) at {url}.")

    def completed_status(self) -> ScrapeRunStatus:
        if getattr(self, "item_errors", 0) or getattr(self, "category_errors", 0):
            return ScrapeRunStatus.PARTIAL
        return ScrapeRunStatus.SUCCEEDED

    def _format_counter_summary(self, counter: Counter[str]) -> str:
        return ", ".join(f"{gate}:{count}" for gate, count in sorted(counter.items()))

    def gate_summary(self) -> str | None:
        parts = []
        if getattr(self, "gate_waits", 0):
            waits = self._format_counter_summary(self.gate_waits_by_type)
            parts.append(f"{self.gate_waits} gate waits ({waits})")
        if getattr(self, "gate_clears", 0):
            clears = self._format_counter_summary(self.gate_clears_by_type)
            parts.append(f"{self.gate_clears} gates auto-cleared ({clears})")
        if getattr(self, "gate_failures", 0):
            failures = self._format_counter_summary(self.gate_failures_by_type)
            parts.append(f"{self.gate_failures} gates failed to clear ({failures})")
        return "; ".join(parts) if parts else None

    def error_summary(self) -> str | None:
        parts = []
        if getattr(self, "category_errors", 0):
            parts.append(f"{self.category_errors} category/page failures")
        if getattr(self, "item_errors", 0):
            parts.append(f"{self.item_errors} item failures")
        gate_summary = self.gate_summary()
        if gate_summary:
            parts.append(gate_summary)
        return "; ".join(parts) if parts else None

    def combine_error_summary(self, detail: str | None = None) -> str | None:
        parts = [part for part in [detail, self.error_summary()] if part]
        return "; ".join(parts) if parts else None

    def run(self):
        raise NotImplementedError("Each scraper must implement the 'run' method.")

    def close(self):
        """
        Gracefully closes the webdriver. This handles potential OSErrors on shutdown.
        """
        if self.driver:
            try:
                self.driver.quit()
            except OSError as e:
                print(f"Ignoring non-critical error during driver shutdown: {e}")


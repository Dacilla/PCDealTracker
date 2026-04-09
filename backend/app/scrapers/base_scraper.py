# backend/app/scrapers/base_scraper.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
import time
import datetime
import threading

# A lock to prevent race conditions during driver initialization
_driver_lock = threading.Lock()

class BaseScraper:
    """
    A base class for Selenium-driven scrapers with explicit waiting and light
    debugging support for failed page loads.
    """
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        self.db_session = db_session
        self.driver = None
        self.shutdown_event = shutdown_event
        
        try:
            # Use a lock to ensure only one thread initializes a driver at a time
            with _driver_lock:
                print("Initializing undetected-chromedriver...")
                options = uc.ChromeOptions()
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                
                self.driver = uc.Chrome(options=options, use_subprocess=True)
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
            
            print(f"Waiting for selector '{wait_for_selector}' to be present...")
            wait = WebDriverWait(self.driver, 15)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector)))
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


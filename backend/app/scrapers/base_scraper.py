import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
import time
import datetime # Import the datetime module

class BaseScraper:
    """
    A base class for web scrapers using undetected-chromedriver with a flexible,
    explicit waiting strategy and enhanced, non-destructive debugging.
    """
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.driver = None # Initialize driver to None
        
        try:
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
        """
        if not self.driver:
            return None
            
        try:
            # Handle cases where we don't need to navigate (e.g., pagination)
            if url:
                print(f"Navigating to {url}...")
                self.driver.get(url)
            
            print(f"Waiting for selector '{wait_for_selector}' to be present...")
            wait = WebDriverWait(self.driver, 15)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector)))
            print("Selector found. Page is ready.")

            time.sleep(1)
            
            return BeautifulSoup(self.driver.page_source, 'html.parser')

        except Exception as e:
            print(f"Error fetching or waiting for content at {url or self.driver.current_url}.")
            print(f"Underlying error: {e}")
            
            # --- ENHANCED DEBUGGING ---
            # Create a unique timestamp for each error's log files.
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
        """
        This method should be implemented by each specific scraper subclass.
        """
        raise NotImplementedError("Each scraper must implement the 'run' method.")

    def close(self):
        """
        Closes the Selenium WebDriver.
        """
        if self.driver:
            self.driver.quit()

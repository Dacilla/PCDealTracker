import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
import time

class BaseScraper:
    """
    A base class for web scrapers using undetected-chromedriver with a flexible,
    explicit waiting strategy and enhanced debugging.
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
            print(f"Navigating to {url}...")
            self.driver.get(url)
            
            print(f"Waiting for selector '{wait_for_selector}' to be present...")
            # Reduced timeout to 15 seconds as requested.
            wait = WebDriverWait(self.driver, 15)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector)))
            print("Selector found. Page is ready.")

            time.sleep(2)
            
            return BeautifulSoup(self.driver.page_source, 'html.parser')

        except Exception as e:
            print(f"Error fetching or waiting for content at {url}.")
            print(f"Underlying error: {e}")
            
            # --- Enhanced Debugging ---
            # Save both a screenshot and the raw HTML for inspection.
            try:
                self.driver.save_screenshot('debug_screenshot.png')
                print("Saved a screenshot to debug_screenshot.png for inspection.")
                
                with open("debug_page_content.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                print("Saved the page HTML to debug_page_content.html for inspection.")

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

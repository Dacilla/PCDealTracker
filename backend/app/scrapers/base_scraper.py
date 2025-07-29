import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import select, func
import time
import datetime
import threading

from ..database import Product, PriceHistory, ProductStatus, Category

# A lock to prevent race conditions during driver initialization
_driver_lock = threading.Lock()

class BaseScraper:
    """
    A base class for web scrapers using undetected-chromedriver with a flexible,
    explicit waiting strategy and enhanced, non-destructive debugging.
    Includes centralized logic for updating products and detecting deals.
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
        Checks for a shutdown signal before proceeding.
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

        except Exception as e:
            print(f"Error fetching or waiting for content at {url or self.driver.current_url}.")
            print(f"Underlying error: {e}")
            
            timestamp = datetime.datetime.now().strftime("%Ym%d_%H%M%S")
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

    def _update_product_and_detect_deal(self, product_data: dict, category: Category):
        """
        Handles the core logic of adding or updating a product in the database,
        including price history tracking and deal detection.
        A product is considered "on sale" if its current price is the lowest ever recorded.
        """
        product_url = product_data.get("url")
        if not product_url:
            return

        session = self.db_session
        
        existing_product = session.execute(
            select(Product).where(Product.url == product_url)
        ).scalar_one_or_none()

        if existing_product:
            product = existing_product
            price_changed = product.current_price != product_data.get("price")
            
            product.name = product_data.get("name")
            product.current_price = product_data.get("price")
            product.image_url = product_data.get("image_url")
            product.status = product_data.get("status")

            if price_changed and product.current_price is not None:
                print(f"  Price changed for {product.name}. New price: ${product.current_price}")
                session.add(PriceHistory(product_id=product.id, price=product.current_price))
                
                price_history_query = select(func.min(PriceHistory.price)).where(PriceHistory.product_id == product.id)
                lowest_price = session.execute(price_history_query).scalar_one_or_none()

                if lowest_price is not None and product.current_price <= lowest_price:
                    if not product.on_sale:
                        print(f"  *** New record low price! Marking as a deal: {product.name} ***")
                    product.on_sale = True
                else:
                    product.on_sale = False
            
        else:
            print(f"  Adding new product: {product_data.get('name')}")
            new_product = Product(
                name=product_data.get("name"),
                url=product_data.get("url"),
                current_price=product_data.get("price"),
                image_url=product_data.get("image_url"),
                retailer_id=self.retailer.id,
                category_id=category.id,
                status=product_data.get("status"),
                on_sale=True  # It's a deal by default as it's the first price
            )
            session.add(new_product)
            session.flush()
            
            if new_product.current_price is not None:
                session.add(PriceHistory(product_id=new_product.id, price=new_product.current_price))

    def run(self):
        raise NotImplementedError("Each scraper must implement the 'run' method.")

    def close(self):
        if self.driver:
            self.driver.quit()

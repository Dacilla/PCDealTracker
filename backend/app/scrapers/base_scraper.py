import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, update
import time
import datetime
import threading

from ..database import Product, PriceHistory, ProductStatus, Category
# Import the new parsing utility
from ..utils.parsing import parse_product_name

# A lock to prevent race conditions during driver initialization
_driver_lock = threading.Lock()

class BaseScraper:
    """
    A base class for web scrapers using undetected-chromedriver with a flexible,
    explicit waiting strategy and enhanced, non-destructive debugging.
    Includes centralized logic for updating products, detecting deals, and handling delisted items.
    """
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        self.db_session = db_session
        self.driver = None
        self.shutdown_event = shutdown_event
        self.scraped_product_urls = set() # To track all URLs found during the scrape
        
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
        including data enrichment, price history tracking, and deal detection.
        """
        product_url = product_data.get("url")
        if not product_url:
            return

        self.scraped_product_urls.add(product_url)
        session = self.db_session
        
        # --- Data Enrichment Step ---
        product_name = product_data.get("name", "")
        enriched_data = parse_product_name(product_name)
        
        existing_product = session.execute(
            select(Product).where(Product.url == product_url)
        ).scalar_one_or_none()

        if existing_product:
            product = existing_product
            price_changed = product.current_price != product_data.get("price")
            
            # Update product details, now including enriched data
            product.name = product_name
            product.brand = enriched_data.get("brand")
            product.model = enriched_data.get("model")
            product.previous_price = product.current_price
            product.current_price = product_data.get("price")
            product.image_url = product_data.get("image_url")
            product.status = product_data.get("status")

            if price_changed and product.current_price is not None:
                print(f"  Price changed for {product.name}. New price: ${product.current_price}")
                session.add(PriceHistory(product_id=product.id, price=product.current_price))
                
                # --- Advanced Deal Detection ---
                is_deal = False
                deal_reasons = []

                lowest_price = session.execute(select(func.min(PriceHistory.price)).where(PriceHistory.product_id == product.id)).scalar_one_or_none()
                if lowest_price is not None and product.current_price <= lowest_price:
                    is_deal = True
                    deal_reasons.append("all-time low price")

                if product.previous_price and product.current_price < (product.previous_price * 0.90):
                    is_deal = True
                    deal_reasons.append("significant price drop")
                
                thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
                avg_price_query = select(func.avg(PriceHistory.price)).where(
                    and_(PriceHistory.product_id == product.id, PriceHistory.date >= thirty_days_ago)
                )
                avg_price = session.execute(avg_price_query).scalar_one_or_none()
                
                if avg_price and product.current_price < avg_price:
                    is_deal = True
                    deal_reasons.append("below 30-day average")

                if is_deal:
                    if not product.on_sale:
                        print(f"  *** New Deal Found! Reasons: {', '.join(deal_reasons)} for {product.name} ***")
                    product.on_sale = True
                else:
                    product.on_sale = False
            
        else:
            print(f"  Adding new product: {product_name}")
            new_product = Product(
                name=product_name,
                brand=enriched_data.get("brand"),
                model=enriched_data.get("model"),
                url=product_data.get("url"),
                current_price=product_data.get("price"),
                previous_price=product_data.get("price"),
                image_url=product_data.get("image_url"),
                retailer_id=self.retailer.id,
                category_id=category.id,
                status=product_data.get("status"),
                on_sale=True
            )
            session.add(new_product)
            session.flush()
            
            if new_product.current_price is not None:
                session.add(PriceHistory(product_id=new_product.id, price=new_product.current_price))

    def mark_delisted_products(self):
        """
        Compares scraped URLs against the database and marks missing products as UNAVAILABLE.
        """
        print("\n--- Checking for Delisted Products ---")
        
        db_product_urls_query = select(Product.url).where(
            Product.retailer_id == self.retailer.id,
            Product.status == ProductStatus.AVAILABLE
        )
        db_product_urls_result = self.db_session.execute(db_product_urls_query).scalars().all()
        db_product_urls = set(db_product_urls_result)

        delisted_urls = db_product_urls - self.scraped_product_urls

        if not delisted_urls:
            print("No delisted products found for this retailer.")
            return

        print(f"Found {len(delisted_urls)} delisted products. Updating their status...")

        update_query = (
            update(Product)
            .where(Product.url.in_(delisted_urls))
            .values(status=ProductStatus.UNAVAILABLE, on_sale=False)
        )
        
        try:
            result = self.db_session.execute(update_query)
            self.db_session.commit()
            print(f"Successfully marked {result.rowcount} products as unavailable.")
        except Exception as e:
            print(f"Error updating delisted products: {e}")
            self.db_session.rollback()

    def run(self):
        raise NotImplementedError("Each scraper must implement the 'run' method.")

    def close(self):
        """
        Gracefully closes the scraper, ensuring delisted products are marked
        and the webdriver is quit.
        """
        self.mark_delisted_products()
        
        if self.driver:
            self.driver.quit()

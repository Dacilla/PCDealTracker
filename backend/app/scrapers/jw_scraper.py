from sqlalchemy.orm import Session
from sqlalchemy import select
import time
from urllib.parse import urljoin
import threading
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, ProductStatus

# --- JW Computers-specific category mapping ---
SCRAPE_TASKS = [
    {"db_category": "Graphics Cards", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=Graphics%20Card"},
    {"db_category": "Memory (RAM)", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=RAM"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=SSD"},
    {"db_category": "Power Supplies", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=Power%20Supply%20Unit"},
    {"db_category": "PC Cases", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=Computer%20Case"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=Hard%20Drive"},
    {"db_category": "Motherboards", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=Motherboard"},
    {"db_category": "CPUs", "url": "https://www.jw.com.au/computer-parts?at__auto_product_type_attrset=CPU"},
    {"db_category": "Monitors", "url": "https://www.jw.com.au/monitors-screens"},
    {"db_category": "Fans & Accessories", "url": "https://www.jw.com.au/accessories?at__auto_product_type_attrset=Case%20Fans"},
]

class JWScraper(BaseScraper):
    """
    A scraper for the retailer JW Computers.
    This site uses a 'Show More' button to load more products.
    """
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "JW Computers")
        ).scalar_one()
        self.base_url = "https://www.jw.com.au"

    def run(self):
        """
        Main scraping process. Iterates through the scrape tasks.
        """
        for task in SCRAPE_TASKS:
            if self.shutdown_event.is_set():
                print("Shutdown signal received, stopping JW scraper.")
                break
            category_name = task["db_category"]
            category_url = task["url"]
            print(f"\n{'='*20}\nStarting JW scrape for DB category: '{category_name}' ({category_url})\n{'='*20}")
            
            category_obj = self.db_session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()

            if not category_obj:
                print(f"Category '{category_name}' not found in the database. Skipping.")
                continue
            
            self.driver.get(category_url)
            
            # Wait for the initial product list to appear
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".ais-InfiniteHits-list"))
                )
            except TimeoutException:
                print("Initial product list did not load. Skipping category.")
                continue

            # Click the 'Show More' button until it's no longer available or disabled
            while not self.shutdown_event.is_set():
                try:
                    # Use a more specific selector for the button that is not disabled
                    show_more_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".ais-InfiniteHits-loadMore:not(.ais-InfiniteHits-loadMore--disabled)"))
                    )
                    self.driver.execute_script("arguments[0].click();", show_more_button)
                    print("  'Show More' button clicked, waiting for new products...")
                    time.sleep(3) # Wait for products to load
                except TimeoutException:
                    print("  No more 'Show More' buttons found or button is disabled.")
                    break
                except Exception as e:
                    print(f"  An error occurred while clicking 'Show More': {e}")
                    break
            
            if self.shutdown_event.is_set():
                print("Shutdown signal received, stopping mid-scrape.")
                break

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            product_list = soup.select(".ais-InfiniteHits-item")
            
            if not product_list:
                print("No products found on this page.")
                continue
                
            print(f"Found {len(product_list)} products in total.")
            self.parse_and_save(product_list, category_obj)
            
            time.sleep(2)

    def parse_and_save(self, items, category):
        """Extracts and saves product data to the database."""
        for item in items:
            if self.shutdown_event.is_set(): break
            try:
                name_element = item.select_one('.result-title')
                price_element = item.select_one('.after_special')
                link_element = item.select_one('a.result')
                image_element = item.select_one('.result-thumbnail img')

                if not name_element or not price_element or not link_element: 
                    continue

                product_name = name_element.get_text(strip=True)
                product_url = urljoin(self.base_url, link_element.get('href'))
                
                image_url = image_element.get('src') if image_element else None
                
                # Corrected price parsing logic
                price_text = price_element.get_text(strip=True)
                price_str = price_text.replace("$", "").replace(",", "").strip()

                price, status = (None, ProductStatus.UNAVAILABLE)
                try:
                    price = float(price_str)
                    status = ProductStatus.AVAILABLE
                except (ValueError, AttributeError):
                    print(f"  Could not parse price from '{price_str}' for {product_name}.")

                product_data = {
                    "name": product_name,
                    "url": product_url,
                    "price": price,
                    "image_url": image_url,
                    "status": status,
                }
                self._update_product_and_detect_deal(product_data, category)
                        
            except Exception as e:
                print(f"  Could not parse an item. Error: {e}")
                continue
        
        try:
            self.db_session.commit()
            print("Successfully committed changes for this page.")
        except Exception as e:
            print(f"Error committing changes: {e}")
            self.db_session.rollback()

def run_jw_scraper(shutdown_event: threading.Event):
    """A standalone function to initialize the database session and run the scraper."""
    from ..dependencies import SessionLocal
    print("Initializing DB session for JW Computers scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = JWScraper(db_session, shutdown_event)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the JW Computers scraping process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

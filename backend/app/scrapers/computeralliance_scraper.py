from sqlalchemy.orm import Session
from sqlalchemy import select
import time
from urllib.parse import urljoin
import threading

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, ProductStatus

# --- Computer Alliance-specific category mapping ---
SCRAPE_TASKS = [
    {"db_category": "CPUs", "url": "https://www.computeralliance.com.au/cpus"},
    {"db_category": "Motherboards", "url": "https://www.computeralliance.com.au/motherboards"},
    {"db_category": "Graphics Cards", "url": "https://www.computeralliance.com.au/graphics-cards"},
    {"db_category": "Memory (RAM)", "url": "https://www.computeralliance.com.au/desktop-ram"},
    {"db_category": "Memory (RAM)", "url": "https://www.computeralliance.com.au/laptop-ram"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.computeralliance.com.au/solid-state-drives"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.computeralliance.com.au/hard-disk-drives"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/storage-accessories"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/thermal-paste"},
    {"db_category": "Cooling", "url": "https://www.computeralliance.com.au/cpu-cooling"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/fans"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/cooling-and-rgb-accessories"},
    {"db_category": "PC Cases", "url": "https://www.computeralliance.com.au/cases"},
    {"db_category": "Power Supplies", "url": "https://www.computeralliance.com.au/power-supply-units"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/power-supply-accessories"},
    {"db_category": "Monitors", "url": "https://www.computeralliance.com.au/monitors"},
]

class ComputerAllianceScraper(BaseScraper):
    """
    A scraper for the retailer Computer Alliance.
    This site loads all products on a single page, so no pagination is needed.
    """
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Computer Alliance")
        ).scalar_one()
        self.base_url = "https://www.computeralliance.com.au"

    def run(self):
        """
        Main scraping process. Iterates through the scrape tasks.
        """
        for task in SCRAPE_TASKS:
            if self.shutdown_event.is_set():
                print("Shutdown signal received, stopping Computer Alliance scraper.")
                break
            category_name = task["db_category"]
            category_url = task["url"]
            print(f"\n{'='*20}\nStarting Computer Alliance scrape for DB category: '{category_name}' ({category_url})\n{'='*20}")
            
            category_obj = self.db_session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()

            if not category_obj:
                print(f"Category '{category_name}' not found in the database. Skipping.")
                continue
            
            soup = self.get_page_content(category_url, wait_for_selector="#PartsPage")
            if not soup:
                print(f"Failed to get content for {category_url}. Skipping category.")
                continue

            product_list = soup.select(".product")
            
            if not product_list:
                print("No products found on this page.")
                continue
                
            print(f"Found {len(product_list)} products on this page.")
            self.parse_and_save(product_list, category_obj)
            
            time.sleep(2) # Delay between categories

    def parse_and_save(self, items, category):
        """Extracts and saves product data to the database."""
        for item in items:
            if self.shutdown_event.is_set(): break
            try:
                # The main link contains all the info we need
                link_element = item.select_one('a[data-pjax]')
                if not link_element:
                    continue

                name_element = link_element.select_one('h2.equalize')
                price_element = link_element.select_one('.price')
                image_element = link_element.select_one('.img-container img')

                if not name_element or not price_element: 
                    continue

                product_name = name_element.get_text(strip=True)
                product_url = urljoin(self.base_url, link_element.get('href'))
                
                image_url = urljoin(self.base_url, image_element.get('src')) if image_element and image_element.get('src') else None
                
                price_text = price_element.get_text(strip=True)
                price_str = price_text.replace("$", "").replace(",", "").strip()
                
                price, status = (None, ProductStatus.UNAVAILABLE)
                try:
                    price = float(price_str)
                    status = ProductStatus.AVAILABLE
                except (ValueError, AttributeError):
                    # Check for "POA" or similar text
                    if "poa" in price_text.lower():
                        status = ProductStatus.UNAVAILABLE
                    else:
                        print(f"  Could not parse price '{price_text}' for {product_name}.")

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

def run_computeralliance_scraper(shutdown_event: threading.Event):
    """A standalone function to initialize the database session and run the scraper."""
    from ..dependencies import SessionLocal
    print("Initializing DB session for Computer Alliance scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = ComputerAllianceScraper(db_session, shutdown_event)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the Computer Alliance scraping process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

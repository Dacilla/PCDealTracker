from sqlalchemy.orm import Session
from sqlalchemy import select
import time
from urllib.parse import urljoin
import threading

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, ProductStatus

# --- Shopping Express-specific category mapping ---
SCRAPE_TASKS = [
    {"db_category": "CPUs", "url": "https://www.shoppingexpress.com.au/CPU"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.shoppingexpress.com.au/hard-drive"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.shoppingexpress.com.au/solid-state-drive-ssd"},
    {"db_category": "Graphics Cards", "url": "https://www.shoppingexpress.com.au/gaming-graphic-card"},
    {"db_category": "Monitors", "url": "https://www.shoppingexpress.com.au/computer-monitors"},
    {"db_category": "Memory (RAM)", "url": "https://www.shoppingexpress.com.au/Memory"},
    {"db_category": "Motherboards", "url": "https://www.shoppingexpress.com.au/Motherboards"},
    {"db_category": "Power Supplies", "url": "https://www.shoppingexpress.com.au/PC-Power-Supplies"},
    {"db_category": "Fans & Accessories", "url": "https://www.shoppingexpress.com.au/Fans-and-Accessories"},
    {"db_category": "Cooling", "url": "https://www.shoppingexpress.com.au/Cooling"},
]

class ShoppingExpressScraper(BaseScraper):
    """
    A scraper for the retailer Shopping Express.
    """
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Shopping Express")
        ).scalar_one()
        self.base_url = "https://www.shoppingexpress.com.au"

    def run(self):
        """
        Main scraping process. Iterates through the scrape tasks.
        """
        for task in SCRAPE_TASKS:
            if self.shutdown_event.is_set():
                print("Shutdown signal received, stopping Shopping Express scraper.")
                break
            category_name = task["db_category"]
            category_url = task["url"]
            print(f"\n{'='*20}\nStarting Shopping Express scrape for DB category: '{category_name}' ({category_url})\n{'='*20}")
            
            category_obj = self.db_session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()

            if not category_obj:
                print(f"Category '{category_name}' not found in the database. Skipping.")
                continue
            
            current_url = category_url
            while current_url:
                if self.shutdown_event.is_set(): break
                print(f"Scraping page: {current_url}")
                
                soup = self.get_page_content(current_url, wait_for_selector=".wrapper-row-thumbnail")
                if not soup:
                    print(f"Failed to get content for {current_url}. Skipping category.")
                    break

                product_list = soup.select(".wrapper-thumbnail")
                
                if not product_list:
                    print("No products found on this page. Assuming end of category.")
                    break
                    
                print(f"Found {len(product_list)} products on this page.")
                self.parse_and_save(product_list, category_obj)
                
                # --- Pagination Logic ---
                next_page_element = soup.select_one("ul.pagination li:last-child a")
                
                # Check if the 'next' button links to the next page (and not the current one)
                if next_page_element and next_page_element.get('href') and 'javascript:void' not in next_page_element.get('href'):
                    next_page_url = urljoin(self.base_url, next_page_element['href'])
                    if next_page_url == current_url:
                        print("Next page URL is the same as current. Finished with this category.")
                        break

                    # Check if the next button is a '»' or a number. If the text is not a chevron, it's the last page number.
                    if not next_page_element.find('i', class_='fa-chevron-right'):
                         print("No 'Next Page' chevron found. Finished with this category.")
                         current_url = None
                    else:
                        current_url = next_page_url
                        time.sleep(2)
                else:
                    print("No 'Next Page' link found. Finished with this category.")
                    current_url = None

            time.sleep(3)

    def parse_and_save(self, items, category):
        """Extracts and saves product data to the database."""
        for item in items:
            if self.shutdown_event.is_set(): break
            try:
                link_element = item.select_one('.caption a')
                price_element = item.select_one('p.price span')
                image_element = item.select_one('.thumbnail-image img')

                if not link_element or not price_element: 
                    continue

                product_name = link_element.get('title', link_element.get_text(strip=True))
                product_url = urljoin(self.base_url, link_element.get('href'))
                
                image_url = urljoin(self.base_url, image_element.get('src')) if image_element and image_element.get('src') else None
                
                price_text = price_element.get_text(strip=True)
                price_str = price_text.replace("$", "").replace(",", "").strip()
                
                price, status = (None, ProductStatus.UNAVAILABLE)
                try:
                    price = float(price_str)
                    status = ProductStatus.AVAILABLE
                except (ValueError, AttributeError):
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

def run_shoppingexpress_scraper(shutdown_event: threading.Event):
    """A standalone function to initialize the database session and run the scraper."""
    from ..dependencies import SessionLocal
    print("Initializing DB session for Shopping Express scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = ShoppingExpressScraper(db_session, shutdown_event)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the Shopping Express scraping process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

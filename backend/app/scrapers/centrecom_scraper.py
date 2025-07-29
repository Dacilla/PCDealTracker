from sqlalchemy.orm import Session
from sqlalchemy import select
import time
import re
from urllib.parse import urljoin

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, PriceHistory, ProductStatus

# --- A more flexible structure for defining scrape tasks ---
# This allows multiple URLs to be mapped to the same database category.
SCRAPE_TASKS = [
    {"db_category": "Graphics Cards", "url": "https://www.centrecom.com.au/nvidia-amd-graphics-cards"},
    {"db_category": "CPUs", "url": "https://www.centrecom.com.au/cpu-processors"},
    {"db_category": "Motherboards", "url": "https://www.centrecom.com.au/motherboards"},
    {"db_category": "Memory (RAM)", "url": "https://www.centrecom.com.au/memory-ram"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.centrecom.com.au/internal-storage"},
    {"db_category": "Power Supplies", "url": "https://www.centrecom.com.au/power-supplies"},
    {"db_category": "PC Cases", "url": "https://www.centrecom.com.au/cases-enclosures"},
    {"db_category": "Monitors", "url": "https://www.centrecom.com.au/monitors"},
    # Corrected URL for Cooling
    {"db_category": "Cooling", "url": "https://www.centrecom.com.au/cooling"},
    # Split "Fans & Accessories" into its constituent parts
    {"db_category": "Fans & Accessories", "url": "https://www.centrecom.com.au/case-fans"},
    {"db_category": "Fans & Accessories", "url": "https://www.centrecom.com.au/case-accessories"},
]


class CentreComScraper(BaseScraper):
    """
    A scraper for the retailer Centre Com, which uses a standard pagination system.
    """
    def __init__(self, db_session: Session):
        super().__init__(db_session)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Centre Com")
        ).scalar_one()
        self.base_url = "https://www.centrecom.com.au"

    def run(self):
        """
        Main scraping process. Iterates through the scrape tasks.
        """
        for task in SCRAPE_TASKS:
            category_name = task["db_category"]
            category_url = task["url"]
            
            print(f"\n{'='*20}\nStarting Centre Com scrape for DB category: '{category_name}' ({category_url})\n{'='*20}")
            
            category_obj = self.db_session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()

            if not category_obj:
                print(f"Category '{category_name}' not found in the database. Skipping.")
                continue
            
            current_url = category_url
            while current_url:
                print(f"Scraping page: {current_url}")
                
                # Use the base scraper's method to get page content, waiting for the product grid.
                soup = self.get_page_content(current_url, wait_for_selector=".product-grid")
                if not soup:
                    print(f"Failed to get content for {current_url}. Skipping category.")
                    break

                # The primary selector for product items
                product_list = soup.select(".product-grid .prbox_box")
                
                if not product_list:
                    print("No products found on this page. Assuming end of category.")
                    break
                    
                print(f"Found {len(product_list)} products on this page.")
                self.parse_and_save(product_list, category_obj)
                
                # --- Pagination Logic ---
                next_page_element = soup.select_one(".pager .next-page a")
                if next_page_element and next_page_element.get('href'):
                    # Construct the absolute URL for the next page
                    next_page_url = urljoin(self.base_url, next_page_element['href'])
                    if next_page_url == current_url:
                        print("Next page URL is the same as current. Ending scrape for this category.")
                        break
                    current_url = next_page_url
                    time.sleep(2)  # Delay between page loads
                else:
                    print("No 'Next Page' link found. Finished with this category.")
                    current_url = None # End the loop

            time.sleep(3) # Increased delay between categories

    def parse_and_save(self, items, category):
        """Extracts and saves product data to the database."""
        for item in items:
            try:
                # Corrected the selector for the name element
                name_element = item.select_one('.prbox_name')
                price_element = item.select_one('.saleprice')
                link_element = item.select_one('a.prbox_link')

                if not name_element or not price_element or not link_element: 
                    print("  Skipping item due to missing name, price, or link.")
                    continue

                product_name = name_element.get_text(strip=True)
                product_href = link_element.get('href')
                
                if not product_href:
                    print(f"  No URL found for product: {product_name}")
                    continue
                
                product_url = urljoin(self.base_url, product_href)

                # --- Image URL Extraction from style attribute ---
                image_url = None
                style_attr = item.get('style')
                if style_attr:
                    match = re.search(r"url\(&quot;(.*?)&quot;\)", style_attr)
                    if match:
                        image_url = match.group(1)

                # Parse price
                price_text = price_element.get_text(strip=True)
                price_str = price_text.replace("$", "").replace(",", "").strip()
                
                price, status = (None, ProductStatus.UNAVAILABLE)
                try:
                    price = float(price_str)
                    status = ProductStatus.AVAILABLE
                except (ValueError, AttributeError):
                    print(f"  Could not parse price '{price_text}' for {product_name}.")

                existing_product = self.db_session.execute(
                    select(Product).where(Product.url == product_url)
                ).scalar_one_or_none()

                if existing_product:
                    # Check if any fields need updating
                    needs_update = False
                    if existing_product.current_price != price:
                        existing_product.current_price = price
                        needs_update = True
                    if existing_product.image_url != image_url:
                        existing_product.image_url = image_url
                        needs_update = True
                    if existing_product.status != status:
                        existing_product.status = status
                        needs_update = True
                    
                    if needs_update:
                        print(f"  Updating: {product_name}")
                        if price is not None:
                            self.db_session.add(PriceHistory(product_id=existing_product.id, price=price))
                else:
                    print(f"  Adding new product: {product_name}")
                    new_product = Product(
                        name=product_name, 
                        url=product_url, 
                        current_price=price, 
                        image_url=image_url,
                        retailer_id=self.retailer.id, 
                        category_id=category.id, 
                        on_sale=False, 
                        status=status
                    )
                    self.db_session.add(new_product)
                    if price is not None:
                        self.db_session.flush() 
                        self.db_session.add(PriceHistory(product_id=new_product.id, price=price))
                        
            except Exception as e:
                print(f"  Could not parse an item. Error: {e}")
                continue
        
        try:
            self.db_session.commit()
            print("Successfully committed changes for this page.")
        except Exception as e:
            print(f"Error committing changes: {e}")
            self.db_session.rollback()

def run_centrecom_scraper():
    """A standalone function to initialize the database session and run the scraper."""
    from ..dependencies import SessionLocal
    print("Initializing DB session for Centre Com scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = CentreComScraper(db_session)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the Centre Com scraping process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

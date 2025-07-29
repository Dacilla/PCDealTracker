from sqlalchemy.orm import Session
from sqlalchemy import select
import time
from urllib.parse import urljoin
import threading

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, PriceHistory, ProductStatus

SCRAPE_TASKS = [
    {"db_category": "Graphics Cards", "url": "https://www.msy.com.au/pc-parts/computer-parts/graphics-cards-gpu-610"},
    {"db_category": "CPUs", "url": "https://www.msy.com.au/pc-parts/computer-parts/cpu-processors-611"},
    {"db_category": "Motherboards", "url": "https://www.msy.com.au/pc-parts/computer-parts/motherboards-104"},
    {"db_category": "Memory (RAM)", "url": "https://www.msy.com.au/pc-parts/computer-parts/memory-ram-108"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.msy.com.au/pc-parts/storage-devices/hard-drives-hdd-127"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.msy.com.au/pc-parts/storage-devices/ssd-hard-drives-580"},
    {"db_category": "Power Supplies", "url": "https://www.msy.com.au/pc-parts/computer-parts/power-supply-psu-140"},
    {"db_category": "PC Cases", "url": "https://www.msy.com.au/pc-parts/computer-parts/cases-139"},
    {"db_category": "Monitors", "url": "https://www.msy.com.au/pc-parts/peripherals/monitors-142"},
    {"db_category": "Cooling", "url": "https://www.msy.com.au/pc-parts/computer-parts/cooling-191"},
    {"db_category": "Cooling", "url": "https://www.msy.com.au/pc-parts/computer-parts/water-cooling-682"},
    {"db_category": "Fans & Accessories", "url": "https://www.msy.com.au/pc-parts/computer-parts/fans-and-accessories-669"},
]

class MSYScraper(BaseScraper):
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "MSY Technology")
        ).scalar_one()
        self.base_url = "https://www.msy.com.au"

    def run(self):
        for task in SCRAPE_TASKS:
            if self.shutdown_event.is_set():
                print("Shutdown signal received, stopping MSY scraper.")
                break
            category_name = task["db_category"]
            category_url = task["url"]
            print(f"\n{'='*20}\nStarting MSY scrape for DB category: '{category_name}' ({category_url})\n{'='*20}")
            
            category_obj = self.db_session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()

            if not category_obj:
                print(f"Category '{category_name}' not found in the database. Skipping.")
                continue
            
            current_url = category_url
            
            soup = self.get_page_content(current_url, wait_for_selector=".category_section")
            if not soup:
                print(f"Failed to get initial content for {current_url}. Skipping category.")
                continue

            page_size_link = soup.select_one('.pull-right.visible-lg-inline .dropdown-menu a[href*="pagesize=3"]')
            if page_size_link and "pagesize=3" not in current_url:
                max_page_url = f"{category_url}?pagesize=3"
                print(f"Setting max page size. Navigating to: {max_page_url}")
                current_url = max_page_url
                soup = self.get_page_content(current_url, wait_for_selector=".category_section")
                if not soup:
                    print(f"Failed to get content for max page size URL {current_url}. Skipping category.")
                    continue
            else:
                print("Already on max page size or link not found. Proceeding with default.")
            
            while current_url:
                if self.shutdown_event.is_set(): break
                if soup is None:
                    print(f"Scraping page: {current_url}")
                    soup = self.get_page_content(current_url, wait_for_selector=".category_section")
                    if not soup:
                        print(f"Failed to get content for {current_url}. Breaking loop.")
                        break

                product_list = soup.select("ul#goods_sty > li.goods_info")
                
                if not product_list:
                    print("No products found on this page. Assuming end of category.")
                    break
                    
                print(f"Found {len(product_list)} products on this page.")
                self.parse_and_save(product_list, category_obj)
                
                next_page_element = None
                pager_links = soup.select(".page a")
                for link in pager_links:
                    if link.get_text(strip=True) == '>':
                        next_page_element = link
                        break
                
                soup = None
                
                if next_page_element and next_page_element.get('href'):
                    next_page_url = urljoin(self.base_url, next_page_element['href'])
                    if next_page_url == current_url:
                        break
                    current_url = next_page_url
                    time.sleep(2)
                else:
                    print("No 'Next Page' link found. Finished with this category.")
                    current_url = None

            time.sleep(3)

    def parse_and_save(self, items, category):
        for item in items:
            if self.shutdown_event.is_set(): break
            try:
                name_element = item.select_one('.goods_name a')
                price_element = item.select_one('.goods-price')
                image_element = item.select_one('.goods_img img')

                if not name_element or not price_element: 
                    continue

                product_name = name_element.get('title', '').strip()
                product_url = urljoin(self.base_url, name_element.get('href'))
                
                image_url = image_element.get('content') if image_element else None
                
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

def run_msy_scraper(shutdown_event: threading.Event):
    from ..dependencies import SessionLocal
    print("Initializing DB session for MSY scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = MSYScraper(db_session, shutdown_event)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the MSY scraping process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

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

SCRAPE_TASKS = [
    {"db_category": "Graphics Cards", "url": "https://www.centrecom.com.au/nvidia-amd-graphics-cards"},
    {"db_category": "CPUs", "url": "https://www.centrecom.com.au/cpu-processors"},
    {"db_category": "Motherboards", "url": "https://www.centrecom.com.au/motherboards"},
    {"db_category": "Memory (RAM)", "url": "https://www.centrecom.com.au/memory-ram"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.centrecom.com.au/internal-storage"},
    {"db_category": "Power Supplies", "url": "https://www.centrecom.com.au/power-supplies"},
    {"db_category": "PC Cases", "url": "https://www.centrecom.com.au/cases-enclosures"},
    {"db_category": "Monitors", "url": "https://www.centrecom.com.au/monitors"},
    {"db_category": "Cooling", "url": "https://www.centrecom.com.au/cooling"},
    {"db_category": "Fans & Accessories", "url": "https://www.centrecom.com.au/case-fans"},
    {"db_category": "Fans & Accessories", "url": "https://www.centrecom.com.au/case-accessories"},
]

class CentreComScraper(BaseScraper):
    def __init__(self, db_session: Session):
        super().__init__(db_session)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Centre Com")
        ).scalar_one()
        self.base_url = "https://www.centrecom.com.au"

    def run(self):
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
                
                soup = self.get_page_content(current_url, wait_for_selector=".product-grid")
                if not soup:
                    print(f"Failed to get content for {current_url}. Skipping category.")
                    break

                product_list = soup.select(".product-grid .prbox_box")
                
                if not product_list:
                    print("No products found on this page. Assuming end of category.")
                    break
                    
                print(f"Found {len(product_list)} products on this page.")
                self.parse_and_save(product_list, category_obj)
                
                next_page_element = soup.select_one(".pager .next-page a")
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
            try:
                name_element = item.select_one('.prbox_name')
                price_element = item.select_one('.saleprice')
                link_element = item.select_one('a.prbox_link')

                if not name_element or not price_element or not link_element: 
                    continue

                product_name = name_element.get_text(strip=True)
                product_href = link_element.get('href')
                
                if not product_href:
                    continue
                
                product_url = urljoin(self.base_url, product_href)

                image_url = None
                style_attr = item.get('style')
                if style_attr:
                    match = re.search(r"url\(&quot;(.*?)&quot;\)", style_attr)
                    if match:
                        image_url = match.group(1)

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

def run_centrecom_scraper():
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

import re
from sqlalchemy.orm import Session
from sqlalchemy import select
import time
from urllib.parse import urljoin

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, PriceHistory, ProductStatus

CATEGORY_URL_MAP = {
    "Graphics Cards": "https://www.pccasegear.com/category/193/graphics-cards",
    "CPUs": "https://www.pccasegear.com/category/187/cpus",
    "Motherboards": "https://www.pccasegear.com/category/138/motherboards",
    "Memory (RAM)": "https://www.pccasegear.com/category/186/memory",
    "Storage (SSD/HDD)": "https://www.pccasegear.com/category/210/hard-drives-ssds",
    "Power Supplies": "https://www.pccasegear.com/category/15/power-supplies",
    "PC Cases": "https://www.pccasegear.com/category/25/cases",
    "Monitors": "https://www.pccasegear.com/category/558/monitors",
    "Cooling": "https://www.pccasegear.com/category/207/cooling",
    "Fans & Accessories": "https://www.pccasegear.com/category/9/fans-accessories",
}

class PCCGScraper(BaseScraper):
    def __init__(self, db_session: Session):
        super().__init__(db_session)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "PC Case Gear")
        ).scalar_one()
        self.base_url = "https://www.pccasegear.com"

    def scrape_products_from_page(self, page_url: str, category: Category):
        print(f"Scraping product page: {page_url}")
        soup = self.get_page_content(page_url, wait_for_selector="footer")
        if not soup:
            print(f"Failed to get content from {page_url}")
            return

        product_list_layout1 = soup.select("[data-product-card-container]")
        product_list_layout2 = soup.select(".product-container.list-view")

        if product_list_layout1:
            print(f"Found {len(product_list_layout1)} products using layout 1.")
            self.parse_and_save(product_list_layout1, '[data-product-card-title] a', '[data-product-price-current]', '[data-product-card-image] img', category)
        elif product_list_layout2:
            print(f"Found {len(product_list_layout2)} products using layout 2.")
            self.parse_and_save(product_list_layout2, '.product-title', '.price', '.product-image img', category)
        else:
            print("No known product layout found on this page. Skipping.")

        self.db_session.commit()
        print("Committing changes for this page.")

    def parse_and_save(self, items, name_selector, price_selector, image_selector, category):
        for item in items:
            try:
                name_element = item.select_one(name_selector)
                price_element = item.select_one(price_selector)
                image_element = item.select_one(image_selector)
                if not name_element or not price_element: continue

                product_name = name_element.get_text(strip=True)
                product_url_suffix = name_element.get('href', name_element.find('a')['href'] if name_element.find('a') else None)
                if not product_url_suffix: continue

                product_url = urljoin(self.base_url, product_url_suffix)
                image_url = image_element.get('src') if image_element else None
                price_str = price_element.get_text(strip=True).replace("$", "").replace(",", "")
                
                price, status = (None, ProductStatus.UNAVAILABLE)
                try:
                    price = float(price_str)
                    status = ProductStatus.AVAILABLE
                except ValueError:
                    print(f"  Could not parse price '{price_str}' for {product_name}.")
                
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

    def run(self):
        for category_name, main_category_url in CATEGORY_URL_MAP.items():
            print(f"\n{'='*20}\nStarting scrape for category: {category_name}\n{'='*20}")
            category_obj = self.db_session.execute(select(Category).where(Category.name == category_name)).scalar_one_or_none()
            if not category_obj:
                print(f"Category '{category_name}' not found. Skipping.")
                continue

            soup = self.get_page_content(main_category_url, wait_for_selector=".prdct_box_sec")
            if not soup:
                print(f"Failed to retrieve main page for {category_name}. Skipping.")
                continue

            subcategory_cards = soup.select('.prdct_box a')
            subcategory_urls = {urljoin(self.base_url, card.get('href')) for card in subcategory_cards if card.get('href') and '/category/' in card.get('href')}

            if not subcategory_urls:
                print("No sub-categories found. Scraping main page directly.")
                self.scrape_products_from_page(main_category_url, category_obj)
                continue
            
            print(f"Found {len(subcategory_urls)} sub-categories.")
            for url in sorted(list(subcategory_urls)):
                print(f"\n--- Navigating to sub-category: {url} ---")
                self.scrape_products_from_page(url, category_obj)
                time.sleep(1)

def run_pccg_scraper():
    from ..dependencies import SessionLocal
    print("Initializing DB session for scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = PCCGScraper(db_session)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

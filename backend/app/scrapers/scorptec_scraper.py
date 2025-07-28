from sqlalchemy.orm import Session
from sqlalchemy import select
import time
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, PriceHistory, ProductStatus

# This map defines which URL on the retailer's site corresponds to which main category in our DB.
CATEGORY_URL_MAP = {
    "Graphics Cards": "https://www.scorptec.com.au/product/graphics-cards",
    "CPUs": "https://www.scorptec.com.au/product/cpu",
    "Motherboards": "https://www.scorptec.com.au/product/motherboards",
    "Memory (RAM)": "https://www.scorptec.com.au/product/memory",
    "Storage (SSD/HDD)": "https://www.scorptec.com.au/product/hard-drives-&-ssds",
    "Power Supplies": "https://www.scorptec.com.au/product/power-supplies",
    "PC Cases": "https://www.scorptec.com.au/product/cases",
    "Monitors": "https://www.scorptec.com.au/product/monitors",
    "Cooling": "https://www.scorptec.com.au/product/cooling",
    # Note: We intentionally omit "Fans & Accessories" here because Scorptec groups it under "Cooling".
}

# --- NEW: Sub-category to DB Category Mapping ---
# This helps us correctly categorize products from a broad hub page.
SUBCATEGORY_DB_MAP = {
    'cpu-coolers': 'Cooling',
    'fans': 'Fans & Accessories',
    'fan-controllers': 'Fans & Accessories',
    'thermal-paste': 'Fans & Accessories',
    'water-cooling': 'Cooling',
    'accessories': 'Fans & Accessories',
}

class ScorptecScraper(BaseScraper):
    def __init__(self, db_session: Session):
        super().__init__(db_session)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Scorptec")
        ).scalar_one()

    def scrape_products_from_page(self, page_url: str, category: Category):
        print(f"Scraping product page: {page_url}")
        
        soup = self.get_page_content(page_url, wait_for_selector="#product-list-detail-wrapper")
        if not soup:
            print(f"Failed to get content from {page_url}")
            return

        product_list = soup.select(".product-list-detail")
        if not product_list:
            print("No products found on this page.")
            return
        
        print(f"Found {len(product_list)} products in total for this category.")
        self.parse_and_save(product_list, category)

    def parse_and_save(self, items, category):
        """Extracts and saves product data to the database."""
        for item in items:
            try:
                name_element = item.select_one('.detail-product-title a')
                price_element = item.select_one('.detail-product-price')
                image_element = item.select_one('.detail-image-wrapper img')
                if not name_element or not price_element: continue

                product_name = name_element.get_text(strip=True)
                product_url = "https://www.scorptec.com.au" + name_element.get('href')
                image_url = image_element.get('data-src') or image_element.get('src') if image_element else None
                price_str = price_element.get_text(strip=True).replace("$", "").replace(",", "")
                
                price, status = (None, ProductStatus.UNAVAILABLE)
                try:
                    price = float(price_str)
                    status = ProductStatus.AVAILABLE
                except ValueError:
                    print(f"  Could not parse price '{price_str}' for {product_name}.")

                existing_product = self.db_session.execute(select(Product).where(Product.url == product_url)).scalar_one_or_none()

                if existing_product:
                    if existing_product.current_price != price or existing_product.image_url != image_url:
                        print(f"  Updating: {product_name}")
                        existing_product.current_price = price
                        existing_product.image_url = image_url
                        existing_product.status = status
                        if price is not None:
                            self.db_session.add(PriceHistory(product_id=existing_product.id, price=price))
                else:
                    print(f"  Adding new product: {product_name}")
                    new_product = Product(
                        name=product_name, url=product_url, current_price=price, image_url=image_url,
                        retailer_id=self.retailer.id, category_id=category.id, 
                        on_sale=False, status=status
                    )
                    self.db_session.add(new_product)
                    if price is not None:
                        self.db_session.flush() 
                        self.db_session.add(PriceHistory(product_id=new_product.id, price=price))
            except Exception as e:
                print(f"  Could not parse an item. Error: {e}")
        
        self.db_session.commit()
        print("Committing changes for this page.")

    def run(self):
        for category_name, main_category_url in CATEGORY_URL_MAP.items():
            print(f"\n{'='*20}\nStarting Scorptec scrape for category: {category_name}\n{'='*20}")
            
            category_obj = self.db_session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()
            if not category_obj:
                print(f"Category '{category_name}' not found. Skipping.")
                continue
            
            soup = self.get_page_content(main_category_url, wait_for_selector=".category-wrapper")
            if not soup:
                print(f"Failed to retrieve main page for {category_name}. Skipping.")
                continue

            subcategory_links = soup.select('.grid-subcategory-title a')
            
            # --- NEW: Smart Category Assignment ---
            if category_name == "Cooling":
                for link in subcategory_links:
                    href = link.get('href')
                    if not href: continue
                    
                    # Find the specific sub-category name from the URL
                    sub_cat_slug = href.split('/')[-1]
                    
                    # Use our mapping to find the correct DB category name
                    db_cat_name = SUBCATEGORY_DB_MAP.get(sub_cat_slug, category_name)
                    
                    # Get the correct category object from the database
                    final_category_obj = self.db_session.execute(
                        select(Category).where(Category.name == db_cat_name)
                    ).scalar_one()
                    
                    url = "https://www.scorptec.com.au" + href
                    print(f"\n--- Navigating to sub-category: {url} (mapped to DB cat: {db_cat_name}) ---")
                    self.scrape_products_from_page(url, final_category_obj)
                    time.sleep(1)
            else:
                # Original logic for all other categories
                subcategory_urls = {"https://www.scorptec.com.au" + link.get('href') for link in subcategory_links if link.get('href')}
                if not subcategory_urls:
                    print("No sub-categories found. Scraping main page directly.")
                    self.scrape_products_from_page(main_category_url, category_obj)
                    continue
                
                print(f"Found {len(subcategory_urls)} sub-categories to scrape.")
                for url in sorted(list(subcategory_urls)):
                    print(f"\n--- Navigating to sub-category: {url} ---")
                    self.scrape_products_from_page(url, category_obj)
                    time.sleep(1)

def run_scorptec_scraper():
    from ..dependencies import SessionLocal
    print("Initializing DB session for Scorptec scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = ScorptecScraper(db_session)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the Scorptec scraping process: {e}")
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

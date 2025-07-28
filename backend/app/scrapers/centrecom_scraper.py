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

# --- Centre Com-specific category mapping ---
CATEGORY_URL_MAP = {
    "Graphics Cards": "https://www.centrecom.com.au/computer-components/graphics-cards",
    "CPUs": "https://www.centrecom.com.au/computer-components/cpus-processors",
    "Motherboards": "https://www.centrecom.com.au/computer-components/motherboards",
    "Memory (RAM)": "https://www.centrecom.com.au/computer-components/memory-ram",
    "Storage (SSD/HDD)": "https://www.centrecom.com.au/computer-components/storage",
    "Power Supplies": "https://www.centrecom.com.au/computer-components/power-supplies",
    "PC Cases": "https://www.centrecom.com.au/computer-components/computer-cases",
    "Monitors": "https://www.centrecom.com.au/peripherals/monitors",
    "Cooling": "https://www.centrecom.com.au/computer-components/cooling",
    "Fans & Accessories": "https://www.centrecom.com.au/computer-components/case-fans",
}

class CentreComScraper(BaseScraper):
    """
    A scraper for the retailer Centre Com, which uses a 'Load More' button for pagination.
    """
    def __init__(self, db_session: Session):
        super().__init__(db_session)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Centre Com")
        ).scalar_one()

    def run(self):
        """
        Main scraping process. Iterates through the category map and scrapes each one.
        """
        for category_name, category_url in CATEGORY_URL_MAP.items():
            print(f"\n{'='*20}\nStarting Centre Com scrape for category: {category_name}\n{'='*20}")
            
            category_obj = self.db_session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()

            if not category_obj:
                print(f"Category '{category_name}' not found in the database. Skipping.")
                continue
            
            # --- "Load More" Pagination Logic ---
            self.driver.get(category_url)
            while True:
                try:
                    # Wait for the load more button to be clickable
                    wait = WebDriverWait(self.driver, 10)
                    load_more_button = wait.until(EC.element_to_be_clickable((By.ID, "btn-load-more")))
                    
                    print("Found 'Load More' button, clicking...")
                    self.driver.execute_script("arguments[0].click();", load_more_button)
                    # Wait a moment for new products to load
                    time.sleep(3)
                except (NoSuchElementException, TimeoutException):
                    print("No more 'Load More' buttons found. All products should be loaded.")
                    break
                except Exception as e:
                    print(f"An error occurred while trying to click 'Load More': {e}")
                    break

            # Now that all products are loaded, parse the entire page
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            product_list = soup.select(".product-layout")
            print(f"Found {len(product_list)} products in total for this category.")
            self.parse_and_save(product_list, category_obj)
            time.sleep(1)

    def parse_and_save(self, items, category):
        """Extracts and saves product data to the database."""
        for item in items:
            try:
                name_element = item.select_one('.name a')
                price_element = item.select_one('.price-new')
                image_element = item.select_one('.image img')
                if not name_element or not price_element: continue

                product_name = name_element.get_text(strip=True)
                product_url = name_element.get('href') # Centre Com uses absolute URLs
                image_url = image_element.get('src') if image_element else None
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
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

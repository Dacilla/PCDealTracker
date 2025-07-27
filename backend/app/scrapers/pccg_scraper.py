import re
from sqlalchemy.orm import Session
from sqlalchemy import select
import time

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, PriceHistory, ProductStatus

class PCCGScraper(BaseScraper):
    """
    A scraper for PC Case Gear that handles multiple page layouts and non-numeric prices.
    """
    def __init__(self, db_session: Session):
        super().__init__(db_session)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "PC Case Gear")
        ).scalar_one()
        self.parent_category = self.db_session.execute(
            select(Category).where(Category.name == "Graphics Cards")
        ).scalar_one()

    def scrape_products_from_page(self, page_url: str):
        """
        Scrapes all product details from a single product listing page,
        handling different possible HTML structures.
        """
        print(f"Scraping product page: {page_url}")
        
        soup = self.get_page_content(page_url, wait_for_selector="footer")
        if not soup:
            print(f"Failed to get content from {page_url}")
            return

        product_list_layout1 = soup.select("[data-product-card-container]")
        product_list_layout2 = soup.select(".product-container.list-view")

        if product_list_layout1:
            print(f"Found {len(product_list_layout1)} products using layout 1.")
            self.parse_layout_1(product_list_layout1)
        elif product_list_layout2:
            print(f"Found {len(product_list_layout2)} products using layout 2.")
            self.parse_layout_2(product_list_layout2)
        else:
            print("No known product layout found on this page. Skipping.")

        self.db_session.commit()
        print("Committing changes for this page.")

    def parse_layout_1(self, items):
        """Parses the layout that uses 'data-*' attributes."""
        for item in items:
            name_element = item.select_one('[data-product-card-title] a')
            price_element = item.select_one('[data-product-price-current]')
            if name_element and price_element:
                self.save_product_data(name_element, price_element)

    def parse_layout_2(self, items):
        """Parses the layout found on the Accessories page."""
        for item in items:
            name_element = item.select_one('.product-title')
            price_element = item.select_one('.price')
            if name_element and price_element:
                self.save_product_data(name_element, price_element)

    def save_product_data(self, name_element, price_element):
        """Extracts and saves product data to the database, handling TBA prices."""
        try:
            product_name = name_element.get_text(strip=True)
            product_url_suffix = name_element.get('href', name_element.find('a')['href'] if name_element.find('a') else None)
            if not product_url_suffix: return

            product_url = "https://www.pccasegear.com" + product_url_suffix
            price_str = price_element.get_text(strip=True).replace("$", "").replace(",", "")
            
            price = None
            status = ProductStatus.AVAILABLE
            try:
                price = float(price_str)
            except ValueError:
                print(f"  Could not parse price '{price_str}' for {product_name}. Setting price to None.")
                status = ProductStatus.UNAVAILABLE

            existing_product = self.db_session.execute(
                select(Product).where(Product.url == product_url)
            ).scalar_one_or_none()

            if existing_product:
                if existing_product.current_price != price:
                    print(f"  Updating price for: {product_name}")
                    existing_product.current_price = price
                    existing_product.status = status
                    if price is not None:
                        history_entry = PriceHistory(product_id=existing_product.id, price=price)
                        self.db_session.add(history_entry)
            else:
                print(f"  Adding new product: {product_name}")
                new_product = Product(
                    name=product_name, url=product_url, current_price=price,
                    retailer_id=self.retailer.id, category_id=self.parent_category.id, 
                    on_sale=False, status=status
                )
                self.db_session.add(new_product)
                if price is not None:
                    self.db_session.flush() 
                    history_entry = PriceHistory(product_id=new_product.id, price=price)
                    self.db_session.add(history_entry)
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            print(f"  Could not parse an item. Error: {e}")

    def run(self):
        """
        Main scraping process. First finds sub-category links, then scrapes each one.
        """
        print(f"Starting scraper for {self.retailer.name} - {self.parent_category.name}")
        
        main_category_url = "https://www.pccasegear.com/category/193/graphics-cards"
        soup = self.get_page_content(main_category_url, wait_for_selector=".prdct_box_sec")

        if not soup:
            print("Failed to retrieve main category page. Aborting.")
            return

        subcategory_cards = soup.select('.prdct_box a')
        
        subcategory_urls = set()
        for card in subcategory_cards:
            href = card.get('href')
            if href and '/category/193_' in href:
                subcategory_urls.add(href)

        if not subcategory_urls:
            print("Could not find any sub-category links after filtering. The website layout may have changed.")
            return
            
        print(f"Found {len(subcategory_urls)} sub-categories to scrape.")

        for url in sorted(list(subcategory_urls)):
            print(f"\n--- Navigating to sub-category: {url} ---")
            self.scrape_products_from_page(url)
            time.sleep(3)


def run_pccg_scraper():
    """A standalone function to initialize the database session and run the scraper."""
    from ..dependencies import SessionLocal
    
    print("Initializing DB session for scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = PCCGScraper(db_session)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the scraping process: {e}")
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

if __name__ == '__main__':
    run_pccg_scraper()

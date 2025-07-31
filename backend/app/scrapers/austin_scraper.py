from sqlalchemy.orm import Session
from sqlalchemy import select
import time
from urllib.parse import urljoin
import threading

from .base_scraper import BaseScraper
from ..database import Product, Retailer, Category, ProductStatus

# --- Austin Computers-specific category mapping ---
SCRAPE_TASKS = [
    {"db_category": "PC Cases", "url": "https://www.austin.net.au/collections/all-cases"},
    {"db_category": "Cooling", "url": "https://www.austin.net.au/collections/cpu-coolers-air"},
    {"db_category": "Cooling", "url": "https://www.austin.net.au/collections/cpu-coolers-water"},
    {"db_category": "Fans & Accessories", "url": "https://www.austin.net.au/collections/120mm-fans"},
    {"db_category": "Fans & Accessories", "url": "https://www.austin.net.au/collections/140mm-fans"},
    {"db_category": "Fans & Accessories", "url": "https://www.austin.net.au/collections/40mm-92mm-fans"},
    {"db_category": "Fans & Accessories", "url": "https://www.austin.net.au/collections/fan-controllers"},
    {"db_category": "Fans & Accessories", "url": "https://www.austin.net.au/collections/thermal-paste"},
    {"db_category": "CPUs", "url": "https://www.austin.net.au/collections/intel-1700-14th-gen"},
    {"db_category": "CPUs", "url": "https://www.austin.net.au/collections/intel-1700-13th-gen"},
    {"db_category": "CPUs", "url": "https://www.austin.net.au/collections/intel-socket-1200-cpu"},
    {"db_category": "CPUs", "url": "https://www.austin.net.au/collections/intel-socket-2066-cpu"},
    {"db_category": "CPUs", "url": "https://www.austin.net.au/collections/amd-socket-am4-cpu"},
    {"db_category": "CPUs", "url": "https://www.austin.net.au/collections/amd-socket-am5-cpu"},
    {"db_category": "Graphics Cards", "url": "https://www.austin.net.au/collections/intel-arc"},
    {"db_category": "Graphics Cards", "url": "https://www.austin.net.au/collections/amd"},
    {"db_category": "Graphics Cards", "url": "https://www.austin.net.au/collections/nvidia"},
    {"db_category": "Graphics Cards", "url": "https://www.austin.net.au/collections/workstation"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.austin.net.au/collections/solid-state-drives-ssd"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.austin.net.au/collections/pcie-ssd"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.austin.net.au/collections/3-5-hard-drives"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.austin.net.au/collections/2-5-hard-drives"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.austin.net.au/collections/external-ssd"},
    {"db_category": "Memory (RAM)", "url": "https://www.austin.net.au/collections/ddr5-memory"},
    {"db_category": "Memory (RAM)", "url": "https://www.austin.net.au/collections/ddr4-memory"},
    {"db_category": "Memory (RAM)", "url": "https://www.austin.net.au/collections/ddr3-memory"},
    {"db_category": "Memory (RAM)", "url": "https://www.austin.net.au/collections/sodimm-memory"},
    {"db_category": "Monitors", "url": "https://www.austin.net.au/collections/22-inch-and-below-monitors"},
    {"db_category": "Monitors", "url": "https://www.austin.net.au/collections/23-26-inch-monitors"},
    {"db_category": "Monitors", "url": "https://www.austin.net.au/collections/27-33-inch-monitors"},
    {"db_category": "Monitors", "url": "https://www.austin.net.au/collections/34-inch-and-above-monitors"},
    {"db_category": "Motherboards", "url": "https://www.austin.net.au/collections/intel-socket-1200"},
    {"db_category": "Motherboards", "url": "https://www.austin.net.au/collections/intel-socket-1700"},
    {"db_category": "Motherboards", "url": "https://www.austin.net.au/collections/amd-socket-am4"},
    {"db_category": "Motherboards", "url": "https://www.austin.net.au/collections/amd-socket-am5"},
    {"db_category": "Motherboards", "url": "https://www.austin.net.au/collections/intel-socket-2066"},
]

class AustinScraper(BaseScraper):
    """
    A scraper for the retailer Austin Computers.
    """
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Austin Computers")
        ).scalar_one()
        self.base_url = "https://www.austin.net.au"

    def run(self):
        """
        Main scraping process. Iterates through the scrape tasks.
        NOTE: This scraper is currently disabled due to issues with the site's
              dynamic loading, which prevents reliable scraping.
        """
        print("--- Austin Computers scraper is currently disabled. ---")
        return

    def parse_and_save(self, items, category):
        """Extracts and saves product data to the database."""
        for item in items:
            if self.shutdown_event.is_set(): break
            try:
                name_element = item.select_one('h3.card__heading a')
                
                price_container = item.select_one('.price')
                price_element = None
                if price_container:
                    price_element = price_container.select_one('.price-item--sale')
                    if not price_element:
                        price_element = price_container.select_one('.price-item--regular')

                image_element = item.select_one('.card__media img')

                if not name_element or not price_element: 
                    continue

                product_name = name_element.get_text(strip=True)
                product_url = urljoin(self.base_url, name_element.get('href'))
                
                image_url = "https:" + image_element.get('src') if image_element and image_element.get('src') else None
                
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

def run_austin_scraper(shutdown_event: threading.Event):
    """A standalone function to initialize the database session and run the scraper."""
    from ..dependencies import SessionLocal
    print("Initializing DB session for Austin Computers scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = AustinScraper(db_session, shutdown_event)
        scraper.run()
    except Exception as e:
        print(f"\nAn error occurred during the Austin Computers scraping process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

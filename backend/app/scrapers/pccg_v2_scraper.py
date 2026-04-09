from urllib.parse import urljoin
import threading
import time

from bs4 import Tag
from sqlalchemy import select
from sqlalchemy.orm import Session

from .base_scraper import BaseScraper
from ..database import Category, ProductStatus, Retailer, ScrapeRunStatus
from ..services.v2_catalog import (
    V2ListingSnapshot,
    finish_scrape_run,
    mark_missing_retailer_urls_unavailable,
    start_scrape_run,
    upsert_v2_listing_snapshot,
)


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

PCCG_LAYOUTS = (
    {
        "container_selector": "[data-product-card-container]",
        "name_selector": "[data-product-card-title] a",
        "price_selector": "[data-product-price-current]",
        "image_selector": "[data-product-card-image] img",
    },
    {
        "container_selector": ".product-container.list-view",
        "name_selector": ".product-title",
        "price_selector": ".price",
        "image_selector": ".product-image img",
    },
)


def extract_pccg_subcategory_urls(soup, base_url: str) -> list[str]:
    subcategory_cards = soup.select(".prdct_box a")
    subcategory_urls = {
        urljoin(base_url, card.get("href"))
        for card in subcategory_cards
        if card.get("href") and "/category/" in card.get("href")
    }
    return sorted(subcategory_urls)


def detect_pccg_product_layout(soup):
    for layout in PCCG_LAYOUTS:
        items = soup.select(layout["container_selector"])
        if items:
            return items, layout
    return None, None


def parse_pccg_listing(
    item: Tag,
    *,
    base_url: str,
    name_selector: str,
    price_selector: str,
    image_selector: str,
) -> V2ListingSnapshot | None:
    name_element = item.select_one(name_selector)
    price_element = item.select_one(price_selector)
    image_element = item.select_one(image_selector)
    if not name_element or not price_element:
        return None

    product_url_suffix = name_element.get("href", name_element.find("a")["href"] if name_element.find("a") else None)
    if not product_url_suffix:
        return None

    product_name = name_element.get_text(strip=True)
    product_url = urljoin(base_url, product_url_suffix)
    image_url = image_element.get("src") if image_element else None

    price_text = price_element.get_text(strip=True)
    price_str = price_text.replace("$", "").replace(",", "").strip()

    price = None
    status = ProductStatus.UNAVAILABLE
    try:
        price = float(price_str)
        status = ProductStatus.AVAILABLE
    except (ValueError, TypeError):
        print(f"  Could not parse price '{price_text}' for {product_name}.")

    return V2ListingSnapshot(
        name=product_name,
        url=product_url,
        price=price,
        status=status,
        image_url=image_url,
        raw_payload={
            "price_text": price_text,
            "source": "pccg_v2",
            "layout_name_selector": name_selector,
        },
    )


class PCCGV2Scraper(BaseScraper):
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "PC Case Gear")
        ).scalar_one()
        self.base_url = "https://www.pccasegear.com"
        self.scrape_run = start_scrape_run(
            self.db_session,
            retailer_id=self.retailer.id,
            scraper_name="pccg_v2",
            trigger_source="scraper",
        )
        self.seen_urls: set[str] = set()
        self.listings_seen = 0
        self.listings_created = 0
        self.listings_updated = 0

    def scrape_products_from_page(self, page_url: str, category: Category):
        if self.shutdown_event.is_set():
            return

        print(f"Scraping product page: {page_url}")
        soup = self.get_page_content(page_url, wait_for_selector="footer")
        if not soup:
            print(f"Failed to get content from {page_url}")
            return

        items, layout = detect_pccg_product_layout(soup)
        if items and layout:
            print(f"Found {len(items)} products using layout {layout['container_selector']}.")
            self.ingest_items(
                items,
                name_selector=layout["name_selector"],
                price_selector=layout["price_selector"],
                image_selector=layout["image_selector"],
                category=category,
            )
        else:
            print("No known product layout found on this page. Skipping.")

        self.db_session.commit()
        print("Committing changes for this page.")

    def ingest_items(self, items, *, name_selector: str, price_selector: str, image_selector: str, category: Category):
        for item in items:
            if self.shutdown_event.is_set():
                break
            try:
                snapshot = parse_pccg_listing(
                    item,
                    base_url=self.base_url,
                    name_selector=name_selector,
                    price_selector=price_selector,
                    image_selector=image_selector,
                )
                if snapshot is None:
                    continue

                self.seen_urls.add(snapshot.url)
                self.listings_seen += 1
                result = upsert_v2_listing_snapshot(
                    self.db_session,
                    scrape_run=self.scrape_run,
                    retailer_id=self.retailer.id,
                    category_id=category.id,
                    category_name=category.name,
                    snapshot=snapshot,
                )
                if result.listing_created:
                    self.listings_created += 1
                else:
                    self.listings_updated += 1
            except Exception as exc:
                print(f"  Could not ingest an item into v2. Error: {exc}")

    def run(self):
        try:
            for category_name, main_category_url in CATEGORY_URL_MAP.items():
                if self.shutdown_event.is_set():
                    print("Shutdown signal received, stopping PCCG v2 scraper.")
                    break

                print(f"\n{'='*20}\nStarting PCCG v2 scrape for category: {category_name}\n{'='*20}")
                category_obj = self.db_session.execute(
                    select(Category).where(Category.name == category_name)
                ).scalar_one_or_none()
                if not category_obj:
                    print(f"Category '{category_name}' not found. Skipping.")
                    continue

                soup = self.get_page_content(main_category_url, wait_for_selector=".prdct_box_sec")
                if not soup:
                    print(f"Failed to retrieve main page for {category_name}. Skipping.")
                    continue

                subcategory_urls = extract_pccg_subcategory_urls(soup, self.base_url)

                if not subcategory_urls:
                    print("No sub-categories found. Scraping main page directly.")
                    self.scrape_products_from_page(main_category_url, category_obj)
                    continue

                print(f"Found {len(subcategory_urls)} sub-categories.")
                for url in subcategory_urls:
                    if self.shutdown_event.is_set():
                        break
                    print(f"\n--- Navigating to sub-category: {url} ---")
                    self.scrape_products_from_page(url, category_obj)
                    time.sleep(1)

            missing_count = mark_missing_retailer_urls_unavailable(
                self.db_session,
                retailer_id=self.retailer.id,
                seen_urls=self.seen_urls,
                scrape_run=self.scrape_run,
            )
            self.listings_updated += missing_count
            finish_scrape_run(
                self.db_session,
                self.scrape_run,
                status=ScrapeRunStatus.SUCCEEDED,
                listings_seen=self.listings_seen,
                listings_created=self.listings_created,
                listings_updated=self.listings_updated,
            )
            self.db_session.commit()
        except Exception as exc:
            self.db_session.rollback()
            finish_scrape_run(
                self.db_session,
                self.scrape_run,
                status=ScrapeRunStatus.FAILED,
                listings_seen=self.listings_seen,
                listings_created=self.listings_created,
                listings_updated=self.listings_updated,
                error_summary=str(exc),
            )
            self.db_session.commit()
            raise

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except OSError as exc:
                print(f"Ignoring non-critical error during driver shutdown: {exc}")


def run_pccg_v2_scraper(shutdown_event: threading.Event):
    from ..dependencies import SessionLocal

    print("Initializing DB session for PCCG v2 scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = PCCGV2Scraper(db_session, shutdown_event)
        scraper.run()
    except Exception as exc:
        print(f"\nAn error occurred during the PCCG v2 scraping process: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

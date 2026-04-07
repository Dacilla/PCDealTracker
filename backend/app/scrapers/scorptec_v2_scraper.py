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
    "Graphics Cards": "https://www.scorptec.com.au/product/graphics-cards",
    "CPUs": "https://www.scorptec.com.au/product/cpu",
    "Motherboards": "https://www.scorptec.com.au/product/motherboards",
    "Memory (RAM)": "https://www.scorptec.com.au/product/memory",
    "Storage (SSD/HDD)": "https://www.scorptec.com.au/product/hard-drives-&-ssds",
    "Power Supplies": "https://www.scorptec.com.au/product/power-supplies",
    "PC Cases": "https://www.scorptec.com.au/product/cases",
    "Monitors": "https://www.scorptec.com.au/product/monitors",
    "Cooling": "https://www.scorptec.com.au/product/cooling",
}

SUBCATEGORY_DB_MAP = {
    "cpu-coolers": "Cooling",
    "fans": "Fans & Accessories",
    "fan-controllers": "Fans & Accessories",
    "thermal-paste": "Fans & Accessories",
    "water-cooling": "Cooling",
    "accessories": "Fans & Accessories",
}


def parse_scorptec_listing(item: Tag, base_url: str) -> V2ListingSnapshot | None:
    name_element = item.select_one(".detail-product-title a")
    price_element = item.select_one(".detail-product-price")
    image_element = item.select_one(".detail-image-wrapper img")
    if not name_element or not price_element:
        return None

    href = name_element.get("href")
    if not href:
        return None

    product_name = name_element.get_text(strip=True)
    product_url = urljoin(base_url, href)

    image_src = None
    if image_element:
        image_src = image_element.get("data-src") or image_element.get("src")
    image_url = urljoin(base_url, image_src) if image_src else None

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
        raw_payload={"price_text": price_text, "source": "scorptec_v2"},
    )


class ScorptecV2Scraper(BaseScraper):
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Scorptec")
        ).scalar_one()
        self.base_url = "https://www.scorptec.com.au"
        self.scrape_run = start_scrape_run(
            self.db_session,
            retailer_id=self.retailer.id,
            scraper_name="scorptec_v2",
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
        soup = self.get_page_content(page_url, wait_for_selector="#product-list-detail-wrapper")
        if not soup:
            print(f"Failed to get content from {page_url}")
            return

        product_list = soup.select(".product-list-detail")
        if not product_list:
            print("No products found on this page.")
            return

        print(f"Found {len(product_list)} products in total for this category.")
        self.ingest_items(product_list, category)

    def ingest_items(self, items, category: Category):
        for item in items:
            if self.shutdown_event.is_set():
                break
            try:
                snapshot = parse_scorptec_listing(item, self.base_url)
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
        self.db_session.commit()

    def run(self):
        try:
            for category_name, main_category_url in CATEGORY_URL_MAP.items():
                if self.shutdown_event.is_set():
                    print("Shutdown signal received, stopping Scorptec v2 scraper.")
                    break

                print(f"\n{'='*20}\nStarting Scorptec v2 scrape for category: {category_name}\n{'='*20}")
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

                subcategory_links = soup.select(".grid-subcategory-title a")

                if category_name == "Cooling":
                    for link in subcategory_links:
                        if self.shutdown_event.is_set():
                            break

                        href = link.get("href")
                        if not href:
                            continue

                        subcategory_slug = href.rstrip("/").split("/")[-1]
                        db_category_name = SUBCATEGORY_DB_MAP.get(subcategory_slug, category_name)
                        final_category_obj = self.db_session.execute(
                            select(Category).where(Category.name == db_category_name)
                        ).scalar_one_or_none()
                        if not final_category_obj:
                            print(f"Mapped category '{db_category_name}' not found. Skipping {href}.")
                            continue

                        url = urljoin(self.base_url, href)
                        print(f"\n--- Navigating to sub-category: {url} (mapped to DB cat: {db_category_name}) ---")
                        self.scrape_products_from_page(url, final_category_obj)
                        time.sleep(1)
                else:
                    subcategory_urls = sorted(
                        {
                            urljoin(self.base_url, link.get("href"))
                            for link in subcategory_links
                            if link.get("href")
                        }
                    )
                    if not subcategory_urls:
                        print("No sub-categories found. Scraping main page directly.")
                        self.scrape_products_from_page(main_category_url, category_obj)
                        continue

                    print(f"Found {len(subcategory_urls)} sub-categories to scrape.")
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


def run_scorptec_v2_scraper(shutdown_event: threading.Event):
    from ..dependencies import SessionLocal

    print("Initializing DB session for Scorptec v2 scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = ScorptecV2Scraper(db_session, shutdown_event)
        scraper.run()
    except Exception as exc:
        print(f"\nAn error occurred during the Scorptec v2 scraping process: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

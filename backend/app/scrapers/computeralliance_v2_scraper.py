from urllib.parse import urljoin
import threading
import time

from bs4 import BeautifulSoup, Tag
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


SCRAPE_TASKS = [
    {"db_category": "CPUs", "url": "https://www.computeralliance.com.au/cpus"},
    {"db_category": "Motherboards", "url": "https://www.computeralliance.com.au/motherboards"},
    {"db_category": "Graphics Cards", "url": "https://www.computeralliance.com.au/graphics-cards"},
    {"db_category": "Memory (RAM)", "url": "https://www.computeralliance.com.au/desktop-ram"},
    {"db_category": "Memory (RAM)", "url": "https://www.computeralliance.com.au/laptop-ram"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.computeralliance.com.au/solid-state-drives"},
    {"db_category": "Storage (SSD/HDD)", "url": "https://www.computeralliance.com.au/hard-disk-drives"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/storage-accessories"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/thermal-paste"},
    {"db_category": "Cooling", "url": "https://www.computeralliance.com.au/cpu-cooling"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/fans"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/cooling-and-rgb-accessories"},
    {"db_category": "PC Cases", "url": "https://www.computeralliance.com.au/cases"},
    {"db_category": "Power Supplies", "url": "https://www.computeralliance.com.au/power-supply-units"},
    {"db_category": "Fans & Accessories", "url": "https://www.computeralliance.com.au/power-supply-accessories"},
    {"db_category": "Monitors", "url": "https://www.computeralliance.com.au/monitors"},
]


def parse_computeralliance_listing(item: Tag, base_url: str) -> V2ListingSnapshot | None:
    link_element = item.select_one("a[data-pjax]")
    if not link_element:
        return None

    name_element = link_element.select_one("h2.equalize")
    price_element = link_element.select_one(".price")
    image_element = link_element.select_one(".img-container img")
    if not name_element or not price_element:
        return None

    product_name = name_element.get_text(strip=True)
    href = link_element.get("href")
    if not href:
        return None

    product_url = urljoin(base_url, href)
    image_url = urljoin(base_url, image_element.get("src")) if image_element and image_element.get("src") else None

    price_text = price_element.get_text(strip=True)
    price_str = price_text.replace("$", "").replace(",", "").strip()

    price = None
    status = ProductStatus.UNAVAILABLE
    try:
        price = float(price_str)
        status = ProductStatus.AVAILABLE
    except (ValueError, TypeError):
        if "poa" not in price_text.lower():
            print(f"  Could not parse price '{price_text}' for {product_name}.")

    return V2ListingSnapshot(
        name=product_name,
        url=product_url,
        price=price,
        status=status,
        image_url=image_url,
        raw_payload={"price_text": price_text, "source": "computer_alliance_v2"},
    )


class ComputerAllianceV2Scraper(BaseScraper):
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Computer Alliance")
        ).scalar_one()
        self.base_url = "https://www.computeralliance.com.au"
        self.scrape_run = start_scrape_run(
            self.db_session,
            retailer_id=self.retailer.id,
            scraper_name="computer_alliance_v2",
            trigger_source="scraper",
        )
        self.seen_urls: set[str] = set()
        self.listings_seen = 0
        self.listings_created = 0
        self.listings_updated = 0

    def run(self):
        try:
            for task in SCRAPE_TASKS:
                if self.shutdown_event.is_set():
                    print("Shutdown signal received, stopping Computer Alliance v2 scraper.")
                    break

                category_name = task["db_category"]
                category_url = task["url"]
                print(f"\n{'='*20}\nStarting Computer Alliance v2 scrape for DB category: '{category_name}' ({category_url})\n{'='*20}")

                category_obj = self.db_session.execute(
                    select(Category).where(Category.name == category_name)
                ).scalar_one_or_none()
                if not category_obj:
                    print(f"Category '{category_name}' not found in the database. Skipping.")
                    continue

                soup = self.get_page_content(category_url, wait_for_selector="#PartsPage")
                if not soup:
                    print(f"Failed to get content for {category_url}. Skipping category.")
                    continue

                product_list = soup.select(".product")
                if not product_list:
                    print("No products found on this page.")
                    continue

                print(f"Found {len(product_list)} products on this page.")
                self.ingest_items(product_list, category_obj)
                time.sleep(2)

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

    def ingest_items(self, items, category: Category):
        for item in items:
            if self.shutdown_event.is_set():
                break
            try:
                snapshot = parse_computeralliance_listing(item, self.base_url)
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

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except OSError as exc:
                print(f"Ignoring non-critical error during driver shutdown: {exc}")


def run_computeralliance_v2_scraper(shutdown_event: threading.Event):
    from ..dependencies import SessionLocal

    print("Initializing DB session for Computer Alliance v2 scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = ComputerAllianceV2Scraper(db_session, shutdown_event)
        scraper.run()
    except Exception as exc:
        print(f"\nAn error occurred during the Computer Alliance v2 scraping process: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

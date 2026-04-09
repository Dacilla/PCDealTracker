from urllib.parse import urljoin
import re
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


def get_centrecom_next_page_url(soup, base_url: str, current_url: str) -> str | None:
    next_page_element = soup.select_one(".pager .next-page a")
    if not next_page_element or not next_page_element.get("href"):
        return None

    next_page_url = urljoin(base_url, next_page_element["href"])
    if next_page_url == current_url:
        return None
    return next_page_url


def parse_centrecom_listing(item: Tag, base_url: str) -> V2ListingSnapshot | None:
    name_element = item.select_one(".prbox_name")
    price_element = item.select_one(".saleprice")
    link_element = item.select_one("a.prbox_link")
    if not name_element or not price_element or not link_element:
        return None

    product_href = link_element.get("href")
    if not product_href:
        return None

    product_name = name_element.get_text(strip=True)
    product_url = urljoin(base_url, product_href)

    image_url = None
    style_attr = item.get("style")
    if style_attr:
        match = re.search(r'url\((?:&quot;|")?(.*?)(?:&quot;|")?\)', style_attr)
        if match:
            image_url = match.group(1)

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
        raw_payload={"price_text": price_text, "source": "centrecom_v2"},
    )


class CentreComV2Scraper(BaseScraper):
    def __init__(self, db_session: Session, shutdown_event: threading.Event):
        super().__init__(db_session, shutdown_event)
        self.retailer = self.db_session.execute(
            select(Retailer).where(Retailer.name == "Centre Com")
        ).scalar_one()
        self.base_url = "https://www.centrecom.com.au"
        self.scrape_run = start_scrape_run(
            self.db_session,
            retailer_id=self.retailer.id,
            scraper_name="centrecom_v2",
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
                    print("Shutdown signal received, stopping Centre Com v2 scraper.")
                    break

                category_name = task["db_category"]
                category_url = task["url"]
                print(f"\n{'='*20}\nStarting Centre Com v2 scrape for DB category: '{category_name}' ({category_url})\n{'='*20}")

                category_obj = self.db_session.execute(
                    select(Category).where(Category.name == category_name)
                ).scalar_one_or_none()
                if not category_obj:
                    print(f"Category '{category_name}' not found in the database. Skipping.")
                    continue

                current_url = category_url
                page_count = 0
                while current_url:
                    if self.shutdown_event.is_set():
                        break
                    page_count += 1
                    if page_count > self.max_pages:
                        self.record_category_error(f"Pagination limit reached for {category_url}")
                        break

                    print(f"Scraping page: {current_url}")
                    soup = self.get_page_content(current_url, wait_for_selector=".product-grid")
                    if not soup:
                        self.record_category_error(f"Failed to load {current_url}")
                        print(f"Failed to get content for {current_url}. Skipping category.")
                        break

                    product_list = soup.select(".product-grid .prbox_box")
                    if not product_list:
                        print("No products found on this page. Assuming end of category.")
                        break

                    print(f"Found {len(product_list)} products on this page.")
                    self.ingest_items(product_list, category_obj)

                    next_page_url = get_centrecom_next_page_url(soup, self.base_url, current_url)
                    if next_page_url:
                        current_url = next_page_url
                        time.sleep(2)
                    else:
                        print("No 'Next Page' link found. Finished with this category.")
                        current_url = None

                time.sleep(3)

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
                status=self.completed_status(),
                listings_seen=self.listings_seen,
                listings_created=self.listings_created,
                listings_updated=self.listings_updated,
                error_summary=self.error_summary(),
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
                error_summary=self.combine_error_summary(str(exc)),
            )
            self.db_session.commit()
            raise

    def ingest_items(self, items, category: Category):
        for item in items:
            if self.shutdown_event.is_set():
                break
            try:
                snapshot = parse_centrecom_listing(item, self.base_url)
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
                self.record_item_error(str(exc))
        self.db_session.commit()

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except OSError as exc:
                print(f"Ignoring non-critical error during driver shutdown: {exc}")


def run_centrecom_v2_scraper(shutdown_event: threading.Event):
    from ..dependencies import SessionLocal

    print("Initializing DB session for Centre Com v2 scraper...")
    db_session = SessionLocal()
    scraper = None
    try:
        scraper = CentreComV2Scraper(db_session, shutdown_event)
        scraper.run()
    except Exception as exc:
        print(f"\nAn error occurred during the Centre Com v2 scraping process: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        db_session.close()
        print("DB session closed.")

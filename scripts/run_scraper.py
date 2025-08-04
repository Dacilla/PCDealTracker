import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings
from scripts.init_database import setup_database
from backend.app.dependencies import SessionLocal
from backend.app.database import ScrapeLog
from scripts.merge_products import group_products_by_model
# Import the cache clearing utility
from backend.app.redis_client import clear_all_cache

# Import the individual scraper runner functions
from backend.app.scrapers.pccg_scraper import run_pccg_scraper
from backend.app.scrapers.scorptec_scraper import run_scorptec_scraper
from backend.app.scrapers.centrecom_scraper import run_centrecom_scraper
from backend.app.scrapers.msy_scraper import run_msy_scraper
from backend.app.scrapers.umart_scraper import run_umart_scraper
from backend.app.scrapers.computeralliance_scraper import run_computeralliance_scraper
from backend.app.scrapers.jw_scraper import run_jw_scraper
from backend.app.scrapers.shoppingexpress_scraper import run_shoppingexpress_scraper
# from backend.app.scrapers.austin_scraper import run_austin_scraper # Temporarily disabled

# A list of all scraper functions to be executed
ALL_SCRAPERS = [
    run_pccg_scraper,
    run_scorptec_scraper,
    run_centrecom_scraper,
    run_msy_scraper,
    run_umart_scraper,
    run_computeralliance_scraper,
    run_jw_scraper,
    run_shoppingexpress_scraper,
    # run_austin_scraper,
]

def main():
    """
    Initializes the database, runs all scrapers, merges products,
    and finally clears the cache.
    """
    # --- Step 1: Initialize the database ---
    print("--- Initializing Database ---")
    setup_database()
    print("--- Database Initialization Complete ---")

    print("\n--- Starting All Scrapers Concurrently ---")

    max_workers = settings.max_concurrent_scrapers
    shutdown_event = threading.Event()
    db_session = SessionLocal()
    print(f"Max concurrent scrapers set to: {max_workers}")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_scraper = {}
            for scraper_func in ALL_SCRAPERS:
                scraper_name = scraper_func.__name__
                start_log = ScrapeLog(status="STARTED", details=f"Starting scraper: {scraper_name}")
                db_session.add(start_log)
                db_session.commit()

                future = executor.submit(scraper_func, shutdown_event)
                future_to_scraper[future] = scraper_name
                print(f"-> Submitted {scraper_name} to the queue.")
                time.sleep(5)

            print("\n--- All scrapers submitted. Waiting for completion... ---")

            for future in as_completed(future_to_scraper):
                scraper_name = future_to_scraper[future]
                status = "SUCCESS"
                details = f"{scraper_name} completed successfully."
                try:
                    future.result()
                    print(f"\n--- {scraper_name} Finished Successfully ---")
                except Exception as exc:
                    status = "FAILURE"
                    details = f"{scraper_name} failed with exception: {exc}"
                    print(f"\n--- {scraper_name} Generated an Exception: {exc} ---")

                end_log = ScrapeLog(status=status, details=details)
                db_session.add(end_log)
                db_session.commit()

    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt received. Signaling scrapers to shut down...")
        shutdown_event.set()
        shutdown_log = ScrapeLog(status="SHUTDOWN", details="Scraping process terminated by user.")
        db_session.add(shutdown_log)
        db_session.commit()

    finally:
        db_session.close()
        print("\n--- All Scrapers Have Completed Their Execution ---")
    
    if not shutdown_event.is_set():
        # --- Step 2: Run the product merging script ---
        group_products_by_model()
        # --- Step 3: Clear the cache to reflect the new data ---
        clear_all_cache()


if __name__ == "__main__":
    main()

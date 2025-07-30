import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to the Python path to allow for correct imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings
# Import the database setup function
from scripts.init_database import setup_database
# Import the individual scraper runner functions
from backend.app.scrapers.pccg_scraper import run_pccg_scraper
from backend.app.scrapers.scorptec_scraper import run_scorptec_scraper
from backend.app.scrapers.centrecom_scraper import run_centrecom_scraper
from backend.app.scrapers.msy_scraper import run_msy_scraper
from backend.app.scrapers.umart_scraper import run_umart_scraper
from backend.app.scrapers.computeralliance_scraper import run_computeralliance_scraper
from backend.app.scrapers.jw_scraper import run_jw_scraper

# A list of all scraper functions to be executed
ALL_SCRAPERS = [
    run_pccg_scraper,
    run_scorptec_scraper,
    run_centrecom_scraper,
    run_msy_scraper,
    run_umart_scraper,
    run_computeralliance_scraper,
    run_jw_scraper,
]

def main():
    """
    Initializes the database and then runs all scrapers concurrently using a thread pool.
    The launch of each scraper is staggered to avoid resource spikes.
    Handles KeyboardInterrupt for graceful shutdown.
    """
    # --- Step 1: Initialize the database before starting any scrapers ---
    print("--- Initializing Database ---")
    setup_database()
    print("--- Database Initialization Complete ---")

    print("\n--- Starting All Scrapers Concurrently ---")
    
    max_workers = settings.max_concurrent_scrapers
    shutdown_event = threading.Event()
    print(f"Max concurrent scrapers set to: {max_workers}")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_scraper = {}
            for scraper_func in ALL_SCRAPERS:
                # Submit the scraper to the thread pool, passing the shutdown event
                future = executor.submit(scraper_func, shutdown_event)
                future_to_scraper[future] = scraper_func.__name__
                print(f"-> Submitted {scraper_func.__name__} to the queue.")
                # Stagger the launch of the next scraper
                time.sleep(5) 
            
            print("\n--- All scrapers submitted. Waiting for completion... ---")
            
            for future in as_completed(future_to_scraper):
                scraper_name = future_to_scraper[future]
                try:
                    future.result()
                    print(f"\n--- {scraper_name} Finished Successfully ---")
                except Exception as exc:
                    print(f"\n--- {scraper_name} Generated an Exception: {exc} ---")

    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt received. Signaling scrapers to shut down...")
        shutdown_event.set()

    finally:
        print("\n--- All Scrapers Have Completed Their Execution ---")


if __name__ == "__main__":
    main()

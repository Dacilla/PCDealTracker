import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to the Python path.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings
from backend.app.redis_client import clear_all_cache
from backend.app.scrapers.centrecom_v2_scraper import run_centrecom_v2_scraper
from backend.app.scrapers.computeralliance_v2_scraper import run_computeralliance_v2_scraper
from backend.app.scrapers.jw_v2_scraper import run_jw_v2_scraper
from backend.app.scrapers.msy_v2_scraper import run_msy_v2_scraper
from backend.app.scrapers.pccg_v2_scraper import run_pccg_v2_scraper
from backend.app.scrapers.scorptec_v2_scraper import run_scorptec_v2_scraper
from backend.app.scrapers.shoppingexpress_v2_scraper import run_shoppingexpress_v2_scraper
from backend.app.scrapers.umart_v2_scraper import run_umart_v2_scraper
from scripts.init_database import setup_database


NATIVE_V2_SCRAPERS = [
    run_computeralliance_v2_scraper,
    run_shoppingexpress_v2_scraper,
    run_scorptec_v2_scraper,
    run_jw_v2_scraper,
    run_centrecom_v2_scraper,
    run_umart_v2_scraper,
    run_msy_v2_scraper,
    run_pccg_v2_scraper,
]

SCRAPER_BY_RETAILER = {
    "centrecom": run_centrecom_v2_scraper,
    "computeralliance": run_computeralliance_v2_scraper,
    "jw": run_jw_v2_scraper,
    "msy": run_msy_v2_scraper,
    "pccg": run_pccg_v2_scraper,
    "scorptec": run_scorptec_v2_scraper,
    "shoppingexpress": run_shoppingexpress_v2_scraper,
    "umart": run_umart_v2_scraper,
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the native v2 PCDealTracker scrapers.")
    parser.add_argument(
        "--retailer",
        action="append",
        choices=sorted(SCRAPER_BY_RETAILER),
        help="Run only the selected retailer scraper. Repeat the flag to run multiple retailers.",
    )
    return parser


def run_scraper_batch(shutdown_event: threading.Event, scraper_funcs, *, batch_label: str) -> None:
    if not scraper_funcs:
        print(f"\n--- No scrapers configured for batch: {batch_label} ---")
        return

    max_workers = settings.max_concurrent_scrapers
    print(f"\n--- Starting {batch_label} Concurrently ---")
    print(f"Max concurrent scrapers set to: {max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_scraper = {}
        for scraper_func in scraper_funcs:
            scraper_name = scraper_func.__name__
            future = executor.submit(scraper_func, shutdown_event)
            future_to_scraper[future] = scraper_name
            print(f"-> Submitted {scraper_name} to the queue.")
            time.sleep(2)

        print(f"\n--- All {batch_label} submitted. Waiting for completion... ---")

        for future in as_completed(future_to_scraper):
            scraper_name = future_to_scraper[future]
            try:
                future.result()
                print(f"\n--- {scraper_name} Finished Successfully ---")
            except Exception as exc:
                print(f"\n--- {scraper_name} Generated an Exception: {exc} ---")


def run_native_v2_pipeline(
    shutdown_event: threading.Event | None = None,
    *,
    scraper_funcs=None,
) -> None:
    active_shutdown_event = shutdown_event or threading.Event()
    selected_scrapers = scraper_funcs or NATIVE_V2_SCRAPERS

    try:
        print("--- Initializing Database ---")
        setup_database()
        print("--- Database Initialization Complete ---")
        run_scraper_batch(active_shutdown_event, selected_scrapers, batch_label="Native V2 Scrapers")
    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt received. Signaling scrapers to shut down...")
        active_shutdown_event.set()
    finally:
        print("\n--- Scrape Pipeline Execution Complete ---")

    if not active_shutdown_event.is_set():
        clear_all_cache()


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    shutdown_event = threading.Event()
    scraper_funcs = NATIVE_V2_SCRAPERS
    if args.retailer:
        scraper_funcs = [SCRAPER_BY_RETAILER[retailer] for retailer in args.retailer]

    run_native_v2_pipeline(shutdown_event, scraper_funcs=scraper_funcs)


if __name__ == "__main__":
    main()

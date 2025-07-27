import os
import sys

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.scrapers.pccg_scraper import run_pccg_scraper

if __name__ == "__main__":
    print("--- Starting PC Case Gear Scraper ---")
    run_pccg_scraper()
    print("\n--- Scraper Finished ---")

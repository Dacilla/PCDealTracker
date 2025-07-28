import os
import sys

# Add the project root to the Python path to allow for correct imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the individual scraper runner functions
from backend.app.scrapers.pccg_scraper import run_pccg_scraper
from backend.app.scrapers.scorptec_scraper import run_scorptec_scraper
from backend.app.scrapers.centrecom_scraper import run_centrecom_scraper

if __name__ == "__main__":
    print("--- Starting All Scrapers Sequentially ---")
    
    # --- Run PC Case Gear Scraper (Commented out for testing) ---
    try:
        print("\n--- Running PC Case Gear Scraper ---")
        run_pccg_scraper()
        print("\n--- PC Case Gear Scraper Finished ---")
    except Exception as e:
        print(f"\n--- PC Case Gear Scraper Failed: {e} ---")

    # --- Run Scorptec Scraper (Commented out for testing) ---
    try:
        print("\n--- Running Scorptec Scraper ---")
        run_scorptec_scraper()
        print("\n--- Scorptec Scraper Finished ---")
    except Exception as e:
        print(f"\n--- Scorptec Scraper Failed: {e} ---")

    # --- Run Centre Com Scraper ---
    try:
        print("\n--- Running Centre Com Scraper ---")
        run_centrecom_scraper()
        print("\n--- Centre Com Scraper Finished ---")
    except Exception as e:
        print(f"\n--- Centre Com Scraper Failed: {e} ---")
    
    print("\n--- All Scrapers Finished ---")

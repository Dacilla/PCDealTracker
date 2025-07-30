import os
import sys
import time
import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

# Add the project root to the Python path to allow for correct imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings
from scripts.run_scraper import main as run_all_scrapers

def scheduled_job():
    """The job that will be executed by the scheduler."""
    print(f"--- SCHEDULER: Starting scheduled scrape run at {time.ctime()} ---")
    try:
        run_all_scrapers()
        print(f"--- SCHEDULER: Scrape run finished successfully at {time.ctime()} ---")
    except Exception as e:
        print(f"--- SCHEDULER: An error occurred during the scheduled scrape run: {e} ---")

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    
    # Get the interval from the settings
    scrape_interval = settings.scrape_interval_hours
    
    print(f"--- Scheduler starting up ---")
    print(f"Scrapers will run every {scrape_interval} hours.")
    
    # Schedule the job to run immediately, and then at the specified interval
    scheduler.add_job(scheduled_job, 'interval', hours=scrape_interval, next_run_time=datetime.datetime.now())
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("--- Scheduler shutting down ---")
        scheduler.shutdown()

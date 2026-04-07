import os
import sys
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.dependencies import SessionLocal
from backend.app.services.v2_catalog import NATIVE_V2_RETAILER_NAMES, rebuild_v2_catalog_from_legacy


def main():
    parser = argparse.ArgumentParser(description="Backfill the persisted v2 catalog from legacy product data.")
    parser.add_argument(
        "--include-native-v2",
        action="store_true",
        help="Include retailers that already have native v2 ingestion paths.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        excluded_names = () if args.include_native_v2 else NATIVE_V2_RETAILER_NAMES
        scrape_run = rebuild_v2_catalog_from_legacy(
            db,
            clear_existing=True,
            exclude_retailer_names=excluded_names,
        )
        exclusion_note = "including native-v2 retailers" if args.include_native_v2 else f"excluding native-v2 retailers: {', '.join(excluded_names)}"
        print(
            f"V2 backfill complete. Scrape run {scrape_run.id} migrated "
            f"{scrape_run.listings_created} listings ({exclusion_note})."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

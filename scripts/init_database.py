import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import Base, Category, Retailer
from backend.app.config import settings


def build_engine(database_url: str | None = None):
    resolved_database_url = database_url or settings.database_url
    engine_kwargs = {}
    if resolved_database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(resolved_database_url, **engine_kwargs)


def build_session_factory(database_url: str | None = None):
    engine = build_engine(database_url)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine), engine


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_reference_tables(database_url: str | None = None) -> None:
    engine = build_engine(database_url)
    try:
        Base.metadata.create_all(bind=engine, tables=[Retailer.__table__, Category.__table__])
    finally:
        engine.dispose()


def run_migrations(database_url: str | None = None) -> None:
    resolved_database_url = database_url or settings.database_url
    alembic_cfg = Config(str(_project_root() / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", resolved_database_url)
    command.upgrade(alembic_cfg, "head")


def seed_reference_data(database_url: str | None = None) -> None:
    SessionLocal, engine = build_session_factory(database_url)
    db = SessionLocal()
    try:
        # --- Populate Retailers with local logo paths ---
        retailers = [
            {"name": "PC Case Gear", "url": "https://www.pccasegear.com", "logo_url": "assets/logos/pccg.png"},
            {"name": "Scorptec", "url": "https://www.scorptec.com.au", "logo_url": "assets/logos/scorptec.png"},
            {"name": "Centre Com", "url": "https://www.centrecom.com.au", "logo_url": None},
            {"name": "MSY Technology", "url": "https://www.msy.com.au", "logo_url": "assets/logos/msy.png"},
            {"name": "Umart", "url": "https://www.umart.com.au", "logo_url": "assets/logos/umart.png"},
            {"name": "Computer Alliance", "url": "https://www.computeralliance.com.au", "logo_url": "assets/logos/computeralliance.png"},
            {"name": "JW Computers", "url": "https://www.jw.com.au", "logo_url": "assets/logos/jw.png"},
            {"name": "Shopping Express", "url": "https://www.shoppingexpress.com.au", "logo_url": "assets/logos/shoppingexpress.png"},
        ]
        
        for retailer_data in retailers:
            # This will update existing retailers with the new logo_url if they already exist
            existing_retailer = db.execute(select(Retailer).where(Retailer.name == retailer_data["name"])).scalar_one_or_none()
            if existing_retailer:
                existing_retailer.logo_url = retailer_data["logo_url"]
            else:
                db.add(Retailer(**retailer_data))

        # --- Populate Categories ---
        categories = [
            "Graphics Cards", "CPUs", "Motherboards", "Memory (RAM)", 
            "Storage (SSD/HDD)", "Power Supplies", "PC Cases", "Monitors",
            "Cooling", "Fans & Accessories"
        ]
        for category_name in categories:
            exists = db.execute(select(Category).where(Category.name == category_name)).scalar_one_or_none()
            if not exists:
                db.add(Category(name=category_name))

        db.commit()
    finally:
        db.close()
        engine.dispose()


def setup_database(database_url: str | None = None):
    """
    Bootstraps reference tables, applies Alembic migrations, and seeds retailers/categories.
    """
    ensure_reference_tables(database_url)
    run_migrations(database_url)
    seed_reference_data(database_url)

if __name__ == "__main__":
    print("Setting up the database...")
    setup_database()
    print("Database setup complete.")

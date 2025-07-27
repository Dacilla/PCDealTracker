from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Correctly import the 'settings' object, not a function.
from .config import settings

# --- Database Connection Setup ---
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    FastAPI Dependency to get a DB session.
    This will be called for each API request. It creates a new session,
    provides it to the request, and ensures it's closed afterward.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

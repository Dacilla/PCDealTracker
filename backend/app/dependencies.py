from fastapi import Header, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings


engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency that provides a database session per request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_review_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if x_api_key != settings.review_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")
    return x_api_key

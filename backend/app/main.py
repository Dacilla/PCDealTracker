from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import products, deals, price_history
from app.database import engine, Base
from app.config import settings

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PCDealTracker API",
    description="Australian PC hardware price tracking API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(products.router, prefix="/api/v1", tags=["products"])
app.include_router(deals.router, prefix="/api/v1", tags=["deals"])
app.include_router(price_history.router, prefix="/api/v1", tags=["price-history"])

@app.get("/")
async def root():
    return {"message": "PCDealTracker API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
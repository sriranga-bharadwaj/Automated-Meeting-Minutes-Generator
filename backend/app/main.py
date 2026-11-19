import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_v1 import router as api_v1_router
from app.database import Base, engine, ensure_schema

logger = logging.getLogger(__name__)

AUDIO_UPLOAD_DIR = Path("uploads/audio")
AUDIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_AUDIO_SIZE = 25 * 1024 * 1024

Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(
    title="Automated Meeting Minutes Generator",
    description="API for generating structured meeting minutes from audio.",
    version="1.0.0",
)

# CORS middleware for dev server access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Consolidated /api/v1 router
app.include_router(api_v1_router)


@app.get("/")
def root():
    return {
        "message": "Automated Meeting Minutes Generator API is running",
        "status": "healthy",
        "version": "1.0.0",
        "docs": "/docs",
        "api_v1": "/api/v1",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}

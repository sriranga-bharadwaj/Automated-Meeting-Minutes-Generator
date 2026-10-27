
from fastapi import FastAPI

app = FastAPI(
    title="Automated Meeting Minutes Generator",
    description="API for generating structured meeting minutes from audio.",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Automated Meeting Minutes Generator API is running",
        "status": "healthy",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}

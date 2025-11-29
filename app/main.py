import uvicorn
from fastapi import FastAPI
from app.db import engine
from app import models
from app.routes.policy_versions import router as policy_versions_router
from app.routes.catalog import router as catalog_router
from app.routes.chat import router as chat_router
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
# Create all tables if not already created (optional if using Alembic)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Insurance Policy Bot API")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# serve /static/* (css/js if you add later)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# serve the SPA at /
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")

app.include_router(policy_versions_router)
app.include_router(catalog_router)
app.include_router(chat_router)

@app.get("/")
def read_root():
    return {"message": "Insurance Policy Bot API is running"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
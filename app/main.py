"""FastAPI Application Entrypoint."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.core.config import settings
from app.db.connection import init_db
from app.api.routes import router, sync_retriever

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database and In-memory indexes
    init_db()
    sync_retriever()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Serve UI if ui directory exists
UI_DIR = os.path.join(os.path.dirname(__file__), "..", "ui")

if os.path.exists(UI_DIR):
    @app.get("/")
    def serve_index():
        # Serves the full-viewport video hero landing page
        return FileResponse(os.path.join(UI_DIR, "index.html"))

    @app.get("/app")
    def serve_app():
        # Serves the full Fintrix intelligence app (Chat, Summary, Vault, Traces, Evals)
        return FileResponse(os.path.join(UI_DIR, "app.html"))

    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)

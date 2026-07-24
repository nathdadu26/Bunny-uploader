from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.database import ensure_indexes
from app.core.scheduler import start_scheduler, scheduler
from app.core.keepalive import register_keepalive_job
from app.routes import upload, files, overview, settings as settings_routes, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    start_scheduler()
    register_keepalive_job(scheduler)
    yield


app = FastAPI(title="Bunny Stream -> R2 -> MongoDB -> Telegram", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(upload.router)
app.include_router(files.router)
app.include_router(overview.router)
app.include_router(settings_routes.router)
app.include_router(dashboard.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard/overview")


@app.get("/api/health")
async def health():
    return {"ok": True}

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.detection_runner import reconcile_interrupted_jobs
from app.events import close_dangling_sessions, event_recorder
from app.routers import (
    analytics,
    auth,
    cameras,
    devices,
    events,
    jobs,
    lines,
    locations,
    members,
    organizations,
    subscription,
    tracking,
    zones,
)
from app.tracking import tracking_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    reconcile_interrupted_jobs()
    # Sessions a crash left "running" get closed, so past uptime isn't overstated.
    close_dangling_sessions()
    yield
    # In this order: stopping sessions emits their final events and heat, and the recorder
    # then drains them to the database before the process exits.
    tracking_manager.stop_all()
    event_recorder.stop()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # localhost:1420 is Vite's dev server; tauri.localhost is where a packaged Tauri
    # window's frontend actually loads from (Phase 16). Both are the same single
    # installed app talking to its own loopback-only backend, never a third party, so
    # listing both permanently is safe rather than branching on a build flag.
    allow_origins=["http://localhost:1420", "http://tauri.localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets the desktop app read how the historical heatmap was drawn.
    expose_headers=["X-Heatmap-Background", "X-Heatmap-Samples"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(locations.router)
app.include_router(members.router)
app.include_router(subscription.router)
app.include_router(devices.router)
app.include_router(jobs.router)
app.include_router(cameras.router)
app.include_router(tracking.router)
app.include_router(lines.router)
app.include_router(zones.router)
app.include_router(events.router)
app.include_router(analytics.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok"}

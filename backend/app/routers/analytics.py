from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import analytics, camera_testing
from app.auth import OrgContext, get_org_context
from app.database import get_db
from app.heatmap import render_heat
from app.routers.cameras import _camera_ids_for_org, _decrypted_credentials, _get_camera_or_404
from app.routers.events import as_utc
from app.schemas import AnalyticsSummaryRead, HeatmapInfoRead, TimeseriesRead

router = APIRouter(prefix="/analytics", tags=["analytics"])

NEUTRAL_BACKGROUND_GREY = 40


def _resolve_range(since: datetime, until: Optional[datetime]) -> tuple[datetime, datetime, datetime]:
    now = analytics.utcnow()
    since, until = as_utc(since), as_utc(until) if until is not None else now
    if since >= until:
        raise HTTPException(status_code=422, detail="'since' must be earlier than 'until'")
    return since, until, now


def _resolve_camera_ids(db: Session, ctx: OrgContext, camera_id: Optional[str]) -> list:
    """One camera (already checked to be in the caller's organization), or every camera
    in it — never unscoped."""
    if camera_id is not None:
        return [_get_camera_or_404(db, ctx, camera_id).id]
    return _camera_ids_for_org(db, ctx)


@router.get("/summary", response_model=AnalyticsSummaryRead)
def get_summary(
    since: datetime,
    until: Optional[datetime] = None,
    camera_id: Optional[str] = None,
    ctx: OrgContext = Depends(get_org_context),
    db: Session = Depends(get_db),
):
    """Totals for [since, until) — `until` defaults to now — for one camera or all of them."""
    since, until, now = _resolve_range(since, until)
    camera_ids = _resolve_camera_ids(db, ctx, camera_id)
    return analytics.summary(db, camera_ids, since, until, now)


@router.get("/timeseries", response_model=TimeseriesRead)
def get_timeseries(
    since: datetime,
    until: Optional[datetime] = None,
    camera_id: Optional[str] = None,
    bucket: str = Query(default="hour", pattern="^(hour|day)$"),
    tz: str = Query(default="UTC", max_length=64),
    ctx: OrgContext = Depends(get_org_context),
    db: Session = Depends(get_db),
):
    """Zero-filled buckets in the given IANA time zone, each with `tracked_seconds` so a
    chart can tell "not running" from "no traffic"."""
    since, until, now = _resolve_range(since, until)
    camera_ids = _resolve_camera_ids(db, ctx, camera_id)
    try:
        return analytics.timeseries(db, camera_ids, since, until, bucket, tz, now)
    except analytics.AnalyticsInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/heatmap/info", response_model=HeatmapInfoRead)
def get_heatmap_info(
    camera_id: str,
    since: datetime,
    until: Optional[datetime] = None,
    ctx: OrgContext = Depends(get_org_context),
    db: Session = Depends(get_db),
):
    since, until, _now = _resolve_range(since, until)
    camera = _get_camera_or_404(db, ctx, camera_id)
    heat = analytics.heat_sum(db, camera.id, since, until)
    if heat is None:
        return HeatmapInfoRead(camera_id=camera.id, available=False)
    return HeatmapInfoRead(
        camera_id=camera.id,
        available=True,
        samples=heat.samples,
        frame_width=heat.frame_width,
        frame_height=heat.frame_height,
        grid_width=heat.grid.shape[1],
        grid_height=heat.grid.shape[0],
        first_period=heat.first_period,
        last_period=heat.last_period,
        ignored_samples=heat.ignored_samples,
    )


@router.get("/heatmap")
def get_heatmap(
    camera_id: str,
    since: datetime,
    until: Optional[datetime] = None,
    ctx: OrgContext = Depends(get_org_context),
    db: Session = Depends(get_db),
):
    """A JPEG of the camera's stored heat over the range, drawn over a fresh snapshot when
    the camera answers, or over a neutral background when it doesn't. No video frame is
    ever stored: the picture underneath is fetched now, or is plain grey."""
    since, until, _now = _resolve_range(since, until)
    camera = _get_camera_or_404(db, ctx, camera_id)
    heat = analytics.heat_sum(db, camera.id, since, until)
    if heat is None:
        raise HTTPException(status_code=404, detail="No heatmap was recorded for this camera in that period")

    username, password = _decrypted_credentials(camera)
    snapshot = camera_testing.grab_snapshot(camera.rtsp_url, username, password)
    if snapshot.frame is not None:
        background, background_kind = snapshot.frame, "snapshot"
    else:
        background = np.full((heat.frame_height, heat.frame_width, 3), NEUTRAL_BACKGROUND_GREY, dtype=np.uint8)
        background_kind = "neutral"

    ok, encoded = cv2.imencode(".jpg", render_heat(background, heat.grid))
    if not ok:
        raise HTTPException(status_code=503, detail="Failed to encode the heatmap")
    return Response(
        content=encoded.tobytes(),
        media_type="image/jpeg",
        headers={"X-Heatmap-Background": background_kind, "X-Heatmap-Samples": str(heat.samples)},
    )

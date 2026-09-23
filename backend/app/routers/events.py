import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.auth import OrgContext, get_org_context
from app.database import get_db
from app.models import Camera, Event, Location
from app.routers.cameras import _get_camera_or_404
from app.schemas import EventListRead, EventRead, EventTypeName

router = APIRouter(tags=["events"])


def as_utc(moment: Optional[datetime]) -> Optional[datetime]:
    """A timestamp without a zone is taken to be UTC rather than guessed at."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _encode_cursor(event: Event) -> str:
    return f"{event.occurred_at.isoformat()}|{event.id}"


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        occurred_at, event_id = cursor.rsplit("|", 1)
        return as_utc(datetime.fromisoformat(occurred_at)), uuid.UUID(event_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid 'before' cursor")


@router.get("/events", response_model=EventListRead)
def list_events(
    camera_id: Optional[str] = None,
    event_type: Optional[list[EventTypeName]] = Query(default=None),
    category: Optional[str] = Query(default=None, max_length=16),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=500),
    before: Optional[str] = None,
    ctx: OrgContext = Depends(get_org_context),
    db: Session = Depends(get_db),
):
    """Newest first. `since` is inclusive, `until` exclusive. `event_type` may be given
    more than once to match any of several types. Page backwards by passing the previous
    response's `next_before` as `before` (stable even while new events arrive)."""
    # Always scoped to the caller's organization, whether or not a specific camera was
    # asked for — Location.organization_id == ctx.organization.id is never omitted.
    filters = [Location.organization_id == ctx.organization.id]
    if camera_id is not None:
        filters.append(Event.camera_id == _get_camera_or_404(db, ctx, camera_id).id)
    if event_type:
        filters.append(Event.event_type.in_([t.value for t in event_type]))
    if category is not None:
        filters.append(Event.category == category)
    if since is not None:
        filters.append(Event.occurred_at >= as_utc(since))
    if until is not None:
        filters.append(Event.occurred_at < as_utc(until))
    if before is not None:
        cursor_at, cursor_id = _decode_cursor(before)
        filters.append(tuple_(Event.occurred_at, Event.id) < tuple_(cursor_at, cursor_id))

    # One extra row tells us whether there is another page without a second query.
    rows = db.execute(
        select(Event, Camera.name)
        .join(Camera, Camera.id == Event.camera_id)
        .join(Location, Camera.location_id == Location.id)
        .where(*filters)
        .order_by(Event.occurred_at.desc(), Event.id.desc())
        .limit(limit + 1)
    ).all()

    page = rows[:limit]
    events = [
        EventRead(
            id=event.id,
            camera_id=event.camera_id,
            camera_name=camera_name,
            occurred_at=event.occurred_at,
            event_type=event.event_type,
            category=event.category,
            direction=event.direction,
            subject_id=event.subject_id,
            subject_name=event.subject_name,
            value=event.value,
            detail=event.detail,
        )
        for event, camera_name in page
    ]
    next_before = _encode_cursor(page[-1][0]) if len(rows) > limit else None
    return EventListRead(events=events, next_before=next_before)

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Line
from app.routers.cameras import _get_camera_or_404
from app.schemas import LineCreate, LineRead

router = APIRouter(tags=["lines"])


def _get_line_or_404(db: Session, line_id: str) -> Line:
    try:
        parsed_id = uuid.UUID(line_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Line not found")
    line = db.get(Line, parsed_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Line not found")
    return line


@router.post("/cameras/{camera_id}/lines", response_model=LineRead)
def create_line(camera_id: str, request: LineCreate, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    line = Line(
        camera_id=camera.id,
        name=request.name,
        x1=request.x1,
        y1=request.y1,
        x2=request.x2,
        y2=request.y2,
    )
    db.add(line)
    db.commit()
    return line


@router.get("/cameras/{camera_id}/lines", response_model=list[LineRead])
def list_lines(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    return db.scalars(select(Line).where(Line.camera_id == camera.id).order_by(Line.created_at)).all()


@router.delete("/lines/{line_id}", status_code=204)
def delete_line(line_id: str, db: Session = Depends(get_db)):
    line = _get_line_or_404(db, line_id)
    db.delete(line)
    db.commit()
    return Response(status_code=204)

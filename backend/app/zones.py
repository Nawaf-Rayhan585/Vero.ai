"""Custom-zone geometry. Pure geometry, no video/model dependency — independently
testable with synthetic coordinates, same philosophy as `counting.classify_crossing`.

A zone is a polygon of 3+ points. Self-intersecting (bow-tie) polygons are accepted and
follow the even-odd rule, so the "twisted" halves count as inside.
"""
import uuid
from dataclasses import dataclass

from app.counting import Point, _on_segment, _orientation


@dataclass(frozen=True)
class ZoneConfig:
    """A zone as loaded from the DB: normalized 0.0-1.0 coordinates."""

    id: uuid.UUID
    name: str
    points: tuple[Point, ...]

    def to_pixels(self, width: int, height: int) -> "ResolvedZone":
        return ResolvedZone(
            id=self.id,
            name=self.name,
            polygon=tuple(Point(p.x * width, p.y * height) for p in self.points),
        )


@dataclass(frozen=True)
class ResolvedZone:
    """A ZoneConfig converted to the pixel space of a specific frame size."""

    id: uuid.UUID
    name: str
    polygon: tuple[Point, ...]


def point_in_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    """Even-odd ray casting. A point exactly on an edge or vertex counts as inside."""
    inside = False
    for i in range(len(polygon)):
        a, b = polygon[i], polygon[(i + 1) % len(polygon)]
        if _orientation(a, b, point) == 0 and _on_segment(a, b, point):
            return True
        if (a.y > point.y) != (b.y > point.y):
            x_at_point_y = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if point.x < x_at_point_y:
                inside = not inside
    return inside

"""Entry/exit line-crossing detection. Pure geometry, no video/model dependency —
independently testable with synthetic coordinates, same philosophy as
`tracking.should_give_up`.
"""
import uuid
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class LineConfig:
    """A line as loaded from the DB: normalized 0.0-1.0 coordinates."""

    id: uuid.UUID
    name: str
    x1: float
    y1: float
    x2: float
    y2: float

    def to_pixels(self, width: int, height: int) -> "ResolvedLine":
        return ResolvedLine(
            id=self.id,
            name=self.name,
            line=Line(self.x1 * width, self.y1 * height, self.x2 * width, self.y2 * height),
        )


@dataclass(frozen=True)
class ResolvedLine:
    """A LineConfig converted to the pixel space of a specific frame size."""

    id: uuid.UUID
    name: str
    line: Line


def _orientation(a: Point, b: Point, c: Point) -> float:
    """Cross product sign: >0 if c is left of the directed line a->b, <0 if right, 0 if on it."""
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return min(a.x, b.x) <= p.x <= max(a.x, b.x) and min(a.y, b.y) <= p.y <= max(a.y, b.y)


def _segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    d1, d2 = _orientation(p3, p4, p1), _orientation(p3, p4, p2)
    d3, d4 = _orientation(p1, p2, p3), _orientation(p1, p2, p4)

    if d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0 and ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    if d1 == 0 and _on_segment(p3, p4, p1):
        return True
    if d2 == 0 and _on_segment(p3, p4, p2):
        return True
    if d3 == 0 and _on_segment(p1, p2, p3):
        return True
    if d4 == 0 and _on_segment(p1, p2, p4):
        return True
    return False


def classify_crossing(line: Line, prev: Point, curr: Point) -> Optional[Literal["in", "out"]]:
    """Did the movement from prev to curr cross the finite segment `line`?

    "in" = crossed to the line's left side as seen walking from (x1,y1) to (x2,y2),
    "out" = crossed to its right. A camera's line-drawing UI controls which physical
    direction that means by the order the two points were placed.
    """
    line_start, line_end = Point(line.x1, line.y1), Point(line.x2, line.y2)
    prev_side = _orientation(line_start, line_end, prev)
    curr_side = _orientation(line_start, line_end, curr)

    if prev_side == 0 or curr_side == 0 or (prev_side > 0) == (curr_side > 0):
        return None
    if not _segments_intersect(prev, curr, line_start, line_end):
        return None
    return "in" if curr_side > 0 else "out"

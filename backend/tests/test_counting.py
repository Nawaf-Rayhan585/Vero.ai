import uuid

from app.counting import Line, LineConfig, Point, classify_crossing

HORIZONTAL = Line(x1=0, y1=50, x2=100, y2=50)


def test_moving_downward_across_a_horizontal_line_is_in():
    assert classify_crossing(HORIZONTAL, Point(50, 40), Point(50, 60)) == "in"


def test_moving_upward_across_the_same_line_is_out():
    assert classify_crossing(HORIZONTAL, Point(50, 60), Point(50, 40)) == "out"


def test_staying_on_the_same_side_does_not_cross():
    assert classify_crossing(HORIZONTAL, Point(50, 10), Point(50, 30)) is None
    assert classify_crossing(HORIZONTAL, Point(50, 60), Point(50, 80)) is None


def test_crossing_the_lines_infinite_extension_outside_the_finite_segment_does_not_count():
    # Same y-crossing as the "in" case above, but x=150 is outside the segment's [0,100].
    assert classify_crossing(HORIZONTAL, Point(150, 40), Point(150, 60)) is None


def test_landing_exactly_on_the_line_is_not_classified():
    # Ambiguous — treated as no-crossing this frame rather than guessing a direction.
    assert classify_crossing(HORIZONTAL, Point(50, 40), Point(50, 50)) is None
    assert classify_crossing(HORIZONTAL, Point(50, 50), Point(50, 60)) is None


def test_diagonal_line_crossing():
    diagonal = Line(x1=0, y1=0, x2=100, y2=100)
    # A point moving from above-left of the diagonal to below-right of it.
    assert classify_crossing(diagonal, Point(10, 40), Point(40, 10)) is not None


def test_diagonal_line_no_crossing_when_movement_stays_on_one_side():
    diagonal = Line(x1=0, y1=0, x2=100, y2=100)
    assert classify_crossing(diagonal, Point(10, 40), Point(20, 60)) is None


def test_direction_is_reversed_by_swapping_the_lines_endpoints():
    reversed_line = Line(x1=100, y1=50, x2=0, y2=50)
    assert classify_crossing(reversed_line, Point(50, 40), Point(50, 60)) == "out"


def test_lineconfig_to_pixels_scales_normalized_coordinates():
    config = LineConfig(id=uuid.uuid4(), name="Entrance", x1=0.1, y1=0.2, x2=0.9, y2=0.8)
    resolved = config.to_pixels(width=1000, height=500)
    assert resolved.line == Line(x1=100, y1=100, x2=900, y2=400)
    assert resolved.name == "Entrance"
    assert resolved.id == config.id

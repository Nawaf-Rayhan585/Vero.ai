"""Zone geometry: pure functions, no video/model — tested with synthetic coordinates."""
import uuid

from app.counting import Point
from app.zones import ZoneConfig, point_in_polygon

SQUARE = (Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10))
TRIANGLE = (Point(0, 0), Point(10, 0), Point(5, 10))
# An "L": the 6x6 notch at the top-right of the 10x10 box is outside the shape.
L_SHAPE = (Point(0, 0), Point(10, 0), Point(10, 4), Point(4, 4), Point(4, 10), Point(0, 10))
# Edges cross at (5, 5): the left and right triangles are inside, the top and bottom outside.
BOW_TIE = (Point(0, 0), Point(10, 10), Point(10, 0), Point(0, 10))


class TestPointInPolygon:
    def test_a_point_well_inside_a_square(self):
        assert point_in_polygon(Point(5, 5), SQUARE)

    def test_points_outside_a_square_on_every_side(self):
        for outside in (Point(-1, 5), Point(11, 5), Point(5, -1), Point(5, 11), Point(20, 20)):
            assert not point_in_polygon(outside, SQUARE)

    def test_a_point_on_an_edge_counts_as_inside(self):
        assert point_in_polygon(Point(5, 0), SQUARE)
        assert point_in_polygon(Point(10, 5), SQUARE)

    def test_a_point_on_a_vertex_counts_as_inside(self):
        assert point_in_polygon(Point(0, 0), SQUARE)
        assert point_in_polygon(Point(10, 10), SQUARE)

    def test_a_triangle(self):
        assert point_in_polygon(Point(5, 3), TRIANGLE)
        assert not point_in_polygon(Point(1, 9), TRIANGLE)  # inside the bounding box, outside the triangle
        assert not point_in_polygon(Point(9, 9), TRIANGLE)

    def test_a_concave_polygon_excludes_its_notch(self):
        assert point_in_polygon(Point(2, 8), L_SHAPE)  # the tall arm
        assert point_in_polygon(Point(8, 2), L_SHAPE)  # the wide arm
        assert not point_in_polygon(Point(8, 8), L_SHAPE)  # the notch
        assert not point_in_polygon(Point(5, 5), L_SHAPE)  # just past the inner corner

    def test_a_self_intersecting_polygon_follows_the_even_odd_rule(self):
        assert point_in_polygon(Point(2, 5), BOW_TIE)
        assert point_in_polygon(Point(8, 5), BOW_TIE)
        assert not point_in_polygon(Point(5, 2), BOW_TIE)
        assert not point_in_polygon(Point(5, 8), BOW_TIE)

    def test_vertex_order_does_not_change_the_answer(self):
        reversed_square = tuple(reversed(SQUARE))
        assert point_in_polygon(Point(5, 5), reversed_square)
        assert not point_in_polygon(Point(15, 5), reversed_square)

    def test_a_ray_passing_exactly_through_a_vertex_is_not_double_counted(self):
        # A horizontal ray at y=5 runs straight through this diamond's left and right
        # vertices; a naive ray caster toggles twice at each and gets the answer wrong.
        diamond = (Point(5, 0), Point(10, 5), Point(5, 10), Point(0, 5))
        assert point_in_polygon(Point(2, 5), diamond)
        assert not point_in_polygon(Point(-5, 5), diamond)
        assert not point_in_polygon(Point(12, 5), diamond)


class TestZoneConfigToPixels:
    def test_scales_normalized_points_to_the_frame_size(self):
        config = ZoneConfig(
            id=uuid.uuid4(),
            name="Checkout",
            points=(Point(0.0, 0.0), Point(0.5, 0.0), Point(0.5, 1.0)),
        )

        resolved = config.to_pixels(1000, 400)

        assert resolved.id == config.id
        assert resolved.name == "Checkout"
        assert resolved.polygon == (Point(0, 0), Point(500, 0), Point(500, 400))

    def test_a_resolved_zone_can_be_tested_directly(self):
        config = ZoneConfig(
            id=uuid.uuid4(),
            name="Left half",
            points=(Point(0, 0), Point(0.5, 0), Point(0.5, 1), Point(0, 1)),
        )
        resolved = config.to_pixels(1000, 500)

        assert point_in_polygon(Point(200, 250), resolved.polygon)
        assert not point_in_polygon(Point(800, 250), resolved.polygon)

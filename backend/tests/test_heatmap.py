"""Heatmap accumulation and rendering: pure numpy/OpenCV, no video/model."""
import numpy as np

from app.counting import Point
from app.heatmap import GRID_WIDTH, HeatmapAccumulator


def _grey_frame(width=800, height=400, value=128) -> np.ndarray:
    return np.full((height, width, 3), value, dtype=np.uint8)


class TestAccumulation:
    def test_the_grid_follows_the_frames_aspect_ratio(self):
        assert HeatmapAccumulator(800, 400)._grid.shape == (GRID_WIDTH // 2, GRID_WIDTH)
        assert HeatmapAccumulator(1000, 1000)._grid.shape == (GRID_WIDTH, GRID_WIDTH)
        assert HeatmapAccumulator(400, 800)._grid.shape == (GRID_WIDTH * 2, GRID_WIDTH)

    def test_a_point_increments_the_cell_underneath_it(self):
        heatmap = HeatmapAccumulator(800, 400)  # 80 columns x 40 rows, so 10px per cell

        heatmap.add([Point(405, 205)])

        assert heatmap._grid[20, 40] == 1
        assert heatmap._grid.sum() == 1
        assert heatmap.sample_count == 1

    def test_repeated_points_accumulate(self):
        heatmap = HeatmapAccumulator(800, 400)

        heatmap.add([Point(405, 205), Point(402, 208)])
        heatmap.add([Point(409, 201)])

        assert heatmap._grid[20, 40] == 3
        assert heatmap.sample_count == 3

    def test_points_outside_the_frame_are_clamped_to_the_nearest_edge_cell(self):
        heatmap = HeatmapAccumulator(800, 400)

        heatmap.add([Point(-50, 9999), Point(9999, -50)])

        assert heatmap._grid[39, 0] == 1  # bottom-left
        assert heatmap._grid[0, 79] == 1  # top-right
        assert heatmap.sample_count == 2

    def test_a_point_exactly_on_the_far_edge_lands_in_the_last_cell(self):
        heatmap = HeatmapAccumulator(800, 400)

        heatmap.add([Point(800, 400)])

        assert heatmap._grid[39, 79] == 1

    def test_adding_no_points_changes_nothing(self):
        heatmap = HeatmapAccumulator(800, 400)

        heatmap.add([])

        assert heatmap.sample_count == 0
        assert heatmap._grid.sum() == 0


class TestRender:
    def test_rendering_with_no_samples_returns_the_frame_untouched(self):
        heatmap = HeatmapAccumulator(800, 400)
        frame = _grey_frame()

        assert heatmap.render(frame) is frame

    def test_the_hot_spot_is_tinted_and_a_distant_pixel_is_left_alone(self):
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(400, 200)] * 50)
        frame = _grey_frame()

        rendered = heatmap.render(frame)

        assert np.abs(rendered[200, 400].astype(int) - 128).max() > 40  # clearly recoloured
        assert (rendered[5, 5] == 128).all()  # far from any heat: exactly the original pixel

    def test_the_output_matches_the_input_frames_shape_and_dtype(self):
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(100, 100)])
        frame = _grey_frame()

        rendered = heatmap.render(frame)

        assert rendered.shape == frame.shape
        assert rendered.dtype == np.uint8

    def test_rendering_does_not_modify_the_input_frame(self):
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(400, 200)] * 10)
        frame = _grey_frame()

        heatmap.render(frame)

        assert (frame == 128).all()

    def test_more_visits_make_a_hotter_spot_than_fewer(self):
        # Two well-separated spots; the busier one must be tinted more strongly.
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(200, 200)] * 40)
        heatmap.add([Point(600, 200)] * 4)
        frame = _grey_frame()

        rendered = heatmap.render(frame)

        busy = np.abs(rendered[200, 200].astype(int) - 128).sum()
        quiet = np.abs(rendered[200, 600].astype(int) - 128).sum()
        assert busy > quiet

    def test_rendering_can_be_repeated_as_more_samples_arrive(self):
        heatmap = HeatmapAccumulator(800, 400)
        frame = _grey_frame()
        heatmap.add([Point(200, 200)] * 5)
        first = heatmap.render(frame)

        heatmap.add([Point(600, 200)] * 30)
        second = heatmap.render(frame)

        assert (first[200, 600] == 128).all()  # nothing there yet
        assert np.abs(second[200, 600].astype(int) - 128).max() > 40  # now the hot spot

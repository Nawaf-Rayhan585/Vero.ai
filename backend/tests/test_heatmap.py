"""Heatmap accumulation and rendering: pure numpy/OpenCV, no video/model."""
import numpy as np
import pytest

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


class TestStorageFormat:
    def test_a_grid_round_trips_exactly(self):
        from app.heatmap import decode_grid, encode_grid

        grid = np.zeros((45, 80), dtype=np.uint32)
        grid[3, 7], grid[44, 79], grid[20, 40] = 1, 4_000_000_000, 123456

        decoded = decode_grid(encode_grid(grid), 80, 45)

        assert decoded.shape == (45, 80) and decoded.dtype == np.uint32
        assert (decoded == grid).all()

    def test_an_empty_grid_is_tiny_and_a_busy_one_still_small(self):
        from app.heatmap import encode_grid

        empty = np.zeros((45, 80), dtype=np.uint32)
        busy = np.random.default_rng(0).integers(0, 50, size=(45, 80), dtype=np.uint32)

        assert len(encode_grid(empty)) < 100
        assert len(encode_grid(busy)) < 45 * 80 * 4  # smaller than the raw uint32 array

    def test_decoding_with_the_wrong_dimensions_is_an_error_not_silent_garbage(self):
        from app.heatmap import decode_grid, encode_grid

        blob = encode_grid(np.ones((40, 80), dtype=np.uint32))

        with pytest.raises(ValueError):
            decode_grid(blob, 80, 45)

    def test_float_grids_from_the_live_accumulator_can_be_encoded(self):
        from app.heatmap import decode_grid, encode_grid

        live = np.zeros((40, 80), dtype=np.float32)
        live[5, 5] = 7.0

        assert decode_grid(encode_grid(live), 80, 40)[5, 5] == 7

    def test_the_grid_height_follows_the_aspect_ratio(self):
        from app.heatmap import GRID_WIDTH, grid_height_for

        assert grid_height_for(800, 400) == GRID_WIDTH // 2
        assert grid_height_for(1000, 1000) == GRID_WIDTH
        assert grid_height_for(1, 1000) >= 1


class TestDeltaHandOff:
    def test_nothing_added_means_nothing_to_hand_off(self):
        assert HeatmapAccumulator(800, 400).take_delta() is None

    def test_the_delta_is_what_was_added_since_the_last_hand_off(self):
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(405, 205)] * 3 + [Point(15, 15)])

        grid, samples = heatmap.take_delta()

        assert samples == 4
        assert grid.dtype == np.uint32 and grid.shape == (40, 80)
        assert grid[20, 40] == 3 and grid[1, 1] == 1 and grid.sum() == 4

    def test_taking_the_delta_starts_a_fresh_one(self):
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(405, 205)] * 3)
        heatmap.take_delta()

        assert heatmap.take_delta() is None
        heatmap.add([Point(405, 205)] * 2)
        grid, samples = heatmap.take_delta()
        assert samples == 2 and grid[20, 40] == 2

    def test_the_returned_grid_is_a_copy_not_a_view_of_live_state(self):
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(405, 205)])
        grid, _ = heatmap.take_delta()

        heatmap.add([Point(405, 205)] * 5)

        assert grid[20, 40] == 1  # unaffected by later adds

    def test_handing_off_does_not_disturb_the_live_heatmap(self):
        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(400, 200)] * 30)
        frame = _grey_frame()
        before = heatmap.render(frame)

        heatmap.take_delta()

        assert heatmap.sample_count == 30
        assert (heatmap.render(frame) == before).all()

    def test_deltas_sum_to_the_whole_even_with_concurrent_adds_and_hand_offs(self):
        import threading

        heatmap = HeatmapAccumulator(800, 400)
        taken = []
        done = threading.Event()

        def adder():
            for _ in range(2000):
                heatmap.add([Point(400, 200)])

        def taker():
            while not done.is_set():
                got = heatmap.take_delta()
                if got:
                    taken.append(got)

        adders = [threading.Thread(target=adder) for _ in range(4)]
        taking = threading.Thread(target=taker)
        taking.start()
        for t in adders:
            t.start()
        for t in adders:
            t.join()
        done.set()
        taking.join()
        final = heatmap.take_delta()
        if final:
            taken.append(final)

        assert sum(samples for _grid, samples in taken) == 8000
        assert sum(int(grid.sum()) for grid, _samples in taken) == 8000  # nothing lost, nothing counted twice


class TestSharedRenderer:
    def test_a_grid_with_no_heat_leaves_the_frame_untouched(self):
        from app.heatmap import render_heat

        frame = _grey_frame()

        assert render_heat(frame, np.zeros((40, 80), dtype=np.uint32)) is frame

    def test_the_hot_cell_is_tinted_and_the_rest_is_not(self):
        from app.heatmap import render_heat

        grid = np.zeros((40, 80), dtype=np.uint32)
        grid[20, 40] = 100

        rendered = render_heat(_grey_frame(), grid)

        assert np.abs(rendered[200, 400].astype(int) - 128).max() > 40
        assert (rendered[5, 5] == 128).all()

    def test_it_works_on_a_frame_of_a_different_size_than_the_grid_was_recorded_at(self):
        from app.heatmap import render_heat

        grid = np.zeros((40, 80), dtype=np.uint32)
        grid[20, 40] = 100
        big = np.full((1080, 1920, 3), 128, np.uint8)  # e.g. a fresh snapshot from a higher-res stream

        rendered = render_heat(big, grid)

        assert rendered.shape == big.shape
        assert np.abs(rendered[540, 960].astype(int) - 128).max() > 40

    def test_the_live_and_historical_views_render_identically(self):
        from app.heatmap import render_heat

        heatmap = HeatmapAccumulator(800, 400)
        heatmap.add([Point(400, 200)] * 20 + [Point(100, 100)] * 5)
        frame = _grey_frame()

        stored = np.zeros((40, 80), dtype=np.uint32)
        stored[20, 40], stored[10, 10] = 20, 5

        assert (heatmap.render(frame) == render_heat(frame, stored)).all()

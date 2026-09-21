"""Heatmap of where tracked people spend time. Pure numpy/OpenCV, no model dependency —
independently testable with synthetic points.

The live grid is in-memory and starts empty every time tracking starts. What has
accumulated since the last hand-off (the "delta") is periodically taken and persisted by
the events recorder as one row per camera per hour (`HeatmapSnapshot`), so past periods
can be viewed later; `encode_grid` / `decode_grid` are that row's storage format and
`render_heat` is the one renderer for both the live and the historical view.
"""
import threading
import zlib
from typing import Optional

import cv2
import numpy as np

from app.counting import Point

GRID_WIDTH = 80  # columns; rows follow the frame's aspect ratio
BLUR_SIGMA_CELLS = 1.5
MAX_ALPHA = 0.65  # opacity of the hottest cell; colder cells fade toward fully transparent


def grid_height_for(frame_width: int, frame_height: int) -> int:
    return max(1, round(GRID_WIDTH * frame_height / frame_width))


def encode_grid(grid: np.ndarray) -> bytes:
    """Compact storage form: zlib over a little-endian uint32 array. A mostly-empty
    80x45 grid is about 1 KB."""
    return zlib.compress(np.ascontiguousarray(grid, dtype="<u4").tobytes(), 6)


def decode_grid(data: bytes, width: int, height: int) -> np.ndarray:
    values = np.frombuffer(zlib.decompress(data), dtype="<u4")
    if values.size != width * height:
        raise ValueError(f"stored heatmap has {values.size} cells, expected {width}x{height}")
    return values.reshape(height, width).astype(np.uint32)


def render_heat(frame: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Returns `frame` blended with the heat overlay for `grid`, or `frame` itself,
    untouched, if the grid holds no heat."""
    heat = cv2.GaussianBlur(np.asarray(grid, dtype=np.float32), (0, 0), BLUR_SIGMA_CELLS)
    peak = float(heat.max())
    if peak <= 0:
        return frame

    height, width = frame.shape[:2]
    intensity = cv2.resize(heat / peak, (width, height), interpolation=cv2.INTER_LINEAR)
    colored = cv2.applyColorMap((intensity * 255).astype(np.uint8), cv2.COLORMAP_JET)
    # Per-pixel alpha scales with heat, so areas nobody walked through stay untouched.
    alpha = (intensity * MAX_ALPHA)[..., None]
    # Rounded, not truncated: astype alone would nudge an untouched pixel (alpha ~ 0)
    # down by one level whenever float error lands just under its original value.
    return np.rint(frame * (1 - alpha) + colored * alpha).astype(np.uint8)


class HeatmapAccumulator:
    def __init__(self, frame_width: int, frame_height: int):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.grid_width = GRID_WIDTH
        self.grid_height = grid_height_for(frame_width, frame_height)
        self._grid = np.zeros((self.grid_height, GRID_WIDTH), dtype=np.float32)
        # What has been added since the last take_delta(), for persistence. Separate from
        # _grid so handing it off never disturbs the live view.
        self._delta = np.zeros((self.grid_height, GRID_WIDTH), dtype=np.uint32)
        self._delta_samples = 0
        # Written by the tracking thread, read by whichever request thread renders.
        self._lock = threading.Lock()
        self.sample_count = 0

    def add(self, points) -> None:
        """One sample per point: the cell under it gets +1. Points outside the frame are
        clamped to the nearest edge cell rather than dropped."""
        with self._lock:
            for p in points:
                col = min(max(int(p.x / self.frame_width * GRID_WIDTH), 0), GRID_WIDTH - 1)
                row = min(max(int(p.y / self.frame_height * self.grid_height), 0), self.grid_height - 1)
                self._grid[row, col] += 1
                self._delta[row, col] += 1
                self.sample_count += 1
                self._delta_samples += 1

    def take_delta(self) -> Optional[tuple[np.ndarray, int]]:
        """Hands off (grid, sample count) accumulated since the last call and starts a
        fresh delta, or returns None if nothing new was added."""
        with self._lock:
            if self._delta_samples == 0:
                return None
            taken = (self._delta.copy(), self._delta_samples)
            self._delta[:] = 0
            self._delta_samples = 0
            return taken

    def render(self, frame: np.ndarray) -> np.ndarray:
        """Returns `frame` blended with the heat overlay, or `frame` itself, untouched, if
        nothing has been accumulated yet."""
        with self._lock:
            if self.sample_count == 0:
                return frame
            grid = self._grid.copy()
        return render_heat(frame, grid)

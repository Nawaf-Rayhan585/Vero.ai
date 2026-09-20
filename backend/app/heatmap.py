"""Per-session heatmap of where tracked people spend time. Pure numpy/OpenCV, no model
dependency — independently testable with synthetic points.

Deliberately ephemeral, like every other tracking-session value: it lives in memory and
starts empty every time tracking starts. Persistent/historical heatmaps are Phase 9's job.
"""
import threading

import cv2
import numpy as np

from app.counting import Point

GRID_WIDTH = 80  # columns; rows follow the frame's aspect ratio
BLUR_SIGMA_CELLS = 1.5
MAX_ALPHA = 0.65  # opacity of the hottest cell; colder cells fade toward fully transparent


class HeatmapAccumulator:
    def __init__(self, frame_width: int, frame_height: int):
        self._frame_width = frame_width
        self._frame_height = frame_height
        self._grid_height = max(1, round(GRID_WIDTH * frame_height / frame_width))
        self._grid = np.zeros((self._grid_height, GRID_WIDTH), dtype=np.float32)
        # Written by the tracking thread, read by whichever request thread renders.
        self._lock = threading.Lock()
        self.sample_count = 0

    def add(self, points) -> None:
        """One sample per point: the cell under it gets +1. Points outside the frame are
        clamped to the nearest edge cell rather than dropped."""
        with self._lock:
            for p in points:
                col = min(max(int(p.x / self._frame_width * GRID_WIDTH), 0), GRID_WIDTH - 1)
                row = min(max(int(p.y / self._frame_height * self._grid_height), 0), self._grid_height - 1)
                self._grid[row, col] += 1
                self.sample_count += 1

    def render(self, frame: np.ndarray) -> np.ndarray:
        """Returns `frame` blended with the heat overlay, or `frame` itself, untouched, if
        nothing has been accumulated yet."""
        with self._lock:
            if self.sample_count == 0:
                return frame
            grid = self._grid.copy()

        heat = cv2.GaussianBlur(grid, (0, 0), BLUR_SIGMA_CELLS)
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

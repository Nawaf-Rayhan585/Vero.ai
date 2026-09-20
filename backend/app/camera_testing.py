import concurrent.futures
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import cv2
import numpy as np

OPEN_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 5000
# Safety net above the cv2 timeouts, comfortably longer than OPEN_TIMEOUT_MS +
# READ_TIMEOUT_MS combined (worst case both elapse in full) so it only fires when the
# native call ignores its own timeout entirely, not as a race against it. This bounds
# how long the calling thread waits; it does NOT kill the native call, which can keep
# running in the background thread until it eventually times out or the process exits.
HARD_TIMEOUT_SECONDS = 15


@dataclass
class FrameResult:
    frame: Optional["np.ndarray"]
    error: Optional[str]
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class ConnectionTestOutcome:
    online: bool
    error: Optional[str]
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


def build_stream_url(rtsp_url: str, username: Optional[str], password: Optional[str]) -> str:
    """Embed credentials the way RTSP/FFmpeg expects. rtsp_url is expected not to
    already contain credentials — that's exactly why they're separate fields."""
    if not username or "://" not in rtsp_url:
        return rtsp_url
    scheme, rest = rtsp_url.split("://", 1)
    userinfo = quote(username, safe="")
    if password:
        userinfo += f":{quote(password, safe='')}"
    return f"{scheme}://{userinfo}@{rest}"


def _open_and_read_frame(stream_url: str) -> FrameResult:
    # The timeout properties only take effect passed via this constructor form.
    # cv2.VideoCapture() + .set(...) + .open(...) silently ignores them here (confirmed
    # empirically: it falls back to OpenCV's own ~30s default "interrupt callback"
    # regardless of the requested value), which is exactly why the hard timeout below
    # exists as a second line of defense rather than being trusted alone.
    cap = cv2.VideoCapture(
        stream_url,
        cv2.CAP_FFMPEG,
        [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS],
    )
    try:
        if not cap.isOpened():
            return FrameResult(frame=None, error="Could not open stream (unreachable, refused, or unsupported)")
        ok, frame = cap.read()
        if not ok or frame is None:
            return FrameResult(frame=None, error="Stream opened but no frame could be read")
        height, width = frame.shape[:2]
        return FrameResult(frame=frame, error=None, fps=cap.get(cv2.CAP_PROP_FPS) or None, width=width, height=height)
    finally:
        cap.release()


def _run_with_hard_timeout(stream_url: str) -> FrameResult:
    # Deliberately not a `with` block: ThreadPoolExecutor.__exit__ calls shutdown(wait=True),
    # which would block here until the abandoned thread finishes on its own — exactly the
    # native-call-not-interruptible case this timeout exists to bound. shutdown(wait=False)
    # lets this function return on time while that thread (and the stuck native cv2 call
    # inside it) finishes in the background, sharing the process's threadpool until it does.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_open_and_read_frame, stream_url)
    try:
        return future.result(timeout=HARD_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        return FrameResult(frame=None, error=f"Connection attempt exceeded {HARD_TIMEOUT_SECONDS}s hard timeout")
    finally:
        executor.shutdown(wait=False)


def test_connection(rtsp_url: str, username: Optional[str] = None, password: Optional[str] = None) -> ConnectionTestOutcome:
    result = _run_with_hard_timeout(build_stream_url(rtsp_url, username, password))
    return ConnectionTestOutcome(
        online=result.frame is not None,
        error=result.error,
        fps=result.fps,
        width=result.width,
        height=result.height,
    )


def grab_snapshot(rtsp_url: str, username: Optional[str] = None, password: Optional[str] = None) -> FrameResult:
    return _run_with_hard_timeout(build_stream_url(rtsp_url, username, password))

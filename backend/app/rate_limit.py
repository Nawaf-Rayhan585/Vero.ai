"""Phase 17: abuse/DoS defense-in-depth for the public auth endpoints
(routers/auth.py's register/login/refresh). Deliberately not a third-party library
(Development Rule 14, "avoid unnecessary dependencies") - a fixed-window counter is all
this needs, and this project already prefers small hand-written modules over pulling in
a package for something this narrow (e.g. app/paypal_client.py over a PayPal SDK).

This is NOT the primary defense against credential guessing - that's the per-account
lockout in app/auth.py's is_account_locked/register_failed_login, which survives even if
an attacker spreads requests across many IPs. This module is a coarser, IP-based limit
against sheer request volume (scripted registration spam, hammering /refresh, etc.),
independent of which account is targeted.
"""
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 10

_lock = threading.Lock()
# {(endpoint_name, ip): (window_start_epoch_seconds, count_in_window)}
_buckets: dict[tuple[str, str], tuple[float, int]] = defaultdict(lambda: (0.0, 0))


def _client_ip(request: Request) -> str:
    # request.client is None in some ASGI test/edge setups (never in real deployment,
    # where the backend only ever hears from the desktop app or PayPal) - fall back to a
    # constant key rather than crashing, since falling back just means "share one bucket"
    # not "no limiting at all".
    return request.client.host if request.client else "unknown"


def rate_limit(endpoint_name: str, max_requests: int = _MAX_REQUESTS_PER_WINDOW, window_seconds: int = _WINDOW_SECONDS):
    """`Depends(rate_limit("login"))` - a fixed window per (endpoint_name, client IP).
    Raises 429 with Retry-After once the window's request budget is exhausted."""

    def check(request: Request) -> None:
        key = (endpoint_name, _client_ip(request))
        now = time.monotonic()
        with _lock:
            window_start, count = _buckets[key]
            if now - window_start >= window_seconds:
                _buckets[key] = (now, 1)
                return
            if count >= max_requests:
                retry_after = int(window_seconds - (now - window_start)) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please wait before trying again.",
                    headers={"Retry-After": str(retry_after)},
                )
            _buckets[key] = (window_start, count + 1)

    return check


def _reset_for_tests() -> None:
    """Test-only: the module-level bucket dict persists across tests in the same process
    otherwise, since it's a plain module global, not something request-scoped."""
    with _lock:
        _buckets.clear()

"""Phase 13: routes camera-processing requests to cloud-engine for organizations on the
Vero Cloud plan, instead of this process's own in-process `tracking_manager`
(app/tracking.py). See routers/tracking.py and routers/cameras.py for the call sites —
every one of them keeps its existing, unchanged local code path for every other
organization (plan unset or "own_hardware"), and only reaches this module when
`is_cloud_organization` is true.
"""
import httpx
from fastapi import HTTPException, Response

from app.auth import OrgContext
from app.config import get_settings

INTERNAL_SECRET_HEADER = "X-Internal-Secret"
_TIMEOUT_SECONDS = 15.0


def is_cloud_organization(ctx: OrgContext) -> bool:
    sub = ctx.organization.subscription
    return sub is not None and sub.plan_type == "vero_cloud"


def proxy_to_cloud_engine(method: str, path: str, **kwargs) -> httpx.Response:
    """Forwards one request to cloud-engine and returns its raw response, for
    `relay_json`/`relay_bytes` below to turn into what this backend's own route would
    have returned. Raises a clear 503 if cloud-engine isn't configured or unreachable,
    rather than ever falling back to processing the camera in this process — that would
    silently run a Vero Cloud customer's camera on the wrong infrastructure."""
    settings = get_settings()
    if not settings.cloud_engine_base_url or not settings.cloud_engine_internal_secret:
        raise HTTPException(status_code=503, detail="Vero Cloud isn't configured on this backend")

    headers = kwargs.pop("headers", {})
    headers[INTERNAL_SECRET_HEADER] = settings.cloud_engine_internal_secret
    try:
        return httpx.request(
            method, f"{settings.cloud_engine_base_url}{path}", headers=headers, timeout=_TIMEOUT_SECONDS, **kwargs
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Could not reach the Vero Cloud engine: {exc}") from exc


def _raise_for_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise HTTPException(status_code=response.status_code, detail=detail)


def relay_json(response: httpx.Response):
    """The JSON-response case (tracking start/stop/status, test-connection)."""
    _raise_for_error(response)
    return response.json()


def relay_bytes(response: httpx.Response) -> Response:
    """The raw-bytes case (a JPEG frame: latest-frame, snapshot)."""
    _raise_for_error(response)
    content_type = response.headers.get("content-type", "application/octet-stream")
    return Response(content=response.content, media_type=content_type)

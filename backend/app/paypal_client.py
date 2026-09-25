"""Phase 15: a thin, direct wrapper around PayPal's REST API (Subscriptions v1 +
Catalog Products v1 + Webhooks v1) — no PayPal SDK dependency, same "plain httpx calls,
clear 503 when unconfigured" style as app/cloud_routing.py. Sandbox-only until a later
phase explicitly goes live (app/config.py's paypal_api_base defaults to PayPal's sandbox
host). See routers/subscription.py for the endpoints that call this, and
scripts/setup_paypal_plan.py for the one-time Product/Plan setup that isn't part of the
running app.
"""
import time
from typing import Optional

import httpx
from fastapi import HTTPException

from app.config import Settings, get_settings

_TIMEOUT_SECONDS = 15.0

# A simple in-memory cache for the OAuth2 access token (module-global, single-process —
# same spirit as app/tracking.py's tracking_manager singleton, no distributed concerns
# for this project). Refetched a little before PayPal's own expiry to avoid a request
# racing an about-to-expire token.
_token_cache: dict[str, object] = {"token": None, "expires_at": 0.0}
_TOKEN_REFRESH_MARGIN_SECONDS = 60.0


def _require_configured(settings: Settings, *fields: str) -> None:
    if any(getattr(settings, field) is None for field in fields):
        raise HTTPException(status_code=503, detail="PayPal billing isn't configured on this backend")


def _get_access_token(settings: Settings) -> str:
    _require_configured(settings, "paypal_client_id", "paypal_client_secret")
    now = time.monotonic()
    if _token_cache["token"] is not None and now < _token_cache["expires_at"]:
        return _token_cache["token"]  # type: ignore[return-value]

    try:
        response = httpx.post(
            f"{settings.paypal_api_base}/v1/oauth2/token",
            auth=(settings.paypal_client_id, settings.paypal_client_secret),
            data={"grant_type": "client_credentials"},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Could not reach PayPal: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"PayPal rejected the credentials on file: {response.text}")

    body = response.json()
    _token_cache["token"] = body["access_token"]
    _token_cache["expires_at"] = now + body["expires_in"] - _TOKEN_REFRESH_MARGIN_SECONDS
    return body["access_token"]


def _request(settings: Settings, method: str, path: str, **kwargs) -> httpx.Response:
    token = _get_access_token(settings)
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    try:
        return httpx.request(
            method, f"{settings.paypal_api_base}{path}", headers=headers, timeout=_TIMEOUT_SECONDS, **kwargs
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Could not reach PayPal: {exc}") from exc


def _raise_for_paypal_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        detail = response.json().get("message", response.text)
    except ValueError:
        detail = response.text
    raise HTTPException(status_code=502, detail=f"PayPal error: {detail}")


def create_subscription(organization_id: str, return_url: str, cancel_url: str) -> dict:
    """POSTs a new subscription against the configured Own Hardware plan, `custom_id`
    tagged with our organization id (so a later webhook/sync can find the right row).
    Returns PayPal's raw response — the caller reads `id` and the `approve` link out of
    `links`."""
    settings = get_settings()
    _require_configured(settings, "paypal_own_hardware_plan_id")
    response = _request(
        settings,
        "POST",
        "/v1/billing/subscriptions",
        json={
            "plan_id": settings.paypal_own_hardware_plan_id,
            "custom_id": organization_id,
            "application_context": {
                "brand_name": "Vero.ai",
                "user_action": "SUBSCRIBE_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        },
    )
    _raise_for_paypal_error(response)
    return response.json()


def get_subscription(paypal_subscription_id: str) -> dict:
    settings = get_settings()
    response = _request(settings, "GET", f"/v1/billing/subscriptions/{paypal_subscription_id}")
    _raise_for_paypal_error(response)
    return response.json()


def cancel_subscription(paypal_subscription_id: str, reason: str = "Canceled from Vero.ai") -> None:
    settings = get_settings()
    response = _request(
        settings, "POST", f"/v1/billing/subscriptions/{paypal_subscription_id}/cancel", json={"reason": reason}
    )
    _raise_for_paypal_error(response)


def verify_webhook_signature(headers: dict, parsed_body: dict) -> bool:
    """Posts the event back to PayPal's own verification endpoint rather than
    reimplementing RSA-SHA256 locally — simpler and matches PayPal's own recommended
    approach. `headers` is the incoming request's headers (case-insensitive mapping)."""
    settings = get_settings()
    if settings.paypal_webhook_id is None:
        return False
    response = _request(
        settings,
        "POST",
        "/v1/notifications/verify-webhook-signature",
        json={
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": settings.paypal_webhook_id,
            "webhook_event": parsed_body,
        },
    )
    if response.status_code >= 400:
        return False
    return response.json().get("verification_status") == "SUCCESS"


def create_product(name: str, description: str) -> dict:
    """Merchant-side setup only — used by scripts/setup_paypal_plan.py, never by the
    running app's request handlers."""
    settings = get_settings()
    response = _request(
        settings,
        "POST",
        "/v1/catalogs/products",
        json={"name": name, "description": description, "type": "SERVICE", "category": "SOFTWARE"},
    )
    _raise_for_paypal_error(response)
    return response.json()


def create_plan(product_id: str, name: str, monthly_price_usd: str) -> dict:
    """Merchant-side setup only — used by scripts/setup_paypal_plan.py."""
    settings = get_settings()
    response = _request(
        settings,
        "POST",
        "/v1/billing/plans",
        json={
            "product_id": product_id,
            "name": name,
            "billing_cycles": [
                {
                    "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,
                    "pricing_scheme": {"fixed_price": {"value": monthly_price_usd, "currency_code": "USD"}},
                }
            ],
            "payment_preferences": {"auto_bill_outstanding": True, "payment_failure_threshold": 3},
        },
    )
    _raise_for_paypal_error(response)
    return response.json()

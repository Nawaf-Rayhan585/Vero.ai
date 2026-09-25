"""Phase 15: real PayPal billing for the Own Hardware plan (Vero Cloud billing doesn't
exist yet). Mocks app.paypal_client's functions at their call boundary — exactly like
test_cloud_routing.py mocks httpx.request — so these tests never make a real network
call. The manual override (Phase 11, tests/test_subscription_api.py) is untouched by
this phase and isn't re-tested here; the full suite re-run is what proves that."""
from unittest.mock import patch

import pytest


class FakeSettings:
    def __init__(self, paypal_return_base_url="http://127.0.0.1:8000"):
        self.paypal_return_base_url = paypal_return_base_url


@pytest.fixture
def own_hardware_client(client):
    """`client`'s own organization, switched onto the Own Hardware plan — the only plan
    PayPal checkout is available for this phase."""
    response = client.patch("/subscription", json={"plan_type": "own_hardware"})
    assert response.status_code == 200, response.text
    return client


def _paypal_subscription(status="APPROVAL_PENDING", sub_id="I-TESTSUB123"):
    return {"id": sub_id, "status": status, "plan_id": "P-TESTPLAN"}


def _checkout_response(sub_id="I-TESTSUB123"):
    return {
        "id": sub_id,
        "status": "APPROVAL_PENDING",
        "plan_id": "P-TESTPLAN",
        "links": [
            {"rel": "self", "href": f"https://api-m.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}"},
            {"rel": "approve", "href": f"https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=X"},
        ],
    }


class TestCheckout:
    def test_owner_can_start_checkout_and_the_subscription_is_stored(self, own_hardware_client):
        with (
            patch("app.routers.subscription.get_settings", return_value=FakeSettings()),
            patch("app.paypal_client.create_subscription", return_value=_checkout_response()) as mock_create,
        ):
            response = own_hardware_client.post("/subscription/paypal/checkout")

        assert response.status_code == 200, response.text
        assert response.json()["approve_url"].startswith("https://www.sandbox.paypal.com")
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["organization_id"] == own_hardware_client.test_organization["id"]
        assert kwargs["return_url"].endswith("/subscription/paypal/return")
        assert kwargs["cancel_url"].endswith("/subscription/paypal/cancel-return")

        sub = own_hardware_client.get("/subscription").json()
        assert sub["paypal_subscription_id"] == "I-TESTSUB123"
        assert sub["paypal_plan_id"] == "P-TESTPLAN"

    def test_checkout_requires_the_own_hardware_plan_to_already_be_chosen(self, client):
        # plan_type is unset by default (Phase 11) - never even reaches paypal_client.
        with (
            patch("app.routers.subscription.get_settings", return_value=FakeSettings()),
            patch("app.paypal_client.create_subscription") as mock_create,
        ):
            response = client.post("/subscription/paypal/checkout")

        assert response.status_code == 400
        mock_create.assert_not_called()

    def test_checkout_returns_503_when_paypal_is_not_configured(self, own_hardware_client):
        with patch("app.routers.subscription.get_settings", return_value=FakeSettings(paypal_return_base_url=None)):
            response = own_hardware_client.post("/subscription/paypal/checkout")

        assert response.status_code == 503

    def test_checkout_is_owner_only(self, own_hardware_client, register_user, add_member):
        member_client = register_user("member-checkout@example.com")
        add_member(own_hardware_client, member_client, role="member")

        with patch("app.routers.subscription.get_settings", return_value=FakeSettings()):
            response = member_client.post("/subscription/paypal/checkout")

        assert response.status_code == 403


class TestSync:
    def test_sync_activates_the_local_subscription_when_paypal_reports_active(self, own_hardware_client):
        with (
            patch("app.routers.subscription.get_settings", return_value=FakeSettings()),
            patch("app.paypal_client.create_subscription", return_value=_checkout_response()),
        ):
            own_hardware_client.post("/subscription/paypal/checkout")

        with patch("app.paypal_client.get_subscription", return_value=_paypal_subscription(status="ACTIVE")):
            response = own_hardware_client.post("/subscription/paypal/sync")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "active"
        assert body["activated_at"] is not None

    def test_sync_leaves_status_unchanged_while_still_approval_pending(self, own_hardware_client):
        with (
            patch("app.routers.subscription.get_settings", return_value=FakeSettings()),
            patch("app.paypal_client.create_subscription", return_value=_checkout_response()),
        ):
            own_hardware_client.post("/subscription/paypal/checkout")
        before = own_hardware_client.get("/subscription").json()["status"]

        with patch("app.paypal_client.get_subscription", return_value=_paypal_subscription(status="APPROVAL_PENDING")):
            response = own_hardware_client.post("/subscription/paypal/sync")

        assert response.status_code == 200
        assert response.json()["status"] == before

    def test_sync_404s_when_no_paypal_subscription_exists_yet(self, own_hardware_client):
        response = own_hardware_client.post("/subscription/paypal/sync")
        assert response.status_code == 404

    def test_sync_is_owner_only(self, own_hardware_client, register_user, add_member):
        member_client = register_user("member-sync@example.com")
        add_member(own_hardware_client, member_client, role="member")

        response = member_client.post("/subscription/paypal/sync")
        assert response.status_code == 403


class TestCancel:
    def test_cancel_calls_paypal_and_cancels_immediately(self, own_hardware_client):
        with (
            patch("app.routers.subscription.get_settings", return_value=FakeSettings()),
            patch("app.paypal_client.create_subscription", return_value=_checkout_response()),
        ):
            own_hardware_client.post("/subscription/paypal/checkout")

        with patch("app.paypal_client.cancel_subscription", return_value=None) as mock_cancel:
            response = own_hardware_client.post("/subscription/paypal/cancel")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "canceled"
        assert body["canceled_at"] is not None
        mock_cancel.assert_called_once_with("I-TESTSUB123")

    def test_cancel_404s_when_no_paypal_subscription_exists(self, own_hardware_client):
        response = own_hardware_client.post("/subscription/paypal/cancel")
        assert response.status_code == 404

    def test_cancel_is_owner_only(self, own_hardware_client, register_user, add_member):
        member_client = register_user("member-cancel@example.com")
        add_member(own_hardware_client, member_client, role="member")

        response = member_client.post("/subscription/paypal/cancel")
        assert response.status_code == 403


class TestReturnPages:
    def test_return_and_cancel_return_pages_are_public_html(self, anonymous_client):
        response = anonymous_client.get("/subscription/paypal/return")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "close this tab" in response.text

        response = anonymous_client.get("/subscription/paypal/cancel-return")
        assert response.status_code == 200
        assert "canceled" in response.text.lower()


class TestWebhook:
    def _linked_subscription(self, own_hardware_client):
        with (
            patch("app.routers.subscription.get_settings", return_value=FakeSettings()),
            patch("app.paypal_client.create_subscription", return_value=_checkout_response()),
        ):
            own_hardware_client.post("/subscription/paypal/checkout")

    def test_a_verified_activated_event_activates_the_subscription(self, own_hardware_client, anonymous_client):
        self._linked_subscription(own_hardware_client)

        with patch("app.paypal_client.verify_webhook_signature", return_value=True):
            response = anonymous_client.post(
                "/subscription/paypal/webhook",
                json={"event_type": "BILLING.SUBSCRIPTION.ACTIVATED", "resource": {"id": "I-TESTSUB123"}},
            )

        assert response.status_code == 200
        assert own_hardware_client.get("/subscription").json()["status"] == "active"

    def test_a_verified_cancelled_event_cancels_the_subscription(self, own_hardware_client, anonymous_client):
        self._linked_subscription(own_hardware_client)

        with patch("app.paypal_client.verify_webhook_signature", return_value=True):
            response = anonymous_client.post(
                "/subscription/paypal/webhook",
                json={"event_type": "BILLING.SUBSCRIPTION.CANCELLED", "resource": {"id": "I-TESTSUB123"}},
            )

        assert response.status_code == 200
        body = own_hardware_client.get("/subscription").json()
        assert body["status"] == "canceled"
        assert body["canceled_at"] is not None

    def test_an_unverifiable_signature_is_rejected(self, anonymous_client):
        with patch("app.paypal_client.verify_webhook_signature", return_value=False):
            response = anonymous_client.post(
                "/subscription/paypal/webhook",
                json={"event_type": "BILLING.SUBSCRIPTION.ACTIVATED", "resource": {"id": "I-TESTSUB123"}},
            )

        assert response.status_code == 400

    def test_an_event_for_an_unknown_subscription_id_is_a_harmless_no_op(self, anonymous_client):
        with patch("app.paypal_client.verify_webhook_signature", return_value=True):
            response = anonymous_client.post(
                "/subscription/paypal/webhook",
                json={"event_type": "BILLING.SUBSCRIPTION.ACTIVATED", "resource": {"id": "I-DOES-NOT-EXIST"}},
            )

        assert response.status_code == 200

    def test_an_unhandled_event_type_is_a_harmless_no_op(self, own_hardware_client, anonymous_client):
        self._linked_subscription(own_hardware_client)
        before = own_hardware_client.get("/subscription").json()["status"]

        with patch("app.paypal_client.verify_webhook_signature", return_value=True):
            response = anonymous_client.post(
                "/subscription/paypal/webhook",
                json={"event_type": "PAYMENT.SALE.COMPLETED", "resource": {"id": "I-TESTSUB123"}},
            )

        assert response.status_code == 200
        assert own_hardware_client.get("/subscription").json()["status"] == before

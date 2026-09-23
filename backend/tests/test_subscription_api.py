"""The subscription/licensing architecture (Phase 11): every organization gets a 3-day
trial on creation, any member can read it, and only an Owner can use the manual override
(a stand-in for real billing until Phase 15 ships PayPal)."""
from datetime import datetime, timedelta, timezone


def _get_subscription_row(db_session, organization_id):
    from app.models import Subscription

    return db_session.query(Subscription).filter_by(organization_id=organization_id).one()


class TestRead:
    def test_a_fresh_organization_starts_on_a_trialing_subscription(self, client):
        response = client.get("/subscription")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "trialing"
        assert body["is_active"] is True
        assert body["plan_type"] is None
        assert body["max_cameras"] is None
        assert body["activated_at"] is None
        assert body["organization_id"] == client.test_organization["id"]

    def test_the_trial_lasts_three_days_by_default(self, client):
        body = client.get("/subscription").json()
        started = datetime.fromisoformat(body["trial_started_at"])
        ends = datetime.fromisoformat(body["trial_ends_at"])

        assert abs((ends - started) - timedelta(days=3)) < timedelta(minutes=1)

    def test_a_member_can_read_the_subscription(self, client, register_user, add_member):
        member_client = register_user("member@example.com")
        add_member(client, member_client, role="member")

        response = member_client.get("/subscription")

        assert response.status_code == 200
        assert response.json()["organization_id"] == client.test_organization["id"]

    def test_an_anonymous_request_is_rejected(self, anonymous_client):
        assert anonymous_client.get("/subscription").status_code == 401


class TestOwnerOverride:
    def test_owner_can_activate_the_subscription(self, client, db_session):
        response = client.patch("/subscription", json={"status": "active"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "active"
        assert body["is_active"] is True
        assert body["activated_at"] is not None

        row = _get_subscription_row(db_session, client.test_organization["id"])
        assert str(row.activated_by_user_id) == client.test_user["id"]

    def test_owner_can_expire_the_subscription(self, client):
        response = client.patch("/subscription", json={"status": "expired"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "expired"
        assert body["is_active"] is False

    def test_owner_can_set_the_plan_type(self, client):
        response = client.patch("/subscription", json={"plan_type": "own_hardware"})
        assert response.json()["plan_type"] == "own_hardware"

        response = client.patch("/subscription", json={"plan_type": "vero_cloud"})
        assert response.json()["plan_type"] == "vero_cloud"

    def test_an_invalid_plan_type_is_rejected(self, client):
        assert client.patch("/subscription", json={"plan_type": "bogus"}).status_code == 422

    def test_an_invalid_status_is_rejected(self, client):
        assert client.patch("/subscription", json={"status": "bogus"}).status_code == 422

    def test_owner_can_extend_the_trial(self, client):
        far_future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        response = client.patch("/subscription", json={"trial_ends_at": far_future})

        assert response.status_code == 200
        body = response.json()
        assert body["is_active"] is True
        assert datetime.fromisoformat(body["trial_ends_at"]) > datetime.now(timezone.utc) + timedelta(days=29)

    def test_activating_does_not_touch_fields_that_were_not_provided(self, client):
        client.patch("/subscription", json={"plan_type": "own_hardware"})

        response = client.patch("/subscription", json={"status": "active"})

        assert response.json()["plan_type"] == "own_hardware"

    def test_an_admin_cannot_use_the_override(self, client, register_user, add_member):
        admin_client = register_user("admin@example.com")
        add_member(client, admin_client, role="admin")

        response = admin_client.patch("/subscription", json={"status": "active"})

        assert response.status_code == 403

    def test_a_member_cannot_use_the_override(self, client, register_user, add_member):
        member_client = register_user("member@example.com")
        add_member(client, member_client, role="member")

        response = member_client.patch("/subscription", json={"status": "active"})

        assert response.status_code == 403

    def test_the_override_works_even_on_an_already_expired_subscription(self, client):
        """You must be able to activate an already-expired organization — the override is
        deliberately not gated by require_active_configurator."""
        client.patch("/subscription", json={"status": "expired"})

        response = client.patch("/subscription", json={"status": "active"})

        assert response.status_code == 200
        assert response.json()["is_active"] is True


class TestOrganizationCreationStartsATrial:
    def test_registering_creates_a_trialing_subscription(self, register_user):
        c = register_user("fresh@example.com")
        assert c.get("/subscription").json()["status"] == "trialing"

    def test_creating_an_additional_organization_gives_it_its_own_fresh_trial(self, client):
        client.patch("/subscription", json={"status": "expired"})  # org A is now expired

        created = client.post("/organizations", json={"name": "Org B"}).json()
        client.headers["X-Organization-Id"] = created["organization"]["id"]

        body = client.get("/subscription").json()
        assert body["status"] == "trialing"
        assert body["is_active"] is True
        assert body["organization_id"] == created["organization"]["id"]

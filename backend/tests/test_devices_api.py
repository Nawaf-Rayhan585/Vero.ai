"""Devices (Phase 12's device entitlement): CRUD, role/tenant scoping, and the
max_devices entitlement-limit mechanism. A device is deliberately just a name someone
typed — no uniqueness constraint, no hardware fingerprinting."""
import uuid


class TestListAndCreate:
    def test_a_fresh_organization_has_no_devices(self, client):
        assert client.get("/devices").json() == []

    def test_creating_a_device(self, client):
        response = client.post("/devices", json={"name": "Warehouse PC", "notes": "Dell OptiPlex, GPU"})

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Warehouse PC"
        assert body["notes"] == "Dell OptiPlex, GPU"
        assert body["organization_id"] is not None

    def test_notes_is_optional(self, client):
        body = client.post("/devices", json={"name": "Office PC"}).json()
        assert body["notes"] is None

    def test_two_devices_in_the_same_organization_may_share_a_name(self, client):
        # Unlike locations, there's no uniqueness rule here — a "device" is just a record,
        # and two machines could plausibly have the same name in the real world.
        first = client.post("/devices", json={"name": "Warehouse PC"})
        second = client.post("/devices", json={"name": "Warehouse PC"})

        assert first.status_code == 200
        assert second.status_code == 200

    def test_a_member_can_list_devices_but_not_create_one(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)

        assert member.get("/devices").status_code == 200
        assert member.post("/devices", json={"name": "Laptop"}).status_code == 403

    def test_requires_authentication(self, anonymous_client):
        assert anonymous_client.get("/devices").status_code == 401

    def test_an_empty_name_is_rejected(self, client):
        assert client.post("/devices", json={"name": ""}).status_code == 422


class TestUpdate:
    def test_renaming_a_device(self, client):
        device_id = client.post("/devices", json={"name": "Warehouse PC"}).json()["id"]

        body = client.patch(f"/devices/{device_id}", json={"name": "Warehouse PC (old)"}).json()

        assert body["name"] == "Warehouse PC (old)"

    def test_changing_only_the_notes(self, client):
        device_id = client.post("/devices", json={"name": "Warehouse PC"}).json()["id"]

        body = client.patch(f"/devices/{device_id}", json={"notes": "replaced 2026-01"}).json()

        assert body["notes"] == "replaced 2026-01"
        assert body["name"] == "Warehouse PC"  # untouched

    def test_a_member_cannot_update_a_device(self, client, register_user, add_member):
        device_id = client.post("/devices", json={"name": "Warehouse PC"}).json()["id"]
        member = register_user("member@example.com")
        add_member(client, member)

        assert member.patch(f"/devices/{device_id}", json={"name": "Nope"}).status_code == 403

    def test_cannot_update_another_organizations_device(self, client, register_user):
        device_id = client.post("/devices", json={"name": "Warehouse PC"}).json()["id"]
        other = register_user("other@example.com")

        assert other.patch(f"/devices/{device_id}", json={"name": "Nope"}).status_code == 404

    def test_an_unknown_device_is_404(self, client):
        assert client.patch(f"/devices/{uuid.uuid4()}", json={"name": "x"}).status_code == 404


class TestDelete:
    def test_deleting_a_device(self, client):
        device_id = client.post("/devices", json={"name": "Warehouse PC"}).json()["id"]

        response = client.delete(f"/devices/{device_id}")

        assert response.status_code == 204
        assert device_id not in [d["id"] for d in client.get("/devices").json()]

    def test_a_member_cannot_delete_a_device(self, client, register_user, add_member):
        device_id = client.post("/devices", json={"name": "Warehouse PC"}).json()["id"]
        member = register_user("member@example.com")
        add_member(client, member)

        assert member.delete(f"/devices/{device_id}").status_code == 403

    def test_cannot_delete_another_organizations_device(self, client, register_user):
        device_id = client.post("/devices", json={"name": "Warehouse PC"}).json()["id"]
        other = register_user("other@example.com")

        assert other.delete(f"/devices/{device_id}").status_code == 404

    def test_an_unknown_device_is_404(self, client):
        assert client.delete(f"/devices/{uuid.uuid4()}").status_code == 404


class TestEntitlementLimit:
    """max_devices (app/models.py's Subscription): real, tested code, but no real
    organization ever has a limit set — Phase 14 decides actual numbers."""

    def test_unlimited_by_default(self, client):
        for i in range(3):
            assert client.post("/devices", json={"name": f"PC {i}"}).status_code == 200

    def test_creating_a_device_beyond_max_devices_is_blocked(self, client, db_session):
        from app.models import Subscription

        sub = db_session.query(Subscription).filter_by(organization_id=client.test_organization["id"]).one()
        sub.max_devices = 1
        db_session.commit()

        first = client.post("/devices", json={"name": "PC 1"})
        assert first.status_code == 200

        second = client.post("/devices", json={"name": "PC 2"})
        assert second.status_code == 402
        assert "1 device" in second.json()["detail"]

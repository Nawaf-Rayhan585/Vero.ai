"""Members: adding an existing account by email, role changes, removal/leaving, and the
"only an owner grants owner" / "an organization always has an owner" rules.

Every added member also belongs to their own organization (created when they registered),
so requests through their client explicitly select the organization under test via the
`add_member` fixture — otherwise "which organization did you mean" (400) would mask the
role check each test is actually exercising.
"""
import uuid


class TestList:
    def test_a_fresh_organization_lists_just_its_owner(self, client):
        members = client.get("/members").json()

        assert len(members) == 1
        assert members[0]["email"] == "owner@example.com"
        assert members[0]["role"] == "owner"

    def test_a_member_can_view_the_list_too(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)

        assert member.get("/members").status_code == 200

    def test_requires_authentication(self, anonymous_client):
        assert anonymous_client.get("/members").status_code == 401


class TestAdd:
    def test_adding_an_existing_user_by_email(self, client, register_user):
        register_user("new-member@example.com")

        response = client.post("/members", json={"email": "new-member@example.com", "role": "member"})

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "new-member@example.com"
        assert body["role"] == "member"
        assert {m["email"] for m in client.get("/members").json()} == {"owner@example.com", "new-member@example.com"}

    def test_the_added_user_can_now_see_the_organizations_cameras(self, client, register_user, add_member):
        client.post("/cameras", json={"name": "Front door", "rtsp_url": "rtsp://x/y"})
        member = register_user("new-member@example.com")
        add_member(client, member)

        cameras = member.get("/cameras").json()

        assert [c["name"] for c in cameras] == ["Front door"]

    def test_email_is_case_insensitive(self, client, register_user):
        register_user("new-member@example.com")

        response = client.post("/members", json={"email": "New-Member@Example.com", "role": "member"})

        assert response.status_code == 200

    def test_an_email_with_no_registered_account_is_rejected(self, client):
        response = client.post("/members", json={"email": "nobody@example.com", "role": "member"})
        assert response.status_code == 404

    def test_adding_the_same_person_twice_is_rejected(self, client, register_user):
        register_user("new-member@example.com")
        client.post("/members", json={"email": "new-member@example.com", "role": "member"})

        response = client.post("/members", json={"email": "new-member@example.com", "role": "member"})

        assert response.status_code == 409

    def test_default_role_is_member(self, client, register_user):
        register_user("new-member@example.com")

        body = client.post("/members", json={"email": "new-member@example.com"}).json()

        assert body["role"] == "member"

    def test_an_admin_can_add_a_plain_member(self, client, register_user, add_member):
        admin = register_user("admin@example.com")
        add_member(client, admin, "admin")
        register_user("newcomer@example.com")

        response = admin.post("/members", json={"email": "newcomer@example.com", "role": "member"})

        assert response.status_code == 200

    def test_an_admin_cannot_grant_the_owner_role(self, client, register_user, add_member):
        admin = register_user("admin@example.com")
        add_member(client, admin, "admin")
        register_user("newcomer@example.com")

        response = admin.post("/members", json={"email": "newcomer@example.com", "role": "owner"})

        assert response.status_code == 403

    def test_an_owner_can_grant_the_owner_role(self, client, register_user):
        register_user("newcomer@example.com")

        response = client.post("/members", json={"email": "newcomer@example.com", "role": "owner"})

        assert response.status_code == 200

    def test_a_plain_member_cannot_add_anyone(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)
        register_user("newcomer@example.com")

        response = member.post("/members", json={"email": "newcomer@example.com", "role": "member"})

        assert response.status_code == 403

    def test_requires_authentication(self, anonymous_client):
        assert anonymous_client.post("/members", json={"email": "x@example.com"}).status_code == 401


class TestRoleUpdate:
    def test_the_owner_can_promote_a_member_to_admin(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)
        user_id = member.test_user["id"]

        response = client.patch(f"/members/{user_id}", json={"role": "admin"})

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_a_member_cannot_change_anyones_role(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)
        owner_id = client.test_user["id"]

        response = member.patch(f"/members/{owner_id}", json={"role": "member"})

        assert response.status_code == 403

    def test_an_admin_cannot_promote_someone_to_owner(self, client, register_user, add_member):
        admin = register_user("admin@example.com")
        add_member(client, admin, "admin")
        newcomer = register_user("newcomer@example.com")
        add_member(client, newcomer)

        response = admin.patch(f"/members/{newcomer.test_user['id']}", json={"role": "owner"})

        assert response.status_code == 403

    def test_the_last_owner_cannot_be_demoted(self, client):
        owner_id = client.test_user["id"]

        response = client.patch(f"/members/{owner_id}", json={"role": "admin"})

        assert response.status_code == 409

    def test_demoting_one_of_two_owners_is_fine(self, client, register_user, add_member):
        second_owner = register_user("second-owner@example.com")
        add_member(client, second_owner, "owner")
        owner_id = client.test_user["id"]

        response = client.patch(f"/members/{owner_id}", json={"role": "admin"})

        assert response.status_code == 200

    def test_an_unknown_member_is_404(self, client):
        assert client.patch(f"/members/{uuid.uuid4()}", json={"role": "admin"}).status_code == 404


class TestRemove:
    def test_an_owner_can_remove_a_member(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)
        user_id = member.test_user["id"]

        response = client.delete(f"/members/{user_id}")

        assert response.status_code == 204
        assert user_id not in [m["user_id"] for m in client.get("/members").json()]

    def test_a_removed_members_access_is_gone(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)
        client.delete(f"/members/{member.test_user['id']}")

        response = member.get("/cameras")

        assert response.status_code == 404  # X-Organization-Id now names an org they're not in

    def test_a_member_can_remove_themself_leave(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)

        response = member.delete(f"/members/{member.test_user['id']}")

        assert response.status_code == 204

    def test_a_plain_member_cannot_remove_someone_else(self, client, register_user, add_member):
        member_a = register_user("member-a@example.com")
        add_member(client, member_a)
        member_b = register_user("member-b@example.com")
        add_member(client, member_b)

        response = member_b.delete(f"/members/{member_a.test_user['id']}")

        assert response.status_code == 403

    def test_the_last_owner_cannot_be_removed(self, client):
        owner_id = client.test_user["id"]

        response = client.delete(f"/members/{owner_id}")

        assert response.status_code == 409

    def test_removing_one_of_two_owners_is_fine(self, client, register_user, add_member):
        second_owner = register_user("second-owner@example.com")
        add_member(client, second_owner, "owner")
        owner_id = client.test_user["id"]

        assert client.delete(f"/members/{owner_id}").status_code == 204

    def test_an_unknown_member_is_404(self, client):
        assert client.delete(f"/members/{uuid.uuid4()}").status_code == 404

"""Organizations: creating a second one, renaming, and the role checks around renaming."""


class TestListAndCreate:
    def test_a_fresh_user_belongs_to_exactly_the_organization_they_registered(self, client):
        orgs = client.get("/organizations").json()

        assert len(orgs) == 1
        assert orgs[0]["organization"]["name"] == "Test Org"
        assert orgs[0]["role"] == "owner"

    def test_creating_a_second_organization_makes_the_creator_its_owner(self, client):
        response = client.post("/organizations", json={"name": "Second Org"})

        assert response.status_code == 200
        body = response.json()
        assert body["organization"]["name"] == "Second Org"
        assert body["role"] == "owner"

    def test_the_new_organization_gets_a_default_location(self, client):
        org_id = client.post("/organizations", json={"name": "Second Org"}).json()["organization"]["id"]

        locations = client.get("/locations", headers={"X-Organization-Id": org_id}).json()

        assert [loc["name"] for loc in locations] == ["Main location"]

    def test_now_belongs_to_both_organizations(self, client):
        client.post("/organizations", json={"name": "Second Org"})

        orgs = client.get("/organizations").json()

        assert sorted(o["organization"]["name"] for o in orgs) == ["Second Org", "Test Org"]

    def test_a_second_organization_does_not_see_the_first_ones_cameras(self, client):
        client.post("/cameras", json={"name": "Front door", "rtsp_url": "rtsp://x/y"})
        second_org_id = client.post("/organizations", json={"name": "Second Org"}).json()["organization"]["id"]

        cameras = client.get("/cameras", headers={"X-Organization-Id": second_org_id}).json()

        assert cameras == []

    def test_requires_authentication(self, anonymous_client):
        assert anonymous_client.get("/organizations").status_code == 401
        assert anonymous_client.post("/organizations", json={"name": "x"}).status_code == 401

    def test_an_empty_name_is_rejected(self, client):
        assert client.post("/organizations", json={"name": ""}).status_code == 422


class TestRename:
    def test_the_owner_can_rename_their_organization(self, client):
        org_id = client.test_organization["id"]

        response = client.patch(f"/organizations/{org_id}", json={"name": "Renamed"})

        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"
        assert client.get("/organizations").json()[0]["organization"]["name"] == "Renamed"

    def test_an_admin_can_rename_it_too(self, client, register_user):
        member = register_user("admin@example.com")
        client.post("/members", json={"email": "admin@example.com", "role": "admin"})
        org_id = client.test_organization["id"]

        response = member.patch(f"/organizations/{org_id}", json={"name": "Renamed by admin"})

        assert response.status_code == 200

    def test_a_plain_member_cannot_rename_it(self, client, register_user):
        member = register_user("member@example.com")
        client.post("/members", json={"email": "member@example.com", "role": "member"})
        org_id = client.test_organization["id"]

        response = member.patch(f"/organizations/{org_id}", json={"name": "Nope"})

        assert response.status_code == 403

    def test_a_non_member_gets_404_not_403(self, client, register_user):
        outsider = register_user("outsider@example.com")
        org_id = client.test_organization["id"]

        response = outsider.patch(f"/organizations/{org_id}", json={"name": "Nope"})

        assert response.status_code == 404

    def test_an_unknown_organization_id_is_404(self, client):
        import uuid

        assert client.patch(f"/organizations/{uuid.uuid4()}", json={"name": "x"}).status_code == 404

    def test_a_malformed_organization_id_is_404(self, client):
        assert client.patch("/organizations/not-a-uuid", json={"name": "x"}).status_code == 404

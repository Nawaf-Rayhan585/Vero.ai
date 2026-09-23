"""POST /auth/register, /login, /refresh, /logout, /change-password, GET /auth/me — real
HTTP requests against a real PostgreSQL database (via the `anonymous_client` and
`register_user` fixtures; `client` is already a registered, logged-in user)."""
import pytest

TEST_PASSWORD = "test-password-123"  # matches the `client` fixture's own registration (conftest.py)

VALID_REGISTRATION = {
    "email": "new-user@example.com",
    "password": "a-fine-password",
    "name": "New User",
    "organization_name": "New Org",
}


class TestRegister:
    def test_registering_returns_tokens_the_user_and_their_new_organization(self, anonymous_client):
        response = anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"] and body["refresh_token"]
        assert body["expires_in"] > 0
        assert body["user"]["email"] == "new-user@example.com"
        assert body["user"]["name"] == "New User"
        assert "password" not in body["user"] and "password_hash" not in body["user"]
        (membership,) = body["organizations"]
        assert membership["organization"]["name"] == "New Org"
        assert membership["role"] == "owner"

    def test_a_default_main_location_is_created(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)
        token = anonymous_client.post(
            "/auth/login", json={"email": VALID_REGISTRATION["email"], "password": VALID_REGISTRATION["password"]}
        ).json()["access_token"]
        anonymous_client.headers["Authorization"] = f"Bearer {token}"

        locations = anonymous_client.get("/locations").json()

        assert [loc["name"] for loc in locations] == ["Main location"]

    def test_the_email_is_normalized_to_lowercase(self, anonymous_client):
        anonymous_client.post("/auth/register", json={**VALID_REGISTRATION, "email": "Mixed.Case@Example.com"})

        response = anonymous_client.post(
            "/auth/login", json={"email": "mixed.case@example.com", "password": VALID_REGISTRATION["password"]}
        )

        assert response.status_code == 200

    def test_registering_the_same_email_twice_is_rejected(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        response = anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        assert response.status_code == 409

    def test_registering_the_same_email_with_different_case_is_still_rejected(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        response = anonymous_client.post("/auth/register", json={**VALID_REGISTRATION, "email": "NEW-USER@EXAMPLE.COM"})

        assert response.status_code == 409

    @pytest.mark.parametrize("password", ["short", "x" * 129, ""])
    def test_a_password_outside_the_length_bounds_is_rejected(self, anonymous_client, password):
        response = anonymous_client.post("/auth/register", json={**VALID_REGISTRATION, "password": password})
        assert response.status_code == 422

    @pytest.mark.parametrize("password", ["x" * 10, "x" * 128])
    def test_a_password_at_the_length_bounds_is_accepted(self, anonymous_client, password):
        response = anonymous_client.post("/auth/register", json={**VALID_REGISTRATION, "password": password})
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "field", ["email", "password", "name", "organization_name"]
    )
    def test_a_missing_required_field_is_rejected(self, anonymous_client, field):
        body = {k: v for k, v in VALID_REGISTRATION.items() if k != field}
        assert anonymous_client.post("/auth/register", json=body).status_code == 422

    def test_a_malformed_email_is_rejected(self, anonymous_client):
        response = anonymous_client.post("/auth/register", json={**VALID_REGISTRATION, "email": "not-an-email"})
        assert response.status_code == 422

    def test_the_password_is_never_returned_or_stored_in_plain_text(self, anonymous_client, db_session):
        import uuid as uuid_mod

        from app.models import User

        body = anonymous_client.post("/auth/register", json=VALID_REGISTRATION).json()

        row = db_session.get(User, uuid_mod.UUID(body["user"]["id"]))
        assert row.password_hash != VALID_REGISTRATION["password"]
        assert VALID_REGISTRATION["password"] not in row.password_hash


class TestLogin:
    def test_logging_in_with_the_right_password_succeeds(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        response = anonymous_client.post(
            "/auth/login", json={"email": VALID_REGISTRATION["email"], "password": VALID_REGISTRATION["password"]}
        )

        assert response.status_code == 200
        assert response.json()["user"]["email"] == VALID_REGISTRATION["email"]

    def test_the_wrong_password_is_rejected(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        response = anonymous_client.post(
            "/auth/login", json={"email": VALID_REGISTRATION["email"], "password": "wrong-password"}
        )

        assert response.status_code == 401

    def test_an_unregistered_email_is_rejected(self, anonymous_client):
        response = anonymous_client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever12"})
        assert response.status_code == 401

    def test_wrong_password_and_unknown_email_give_the_identical_response(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        wrong_password = anonymous_client.post(
            "/auth/login", json={"email": VALID_REGISTRATION["email"], "password": "wrong-password"}
        )
        unknown_email = anonymous_client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
        )

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()

    def test_login_email_is_case_insensitive(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)

        response = anonymous_client.post(
            "/auth/login", json={"email": "NEW-USER@EXAMPLE.COM", "password": VALID_REGISTRATION["password"]}
        )

        assert response.status_code == 200

    def test_each_login_issues_a_new_refresh_token(self, anonymous_client):
        anonymous_client.post("/auth/register", json=VALID_REGISTRATION)
        credentials = {"email": VALID_REGISTRATION["email"], "password": VALID_REGISTRATION["password"]}

        first = anonymous_client.post("/auth/login", json=credentials).json()
        second = anonymous_client.post("/auth/login", json=credentials).json()

        assert first["refresh_token"] != second["refresh_token"]
        # Both remain valid — logging in elsewhere doesn't silently sign out other sessions.
        assert anonymous_client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 200


class TestRefresh:
    @pytest.fixture
    def registered(self, anonymous_client):
        return anonymous_client.post("/auth/register", json=VALID_REGISTRATION).json()

    def test_a_valid_refresh_token_issues_a_new_pair(self, anonymous_client, registered):
        response = anonymous_client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]})

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] != registered["access_token"]
        assert body["refresh_token"] != registered["refresh_token"]
        assert body["user"]["id"] == registered["user"]["id"]

    def test_the_new_access_token_works(self, anonymous_client, registered):
        new_tokens = anonymous_client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]}).json()
        anonymous_client.headers["Authorization"] = f"Bearer {new_tokens['access_token']}"

        assert anonymous_client.get("/auth/me").status_code == 200

    def test_the_old_refresh_token_no_longer_works_once_rotated(self, anonymous_client, registered):
        anonymous_client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]})

        reuse = anonymous_client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]})

        assert reuse.status_code == 401

    def test_reusing_a_rotated_token_revokes_every_session_for_that_user(self, anonymous_client, registered):
        first_rotation = anonymous_client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]}).json()

        # The original token is presented again (a copy that leaked, or a client retrying
        # a request it thinks failed) — this is treated as theft.
        anonymous_client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]})

        # The token that *did* legitimately succeed from the rotation is now dead too.
        response = anonymous_client.post("/auth/refresh", json={"refresh_token": first_rotation["refresh_token"]})
        assert response.status_code == 401

    def test_an_unknown_refresh_token_is_rejected(self, anonymous_client):
        response = anonymous_client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert response.status_code == 401

    def test_a_malformed_refresh_token_is_rejected_not_a_500(self, anonymous_client):
        response = anonymous_client.post("/auth/refresh", json={"refresh_token": ""})
        assert response.status_code == 401

    def test_refreshing_after_logout_is_rejected(self, anonymous_client, registered):
        anonymous_client.headers["Authorization"] = f"Bearer {registered['access_token']}"
        anonymous_client.post("/auth/logout", json={"refresh_token": registered["refresh_token"]})

        response = anonymous_client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]})

        assert response.status_code == 401


class TestLogout:
    def test_logout_revokes_the_given_refresh_token(self, client):
        response = client.post("/auth/logout", json={"refresh_token": client.test_refresh_token})
        assert response.status_code == 204

        assert client.post("/auth/refresh", json={"refresh_token": client.test_refresh_token}).status_code == 401

    def test_logging_out_does_not_revoke_the_current_access_token(self, client):
        # Access tokens are short-lived and stateless (not tracked for revocation) — this
        # is a documented, deliberate limitation, not an oversight.
        client.post("/auth/logout", json={"refresh_token": client.test_refresh_token})

        assert client.get("/auth/me").status_code == 200

    def test_logout_requires_authentication(self, anonymous_client):
        response = anonymous_client.post("/auth/logout", json={"refresh_token": "whatever"})
        assert response.status_code == 401

    def test_logging_out_twice_is_not_an_error(self, client):
        client.post("/auth/logout", json={"refresh_token": client.test_refresh_token})

        response = client.post("/auth/logout", json={"refresh_token": client.test_refresh_token})

        assert response.status_code == 204

    def test_a_user_cannot_log_out_someone_elses_refresh_token(self, client, register_user):
        other = register_user("someone-else@example.com")

        response = client.post("/auth/logout", json={"refresh_token": other.test_refresh_token})
        assert response.status_code == 204  # silently a no-op, not an information leak

        # The other user's session is unaffected.
        assert other.post("/auth/refresh", json={"refresh_token": other.test_refresh_token}).status_code == 200


class TestMe:
    def test_returns_the_current_user_and_their_organizations(self, client):
        body = client.get("/auth/me").json()

        assert body["user"]["email"] == "owner@example.com"
        assert [m["organization"]["name"] for m in body["organizations"]] == ["Test Org"]
        assert body["organizations"][0]["role"] == "owner"

    def test_requires_authentication(self, anonymous_client):
        assert anonymous_client.get("/auth/me").status_code == 401

    def test_lists_every_organization_the_user_belongs_to(self, client, register_user):
        second_org_owner_token = register_user("dummy@example.com").test_user  # just to get a fresh org id via admin flow below
        # Have an admin of another org add our test user to it.
        other_org_admin = register_user("other-admin@example.com", organization_name="Other Org")
        other_org_admin.post("/members", json={"email": "owner@example.com", "role": "member"})

        body = client.get("/auth/me").json()

        org_names = sorted(m["organization"]["name"] for m in body["organizations"])
        assert org_names == ["Other Org", "Test Org"]


class TestChangePassword:
    def test_changes_the_password_and_returns_fresh_tokens(self, client):
        response = client.post(
            "/auth/change-password", json={"current_password": TEST_PASSWORD, "new_password": "a-new-password"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] and body["refresh_token"]

        # The old password no longer works; the new one does.
        assert client.post("/auth/login", json={"email": "owner@example.com", "password": TEST_PASSWORD}).status_code == 401
        assert client.post(
            "/auth/login", json={"email": "owner@example.com", "password": "a-new-password"}
        ).status_code == 200

    def test_the_wrong_current_password_is_rejected(self, client):
        response = client.post(
            "/auth/change-password", json={"current_password": "not-my-password", "new_password": "a-new-password"}
        )
        assert response.status_code == 401

    def test_other_sessions_refresh_tokens_are_revoked(self, anonymous_client):
        registered = anonymous_client.post("/auth/register", json=VALID_REGISTRATION).json()
        second_login = anonymous_client.post(
            "/auth/login", json={"email": VALID_REGISTRATION["email"], "password": VALID_REGISTRATION["password"]}
        ).json()
        anonymous_client.headers["Authorization"] = f"Bearer {registered['access_token']}"

        anonymous_client.post(
            "/auth/change-password",
            json={"current_password": VALID_REGISTRATION["password"], "new_password": "a-new-password"},
        )

        response = anonymous_client.post("/auth/refresh", json={"refresh_token": second_login["refresh_token"]})
        assert response.status_code == 401

    def test_requires_authentication(self, anonymous_client):
        response = anonymous_client.post(
            "/auth/change-password", json={"current_password": "x", "new_password": "a-new-password"}
        )
        assert response.status_code == 401

    def test_a_short_new_password_is_rejected(self, client):
        response = client.post("/auth/change-password", json={"current_password": TEST_PASSWORD, "new_password": "short"})
        assert response.status_code == 422

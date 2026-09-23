"""adopt_orphans: pre-Phase-10 cameras and jobs (no organization) are adopted into the
first account to ever register — one Location per distinct old location_label — and only
that first registration triggers it.

These tests insert rows the way they existed before Phase 10 (raw SQL, no organization/
location columns set) and then register through the real `/auth/register` endpoint, since
the `client` fixture would already have registered the first user before a test body runs.
"""
from datetime import datetime, timezone

from sqlalchemy import text

from app.auth import DEFAULT_LOCATION_NAME

REGISTRATION = {
    "email": "owner@example.com",
    "password": "test-password-123",
    "name": "Owner",
    "organization_name": "Test Org",
}


def _insert_orphan_camera(db_session, name: str, location_label: str | None) -> str:
    import uuid

    camera_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO cameras (id, name, rtsp_url, connection_status, location_label) "
            "VALUES (:id, :name, 'rtsp://x/y', 'unknown', :label)"
        ),
        {"id": camera_id, "name": name, "label": location_label},
    )
    db_session.commit()
    return str(camera_id)


def _insert_orphan_job(db_session, video_source: str) -> str:
    import uuid

    job_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO jobs (id, video_source, model_type, confidence_threshold, status, created_at) "
            "VALUES (:id, :src, 'yolo', 0.25, 'completed', :created_at)"
        ),
        {"id": job_id, "src": video_source, "created_at": datetime.now(timezone.utc)},
    )
    db_session.commit()
    return str(job_id)


def _register(anonymous_client, **overrides) -> dict:
    body = {**REGISTRATION, **overrides}
    response = anonymous_client.post("/auth/register", json=body)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    anonymous_client.headers["Authorization"] = f"Bearer {token}"
    return response.json()


class TestAdoptingCameras:
    def test_a_camera_with_no_location_label_goes_to_the_default_location(self, anonymous_client, db_session):
        camera_id = _insert_orphan_camera(db_session, "Old camera", None)

        _register(anonymous_client)

        body = anonymous_client.get(f"/cameras/{camera_id}").json()
        assert body["location_name"] == DEFAULT_LOCATION_NAME == "Main location"

    def test_a_camera_with_a_location_label_gets_a_real_location_of_that_name(self, anonymous_client, db_session):
        camera_id = _insert_orphan_camera(db_session, "Loading dock cam", "Warehouse")

        _register(anonymous_client)

        body = anonymous_client.get(f"/cameras/{camera_id}").json()
        assert body["location_name"] == "Warehouse"

    def test_cameras_sharing_a_label_share_one_location(self, anonymous_client, db_session):
        cam_a = _insert_orphan_camera(db_session, "Cam A", "Warehouse")
        cam_b = _insert_orphan_camera(db_session, "Cam B", "Warehouse")

        _register(anonymous_client)

        a = anonymous_client.get(f"/cameras/{cam_a}").json()
        b = anonymous_client.get(f"/cameras/{cam_b}").json()
        assert a["location_id"] == b["location_id"]
        # "Main location" (created at registration, regardless of adoption) + "Warehouse".
        assert sorted(loc["name"] for loc in anonymous_client.get("/locations").json()) == ["Main location", "Warehouse"]

    def test_cameras_with_different_labels_get_different_locations(self, anonymous_client, db_session):
        cam_a = _insert_orphan_camera(db_session, "Cam A", "Warehouse")
        cam_b = _insert_orphan_camera(db_session, "Cam B", "Office")

        _register(anonymous_client)

        a = anonymous_client.get(f"/cameras/{cam_a}").json()
        b = anonymous_client.get(f"/cameras/{cam_b}").json()
        assert a["location_id"] != b["location_id"]
        assert sorted(loc["name"] for loc in anonymous_client.get("/locations").json()) == ["Main location", "Office", "Warehouse"]

    def test_a_mix_of_labelled_and_unlabelled_cameras(self, anonymous_client, db_session):
        labelled = _insert_orphan_camera(db_session, "Labelled", "Warehouse")
        unlabelled = _insert_orphan_camera(db_session, "Unlabelled", None)

        _register(anonymous_client)

        a = anonymous_client.get(f"/cameras/{labelled}").json()
        b = anonymous_client.get(f"/cameras/{unlabelled}").json()
        assert a["location_name"] == "Warehouse"
        assert b["location_name"] == "Main location"

    def test_an_empty_string_label_is_treated_the_same_as_no_label(self, anonymous_client, db_session):
        camera_id = _insert_orphan_camera(db_session, "Old camera", "")

        _register(anonymous_client)

        body = anonymous_client.get(f"/cameras/{camera_id}").json()
        assert body["location_name"] == "Main location"

    def test_all_the_cameras_original_fields_survive_adoption_untouched(self, anonymous_client, db_session):
        camera_id = _insert_orphan_camera(db_session, "Loading dock cam", "Warehouse")

        _register(anonymous_client)

        body = anonymous_client.get(f"/cameras/{camera_id}").json()
        assert body["name"] == "Loading dock cam"
        assert body["rtsp_url"] == "rtsp://x/y"
        assert body["enabled_modules"] == ["people"]  # the server default, untouched


class TestAdoptingJobs:
    def test_an_orphan_job_is_attached_to_the_first_organization(self, anonymous_client, db_session):
        job_id = _insert_orphan_job(db_session, "video.mp4")

        _register(anonymous_client)

        response = anonymous_client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["video_source"] == "video.mp4"

    def test_several_orphan_jobs_are_all_adopted(self, anonymous_client, db_session):
        _insert_orphan_job(db_session, "a.mp4")
        _insert_orphan_job(db_session, "b.mp4")

        _register(anonymous_client)

        assert {j["video_source"] for j in anonymous_client.get("/jobs").json()} == {"a.mp4", "b.mp4"}


class TestOnlyTheFirstRegistrationAdopts:
    def test_a_second_registration_does_not_adopt_a_still_orphaned_camera(self, anonymous_client, register_user, db_session):
        _register(anonymous_client)  # first: nothing to adopt yet, but "first" is now taken
        camera_id = _insert_orphan_camera(db_session, "Too late", None)

        second = register_user("second@example.com", organization_name="Second Org")

        assert second.get(f"/cameras/{camera_id}").status_code == 404
        assert anonymous_client.get(f"/cameras/{camera_id}").status_code == 404  # nobody's, until fixed by hand

    def test_a_second_organization_created_by_the_first_user_does_not_re_adopt_anything(self, anonymous_client, db_session):
        camera_id = _insert_orphan_camera(db_session, "Old camera", None)
        registered = _register(anonymous_client)  # adopts it into Test Org
        test_org_id = registered["organizations"][0]["organization"]["id"]

        second_org = anonymous_client.post("/organizations", json={"name": "Second Org"}).json()["organization"]["id"]

        cameras_in_second_org = anonymous_client.get("/cameras", headers={"X-Organization-Id": second_org}).json()
        assert cameras_in_second_org == []
        # It's still exactly where the first adoption put it — belonging to two
        # organizations now makes the header required to say which one is meant.
        response = anonymous_client.get(f"/cameras/{camera_id}", headers={"X-Organization-Id": test_org_id})
        assert response.status_code == 200

    def test_with_nothing_to_adopt_registration_is_unaffected(self, anonymous_client):
        response = anonymous_client.post("/auth/register", json=REGISTRATION)

        assert response.status_code == 200
        anonymous_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        assert anonymous_client.get("/cameras").json() == []
        assert anonymous_client.get("/jobs").json() == []

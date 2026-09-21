"""GET /events against seeded rows: filters, ordering, and cursor pagination."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

T0 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


def _create_camera(client, name="Front door") -> str:
    return client.post("/cameras", json={"name": name, "rtsp_url": "rtsp://192.0.2.10:554/stream1"}).json()["id"]


def _get(client, **params):
    response = client.get("/events", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_no_events_is_an_empty_list(client):
    assert _get(client) == {"events": [], "next_before": None}


def test_an_event_comes_back_with_every_field_and_its_camera_name(client, add_event):
    camera_id = _create_camera(client, "Loading dock")
    line_id = uuid.uuid4()
    add_event(
        camera_id, "line_crossed", T0, category="person", direction="in", subject_id=line_id, subject_name="Gate"
    )

    (event,) = _get(client)["events"]

    assert set(event) == {
        "id", "camera_id", "camera_name", "occurred_at", "event_type", "category", "direction",
        "subject_id", "subject_name", "value", "detail",
    }
    assert event["camera_name"] == "Loading dock"
    assert event["camera_id"] == camera_id
    assert (event["event_type"], event["category"], event["direction"]) == ("line_crossed", "person", "in")
    assert (event["subject_id"], event["subject_name"]) == (str(line_id), "Gate")
    assert event["value"] is None and event["detail"] is None
    assert datetime.fromisoformat(event["occurred_at"]) == T0


def test_a_read_event_carries_its_value_and_detail(client, add_event):
    camera_id = _create_camera(client)
    add_event(camera_id, "read", T0, category="qr", value="https://vero.ai/t/42", detail="QR Code")

    (event,) = _get(client)["events"]

    assert (event["category"], event["value"], event["detail"]) == ("qr", "https://vero.ai/t/42", "QR Code")


def test_newest_first(client, add_event):
    camera_id = _create_camera(client)
    for i in (2, 0, 3, 1):
        add_event(camera_id, "read", T0 + timedelta(minutes=i), category="ocr", value=f"v{i}")

    assert [e["value"] for e in _get(client)["events"]] == ["v3", "v2", "v1", "v0"]


class TestFilters:
    @pytest.fixture
    def seeded(self, client, add_event):
        a, b = _create_camera(client, "A"), _create_camera(client, "B")
        add_event(a, "line_crossed", T0, category="person", direction="in", subject_name="L")
        add_event(a, "line_crossed", T0 + timedelta(minutes=1), category="vehicle", direction="out", subject_name="L")
        add_event(a, "zone_entered", T0 + timedelta(minutes=2), category="person", subject_name="Z")
        add_event(b, "read", T0 + timedelta(minutes=3), category="qr", value="q")
        add_event(b, "tracking_started", T0 + timedelta(minutes=4))
        return a, b

    def test_by_camera(self, client, seeded):
        a, b = seeded
        assert len(_get(client, camera_id=a)["events"]) == 3
        assert len(_get(client, camera_id=b)["events"]) == 2

    def test_by_type(self, client, seeded):
        assert [e["event_type"] for e in _get(client, event_type="line_crossed")["events"]] == ["line_crossed"] * 2
        assert len(_get(client, event_type="tracking_started")["events"]) == 1

    def test_by_several_types_at_once(self, client, seeded):
        events = _get(client, event_type=["zone_entered", "read"])["events"]

        assert sorted(e["event_type"] for e in events) == ["read", "zone_entered"]

    def test_several_types_with_one_unknown_is_rejected(self, client, seeded):
        assert client.get("/events", params={"event_type": ["read", "nonsense"]}).status_code == 422

    def test_by_category(self, client, seeded):
        assert len(_get(client, category="person")["events"]) == 2
        assert len(_get(client, category="vehicle")["events"]) == 1

    def test_filters_combine(self, client, seeded):
        a, _b = seeded
        events = _get(client, camera_id=a, event_type="line_crossed", category="vehicle")["events"]
        assert [(e["category"], e["direction"]) for e in events] == [("vehicle", "out")]

    def test_since_is_inclusive_and_until_is_exclusive(self, client, seeded):
        events = _get(client, since=(T0 + timedelta(minutes=1)).isoformat(), until=(T0 + timedelta(minutes=3)).isoformat())["events"]

        assert [e["event_type"] for e in events] == ["zone_entered", "line_crossed"]  # minutes 2 then 1

    def test_a_timestamp_without_a_zone_is_taken_as_utc(self, client, seeded):
        events = _get(client, since="2026-03-10T12:03:00")["events"]  # no offset

        assert len(events) == 2  # minutes 3 and 4

    def test_a_timestamp_with_an_offset_is_converted(self, client, seeded):
        # 18:03+06:00 is 12:03 UTC.
        events = _get(client, since="2026-03-10T18:03:00+06:00")["events"]

        assert len(events) == 2

    def test_nothing_matching_is_an_empty_list(self, client, seeded):
        assert _get(client, category="ocr")["events"] == []


class TestPagination:
    def test_pages_are_stable_complete_and_duplicate_free(self, client, add_event):
        camera_id = _create_camera(client)
        # Many events share a timestamp, so the id tiebreak is what keeps the pages honest.
        for i in range(25):
            add_event(camera_id, "read", T0 + timedelta(seconds=i // 5), category="ocr", value=f"v{i}")

        seen, before = [], None
        for _ in range(10):
            page = _get(client, limit=10, **({"before": before} if before else {}))
            seen += [e["id"] for e in page["events"]]
            before = page["next_before"]
            if before is None:
                break

        assert len(seen) == 25 and len(set(seen)) == 25

    def test_the_last_page_has_no_cursor(self, client, add_event):
        camera_id = _create_camera(client)
        for i in range(3):
            add_event(camera_id, "read", T0 + timedelta(seconds=i), category="ocr", value=str(i))

        page = _get(client, limit=3)

        assert len(page["events"]) == 3 and page["next_before"] is None

    def test_a_full_page_with_more_behind_it_has_a_cursor(self, client, add_event):
        camera_id = _create_camera(client)
        for i in range(4):
            add_event(camera_id, "read", T0 + timedelta(seconds=i), category="ocr", value=str(i))

        page = _get(client, limit=3)

        assert len(page["events"]) == 3 and page["next_before"] is not None
        assert [e["value"] for e in _get(client, limit=3, before=page["next_before"])["events"]] == ["0"]

    def test_new_events_arriving_between_pages_do_not_disturb_paging(self, client, add_event):
        camera_id = _create_camera(client)
        for i in range(6):
            add_event(camera_id, "read", T0 + timedelta(seconds=i), category="ocr", value=f"v{i}")
        first = _get(client, limit=3)
        assert [e["value"] for e in first["events"]] == ["v5", "v4", "v3"]

        add_event(camera_id, "read", T0 + timedelta(minutes=5), category="ocr", value="newest")  # arrives now

        second = _get(client, limit=3, before=first["next_before"])
        assert [e["value"] for e in second["events"]] == ["v2", "v1", "v0"]  # no repeats, none skipped

    def test_the_cursor_works_alongside_filters(self, client, add_event):
        camera_id = _create_camera(client)
        for i in range(6):
            add_event(camera_id, "read", T0 + timedelta(seconds=i), category="qr", value=f"q{i}")
            add_event(camera_id, "read", T0 + timedelta(seconds=i), category="ocr", value=f"o{i}")

        first = _get(client, category="qr", limit=4)
        second = _get(client, category="qr", limit=4, before=first["next_before"])

        assert [e["value"] for e in first["events"] + second["events"]] == [f"q{i}" for i in (5, 4, 3, 2, 1, 0)]

    def test_the_default_page_size_is_50(self, client, add_event):
        camera_id = _create_camera(client)
        for i in range(60):
            add_event(camera_id, "read", T0 + timedelta(seconds=i), category="ocr", value=str(i))

        assert len(_get(client)["events"]) == 50


class TestValidation:
    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"limit": "many"}])
    def test_a_bad_limit_is_rejected(self, client, params):
        assert client.get("/events", params=params).status_code == 422

    def test_an_unknown_event_type_is_rejected(self, client):
        assert client.get("/events", params={"event_type": "person_teleported"}).status_code == 422

    def test_every_event_type_the_tracker_emits_is_accepted(self, client):
        from app.events import EVENT_TYPES

        for event_type in EVENT_TYPES:
            assert client.get("/events", params={"event_type": event_type}).status_code == 200

    @pytest.mark.parametrize("cursor", ["garbage", "2026-03-10T12:00:00Z|not-a-uuid", "|", "not-a-date|" + str(uuid.uuid4())])
    def test_a_malformed_cursor_is_rejected(self, client, cursor):
        assert client.get("/events", params={"before": cursor}).status_code == 422

    def test_an_unknown_camera_is_a_404(self, client):
        assert client.get("/events", params={"camera_id": str(uuid.uuid4())}).status_code == 404

    def test_a_malformed_camera_id_is_a_404(self, client):
        assert client.get("/events", params={"camera_id": "nope"}).status_code == 404

    def test_a_malformed_timestamp_is_rejected(self, client):
        assert client.get("/events", params={"since": "yesterday"}).status_code == 422


def test_history_survives_deleting_the_line_it_names(client, add_event):
    camera_id = _create_camera(client)
    line = client.post(f"/cameras/{camera_id}/lines", json={"name": "Old entrance", "x1": 0.5, "y1": 0, "x2": 0.5, "y2": 1}).json()
    add_event(camera_id, "line_crossed", T0, category="person", direction="in", subject_id=line["id"], subject_name="Old entrance")

    assert client.delete(f"/lines/{line['id']}").status_code == 204

    (event,) = _get(client)["events"]
    assert event["subject_name"] == "Old entrance"  # the name it had at the time
    assert event["subject_id"] == line["id"]


def test_deleting_a_camera_deletes_its_events_but_not_other_cameras(client, add_event):
    a, b = _create_camera(client, "A"), _create_camera(client, "B")
    add_event(a, "read", T0, category="qr", value="gone")
    add_event(b, "read", T0, category="qr", value="kept")

    assert client.delete(f"/cameras/{a}").status_code == 204

    assert [e["value"] for e in _get(client)["events"]] == ["kept"]

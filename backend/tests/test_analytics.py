"""Historical analytics. Data is seeded straight into the events table with chosen
timestamps, so every expected number is exact and known rather than measured.
"""
import uuid
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest

from app.analytics import overlap_seconds, tracked_intervals
from app.events import close_dangling_sessions
from app.models import Event

UTC = timezone.utc
T0 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)
M = timedelta(minutes=1)
H = timedelta(hours=1)


def _create_camera(client, name="Front door", rtsp_url="rtsp://127.0.0.1:1/unused") -> str:
    return client.post("/cameras", json={"name": name, "rtsp_url": rtsp_url}).json()["id"]


def _get(client, path, expect=200, **params):
    response = client.get(f"/analytics/{path}", params=params)
    assert response.status_code == expect, response.text
    return response.json()


def _iso(moment: datetime) -> str:
    return moment.isoformat()


# -- uptime: pure ----------------------------------------------------------------------------


class TestTrackedIntervals:
    SINCE, END = T0, T0 + 10 * H

    def test_a_start_and_stop_is_one_interval(self):
        events = [(T0 + 1 * H, "tracking_started"), (T0 + 2 * H, "tracking_stopped")]

        assert tracked_intervals(None, events, self.SINCE, self.END) == [(T0 + 1 * H, T0 + 2 * H)]

    def test_already_running_at_the_start_of_the_range(self):
        events = [(T0 + 2 * H, "tracking_stopped")]

        assert tracked_intervals("tracking_started", events, self.SINCE, self.END) == [(T0, T0 + 2 * H)]

    def test_a_resume_after_a_prior_running_state_also_counts(self):
        assert tracked_intervals("tracking_resumed", [], self.SINCE, self.END) == [(T0, self.END)]

    @pytest.mark.parametrize("prior", [None, "tracking_stopped", "tracking_error", "tracking_reconnecting"])
    def test_not_running_at_the_start_means_no_interval_until_a_start(self, prior):
        assert tracked_intervals(prior, [], self.SINCE, self.END) == []

    def test_a_start_with_no_stop_runs_to_the_end_of_the_range(self):
        events = [(T0 + 3 * H, "tracking_started")]

        assert tracked_intervals(None, events, self.SINCE, self.END) == [(T0 + 3 * H, self.END)]

    def test_reconnecting_ends_the_interval_and_resuming_starts_a_new_one(self):
        events = [
            (T0 + 0 * M, "tracking_started"),
            (T0 + 20 * M, "tracking_reconnecting"),
            (T0 + 30 * M, "tracking_resumed"),
            (T0 + 50 * M, "tracking_stopped"),
        ]

        assert tracked_intervals(None, events, self.SINCE, self.END) == [(T0, T0 + 20 * M), (T0 + 30 * M, T0 + 50 * M)]

    def test_an_error_ends_the_interval(self):
        events = [(T0 + 1 * H, "tracking_started"), (T0 + 2 * H, "tracking_error")]

        assert tracked_intervals(None, events, self.SINCE, self.END) == [(T0 + 1 * H, T0 + 2 * H)]

    def test_a_stop_with_nothing_open_is_ignored(self):
        assert tracked_intervals(None, [(T0 + 1 * H, "tracking_stopped")], self.SINCE, self.END) == []

    def test_a_second_start_while_running_does_not_restart_the_interval(self):
        events = [(T0 + 1 * H, "tracking_started"), (T0 + 2 * H, "tracking_started"), (T0 + 3 * H, "tracking_stopped")]

        assert tracked_intervals(None, events, self.SINCE, self.END) == [(T0 + 1 * H, T0 + 3 * H)]

    def test_zero_length_intervals_are_dropped(self):
        events = [(T0 + 1 * H, "tracking_started"), (T0 + 1 * H, "tracking_stopped")]

        assert tracked_intervals(None, events, self.SINCE, self.END) == []

    def test_several_sessions(self):
        events = [
            (T0 + 1 * H, "tracking_started"),
            (T0 + 2 * H, "tracking_stopped"),
            (T0 + 5 * H, "tracking_started"),
            (T0 + 6 * H, "tracking_stopped"),
        ]

        assert len(tracked_intervals(None, events, self.SINCE, self.END)) == 2


class TestOverlapSeconds:
    def test_full_partial_and_no_overlap(self):
        intervals = [(T0, T0 + 1 * H)]

        assert overlap_seconds(intervals, T0, T0 + 1 * H) == 3600
        assert overlap_seconds(intervals, T0 + 30 * M, T0 + 2 * H) == 1800
        assert overlap_seconds(intervals, T0 - 1 * H, T0 + 15 * M) == 900
        assert overlap_seconds(intervals, T0 + 2 * H, T0 + 3 * H) == 0
        assert overlap_seconds(intervals, T0 - 2 * H, T0 - 1 * H) == 0

    def test_several_intervals_add_up(self):
        intervals = [(T0, T0 + 10 * M), (T0 + 30 * M, T0 + 40 * M)]

        assert overlap_seconds(intervals, T0, T0 + 1 * H) == 1200


# -- summary -----------------------------------------------------------------------------------


class TestSummary:
    @pytest.fixture
    def seeded(self, client, add_event):
        a, b = _create_camera(client, "A"), _create_camera(client, "B")
        gate, door, checkout = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        for _ in range(3):
            add_event(a, "line_crossed", T0 + 5 * M, category="person", direction="in", subject_id=gate, subject_name="Gate")
        add_event(a, "line_crossed", T0 + 6 * M, category="person", direction="out", subject_id=gate, subject_name="Gate")
        for _ in range(2):
            add_event(a, "line_crossed", T0 + 7 * M, category="vehicle", direction="in", subject_id=gate, subject_name="Gate")
        add_event(b, "line_crossed", T0 + 8 * M, category="person", direction="in", subject_id=door, subject_name="Door")
        add_event(a, "zone_entered", T0 + 9 * M, category="person", subject_id=checkout, subject_name="Checkout")
        add_event(a, "zone_entered", T0 + 10 * M, category="person", subject_id=checkout, subject_name="Checkout")
        add_event(a, "zone_exited", T0 + 11 * M, category="person", subject_id=checkout, subject_name="Checkout")
        add_event(a, "read", T0 + 12 * M, category="qr", value="x")
        add_event(a, "read", T0 + 13 * M, category="qr", value="y")
        add_event(b, "read", T0 + 14 * M, category="ocr", value="TEXT")
        add_event(a, "tracking_started", T0)
        add_event(a, "tracking_stopped", T0 + 30 * M)
        return a, b

    def test_totals_across_all_cameras(self, client, seeded):
        summary = _get(client, "summary", since=_iso(T0), until=_iso(T0 + 1 * H))

        assert (summary["people_in"], summary["people_out"]) == (4, 1)
        assert (summary["vehicle_in"], summary["vehicle_out"]) == (2, 0)
        assert summary["reads"] == {"qr": 2, "barcode": 0, "ocr": 1}

    def test_the_breakdown_by_line(self, client, seeded):
        lines = {row["name"]: row for row in _get(client, "summary", since=_iso(T0), until=_iso(T0 + 1 * H))["lines"]}

        assert (lines["Gate"]["people_in"], lines["Gate"]["people_out"], lines["Gate"]["vehicle_in"]) == (3, 1, 2)
        assert (lines["Door"]["people_in"], lines["Door"]["people_out"]) == (1, 0)

    def test_the_breakdown_by_zone(self, client, seeded):
        (zone,) = _get(client, "summary", since=_iso(T0), until=_iso(T0 + 1 * H))["zones"]

        assert (zone["name"], zone["entered"], zone["exited"]) == ("Checkout", 2, 1)

    def test_one_camera(self, client, seeded):
        a, b = seeded

        only_b = _get(client, "summary", camera_id=b, since=_iso(T0), until=_iso(T0 + 1 * H))

        assert (only_b["people_in"], only_b["vehicle_in"]) == (1, 0)
        assert only_b["reads"] == {"qr": 0, "barcode": 0, "ocr": 1}
        assert only_b["zones"] == []

    def test_the_range_edges_since_inclusive_until_exclusive(self, client, seeded):
        # People-in events sit at T0+5m (x3) and T0+8m (x1).
        assert _get(client, "summary", since=_iso(T0 + 5 * M), until=_iso(T0 + 8 * M))["people_in"] == 3
        assert _get(client, "summary", since=_iso(T0 + 5 * M), until=_iso(T0 + 8 * M + timedelta(seconds=1)))["people_in"] == 4
        assert _get(client, "summary", since=_iso(T0 + 5 * M + timedelta(seconds=1)), until=_iso(T0 + 1 * H))["people_in"] == 1

    def test_an_empty_range_is_all_zeros_not_an_error(self, client, seeded):
        summary = _get(client, "summary", since=_iso(T0 + 5 * H), until=_iso(T0 + 6 * H))

        assert (summary["people_in"], summary["people_out"], summary["vehicle_in"], summary["vehicle_out"]) == (0, 0, 0, 0)
        assert summary["lines"] == [] and summary["zones"] == []
        assert summary["reads"] == {"qr": 0, "barcode": 0, "ocr": 0}

    def test_tracked_seconds_come_from_the_uptime_events(self, client, seeded):
        assert _get(client, "summary", since=_iso(T0), until=_iso(T0 + 1 * H))["tracked_seconds"] == 1800

    def test_tracked_seconds_are_clipped_to_the_range(self, client, seeded):
        assert _get(client, "summary", since=_iso(T0 + 10 * M), until=_iso(T0 + 20 * M))["tracked_seconds"] == 600

    def test_until_defaults_to_now(self, client, seeded):
        summary = _get(client, "summary", since=_iso(T0 - 1 * H))

        assert summary["people_in"] == 4
        assert datetime.fromisoformat(summary["until"]) > T0 + 1 * H

    def test_the_time_zone_of_the_request_does_not_change_totals(self, client, seeded):
        assert _get(client, "summary", since="2026-03-10T18:00:00+06:00", until="2026-03-10T19:00:00+06:00")["people_in"] == 4

    def test_validation(self, client, seeded):
        assert client.get("/analytics/summary").status_code == 422  # since is required
        assert client.get("/analytics/summary", params={"since": _iso(T0), "until": _iso(T0)}).status_code == 422
        assert client.get("/analytics/summary", params={"since": _iso(T0 + 1 * H), "until": _iso(T0)}).status_code == 422
        assert client.get("/analytics/summary", params={"since": _iso(T0), "camera_id": str(uuid.uuid4())}).status_code == 404


# -- time series ---------------------------------------------------------------------------------


class TestTimeseries:
    def test_hourly_buckets_are_zero_filled_and_counted(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", T0 + 10 * M, category="person", direction="in")
        add_event(camera_id, "line_crossed", T0 + 50 * M, category="person", direction="out")
        add_event(camera_id, "line_crossed", T0 + 2 * H + 30 * M, category="vehicle", direction="in")

        series = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 3 * H), bucket="hour", tz="UTC")

        points = series["points"]
        assert len(points) == 3
        assert [(p["people_in"], p["people_out"], p["vehicle_in"]) for p in points] == [(1, 1, 0), (0, 0, 0), (0, 0, 1)]
        assert datetime.fromisoformat(points[0]["start"]) == T0
        assert datetime.fromisoformat(points[0]["end"]) == T0 + 1 * H
        assert datetime.fromisoformat(points[2]["start"]) == T0 + 2 * H
        assert (series["bucket"], series["tz"]) == ("hour", "UTC")

    def test_every_kind_of_count_lands_in_its_own_field(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "zone_entered", T0 + 1 * M, category="person")
        add_event(camera_id, "zone_entered", T0 + 2 * M, category="person")
        add_event(camera_id, "zone_exited", T0 + 3 * M, category="person")
        add_event(camera_id, "read", T0 + 4 * M, category="qr", value="a")
        add_event(camera_id, "read", T0 + 5 * M, category="ocr", value="b")
        add_event(camera_id, "tracking_started", T0 + 6 * M)  # not a count of anything

        (point,) = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 1 * H), tz="UTC")["points"]

        assert (point["zone_entered"], point["zone_exited"], point["reads"]) == (2, 1, 2)
        assert (point["people_in"], point["vehicle_in"]) == (0, 0)

    def test_the_bucket_end_is_exclusive(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", T0 + 1 * H, category="person", direction="in")  # exactly on a boundary

        points = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 2 * H), tz="UTC")["points"]

        assert [p["people_in"] for p in points] == [0, 1]

    def test_events_outside_the_range_are_not_counted(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", T0 - 1 * M, category="person", direction="in")
        add_event(camera_id, "line_crossed", T0 + 1 * H, category="person", direction="in")

        points = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 1 * H), tz="UTC")["points"]

        assert [p["people_in"] for p in points] == [0]

    def test_a_range_that_does_not_start_on_a_bucket_boundary(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", T0 + 20 * M, category="person", direction="in")

        points = _get(client, "timeseries", since=_iso(T0 + 15 * M), until=_iso(T0 + 1 * H + 15 * M), tz="UTC")["points"]

        assert len(points) == 2
        assert datetime.fromisoformat(points[0]["start"]) == T0  # the bucket that contains `since`
        assert points[0]["people_in"] == 1

    def test_one_camera_or_all(self, client, add_event):
        a, b = _create_camera(client, "A"), _create_camera(client, "B")
        add_event(a, "line_crossed", T0 + 1 * M, category="person", direction="in")
        add_event(b, "line_crossed", T0 + 1 * M, category="person", direction="in")
        add_event(b, "line_crossed", T0 + 2 * M, category="person", direction="in")

        def total(**extra):
            return _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 1 * H), tz="UTC", **extra)["points"][0]["people_in"]

        assert (total(), total(camera_id=a), total(camera_id=b)) == (3, 1, 2)

    def test_daily_buckets(self, client, add_event):
        camera_id = _create_camera(client)
        day1, day2 = datetime(2026, 3, 10, 9, tzinfo=UTC), datetime(2026, 3, 11, 9, tzinfo=UTC)
        add_event(camera_id, "line_crossed", day1, category="person", direction="in")
        add_event(camera_id, "line_crossed", day1 + 2 * H, category="person", direction="in")
        add_event(camera_id, "line_crossed", day2, category="person", direction="in")

        series = _get(
            client, "timeseries", since="2026-03-10T00:00:00Z", until="2026-03-13T00:00:00Z", bucket="day", tz="UTC"
        )

        assert [p["people_in"] for p in series["points"]] == [2, 1, 0]

    # -- time zones and DST --------------------------------------------------------------------

    def test_an_event_just_before_utc_midnight_lands_in_the_next_local_day_east_of_utc(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", datetime(2026, 3, 10, 23, 30, tzinfo=UTC), category="person", direction="in")

        # Dhaka is UTC+6: local days start at 18:00 UTC.
        series = _get(
            client, "timeseries", since="2026-03-09T18:00:00Z", until="2026-03-12T18:00:00Z", bucket="day", tz="Asia/Dhaka"
        )

        assert [datetime.fromisoformat(p["start"]) for p in series["points"]] == [
            datetime(2026, 3, 9, 18, tzinfo=UTC),
            datetime(2026, 3, 10, 18, tzinfo=UTC),
            datetime(2026, 3, 11, 18, tzinfo=UTC),
        ]
        assert [p["people_in"] for p in series["points"]] == [0, 1, 0]  # 05:30 local on the 11th

    def test_the_same_event_lands_in_the_previous_local_day_west_of_utc(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", datetime(2026, 3, 3, 2, 0, tzinfo=UTC), category="person", direction="in")

        # New York is UTC-5 until the clocks go forward on 8 March: 02:00 UTC on the 3rd is
        # 21:00 on the 2nd.
        series = _get(
            client, "timeseries", since="2026-03-02T05:00:00Z", until="2026-03-04T05:00:00Z", bucket="day", tz="America/New_York"
        )

        assert [p["people_in"] for p in series["points"]] == [1, 0]

    def test_a_half_hour_offset_time_zone(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", datetime(2026, 3, 10, 18, 40, tzinfo=UTC), category="person", direction="in")

        # India is UTC+5:30: that instant is 00:10 on the 11th local.
        series = _get(
            client, "timeseries", since="2026-03-10T18:30:00Z", until="2026-03-11T18:30:00Z", bucket="day", tz="Asia/Kolkata"
        )

        assert len(series["points"]) == 1
        assert datetime.fromisoformat(series["points"][0]["start"]) == datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        assert series["points"][0]["people_in"] == 1

    def test_the_day_the_clocks_go_forward_is_23_hours_long(self, client):
        camera_id = _create_camera(client)  # noqa: F841  (no events needed)

        day = _get(
            client, "timeseries", since="2026-03-08T05:00:00Z", until="2026-03-09T04:00:00Z", bucket="day", tz="America/New_York"
        )["points"]
        hours = _get(
            client, "timeseries", since="2026-03-08T05:00:00Z", until="2026-03-09T04:00:00Z", bucket="hour", tz="America/New_York"
        )["points"]

        assert len(day) == 1
        assert datetime.fromisoformat(day[0]["end"]) - datetime.fromisoformat(day[0]["start"]) == timedelta(hours=23)
        assert len(hours) == 23  # the skipped 02:00 hour is not offered as a bucket
        assert all(datetime.fromisoformat(h["end"]) - datetime.fromisoformat(h["start"]) == timedelta(hours=1) for h in hours)

    def test_the_day_the_clocks_go_back_is_25_hours_long(self, client):
        day = _get(
            client, "timeseries", since="2026-11-01T04:00:00Z", until="2026-11-02T05:00:00Z", bucket="day", tz="America/New_York"
        )["points"]

        assert len(day) == 1
        assert datetime.fromisoformat(day[0]["end"]) - datetime.fromisoformat(day[0]["start"]) == timedelta(hours=25)

    def test_a_repeated_dst_hour_merges_into_one_bucket(self, client, add_event):
        # Documented limitation: local 01:00-02:00 happens twice on 2026-11-01 in New York
        # (05:30 UTC and 06:30 UTC are both 01:30 local); hourly buckets are keyed by local
        # time, so both land in the one bucket.
        camera_id = _create_camera(client)
        add_event(camera_id, "line_crossed", datetime(2026, 11, 1, 5, 30, tzinfo=UTC), category="person", direction="in")
        add_event(camera_id, "line_crossed", datetime(2026, 11, 1, 6, 30, tzinfo=UTC), category="person", direction="in")

        points = _get(
            client, "timeseries", since="2026-11-01T04:00:00Z", until="2026-11-02T05:00:00Z", bucket="hour", tz="America/New_York"
        )["points"]

        assert len(points) == 24
        assert sorted(p["people_in"] for p in points)[-1] == 2

    # -- uptime coverage -----------------------------------------------------------------------

    def test_buckets_report_how_long_tracking_actually_ran(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0 + 10 * M)
        add_event(camera_id, "tracking_stopped", T0 + 70 * M)

        points = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 3 * H), tz="UTC")["points"]

        assert [p["tracked_seconds"] for p in points] == [3000, 600, 0]  # the last hour: "not running"

    def test_a_session_already_running_when_the_range_starts_counts_from_its_start(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0 - 5 * H)  # long before the range, never stopped

        points = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 2 * H), tz="UTC")["points"]

        assert [p["tracked_seconds"] for p in points] == [3600, 3600]

    def test_a_reconnect_gap_is_not_counted_as_tracked(self, client, add_event):
        camera_id = _create_camera(client)
        for minutes, event_type in [
            (0, "tracking_started"), (20, "tracking_reconnecting"), (30, "tracking_resumed"), (50, "tracking_stopped")
        ]:
            add_event(camera_id, event_type, T0 + minutes * M)

        (point,) = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 1 * H), tz="UTC")["points"]

        assert point["tracked_seconds"] == 2400

    def test_two_cameras_add_up_as_camera_seconds(self, client, add_event):
        a, b = _create_camera(client, "A"), _create_camera(client, "B")
        for camera_id in (a, b):
            add_event(camera_id, "tracking_started", T0)
            add_event(camera_id, "tracking_stopped", T0 + 1 * H)

        def tracked(**extra):
            return _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 1 * H), tz="UTC", **extra)["points"][0]["tracked_seconds"]

        assert (tracked(), tracked(camera_id=a)) == (7200, 3600)

    def test_a_session_still_running_now_counts_up_to_now_and_no_further(self, client, add_event):
        camera_id = _create_camera(client)
        now = datetime.now(UTC)
        add_event(camera_id, "tracking_started", now - 90 * M)  # never stopped: live right now

        # A range reaching an hour into the future must not credit uptime that hasn't happened.
        since = (now - 3 * H).replace(minute=0, second=0, microsecond=0)
        series = _get(client, "timeseries", since=_iso(since), until=_iso(now + 1 * H), tz="UTC")

        total = sum(p["tracked_seconds"] for p in series["points"])
        assert 5400 - 60 < total < 5400 + 60

    def test_events_do_not_change_the_reported_uptime(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0)
        add_event(camera_id, "tracking_stopped", T0 + 1 * H)
        before = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 1 * H), tz="UTC")["points"][0]["tracked_seconds"]

        for i in range(20):
            add_event(camera_id, "line_crossed", T0 + i * M, category="person", direction="in")

        after = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + 1 * H), tz="UTC")["points"][0]["tracked_seconds"]
        assert before == after == 3600

    # -- validation ----------------------------------------------------------------------------

    def test_an_unknown_time_zone_is_rejected(self, client):
        response = client.get("/analytics/timeseries", params={"since": _iso(T0), "until": _iso(T0 + 1 * H), "tz": "Mars/Olympus"})

        assert response.status_code == 422 and "time zone" in response.json()["detail"].lower()

    @pytest.mark.parametrize("bucket", ["week", "minute", "", "HOUR"])
    def test_an_unknown_bucket_is_rejected(self, client, bucket):
        assert client.get("/analytics/timeseries", params={"since": _iso(T0), "until": _iso(T0 + 1 * H), "bucket": bucket}).status_code == 422

    def test_too_many_buckets_is_rejected_with_advice(self, client):
        response = client.get(
            "/analytics/timeseries", params={"since": _iso(T0), "until": _iso(T0 + timedelta(days=60)), "bucket": "hour"}
        )

        assert response.status_code == 422 and "day buckets" in response.json()["detail"]

    def test_the_same_range_in_day_buckets_is_fine(self, client):
        series = _get(client, "timeseries", since=_iso(T0), until=_iso(T0 + timedelta(days=60)), bucket="day", tz="UTC")

        assert len(series["points"]) in (60, 61)

    def test_a_backwards_range_is_rejected(self, client):
        assert client.get("/analytics/timeseries", params={"since": _iso(T0 + 1 * H), "until": _iso(T0)}).status_code == 422

    def test_an_unknown_camera_is_a_404(self, client):
        assert client.get("/analytics/timeseries", params={"since": _iso(T0), "camera_id": str(uuid.uuid4())}).status_code == 404

    def test_a_hostile_time_zone_string_cannot_inject_anything(self, client):
        response = client.get(
            "/analytics/timeseries", params={"since": _iso(T0), "until": _iso(T0 + 1 * H), "tz": "UTC'; DROP TABLE events;--"}
        )

        assert response.status_code == 422
        assert client.get("/events").status_code == 200  # the table is fine


# -- heatmap -------------------------------------------------------------------------------------


class TestHeatmap:
    def _params(self, camera_id, since=T0, until=T0 + 6 * H):
        return {"camera_id": camera_id, "since": _iso(since), "until": _iso(until)}

    def test_with_nothing_recorded_the_info_says_so_and_the_image_is_a_404(self, client):
        camera_id = _create_camera(client)

        info = _get(client, "heatmap/info", **self._params(camera_id))

        assert info["available"] is False and info["samples"] == 0
        assert client.get("/analytics/heatmap", params=self._params(camera_id)).status_code == 404

    def test_the_info_describes_what_was_recorded(self, client, add_heat):
        camera_id = _create_camera(client)
        add_heat(camera_id, T0, {(10, 10): 5})
        add_heat(camera_id, T0 + 1 * H, {(10, 10): 3, (20, 20): 2})

        info = _get(client, "heatmap/info", **self._params(camera_id))

        assert info["available"] is True
        assert info["samples"] == 10
        assert (info["frame_width"], info["frame_height"], info["grid_width"], info["grid_height"]) == (800, 400, 80, 40)
        assert datetime.fromisoformat(info["first_period"]) == T0
        assert datetime.fromisoformat(info["last_period"]) == T0 + 1 * H
        assert info["ignored_samples"] == 0

    def test_only_snapshots_in_the_range_are_used(self, client, add_heat):
        camera_id = _create_camera(client)
        add_heat(camera_id, T0 - 3 * H, {(1, 1): 100})  # before
        add_heat(camera_id, T0 + 1 * H, {(2, 2): 4})  # inside
        add_heat(camera_id, T0 + 8 * H, {(3, 3): 100})  # after

        info = _get(client, "heatmap/info", **self._params(camera_id))

        assert info["samples"] == 4

    def test_the_hour_containing_since_is_included_whole(self, client, add_heat):
        # Snapshots are hourly, so a range starting at 12:30 includes the 12:00 snapshot.
        camera_id = _create_camera(client)
        add_heat(camera_id, T0, {(1, 1): 7})

        info = _get(client, "heatmap/info", **self._params(camera_id, since=T0 + 30 * M, until=T0 + 2 * H))

        assert info["samples"] == 7

    def test_another_cameras_heat_is_not_mixed_in(self, client, add_heat):
        a, b = _create_camera(client, "A"), _create_camera(client, "B")
        add_heat(a, T0, {(1, 1): 3})
        add_heat(b, T0, {(1, 1): 50})

        assert _get(client, "heatmap/info", **self._params(a))["samples"] == 3

    def test_snapshots_from_a_different_resolution_are_not_added_in_and_are_reported(self, client, add_heat):
        camera_id = _create_camera(client)
        add_heat(camera_id, T0, {(5, 5): 10})  # 80x40
        add_heat(camera_id, T0 + 1 * H, {(5, 5): 2}, frame=(800, 450), grid_height=45)  # the camera changed resolution

        info = _get(client, "heatmap/info", **self._params(camera_id))

        assert (info["grid_height"], info["samples"], info["ignored_samples"]) == (40, 10, 2)

    def test_the_image_is_a_jpeg_tinted_where_people_stood_over_a_neutral_background_when_the_camera_is_unreachable(
        self, client, add_heat
    ):
        camera_id = _create_camera(client, rtsp_url="rtsp://127.0.0.1:1/does-not-exist")
        add_heat(camera_id, T0, {(20, 40): 50})  # the middle of an 800x400 frame

        response = client.get("/analytics/heatmap", params=self._params(camera_id))

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["x-heatmap-background"] == "neutral"
        assert response.headers["x-heatmap-samples"] == "50"
        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        assert image.shape == (400, 800, 3)
        assert np.abs(image[200, 400].astype(int) - 40).max() > 40  # the hot spot
        assert np.abs(image[5, 5].astype(int) - 40).max() < 8  # far away: still the neutral grey

    def test_the_image_sits_over_a_live_snapshot_when_the_camera_answers(self, client, add_heat, panning_video):
        video_path, width, height = panning_video
        camera_id = _create_camera(client, rtsp_url=video_path)
        add_heat(camera_id, T0, {(20, 40): 50})

        response = client.get("/analytics/heatmap", params=self._params(camera_id))

        assert response.status_code == 200
        assert response.headers["x-heatmap-background"] == "snapshot"
        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        assert image.shape == (height, width, 3)  # the camera's own frame size, not the stored one

    def test_hours_are_summed_into_one_picture(self, client, add_heat):
        camera_id = _create_camera(client, rtsp_url="rtsp://127.0.0.1:1/does-not-exist")
        add_heat(camera_id, T0, {(20, 10): 5})
        add_heat(camera_id, T0 + 1 * H, {(20, 70): 5})

        response = client.get("/analytics/heatmap", params=self._params(camera_id))

        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        assert np.abs(image[200, 100].astype(int) - 40).max() > 40  # both hot spots are drawn
        assert np.abs(image[200, 700].astype(int) - 40).max() > 40

    def test_validation(self, client):
        camera_id = _create_camera(client)

        assert client.get("/analytics/heatmap", params={"since": _iso(T0)}).status_code == 422  # camera_id required
        assert client.get("/analytics/heatmap/info", params={"since": _iso(T0)}).status_code == 422
        assert client.get("/analytics/heatmap", params={"camera_id": camera_id, "since": _iso(T0), "until": _iso(T0)}).status_code == 422
        assert client.get("/analytics/heatmap", params={"camera_id": str(uuid.uuid4()), "since": _iso(T0)}).status_code == 404
        assert client.get("/analytics/heatmap/info", params={"camera_id": str(uuid.uuid4()), "since": _iso(T0)}).status_code == 404


# -- startup: closing sessions a crash left open --------------------------------------------------


class TestCloseDanglingSessions:
    def _types(self, db_session, camera_id):
        db_session.expire_all()
        return [e.event_type for e in db_session.query(Event).filter(Event.camera_id == uuid.UUID(camera_id)).order_by(Event.occurred_at, Event.id)]

    def test_a_running_session_with_no_stop_is_closed_at_its_last_event(self, client, db_session, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0)
        add_event(camera_id, "line_crossed", T0 + 10 * M, category="person", direction="in")

        assert close_dangling_sessions() == 1

        closing = db_session.query(Event).filter(Event.event_type == "tracking_stopped").one()
        # The last thing we know it did (not "now"), a microsecond later so it sorts after it.
        assert closing.occurred_at == T0 + 10 * M + timedelta(microseconds=1)
        assert closing.value == "Backend restarted"

    def test_an_interrupted_reconnect_is_closed_too(self, client, db_session, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0)
        add_event(camera_id, "tracking_reconnecting", T0 + 5 * M)

        assert close_dangling_sessions() == 1
        assert self._types(db_session, camera_id)[-1] == "tracking_stopped"

    @pytest.mark.parametrize("last", ["tracking_stopped", "tracking_error"])
    def test_sessions_that_ended_properly_are_left_alone(self, client, db_session, add_event, last):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0)
        add_event(camera_id, last, T0 + 5 * M)

        assert close_dangling_sessions() == 0
        assert self._types(db_session, camera_id) == ["tracking_started", last]

    def test_a_camera_with_no_uptime_events_is_left_alone(self, client, db_session, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "read", T0, category="qr", value="x")

        assert close_dangling_sessions() == 0

    def test_only_the_most_recent_uptime_event_counts(self, client, db_session, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0)
        add_event(camera_id, "tracking_stopped", T0 + 1 * H)  # ended properly
        add_event(camera_id, "tracking_started", T0 + 2 * H)  # then started again and was cut off

        assert close_dangling_sessions() == 1

    def test_running_it_twice_closes_nothing_the_second_time(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0)

        assert close_dangling_sessions() == 1
        assert close_dangling_sessions() == 0

    def test_each_camera_is_handled_independently(self, client, add_event):
        a, b, c = (_create_camera(client, n) for n in "ABC")
        add_event(a, "tracking_started", T0)  # dangling
        add_event(b, "tracking_started", T0)
        add_event(b, "tracking_stopped", T0 + 1 * M)  # fine
        add_event(c, "tracking_started", T0)  # dangling

        assert close_dangling_sessions() == 2

    def test_uptime_after_a_crash_is_not_overstated(self, client, add_event):
        camera_id = _create_camera(client)
        add_event(camera_id, "tracking_started", T0)
        add_event(camera_id, "line_crossed", T0 + 10 * M, category="person", direction="in")
        close_dangling_sessions()

        summary = _get(client, "summary", camera_id=camera_id, since=_iso(T0), until=_iso(T0 + 5 * H))

        assert summary["tracked_seconds"] == pytest.approx(600, abs=0.01)  # ten minutes, not five hours

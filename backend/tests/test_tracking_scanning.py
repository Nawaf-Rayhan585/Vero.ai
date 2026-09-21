"""The reading modules inside a real TrackingSession, end to end: a real video file goes in
through the real capture loop, real zxing-cpp decodes the QR code and barcode, real
RapidOCR (PaddleOCR's models) reads the text on its background thread, and the results
come out of the real HTTP API — with no detector (YOLO) involved at all.
"""
import time
import uuid

import cv2
import numpy as np
import pytest

from app.tracking import tracking_manager

MAGENTA_BGR = np.array([255, 0, 255])


def _create_camera(client, video_path, modules) -> str:
    response = client.post("/cameras", json={"name": "Dock", "rtsp_url": video_path, "enabled_modules": modules})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _poll_status(client, camera_id, done, timeout=90):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = client.get(f"/cameras/{camera_id}/tracking/status").json()
        if status["status"] == "error":
            pytest.fail(f"tracking errored: {status}")
        if done(status):
            return status
        time.sleep(0.2)
    pytest.fail(f"condition not met within {timeout}s; last status: {status}")


def _magenta_pixels(jpeg_bytes) -> int:
    image = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR).astype(int)
    return int((np.abs(image - MAGENTA_BGR).max(axis=2) < 70).sum())


def test_qr_barcode_and_text_are_all_read_from_a_real_video_with_no_detector(client, scan_video):
    camera_id = _create_camera(client, scan_video.path, ["qr", "barcode", "ocr"])
    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200

    try:
        status = _poll_status(
            client, camera_id, lambda s: {r["kind"] for r in s["reads"]} >= {"qr", "barcode", "ocr"}
        )
        session = tracking_manager.get(uuid.UUID(camera_id))
        # Freeze the session on its last frame so the served frame below is a stable one.
        session.stop()
        frame_response = client.get(f"/cameras/{camera_id}/tracking/latest-frame")
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")

    by_kind = {r["kind"]: r for r in status["reads"]}
    assert by_kind["qr"]["value"] == scan_video.qr
    assert by_kind["qr"]["detail"] == "QR Code"
    assert by_kind["barcode"]["value"] == scan_video.barcode
    assert by_kind["barcode"]["detail"] == "Code 128"
    text_values = {r["value"] for r in status["reads"] if r["kind"] == "ocr"}
    assert scan_video.text in text_values
    for read in status["reads"]:
        assert read["sightings"] >= 1
        assert read["first_seen_at"] <= read["last_seen_at"]

    # No detector was needed or loaded: nothing to track, and the session knew it.
    assert session._class_ids == []
    assert status["active_track_ids"] == [] and status["active_vehicle_track_ids"] == []

    # The QR code and barcode were read on the raw frame and then drawn back onto the
    # served video as magenta boxes.
    assert frame_response.status_code == 200
    assert _magenta_pixels(frame_response.content) > 100


def test_only_the_enabled_reading_modules_produce_reads(client, scan_video):
    # The video contains a QR code, a barcode and text, but this camera only reads QR codes.
    camera_id = _create_camera(client, scan_video.path, ["qr"])
    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200

    try:
        status = _poll_status(client, camera_id, lambda s: s["reads"], timeout=30)
        time.sleep(1.0)  # give a barcode/OCR read every chance to (wrongly) appear too
        status = client.get(f"/cameras/{camera_id}/tracking/status").json()
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")

    assert [(r["kind"], r["value"]) for r in status["reads"]] == [("qr", scan_video.qr)]


def test_reads_start_empty_every_time_tracking_starts(client, scan_video):
    camera_id = _create_camera(client, scan_video.path, ["qr"])

    client.post(f"/cameras/{camera_id}/tracking/start")
    try:
        _poll_status(client, camera_id, lambda s: s["reads"], timeout=30)
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")

    # Right after a fresh start, before its first frame is processed, nothing is remembered.
    restarted = client.post(f"/cameras/{camera_id}/tracking/start").json()
    try:
        assert restarted["reads"] == []
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")


def test_a_stopped_or_unstarted_cameras_status_lists_no_reads_or_vehicles(client):
    camera_id = client.post("/cameras", json={"name": "x", "rtsp_url": "rtsp://192.0.2.1/x"}).json()["id"]

    status = client.get(f"/cameras/{camera_id}/tracking/status").json()

    assert status["reads"] == []
    assert status["active_vehicle_track_ids"] == []

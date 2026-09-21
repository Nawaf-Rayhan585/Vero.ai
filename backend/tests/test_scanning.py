"""The reading modules (QR, barcode, OCR): real decoding on real generated images, plus
deterministic tests of the registry and the OCR worker using fakes for the slow/real parts.
"""
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import zxingcpp
from ultralytics.utils import ASSETS

from app import scanning
from app.scanning import (
    CodeScanner,
    OcrWorker,
    ReadRegistry,
    TextReader,
    ascii_label,
)

SCAN_QR_VALUE = "https://vero.ai/t/42"
SCAN_BARCODE_VALUE = "PKG-99812"
SCAN_TEXT_VALUE = "PALLET 4471-B"


def _wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


class TestCodeScanner:
    def test_reads_a_qr_code(self, scan_scene):
        reads = CodeScanner(["qr"]).scan(scan_scene(qr=SCAN_QR_VALUE))

        assert [(r.kind, r.value, r.detail) for r in reads] == [("qr", SCAN_QR_VALUE, "QR Code")]

    def test_reports_the_codes_corner_points_where_it_is_in_the_frame(self, scan_scene):
        (read,) = CodeScanner(["qr"]).scan(scan_scene(qr=SCAN_QR_VALUE))

        assert len(read.points) == 4
        for x, y in read.points:
            assert 80 <= x <= 450 and 60 <= y <= 450  # the QR is drawn in the upper left

    @pytest.mark.parametrize(
        "fmt, value, detail",
        [
            (zxingcpp.BarcodeFormat.Code128, "PKG-99812", "Code 128"),
            (zxingcpp.BarcodeFormat.Code39, "ABC123", "Code 39"),
            (zxingcpp.BarcodeFormat.EAN13, "4006381333931", "EAN-13"),
        ],
    )
    def test_reads_common_barcode_symbologies(self, scan_scene, fmt, value, detail):
        reads = CodeScanner(["barcode"]).scan(scan_scene(barcode=value, barcode_format=fmt))

        assert [(r.kind, r.value, r.detail) for r in reads] == [("barcode", value, detail)]

    def test_the_qr_module_alone_ignores_barcodes(self, scan_scene):
        frame = scan_scene(qr=SCAN_QR_VALUE, barcode=SCAN_BARCODE_VALUE)

        assert [r.value for r in CodeScanner(["qr"]).scan(frame)] == [SCAN_QR_VALUE]

    def test_the_barcode_module_alone_ignores_qr_codes(self, scan_scene):
        frame = scan_scene(qr=SCAN_QR_VALUE, barcode=SCAN_BARCODE_VALUE)

        assert [r.value for r in CodeScanner(["barcode"]).scan(frame)] == [SCAN_BARCODE_VALUE]

    def test_both_modules_read_both_kinds(self, scan_scene):
        frame = scan_scene(qr=SCAN_QR_VALUE, barcode=SCAN_BARCODE_VALUE)

        reads = CodeScanner(["qr", "barcode"]).scan(frame)

        assert {(r.kind, r.value) for r in reads} == {("qr", SCAN_QR_VALUE), ("barcode", SCAN_BARCODE_VALUE)}

    def test_a_frame_with_nothing_to_read_yields_nothing(self, scan_scene):
        assert CodeScanner(["qr", "barcode"]).scan(scan_scene()) == []

    def test_a_plain_photo_yields_nothing(self):
        photo = cv2.imread(str(ASSETS / "bus.jpg"))

        assert CodeScanner(["qr", "barcode"]).scan(photo) == []

    def test_without_the_qr_or_barcode_module_the_scanner_is_disabled(self, scan_scene):
        scanner = CodeScanner(["people", "ocr"])

        assert not scanner.enabled
        assert scanner.scan(scan_scene(qr=SCAN_QR_VALUE)) == []

    def test_a_code_too_small_in_the_frame_is_not_read(self, scan_scene):
        # The honest CCTV limit, pinned so it's documented behavior rather than a surprise:
        # a barcode squeezed to ~60 px wide in a 720p frame can't be decoded.
        frame = scan_scene()
        code = np.array(zxingcpp.write_barcode_to_image(zxingcpp.create_barcode("PKG-99812", zxingcpp.BarcodeFormat.Code128)))
        small = cv2.resize(cv2.cvtColor(code, cv2.COLOR_GRAY2BGR), (60, 24), interpolation=cv2.INTER_AREA)
        frame[300:324, 600:660] = small

        assert CodeScanner(["barcode"]).scan(frame) == []


class _FakeOcrResult:
    def __init__(self, entries):
        # entries: (text, score) pairs
        self.txts = tuple(t for t, _ in entries) if entries else None
        self.scores = tuple(s for _, s in entries) if entries else None
        self.boxes = np.array([[[0, 0], [10, 0], [10, 5], [0, 5]]] * len(entries), dtype=np.float32) if entries else None


class TestTextReaderFiltering:
    def _reader(self, entries):
        return TextReader(engine_factory=lambda: (lambda frame: _FakeOcrResult(entries)))

    def test_keeps_confident_text_with_its_box(self):
        (read,) = self._reader([("EXIT ONLY", 0.93)]).read(np.zeros((10, 10, 3), np.uint8))

        assert read.value == "EXIT ONLY"
        assert read.confidence == pytest.approx(0.93)
        assert read.points == [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]

    def test_drops_low_confidence_text(self):
        reads = self._reader([("noise", 0.59), ("real", 0.60)]).read(np.zeros((10, 10, 3), np.uint8))

        assert [r.value for r in reads] == ["real"]

    def test_drops_text_shorter_than_two_characters_and_strips_whitespace(self):
        reads = self._reader([("a", 0.99), ("  ", 0.99), ("  Dock 7 ", 0.99)]).read(np.zeros((10, 10, 3), np.uint8))

        assert [r.value for r in reads] == ["Dock 7"]

    def test_no_text_found_returns_nothing(self):
        assert self._reader([]).read(np.zeros((10, 10, 3), np.uint8)) == []

    def test_the_engine_is_created_lazily_and_only_once(self):
        created = []

        def factory():
            created.append(1)
            return lambda frame: _FakeOcrResult([("Hello", 0.9)])

        reader = TextReader(engine_factory=factory)
        assert created == []

        reader.read(np.zeros((10, 10, 3), np.uint8))
        reader.read(np.zeros((10, 10, 3), np.uint8))

        assert created == [1]


@pytest.fixture(scope="module")
def real_text_reader():
    return TextReader()


class TestRealOcr:
    """Real RapidOCR inference (PaddleOCR's models via ONNX Runtime) — no fakes."""

    def test_reads_rendered_text_from_a_synthetic_frame(self, real_text_reader, scan_scene):
        frame = scan_scene(text=SCAN_TEXT_VALUE)

        reads = real_text_reader.read(frame)

        assert SCAN_TEXT_VALUE in [r.value for r in reads]
        read = next(r for r in reads if r.value == SCAN_TEXT_VALUE)
        assert read.confidence > 0.8
        assert len(read.points) == 4

    def test_reads_real_signage_from_a_real_photograph(self, real_text_reader):
        # bus.jpg is a real street photo with real lettering on the bus.
        reads = real_text_reader.read(cv2.imread(str(ASSETS / "bus.jpg")))

        values = {r.value for r in reads}
        assert "cero" in values
        assert "emisiones" in values

    def test_a_frame_with_no_text_yields_nothing_confident(self, real_text_reader):
        assert real_text_reader.read(np.full((480, 640, 3), 90, np.uint8)) == []


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


_BOX = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


class TestReadRegistry:
    def test_a_first_read_is_one_sighting(self):
        registry = ReadRegistry(clock=_Clock())

        registry.record("qr", "abc", "QR Code", _BOX)

        (entry,) = registry.snapshot()
        assert (entry["kind"], entry["value"], entry["detail"], entry["sightings"]) == ("qr", "abc", "QR Code", 1)
        assert entry["first_seen_at"] == entry["last_seen_at"]

    def test_seeing_the_same_thing_every_frame_stays_one_sighting(self):
        clock = _Clock()
        registry = ReadRegistry(clock=clock)

        for _ in range(300):  # a code sitting in view for a minute at 5 fps
            registry.record("qr", "abc", "QR Code", _BOX)
            clock.advance(0.2)

        (entry,) = registry.snapshot()
        assert entry["sightings"] == 1

    def test_seeing_it_again_after_a_gap_is_a_new_sighting(self):
        clock = _Clock()
        registry = ReadRegistry(clock=clock)
        registry.record("qr", "abc", "QR Code", _BOX)

        clock.advance(scanning.SIGHTING_GAP_SECONDS + 0.5)
        registry.record("qr", "abc", "QR Code", _BOX)
        clock.advance(scanning.SIGHTING_GAP_SECONDS - 1)  # not yet a full gap since the last one
        registry.record("qr", "abc", "QR Code", _BOX)

        (entry,) = registry.snapshot()
        assert entry["sightings"] == 2

    def test_last_seen_advances_but_first_seen_does_not(self):
        clock = _Clock()
        ticks = iter(range(1, 100))
        registry = ReadRegistry(clock=clock, wall_clock=lambda: __import__("datetime").datetime.fromtimestamp(next(ticks), __import__("datetime").timezone.utc))
        registry.record("qr", "abc", "QR Code", _BOX)
        registry.record("qr", "abc", "QR Code", _BOX)

        (entry,) = registry.snapshot()
        assert entry["last_seen_at"] > entry["first_seen_at"]

    def test_the_same_value_as_different_kinds_is_kept_separately(self):
        registry = ReadRegistry(clock=_Clock())

        registry.record("qr", "12345", "QR Code", _BOX)
        registry.record("barcode", "12345", "EAN-13", _BOX)
        registry.record("ocr", "12345", "0.97", _BOX)

        assert sorted(e["kind"] for e in registry.snapshot()) == ["barcode", "ocr", "qr"]

    def test_the_snapshot_lists_the_most_recently_seen_first(self):
        clock = _Clock()
        registry = ReadRegistry(clock=clock)
        for value in ("first", "second", "third"):
            registry.record("ocr", value, "0.9", _BOX)
            clock.advance(1)
        registry.record("ocr", "first", "0.9", _BOX)  # seen again, now the newest

        assert [e["value"] for e in registry.snapshot()] == ["first", "third", "second"]

    def test_only_the_most_recent_50_are_kept(self):
        clock = _Clock()
        registry = ReadRegistry(clock=clock)
        for i in range(60):
            registry.record("ocr", f"value-{i}", "0.9", _BOX)
            clock.advance(1)

        values = [e["value"] for e in registry.snapshot()]
        assert len(values) == scanning.MAX_READS == 50
        assert "value-0" not in values  # the oldest were evicted
        assert "value-59" in values

    def test_overlays_include_only_recently_seen_reads_with_a_box(self):
        clock = _Clock()
        registry = ReadRegistry(clock=clock)
        registry.record("qr", "old", "QR Code", _BOX)
        clock.advance(scanning.OVERLAY_WINDOW_SECONDS + 1)
        registry.record("qr", "fresh", "QR Code", _BOX)
        registry.record("ocr", "no-box", "0.9", [])

        assert [o.value for o in registry.recent_overlays()] == ["fresh"]

    def test_overlays_expire_as_time_passes(self):
        clock = _Clock()
        registry = ReadRegistry(clock=clock)
        registry.record("qr", "abc", "QR Code", _BOX)
        assert len(registry.recent_overlays()) == 1

        clock.advance(scanning.OVERLAY_WINDOW_SECONDS + 0.1)

        assert registry.recent_overlays() == []

    def test_is_safe_to_write_from_many_threads(self):
        registry = ReadRegistry()

        def writer(n):
            for i in range(200):
                registry.record("ocr", f"t{n}-{i % 10}", "0.9", _BOX)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 4 threads x 10 distinct values each, all under the 50-entry cap.
        assert len(registry.snapshot()) == 4 * 10
        assert all(e["sightings"] >= 1 for e in registry.snapshot())


class _FakeReader:
    def __init__(self, texts=(), block=None, fail_times=0):
        self.calls = 0
        self._texts = texts
        self._block = block
        self._fail_times = fail_times

    def read(self, frame):
        self.calls += 1
        if self._block is not None:
            self._block.wait(5)
        if self.calls <= self._fail_times:
            raise RuntimeError("model failed to load")
        return [SimpleNamespace(value=t, confidence=0.9, points=_BOX) for t in self._texts]


class TestOcrWorker:
    def _worker(self, reader, interval=0.2, clock=time.monotonic):
        stop = threading.Event()
        registry = ReadRegistry()
        worker = OcrWorker(reader, registry, stop, interval_seconds=interval, clock=clock)
        worker.start()
        return worker, registry, stop

    def test_a_submitted_frame_is_read_and_recorded_as_text(self):
        worker, registry, stop = self._worker(_FakeReader(["PALLET 4471-B"]))
        try:
            assert worker.wants_frame()
            worker.submit(np.zeros((10, 10, 3), np.uint8))

            assert _wait_until(lambda: registry.snapshot())
            (entry,) = registry.snapshot()
            assert (entry["kind"], entry["value"], entry["detail"]) == ("ocr", "PALLET 4471-B", "0.90")
        finally:
            stop.set()
            worker.join(timeout=3)

    def test_it_does_not_want_another_frame_while_one_is_being_read(self):
        release = threading.Event()
        reader = _FakeReader(["x1"], block=release)
        worker, registry, stop = self._worker(reader)
        try:
            worker.submit(np.zeros((10, 10, 3), np.uint8))
            assert _wait_until(lambda: reader.calls == 1)

            assert not worker.wants_frame()  # busy inside read()
        finally:
            release.set()
            stop.set()
            worker.join(timeout=3)

    def test_it_waits_out_the_interval_before_wanting_the_next_frame(self):
        clock = _Clock()
        worker, registry, stop = self._worker(_FakeReader(["abcd"]), interval=5.0, clock=clock)
        try:
            worker.submit(np.zeros((10, 10, 3), np.uint8))
            assert _wait_until(lambda: registry.snapshot())
            assert _wait_until(lambda: not worker._busy)

            assert not worker.wants_frame()  # pass just finished: cooling down
            clock.advance(4.9)
            assert not worker.wants_frame()
            clock.advance(0.2)
            assert worker.wants_frame()
        finally:
            stop.set()
            worker.join(timeout=3)

    def test_a_failing_pass_is_survived_and_the_next_one_works(self):
        reader = _FakeReader(["recovered text"], fail_times=1)
        worker, registry, stop = self._worker(reader, interval=0.05)
        try:
            worker.submit(np.zeros((10, 10, 3), np.uint8))
            assert _wait_until(lambda: reader.calls == 1)
            assert registry.snapshot() == []
            assert _wait_until(worker.wants_frame)

            worker.submit(np.zeros((10, 10, 3), np.uint8))

            assert _wait_until(lambda: registry.snapshot())
            assert registry.snapshot()[0]["value"] == "recovered text"
        finally:
            stop.set()
            worker.join(timeout=3)

    def test_the_worker_stops_promptly_when_the_stop_event_is_set(self):
        worker, _registry, stop = self._worker(_FakeReader())
        assert worker.started

        started = time.monotonic()
        stop.set()
        worker.join(timeout=3)

        assert not worker._thread.is_alive()
        assert time.monotonic() - started < 2

    def test_a_worker_that_was_never_started_reports_so(self):
        worker = OcrWorker(_FakeReader(), ReadRegistry(), threading.Event())

        assert not worker.started


class TestAsciiLabel:
    def test_leaves_plain_ascii_alone(self):
        assert ascii_label("PALLET 4471-B") == "PALLET 4471-B"

    def test_replaces_characters_opencv_cannot_draw(self):
        assert ascii_label("eléctrico ✓") == "el?ctrico ?"

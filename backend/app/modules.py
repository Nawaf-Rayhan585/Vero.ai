"""The AI modules a camera can run. What a camera runs is persisted per-camera
configuration (`Camera.enabled_modules`); what it produces is ephemeral session state.
"""
from typing import Iterable

PEOPLE = "people"
VEHICLES = "vehicles"
OCR = "ocr"
QR = "qr"
BARCODE = "barcode"

ALL_MODULES: tuple[str, ...] = (PEOPLE, VEHICLES, OCR, QR, BARCODE)
# People only: what every camera did before per-camera selection existed, so cameras that
# predate the enabled_modules column behave exactly as they always have.
DEFAULT_MODULES: tuple[str, ...] = (PEOPLE,)

# COCO class ids in the bundled yolov8n weights.
PERSON_CLASS_ID = 0
VEHICLE_CLASS_IDS: tuple[int, ...] = (2, 3, 5, 7)  # car, motorcycle, bus, truck


def detector_class_ids(modules: Iterable[str]) -> list[int]:
    """YOLO classes needed for the enabled modules. Empty means no detector is needed
    at all (e.g. a camera that only reads QR codes)."""
    modules = set(modules)
    class_ids: list[int] = []
    if PEOPLE in modules:
        class_ids.append(PERSON_CLASS_ID)
    if VEHICLES in modules:
        class_ids.extend(VEHICLE_CLASS_IDS)
    return class_ids

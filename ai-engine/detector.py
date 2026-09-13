from dataclasses import dataclass
from typing import Generator

import cv2
from ultralytics import YOLO


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2


class Detector:
    def __init__(self, model_path: str = "yolov8n.pt"):
        self.model = YOLO(model_path)

    def detect_image(self, image_path: str, conf: float = 0.25) -> list[Detection]:
        results = self.model(image_path, conf=conf, verbose=False)
        return self._to_detections(results[0])

    def detect_video(
        self, video_path: str, conf: float = 0.25
    ) -> Generator[list[Detection], None, None]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                results = self.model(frame, conf=conf, verbose=False)
                yield self._to_detections(results[0])
        finally:
            cap.release()

    def _to_detections(self, result) -> list[Detection]:
        detections = []
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            label = result.names[int(box.cls[0])]
            confidence = float(box.conf[0])
            detections.append(Detection(label=label, confidence=confidence, box=(x1, y1, x2, y2)))
        return detections

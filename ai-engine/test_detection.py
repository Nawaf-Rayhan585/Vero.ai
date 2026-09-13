import sys

from detector import Detector


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_detection.py <path-to-image-or-video> [model_path]")
        sys.exit(1)

    source = sys.argv[1]
    model_path = sys.argv[2] if len(sys.argv) > 2 else "yolov8n.pt"
    is_video = source.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))

    detector = Detector(model_path=model_path)

    if is_video:
        for frame_index, detections in enumerate(detector.detect_video(source)):
            print(f"Frame {frame_index}: {len(detections)} detection(s)")
            for d in detections:
                print(f"  {d.label} ({d.confidence:.2f}) {d.box}")
    else:
        detections = detector.detect_image(source)
        print(f"{len(detections)} detection(s)")
        for d in detections:
            print(f"  {d.label} ({d.confidence:.2f}) {d.box}")


if __name__ == "__main__":
    main()

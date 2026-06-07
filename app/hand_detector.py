import cv2
import mediapipe as mp
from pathlib import Path
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from app.runtime_paths import resource_path


class HandDetector:
    def __init__(self, model_path="models/hand_landmarker.task"):
        resolved_model_path = str(resource_path(*Path(model_path).parts)) if isinstance(model_path, str) else str(model_path)
        base_options = python.BaseOptions(model_asset_path=resolved_model_path)
        video_options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.2,
            min_hand_presence_confidence=0.1,
            min_tracking_confidence=0.1,
        )
        image_options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=0.18,
            min_hand_presence_confidence=0.1,
            min_tracking_confidence=0.1,
        )
        self.detector = vision.HandLandmarker.create_from_options(video_options)
        self.fallback_detector = vision.HandLandmarker.create_from_options(image_options)

    def process_frame(self, frame, timestamp_ms):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.detector.detect_for_video(mp_image, timestamp_ms)
        if not getattr(result, "hand_landmarks", []):
            try:
                fallback_result = self.fallback_detector.detect(mp_image)
                if getattr(fallback_result, "hand_landmarks", []):
                    result = fallback_result
            except Exception:
                pass
        return frame, result

    def close(self):
        self.detector.close()
        self.fallback_detector.close()

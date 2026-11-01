"""MediaPipe Face Mesh smile detection for menu controls."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src import config


@dataclass
class FaceObservation:
    detected: bool = False
    smiling: bool = False


class FaceDetectorError(RuntimeError):
    pass


def mouth_is_smiling(left, right, upper, lower) -> bool:
    """A smile lifts the mouth corners. A closed mouth does not count."""
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    upper = np.asarray(upper, dtype=float)
    lower = np.asarray(lower, dtype=float)
    mouth_width = float(np.linalg.norm(right - left))
    if mouth_width < 1e-4:
        return False
    lip_center_y = (float(upper[1]) + float(lower[1])) / 2.0
    corner_y = (float(left[1]) + float(right[1])) / 2.0
    lift = (lip_center_y - corner_y) / mouth_width
    return lift >= config.SMILE_CORNER_LIFT


class FaceDetector:
    def __init__(self) -> None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise FaceDetectorError("MediaPipe is not installed. Run: pip install -r requirements.txt") from exc
        solutions = getattr(mp, "solutions", None)
        if solutions is None or not hasattr(solutions, "face_mesh"):
            raise FaceDetectorError("This MediaPipe version does not provide Face Mesh.")
        self._face_mesh = solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def process(self, frame_bgr) -> FaceObservation:
        observation = FaceObservation()
        if frame_bgr is None:
            return observation
        try:
            rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
            result = self._face_mesh.process(rgb)
        except Exception:
            return observation
        if not result.multi_face_landmarks:
            return observation
        observation.detected = True
        landmarks = result.multi_face_landmarks[0].landmark
        observation.smiling = mouth_is_smiling(
            (landmarks[61].x, landmarks[61].y),
            (landmarks[291].x, landmarks[291].y),
            (landmarks[13].x, landmarks[13].y),
            (landmarks[14].x, landmarks[14].y),
        )
        return observation

    def close(self) -> None:
        if self._face_mesh is not None:
            try:
                self._face_mesh.close()
            except Exception:
                pass
            self._face_mesh = None

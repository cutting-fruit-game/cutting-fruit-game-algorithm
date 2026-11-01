"""MediaPipe hand tracking with fingertip extraction and hand-loss handling.

Two MediaPipe back-ends are supported because the API differs by version:

* ``solutions``: legacy ``mp.solutions.hands`` (MediaPipe <= ~0.10.21).
* ``tasks``: ``HandLandmarker`` from the Tasks API (all recent versions).
  It needs the model file ``assets/hand_landmarker.task``.

The legacy API is preferred when present; otherwise the Tasks API is used.
Frames must already be mirrored (see camera.py), so normalised x maps
directly to screen x.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from src import config

Point = Tuple[float, float]


class HandTrackerError(RuntimeError):
    """Raised when hand tracking cannot be initialised."""


def normalized_to_screen(
    nx: float, ny: float, screen_w: int, screen_h: int,
    margin: float = config.INPUT_MARGIN,
) -> Point:
    """Map normalised camera coordinates (0..1) to screen pixels.

    The outer ``margin`` of the camera frame is cropped away and the rest is
    stretched over the whole screen, so screen edges are reachable. Output is
    always clamped to the screen.
    """
    span = max(1e-6, 1.0 - 2.0 * margin)
    u = min(1.0, max(0.0, (nx - margin) / span))
    v = min(1.0, max(0.0, (ny - margin) / span))
    return (u * (screen_w - 1), v * (screen_h - 1))


# Index, middle, ring, and little fingertips, each paired with the joint below it.
_FINGER_TIPS = (8, 12, 16, 20)
_FINGER_PIPS = (6, 10, 14, 18)


def count_raised_fingers(landmarks: List[Point], margin: float = config.FINGER_RAISE_MARGIN) -> int:
    """How many fingers are extended, in any direction. The thumb is ignored."""
    if len(landmarks) < 21:
        return 0
    wrist = landmarks[0]
    raised = 0
    for tip, pip in zip(_FINGER_TIPS, _FINGER_PIPS):
        tip_reach = float(np.hypot(landmarks[tip][0] - wrist[0], landmarks[tip][1] - wrist[1]))
        pip_reach = float(np.hypot(landmarks[pip][0] - wrist[0], landmarks[pip][1] - wrist[1]))
        if tip_reach > pip_reach + margin:
            raised += 1
    return raised


def only_one_finger(landmarks: List[Point], margin: float = config.FINGER_RAISE_MARGIN,
                    gap: float = config.ONE_FINGER_GAP) -> bool:
    """True only when a single finger is extended and the other three are curled."""
    if len(landmarks) < 21:
        return False
    wrist = landmarks[0]

    def reach(index: int) -> float:
        return float(np.hypot(landmarks[index][0] - wrist[0], landmarks[index][1] - wrist[1]))

    extended: List[float] = []
    folded: List[float] = []
    for tip, pip in zip(_FINGER_TIPS, _FINGER_PIPS):
        tip_reach, pip_reach = reach(tip), reach(pip)
        if tip_reach > pip_reach + margin:
            extended.append(tip_reach)
        else:
            folded.append(tip_reach)
    if len(extended) != 1 or len(folded) != 3:
        return False
    return all(extended[0] > other + gap for other in folded)


def update_one_finger_hold(held_since: Optional[float], lost_since: Optional[float], now: float,
                           one_finger: bool, raised_fingers: int,
                           grace: float = config.ONE_FINGER_FLICKER):
    """Keep a one-finger start through a short flicker. Three or more fingers cancel it."""
    if raised_fingers >= 3:
        return None, None
    if one_finger:
        return (now if held_since is None else held_since), None
    if held_since is None:
        return None, None
    lost_since = now if lost_since is None else lost_since
    if now - lost_since >= grace:
        return None, None
    return held_since, lost_since


def exactly_two_fingers(landmarks: List[Point], margin: float = config.FINGER_RAISE_MARGIN,
                        gap: float = config.TWO_FINGER_GAP) -> bool:
    """True when two fingers clearly stick out. An open hand does not count.

    A third finger that only lifts a little does not cancel the pose, as long as
    the two raised fingers are still clearly longer.
    """
    if len(landmarks) < 21:
        return False
    wrist = landmarks[0]

    def reach(index: int) -> float:
        return float(np.hypot(landmarks[index][0] - wrist[0], landmarks[index][1] - wrist[1]))

    reaches = []
    for tip, pip in zip(_FINGER_TIPS, _FINGER_PIPS):
        tip_reach, pip_reach = reach(tip), reach(pip)
        reaches.append((tip_reach, tip_reach > pip_reach + margin))
    reaches.sort(key=lambda item: item[0], reverse=True)
    top, rest = reaches[:2], reaches[2:]
    if not all(extended for _, extended in top):
        return False
    return all(tip > other + gap for tip, _extended in top for other, _folded in rest)


def update_two_finger_hold(held_since: Optional[float], lost_since: Optional[float], now: float,
                           two_fingers: bool, raised_fingers: int,
                           grace: float = config.ONE_FINGER_FLICKER):
    """Keep a two-finger restart through a short flicker. One, three, or more fingers cancel it."""
    if raised_fingers == 1 or raised_fingers >= 3:
        return None, None
    if two_fingers:
        return (now if held_since is None else held_since), None
    if held_since is None:
        return None, None
    lost_since = now if lost_since is None else lost_since
    if now - lost_since >= grace:
        return None, None
    return held_since, lost_since


@dataclass
class HandObservation:
    detected: bool = False
    point: Optional[Point] = None                 # primary landmark in screen px
    normalized: Optional[Point] = None            # primary landmark, 0..1
    landmarks: List[Point] = field(default_factory=list)   # all 21, normalised
    pinching: bool = False
    raised_fingers: int = 0
    one_finger: bool = False
    two_fingers: bool = False
    timestamp: float = 0.0


class HandTracker:
    """Detects one hand and returns its primary landmark (index fingertip)."""

    def __init__(self, primary_landmark: int = config.PRIMARY_LANDMARK) -> None:
        self.primary_landmark = int(primary_landmark)
        self.backend_name = ""
        self._hands = None          # legacy solver
        self._landmarker = None     # tasks landmarker
        self._mp = None
        self._last_ts_ms = 0
        self._last_seen: Optional[float] = None
        self._error_count = 0
        self._init_backend()

    # ------------------------------------------------------------------
    def _init_backend(self) -> None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise HandTrackerError("MediaPipe is not installed. Run: pip install -r requirements.txt") from exc
        self._mp = mp

        solutions = getattr(mp, "solutions", None)
        if solutions is not None and hasattr(solutions, "hands"):
            self._hands = solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=config.MAX_HANDS,
                model_complexity=config.MODEL_COMPLEXITY,
                min_detection_confidence=config.DETECTION_CONFIDENCE,
                min_tracking_confidence=config.TRACKING_CONFIDENCE,
            )
            self.backend_name = "solutions"
            return

        model = config.HAND_MODEL_PATH
        if not model.exists():
            raise HandTrackerError(
                "This MediaPipe version has no legacy 'mp.solutions' API, so the Tasks API is used, "
                f"which needs the model file:\n{model}\n"
                "Download hand_landmarker.task (see README, 'MediaPipe compatibility') "
                "or install a MediaPipe version <0.10.22."
            )
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            options = vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=config.MAX_HANDS,
                min_hand_detection_confidence=config.DETECTION_CONFIDENCE,
                min_hand_presence_confidence=config.DETECTION_CONFIDENCE,
                min_tracking_confidence=config.TRACKING_CONFIDENCE,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
        except Exception as exc:
            raise HandTrackerError(f"Could not create the MediaPipe HandLandmarker: {exc}") from exc
        self.backend_name = "tasks"

    # ------------------------------------------------------------------
    def process(self, frame_bgr, timestamp: float, screen_size: Tuple[int, int]) -> HandObservation:
        """Detect the hand in a BGR frame. Never raises on tracking failures."""
        obs = HandObservation(timestamp=timestamp)
        if frame_bgr is None:
            return obs
        try:
            rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
            landmarks = self._detect(rgb)
        except Exception:
            self._error_count += 1
            return obs
        if not landmarks or self.primary_landmark >= len(landmarks):
            return obs

        nx, ny = landmarks[self.primary_landmark]
        if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
            nx, ny = min(1.0, max(0.0, nx)), min(1.0, max(0.0, ny))
        obs.detected = True
        obs.landmarks = landmarks
        obs.normalized = (nx, ny)
        obs.point = normalized_to_screen(nx, ny, screen_size[0], screen_size[1])
        thumb_x, thumb_y = landmarks[4]
        index_x, index_y = landmarks[8]
        distance = float(np.hypot(index_x - thumb_x, index_y - thumb_y))
        obs.pinching = distance <= config.PINCH_THRESHOLD
        obs.raised_fingers = count_raised_fingers(landmarks)
        obs.one_finger = only_one_finger(landmarks)
        obs.two_fingers = exactly_two_fingers(landmarks)
        self._last_seen = timestamp
        return obs

    def _detect(self, rgb) -> List[Point]:
        if self._hands is not None:
            rgb.flags.writeable = False
            result = self._hands.process(rgb)
            if result.multi_hand_landmarks:
                return [(lm.x, lm.y) for lm in result.multi_hand_landmarks[0].landmark]
            return []
        mp = self._mp
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._last_ts_ms = max(self._last_ts_ms + 1, int(self._now_ms()))
        result = self._landmarker.detect_for_video(image, self._last_ts_ms)
        if result.hand_landmarks:
            return [(lm.x, lm.y) for lm in result.hand_landmarks[0]]
        return []

    @staticmethod
    def _now_ms() -> float:
        import time
        return time.perf_counter() * 1000.0

    # ------------------------------------------------------------------
    def hand_lost(self, now: float) -> bool:
        """True if no hand has been seen for ``HAND_LOSS_TIMEOUT`` seconds."""
        return self._last_seen is None or (now - self._last_seen) > config.HAND_LOSS_TIMEOUT

    def reset(self) -> None:
        self._last_seen = None

    @staticmethod
    def draw_debug(frame_bgr, observation: HandObservation) -> None:
        """Draw all 21 landmarks onto a BGR frame in place (optional debugging)."""
        if frame_bgr is None or not observation.detected:
            return
        import cv2
        h, w = frame_bgr.shape[:2]
        for i, (x, y) in enumerate(observation.landmarks):
            primary = i == config.PRIMARY_LANDMARK
            colour = (0, 255, 255) if primary else (0, 200, 0)
            cv2.circle(frame_bgr, (int(x * w), int(y * h)), 6 if primary else 3, colour, -1)

    def close(self) -> None:
        for obj in (self._hands, self._landmarker):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        self._hands = None
        self._landmarker = None

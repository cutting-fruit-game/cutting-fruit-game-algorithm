"""Webcam capture with mirroring, error handling and guaranteed cleanup."""
from __future__ import annotations

import os
from typing import Optional

from src import config


class CameraError(RuntimeError):
    """Raised when the webcam cannot be opened or has been lost."""


class Camera:
    """Thin wrapper around cv2.VideoCapture. Frames are processed locally only."""

    def __init__(
        self,
        index: int = config.CAMERA_INDEX,
        width: int = config.CAMERA_WIDTH,
        height: int = config.CAMERA_HEIGHT,
        fps: int = config.CAMERA_FPS,
        mirror: bool = config.MIRROR_CAMERA,
    ) -> None:
        self.index, self.width, self.height, self.fps, self.mirror = index, width, height, fps, mirror
        self._cap = None
        self._cv2 = None
        self.consecutive_failures = 0

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def lost(self) -> bool:
        """True after too many consecutive failed reads."""
        return self.consecutive_failures >= config.CAMERA_MAX_READ_FAILURES

    def open(self) -> None:
        """Open the webcam; raises CameraError with a readable message."""
        if self.is_open:
            return
        try:
            import cv2
        except ImportError as exc:
            raise CameraError("OpenCV is not installed. Run: pip install opencv-python") from exc
        self._cv2 = cv2

        backends = [cv2.CAP_ANY]
        if os.name == "nt" and hasattr(cv2, "CAP_DSHOW"):
            backends.insert(0, cv2.CAP_DSHOW)      # faster start-up on Windows

        for backend in backends:
            cap = cv2.VideoCapture(self.index, backend)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            for _ in range(10):                    # warm-up: first frames may fail
                ok, frame = cap.read()
                if ok and frame is not None:
                    self._cap = cap
                    self.consecutive_failures = 0
                    return
            cap.release()
        if os.name == "nt":
            access = "camera access is allowed in Windows Settings > Privacy & security > Camera."
        else:
            access = "this user can open the camera (for example /dev/video0)."
        raise CameraError(
            f"Could not open webcam #{self.index}. Check that it is connected, "
            f"not used by another app, and that {access}"
        )

    def read(self):
        """Return the next BGR frame (mirrored if configured) or None on failure."""
        if not self.is_open:
            return None
        try:
            ok, frame = self._cap.read()
        except Exception:
            ok, frame = False, None
        if not ok or frame is None or frame.size == 0:
            self.consecutive_failures += 1
            return None
        self.consecutive_failures = 0
        if self.mirror:
            frame = self._cv2.flip(frame, 1)
        return frame

    def release(self) -> None:
        """Release the webcam (safe to call repeatedly)."""
        if self._cap is not None:
            try:
                self._cap.release()
            finally:
                self._cap = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.release()

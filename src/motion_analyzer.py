"""Position history, smoothing and motion measurements (pure logic, no I/O)."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple

from src import config

Point = Tuple[float, float]


@dataclass(frozen=True)
class MotionSample:
    """Result of analysing the recent movement window."""

    start: Point
    end: Point
    distance: float          # net displacement in px
    speed: float             # px / second
    direction: Point         # unit vector start -> end ((0, 0) if no movement)
    elapsed: float           # seconds covered by the window
    timestamp: float         # time of the newest point

    @property
    def angle_degrees(self) -> float:
        """Direction angle in degrees (screen coordinates, y points down)."""
        return math.degrees(math.atan2(self.direction[1], self.direction[0]))


def distance_between(a: Point, b: Point) -> float:
    """Euclidean distance between two points."""
    return math.hypot(b[0] - a[0], b[1] - a[1])


def compute_speed(distance: float, elapsed: float) -> float:
    """distance / elapsed, returning 0.0 for non-positive elapsed time."""
    if elapsed <= 0.0 or not math.isfinite(elapsed):
        return 0.0
    return distance / elapsed


def compute_direction(a: Point, b: Point) -> Point:
    """Unit vector from a to b, or (0.0, 0.0) when the points coincide."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (0.0, 0.0)
    return (dx / length, dy / length)


class MotionAnalyzer:
    """Keeps a timestamped, smoothed history of one tracked point.

    * Exponential smoothing reduces tracking jitter.
    * A dead-zone freezes the smoothed point for tiny movements.
    * ``analyze`` measures displacement/speed over a short recent window
      rather than a single frame.
    """

    def __init__(
        self,
        alpha: float = config.SMOOTHING_ALPHA,
        deadzone: float = config.JITTER_DEADZONE_PX,
        history_size: int = config.MOTION_HISTORY_SIZE,
        window_seconds: float = config.MOTION_WINDOW_SECONDS,
        min_elapsed: float = config.MIN_ELAPSED_SECONDS,
    ) -> None:
        self.alpha = min(1.0, max(0.01, alpha))
        self.deadzone = max(0.0, deadzone)
        self.window_seconds = window_seconds
        self.min_elapsed = min_elapsed
        self._history: Deque[Tuple[float, float, float]] = deque(maxlen=max(2, history_size))

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Forget all history (e.g. after the hand was lost)."""
        self._history.clear()

    def __len__(self) -> int:
        return len(self._history)

    @property
    def latest_point(self) -> Optional[Point]:
        """Newest smoothed point, or None if there is no history."""
        if not self._history:
            return None
        _, x, y = self._history[-1]
        return (x, y)

    @property
    def latest_timestamp(self) -> Optional[float]:
        return self._history[-1][0] if self._history else None

    # ------------------------------------------------------------------
    def add_point(self, point: Point, timestamp: float) -> Optional[Point]:
        """Add a raw point; returns the smoothed point (None if input invalid).

        Invalid (non-finite) input and non-increasing timestamps are ignored.
        """
        x, y = point
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(timestamp)):
            return self.latest_point
        if self._history and timestamp <= self._history[-1][0]:
            return self.latest_point

        if not self._history:
            sx, sy = float(x), float(y)
        else:
            _, px, py = self._history[-1]
            cx = px + self.alpha * (x - px)
            cy = py + self.alpha * (y - py)
            if math.hypot(cx - px, cy - py) < self.deadzone:
                cx, cy = px, py          # jitter: hold still
            sx, sy = cx, cy
        self._history.append((float(timestamp), sx, sy))
        return (sx, sy)

    def last_step(self):
        """Distance, speed, start and end of the newest pair of points."""
        if len(self._history) < 2:
            return None
        t0, x0, y0 = self._history[-2]
        t1, x1, y1 = self._history[-1]
        elapsed = t1 - t0
        if elapsed <= 0:
            return None
        start, end = (x0, y0), (x1, y1)
        dist = distance_between(start, end)
        return (dist, compute_speed(dist, elapsed), start, end)

    def window(self, window_seconds: Optional[float] = None):
        """Return history entries inside the recent window (oldest first)."""
        if not self._history:
            return []
        span = self.window_seconds if window_seconds is None else window_seconds
        newest_t = self._history[-1][0]
        return [h for h in self._history if newest_t - h[0] <= span]

    def analyze(self, window_seconds: Optional[float] = None) -> Optional[MotionSample]:
        """Measure net distance / speed / direction over the recent window.

        Returns None if there are fewer than two points or the window is too
        short in time to give a trustworthy speed.
        """
        samples = self.window(window_seconds)
        if len(samples) < 2:
            return None
        t0, x0, y0 = samples[0]
        t1, x1, y1 = samples[-1]
        elapsed = t1 - t0
        if elapsed < self.min_elapsed:
            return None
        start, end = (x0, y0), (x1, y1)
        dist = distance_between(start, end)
        return MotionSample(
            start=start,
            end=end,
            distance=dist,
            speed=compute_speed(dist, elapsed),
            direction=compute_direction(start, end),
            elapsed=elapsed,
            timestamp=t1,
        )
    

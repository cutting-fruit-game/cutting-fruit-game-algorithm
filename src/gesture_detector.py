"""Cutting-gesture recognition built on MotionAnalyzer (pure logic)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src import config
from src.motion_analyzer import MotionAnalyzer, MotionSample, Point


def calibrated_cut_speed(measured: float, preset: float) -> float:
    """Speed for this round: 75% of the practice swipe, inside the safe range.

    Never below the floor, and never above the sensitivity preset, so a fast
    practice swipe cannot make the game harder than the chosen setting.
    """
    scaled = float(measured) * config.CALIBRATED_SPEED_SCALE
    return min(float(preset), max(config.CALIBRATED_SPEED_FLOOR, scaled))


def swipe_too_slow(speed: float, distance: float, min_speed: float, min_distance: float) -> bool:
    """True when the hand is swiping, but slower than this round's cut speed."""
    if distance >= min_distance and speed >= min_speed:
        return False
    if speed < 80.0 or distance < 30.0:
        return False
    return speed < min_speed


def swipe_segments(window_points, previous, current, started: bool, active: bool):
    """Path the blade should test. A new swipe includes the whole recent path."""
    if started and len(window_points) >= 2:
        return [(a, b) for a, b in zip(window_points, window_points[1:])]
    if active and previous is not None and current is not None:
        return [(previous, current)]
    return []


def practice_swipe_ready(speed: float, distance: float,
                         min_distance: float = config.MIN_CUT_DISTANCE) -> bool:
    """A practice swipe is a real move, not a twitch while the hand is raised."""
    return distance >= min_distance and speed >= 200.0


@dataclass(frozen=True)
class CutGesture:
    """One detected cutting swipe."""

    start: Point
    end: Point
    direction: Point
    speed: float
    distance: float
    timestamp: float


class GestureDetector:
    """Turns a stream of fingertip positions into discrete cut gestures.

    A cut is reported **once** when the recent movement window satisfies both
    the distance and speed thresholds. The swipe then stays "active" (so the
    blade can keep slicing) until the speed drops below ``end_speed``; only
    after that - plus a short cooldown - can another cut be reported. This
    stops one continuous swipe from generating repeated cuts.
    """

    def __init__(
        self,
        analyzer: Optional[MotionAnalyzer] = None,
        min_distance: float = config.MIN_CUT_DISTANCE,
        min_speed: float = config.MIN_CUT_SPEED,
        end_speed: float = config.GESTURE_END_SPEED,
        cooldown: float = config.GESTURE_COOLDOWN,
    ) -> None:
        self.analyzer = analyzer or MotionAnalyzer()
        self.min_distance = min_distance
        self.min_speed = min_speed
        self.end_speed = end_speed
        self.cooldown = cooldown
        self._active = False
        self._tail_until = None
        self._cooldown_until = float("-inf")
        self.last_sample: Optional[MotionSample] = None

    # ------------------------------------------------------------------
    def configure(self, min_distance: Optional[float] = None,
                  min_speed: Optional[float] = None) -> None:
        """Change thresholds at runtime (per-user / per-webcam tuning)."""
        if min_distance is not None:
            self.min_distance = float(min_distance)
        if min_speed is not None:
            self.min_speed = float(min_speed)

    def is_cut(self, sample: Optional[MotionSample]) -> bool:
        """True if the recent window, or one fast step, is a real swipe."""
        if self._step_is_cut():
            return True
        return (
            sample is not None
            and sample.distance >= self.min_distance
            and sample.speed >= self.min_speed
        )

    def _motion_speed(self, sample: Optional[MotionSample]) -> float:
        speed = sample.speed if sample is not None else 0.0
        step = self.analyzer.last_step()
        if step is not None:
            speed = max(speed, step[1])
        return speed

    def _step_is_cut(self) -> bool:
        step = self.analyzer.last_step()
        if step is None:
            return False
        distance, speed = step[0], step[1]
        return distance >= config.RECENT_STEP_MIN_DISTANCE and speed >= self.min_speed

    @property
    def is_active(self) -> bool:
        """True while a swipe is in progress (blade may slice)."""
        return self._active

    @property
    def current_speed(self) -> float:
        return self.last_sample.speed if self.last_sample else 0.0

    @property
    def smoothed_point(self) -> Optional[Point]:
        return self.analyzer.latest_point

    def reset(self) -> None:
        """Clear state, e.g. when the hand is lost."""
        self.analyzer.reset()
        self._active = False
        self._tail_until = None
        self._cooldown_until = float("-inf")
        self.last_sample = None

    # ------------------------------------------------------------------
    def update(self, point: Point, timestamp: float) -> Optional[CutGesture]:
        """Feed one raw point. Returns a CutGesture only when a swipe starts."""
        self.analyzer.add_point(point, timestamp)
        sample = self.analyzer.analyze()
        self.last_sample = sample

        if self._active:
            if self._motion_speed(sample) >= self.end_speed:
                self._tail_until = None
            elif self._tail_until is None:
                self._tail_until = timestamp + config.SWIPE_TAIL_SECONDS
            if self._tail_until is not None and timestamp >= self._tail_until:
                self._active = False
                self._tail_until = None
                self._cooldown_until = timestamp + self.cooldown
            return None

        if timestamp < self._cooldown_until:
            return None

        if self.is_cut(sample):
            self._active = True
            if sample is None:
                distance, speed, start, end = self.analyzer.last_step()
                direction = (
                    (end[0] - start[0]) / distance if distance else 0.0,
                    (end[1] - start[1]) / distance if distance else 0.0,
                )
                return CutGesture(start, end, direction, speed, distance, timestamp)
            return CutGesture(
                start=sample.start,
                end=sample.end,
                direction=sample.direction,
                speed=sample.speed,
                distance=sample.distance,
                timestamp=sample.timestamp,
            )
        return None

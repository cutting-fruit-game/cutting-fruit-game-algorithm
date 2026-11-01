"""Tests for src/motion_analyzer.py (no webcam / display needed)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.motion_analyzer import (MotionAnalyzer, compute_direction, compute_speed,
                                 distance_between)


def make(**kw):
    """Analyzer without smoothing so numbers are exact."""
    defaults = dict(alpha=1.0, deadzone=0.0, window_seconds=0.2, min_elapsed=0.005)
    defaults.update(kw)
    return MotionAnalyzer(**defaults)


def test_distance():
    assert distance_between((0, 0), (3, 4)) == 5.0
    assert distance_between((2, 2), (2, 2)) == 0.0


def test_speed_calculation():
    a = make()
    a.add_point((0, 0), 0.0)
    a.add_point((100, 0), 0.1)
    s = a.analyze()
    assert s is not None
    assert math.isclose(s.distance, 100.0)
    assert math.isclose(s.speed, 1000.0)
    assert math.isclose(s.elapsed, 0.1)
    assert compute_speed(50, 0.5) == 100.0


def test_direction():
    assert compute_direction((0, 0), (10, 0)) == (1.0, 0.0)
    assert compute_direction((0, 0), (0, 5)) == (0.0, 1.0)      # y grows downwards
    assert compute_direction((4, 4), (4, 4)) == (0.0, 0.0)
    a = make()
    a.add_point((0, 0), 0.0)
    a.add_point((0, -50), 0.05)
    s = a.analyze()
    assert s.direction == (0.0, -1.0)
    assert math.isclose(s.angle_degrees, -90.0)


def test_slow_motion_is_measured_as_slow():
    a = make()
    for i in range(10):
        a.add_point((i * 3, 0), i / 30)        # 90 px/s
    s = a.analyze()
    assert s is not None
    assert s.speed < config.MIN_CUT_SPEED
    assert s.speed < 100


def test_short_movement_and_jitter_are_suppressed():
    a = MotionAnalyzer(alpha=0.5, deadzone=4.0, window_seconds=0.2)
    jitter = [(100, 100), (101, 99), (99, 101), (100, 102), (102, 100), (100, 100)]
    for i, p in enumerate(jitter):
        a.add_point(p, i / 30)
    s = a.analyze()
    assert s is not None
    assert s.distance < 1.0           # smoothed point never left the dead-zone
    assert s.speed < 10.0


def test_empty_and_single_point_history():
    a = make()
    assert a.analyze() is None
    assert a.latest_point is None
    a.add_point((5, 5), 1.0)
    assert a.analyze() is None         # one point is not a movement
    assert a.latest_point == (5.0, 5.0)


def test_timestamp_edge_cases():
    a = make(min_elapsed=0.01)
    a.add_point((0, 0), 1.0)
    a.add_point((50, 0), 1.0)          # same timestamp -> ignored
    a.add_point((60, 0), 0.5)          # going backwards -> ignored
    assert len(a) == 1
    a.add_point((50, 0), 1.001)        # elapsed below minimum
    assert a.analyze() is None
    assert compute_speed(100, 0.0) == 0.0
    assert compute_speed(100, -1.0) == 0.0


def test_invalid_points_ignored():
    a = make()
    a.add_point((0, 0), 0.0)
    a.add_point((float("nan"), 3), 0.1)
    a.add_point((3, float("inf")), 0.2)
    a.add_point((3, 3), float("nan"))
    assert len(a) == 1


def test_window_only_uses_recent_points():
    a = make(window_seconds=0.1)
    a.add_point((0, 0), 0.0)
    a.add_point((1000, 0), 0.05)
    a.add_point((1000, 0), 1.0)        # long pause afterwards
    a.add_point((1000, 0), 1.05)
    s = a.analyze()
    assert s.distance == 0.0           # the old fast movement is outside the window


def test_reset_clears_history():
    a = make()
    a.add_point((0, 0), 0.0)
    a.add_point((10, 0), 0.1)
    a.reset()
    assert len(a) == 0 and a.analyze() is None

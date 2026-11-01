"""Tests for src/gesture_detector.py (deterministic input, no hardware)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gesture_detector import GestureDetector
from src.motion_analyzer import MotionAnalyzer

DT = 1 / 30


def detector(**kw):
    analyzer = MotionAnalyzer(alpha=1.0, deadzone=0.0, window_seconds=0.18)
    return GestureDetector(analyzer=analyzer, **kw)


def swipe(det, start_x, step, frames, t0, y=200):
    """Feed a horizontal movement; returns (gestures, next_time)."""
    gestures = []
    for i in range(frames):
        g = det.update((start_x + i * step, y), t0 + i * DT)
        if g is not None:
            gestures.append(g)
    return gestures, t0 + frames * DT


def test_valid_cutting_gesture():
    det = detector()
    gestures, _ = swipe(det, 100, 40, 8, 0.0)       # ~1200 px/s
    assert len(gestures) == 1
    g = gestures[0]
    assert g.distance >= det.min_distance
    assert g.speed >= det.min_speed
    assert g.direction[0] > 0.99 and abs(g.direction[1]) < 1e-6
    assert g.end[0] > g.start[0]
    assert g.timestamp > 0
    assert det.is_active


def test_slow_movement_rejected():
    det = detector()
    gestures, _ = swipe(det, 100, 3, 40, 0.0)       # ~90 px/s
    assert gestures == []
    assert not det.is_active


def test_short_movement_rejected():
    det = detector()
    g1 = det.update((100, 100), 0.0)
    g2 = det.update((120, 100), 0.02)               # fast (1000 px/s) but only 20 px
    assert g1 is None and g2 is None


def test_thresholds_are_configurable():
    # ~500 px/s over ~83 px: below the default speed threshold ...
    strict = detector()
    gestures, _ = swipe(strict, 100, 500 * DT, 8, 0.0)
    assert gestures == []
    # ... but accepted with relaxed thresholds.
    relaxed = detector(min_distance=50, min_speed=300)
    gestures, _ = swipe(relaxed, 100, 500 * DT, 8, 0.0)
    assert len(gestures) == 1
    # configure() changes thresholds at runtime
    runtime = detector()
    runtime.configure(min_distance=50, min_speed=300)
    gestures, _ = swipe(runtime, 100, 500 * DT, 8, 0.0)
    assert len(gestures) == 1


def test_continuous_swipe_triggers_only_once():
    det = detector()
    gestures, t = swipe(det, 100, 40, 30, 0.0)      # long uninterrupted swipe
    assert len(gestures) == 1


def test_second_swipe_after_pause_triggers_again():
    det = detector()
    first, t = swipe(det, 100, 40, 8, 0.0)
    assert len(first) == 1
    # hold still long enough for the swipe to end and the cooldown to pass
    for i in range(20):
        det.update((420, 200), t + i * DT)
    assert not det.is_active
    t += 20 * DT
    second, _ = swipe(det, 420, -40, 8, t)
    assert len(second) == 1
    assert second[0].direction[0] < 0


def test_reset_clears_state():
    det = detector()
    swipe(det, 100, 40, 8, 0.0)
    assert det.is_active
    det.reset()
    assert not det.is_active
    assert det.smoothed_point is None
    assert det.current_speed == 0.0


def test_fast_step_without_a_full_window_does_not_crash():
    det = detector()
    det.update((0, 100), 0.0)
    gesture = det.update((80, 100), 0.005)
    assert gesture is not None
    assert gesture.distance >= 48
    assert det.is_active


def test_fast_step_counts_when_the_window_is_diluted():
    det = detector()
    det.update((0, 100), 0.0)
    det.update((0, 100), 0.12)
    gesture = det.update((70, 100), 0.15)
    assert gesture is not None
    assert det.is_active


def test_swipe_stays_active_briefly_after_it_slows():
    det = detector()
    _gestures, t = swipe(det, 100, 40, 8, 0.0)
    end_x = 100 + 7 * 40
    det.update((end_x, 200), t + 0.20)
    assert det.is_active
    det.update((end_x, 200), t + 0.20 + 0.13)
    assert not det.is_active


def test_practice_swipe_speed_stays_inside_the_safe_range():
    from src.gesture_detector import calibrated_cut_speed
    preset = 650.0
    assert calibrated_cut_speed(800, preset) == 600.0
    assert calibrated_cut_speed(200, preset) == 400.0
    assert calibrated_cut_speed(2000, preset) == preset
    assert calibrated_cut_speed(2000, 450) == 450.0


def test_slow_swipe_hint_ignores_a_real_cut_and_a_still_hand():
    from src.gesture_detector import swipe_too_slow
    assert swipe_too_slow(500, 100, 650, 80)
    assert not swipe_too_slow(700, 100, 650, 80)
    assert not swipe_too_slow(0, 0, 650, 80)
    assert not swipe_too_slow(40, 10, 650, 80)

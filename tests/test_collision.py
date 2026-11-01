"""Tests for src/collision.py and fruit slicing (no display needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.collision import (CollisionDetector, closest_point_on_segment,
                           point_segment_distance, segment_hits_circle)
from src.fruit import Fruit
from src.fruit_manager import FruitManager


def apple(x=100, y=100):
    return Fruit(config.FRUIT_SPECS["apple"], x, y, radius=40)   # hitbox radius = 36


def test_halves_split_across_the_cut():
    horizontal = apple()
    horizontal.slice(0.0)
    assert abs(horizontal.pieces[0].y - horizontal.pieces[1].y) > horizontal.radius
    assert abs(horizontal.pieces[0].x - horizontal.pieces[1].x) < horizontal.radius

    vertical = apple()
    vertical.slice(90.0)
    assert abs(vertical.pieces[0].x - vertical.pieces[1].x) > vertical.radius
    assert abs(vertical.pieces[0].y - vertical.pieces[1].y) < vertical.radius


def test_swipe_path_hits_fruit_the_last_step_misses():
    from src.gesture_detector import swipe_segments
    fruit = Fruit(config.FRUIT_SPECS["apple"], 60, 100, radius=20)
    last_step = swipe_segments([], (90, 100), (130, 100), False, True)
    assert CollisionDetector(tolerance=0).check(last_step, [fruit]) == []
    path = [(0, 100), (40, 100), (80, 100), (120, 100)]
    segments = swipe_segments(path, None, None, True, True)
    assert len(CollisionDetector(tolerance=0).check(segments, [fruit])) == 1


def test_blade_fruit_intersection():
    f = apple()
    results = CollisionDetector(tolerance=0).check([((50, 100), (150, 100))], [f])
    assert len(results) == 1
    assert results[0].fruit is f
    assert f.sliced and len(f.pieces) == 2


def test_non_intersecting_movement():
    f = apple()
    results = CollisionDetector(tolerance=0).check([((300, 300), (400, 320))], [f])
    assert results == []
    assert not f.sliced


def test_fast_segment_crossing_with_endpoints_outside():
    """Neither endpoint is inside the fruit, yet the segment crosses it."""
    f = apple()
    results = CollisionDetector(tolerance=0).check([((-500, 100), (700, 100))], [f])
    assert len(results) == 1


def test_collision_tolerance():
    # Segment passes 40 px below the centre; hitbox radius is 36.
    seg = [((0, 140), (200, 140))]
    assert CollisionDetector(tolerance=0).check(seg, [apple()]) == []
    assert len(CollisionDetector(tolerance=8).check(seg, [apple()])) == 1


def test_duplicate_hit_prevention():
    f = apple()
    det = CollisionDetector(tolerance=0)
    seg = [((50, 100), (150, 100))]
    assert len(det.check(seg, [f])) == 1
    assert det.check(seg, [f]) == []                # blade still inside the fruit
    assert det.check(seg + seg, [f]) == []
    assert f.slice(0.0) is False                    # slice() only succeeds once


def test_multiple_fruits_in_one_swipe():
    a, b = apple(100, 100), apple(300, 100)
    results = CollisionDetector(tolerance=0).check([((0, 100), (400, 100))], [a, b])
    assert {r.fruit for r in results} == {a, b}


def test_geometry_helpers():
    assert point_segment_distance((0, 5), (-10, 0), (10, 0)) == 5.0
    assert point_segment_distance((20, 0), (-10, 0), (10, 0)) == 10.0     # beyond the end
    assert point_segment_distance((3, 4), (0, 0), (0, 0)) == 5.0          # zero-length
    assert closest_point_on_segment((5, 9), (0, 0), (10, 0)) == (5.0, 0.0)
    assert segment_hits_circle((0, 0), (10, 0), (5, 3), 3.0)
    assert not segment_hits_circle((0, 0), (10, 0), (5, 4), 3.0)


def test_launch_speed_starts_slow_then_steps_every_10_seconds():
    start = config.SPEED_RAMP_START
    step = config.SPEED_RAMP_STEP
    assert FruitManager.time_speed_multiplier(0, 60) == start
    assert FruitManager.time_speed_multiplier(9.9, 60) == start
    assert FruitManager.time_speed_multiplier(10, 60) == start + step
    assert FruitManager.time_speed_multiplier(30, 60) == start + 3 * step
    assert FruitManager.time_speed_multiplier(50, 60) == start + 5 * step


def test_fruit_physics_gravity_and_removal():
    f = Fruit(config.FRUIT_SPECS["orange"], 100, 700, vx=50, vy=-900)
    f.update(0.1)
    assert f.x > 100 and f.y < 700              # moving up and sideways
    assert f.vy > -900                          # gravity slows the rise
    for _ in range(200):
        f.update(0.05)
    assert f.is_finished(720)                   # fell below the screen
    f.update(0)                                 # dt = 0 is harmless

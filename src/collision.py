"""Geometric blade-vs-fruit collision tests (pure logic)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from src import config
from src.motion_analyzer import Point

Segment = tuple  # ((x1, y1), (x2, y2))


def closest_point_on_segment(p: Point, a: Point, b: Point) -> Point:
    """Closest point to ``p`` on the segment a-b (handles zero-length segments)."""
    abx, aby = b[0] - a[0], b[1] - a[1]
    length_sq = abx * abx + aby * aby
    if length_sq < 1e-12:
        return a
    t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / length_sq
    t = max(0.0, min(1.0, t))
    return (a[0] + t * abx, a[1] + t * aby)


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """Shortest distance from point ``p`` to segment a-b."""
    c = closest_point_on_segment(p, a, b)
    return math.hypot(p[0] - c[0], p[1] - c[1])


def segment_hits_circle(a: Point, b: Point, center: Point, radius: float,
                        tolerance: float = 0.0) -> bool:
    """True if the segment passes within ``radius + tolerance`` of ``center``.

    Because the whole segment is tested, a fast fingertip that jumps across a
    fruit between two frames is still detected.
    """
    return point_segment_distance(center, a, b) <= max(0.0, radius + tolerance)


@dataclass(frozen=True)
class CollisionResult:
    fruit: object            # src.fruit.Fruit (typed loosely to avoid import cycles)
    point: Point             # contact point on the blade segment
    angle_degrees: float     # direction of the blade segment


class CollisionDetector:
    """Tests blade segments against fruit hitboxes and reports first hits only."""

    def __init__(self, tolerance: float = config.COLLISION_TOLERANCE) -> None:
        self.tolerance = tolerance

    def check(self, segments: Iterable[Segment], fruits: Sequence) -> List[CollisionResult]:
        """Return a CollisionResult for every fruit newly sliced this call.

        ``fruit.slice()`` returns False for an already-sliced fruit, so a blade
        that stays inside a fruit can never produce a duplicate event.
        """
        results: List[CollisionResult] = []
        segs = list(segments)
        for fruit in fruits:
            if getattr(fruit, "sliced", False):
                continue
            cx, cy, radius = fruit.hitbox
            for a, b in segs:
                if segment_hits_circle(a, b, (cx, cy), radius, self.tolerance):
                    angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                    if fruit.slice(angle):
                        results.append(
                            CollisionResult(fruit, closest_point_on_segment((cx, cy), a, b), angle)
                        )
                    break
        return results

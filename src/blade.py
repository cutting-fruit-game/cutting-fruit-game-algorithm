"""Virtual blade: trail history, fading and cutting-effect state (no drawing)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from src import config
from src.motion_analyzer import Point

Segment = Tuple[Point, Point]


@dataclass(frozen=True)
class BladePoint:
    x: float
    y: float
    t: float
    stroke: int
    active: bool


@dataclass(frozen=True)
class TrailPoint:
    """Render-ready trail point."""

    x: float
    y: float
    alpha: float     # 0..1 opacity
    width: float     # px
    stroke: int      # consecutive points only connect inside the same stroke


class Blade:
    """Stores recent fingertip points and exposes render data and segments."""

    def __init__(
        self,
        max_points: int = config.BLADE_MAX_POINTS,
        lifetime: float = config.BLADE_LIFETIME,
        base_width: float = config.BLADE_BASE_WIDTH,
        active_width: float = config.BLADE_ACTIVE_WIDTH,
    ) -> None:
        self.lifetime = max(0.01, lifetime)
        self.base_width = base_width
        self.active_width = active_width
        self._points: Deque[BladePoint] = deque(maxlen=max(2, max_points))
        self._stroke = 0
        self._broken = False
        self.active = False

    def clear(self) -> None:
        self._points.clear()
        self._broken = True
        self.active = False

    def break_trail(self) -> None:
        """Start a new stroke at the next point (e.g. after hand loss)."""
        self._broken = True
        self.active = False

    def add_point(self, point: Point, now: float, active: bool = False) -> Optional[Segment]:
        """Append a point; return the segment from the previous point if any."""
        if self._broken:
            self._stroke += 1
            self._broken = False
        prev = self._points[-1] if self._points else None
        self._points.append(BladePoint(point[0], point[1], now, self._stroke, active))
        self.active = active
        if prev is not None and prev.stroke == self._stroke:
            return ((prev.x, prev.y), point)
        return None

    def update(self, now: float) -> None:
        """Drop points older than the lifetime."""
        while self._points and now - self._points[0].t > self.lifetime:
            self._points.popleft()

    def trail(self, now: float) -> List[TrailPoint]:
        """Trail points with fading opacity and tapering width."""
        out: List[TrailPoint] = []
        for p in self._points:
            age = now - p.t
            if age > self.lifetime or age < 0:
                continue
            fade = 1.0 - age / self.lifetime
            width = (self.active_width if p.active else self.base_width) * (0.3 + 0.7 * fade)
            out.append(TrailPoint(p.x, p.y, fade, width, p.stroke))
        return out

    def segments(self, now: float) -> List[Segment]:
        """All live segments inside the same stroke (oldest first)."""
        pts = self.trail(now)
        return [((a.x, a.y), (b.x, b.y)) for a, b in zip(pts, pts[1:]) if a.stroke == b.stroke]

    def __len__(self) -> int:
        return len(self._points)

"""Fruit and bomb objects: physics, hitbox, slicing state, falling pieces."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src import config
from src.config import FruitSpec

_ids = itertools.count(1)


@dataclass
class FruitPiece:
    """One half of a sliced fruit."""

    x: float
    y: float
    vx: float
    vy: float
    rotation: float            # degrees, clockwise
    angular_velocity: float
    side: int                  # -1 = left half, +1 = right half


class Fruit:
    """A flying fruit or bomb."""

    def __init__(
        self,
        spec: FruitSpec,
        x: float,
        y: float,
        vx: float = 0.0,
        vy: float = 0.0,
        gravity: float = config.GRAVITY,
        radius: Optional[float] = None,
        rotation: float = 0.0,
        angular_velocity: float = 0.0,
    ) -> None:
        self.id = next(_ids)
        self.spec = spec
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.gravity = float(gravity)
        self.radius = float(radius if radius is not None else spec.radius)
        self.rotation = float(rotation)
        self.angular_velocity = float(angular_velocity)
        self.sliced = False
        self.slice_angle = 0.0
        self.age_since_slice = 0.0
        self.pieces: List[FruitPiece] = []

    # -- properties -----------------------------------------------------
    @property
    def kind(self) -> str:
        return self.spec.name

    @property
    def is_bomb(self) -> bool:
        return self.spec.is_bomb

    @property
    def hitbox(self) -> Tuple[float, float, float]:
        """(center_x, center_y, radius) of the circular hitbox."""
        return (self.x, self.y, self.radius * config.HITBOX_SCALE)

    # -- behaviour ------------------------------------------------------
    def update(self, dt: float) -> None:
        """Advance physics by ``dt`` seconds (ignored if dt <= 0)."""
        if dt <= 0:
            return
        if not self.sliced:
            self.vy += self.gravity * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.rotation = (self.rotation + self.angular_velocity * dt) % 360.0
            return
        self.age_since_slice += dt
        for p in self.pieces:
            p.vy += self.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rotation = (p.rotation + p.angular_velocity * dt) % 360.0

    def slice(self, angle_degrees: float = 0.0) -> bool:
        """Slice the fruit. Returns True only the first time it is called."""
        if self.sliced:
            return False
        self.sliced = True
        self.slice_angle = angle_degrees
        theta = math.radians(angle_degrees)
        # Normal points across the cut. Halves fly apart along it.
        nx, ny = -math.sin(theta), math.cos(theta)
        cut_rotation = angle_degrees - 90.0
        gap = self.radius * 0.16
        half = self.radius * 0.5
        if self.is_bomb:
            carry = 0.35
            speed = config.SLICE_SEPARATION_SPEED * 2.6
            spin_mag = 640.0
        else:
            carry = 0.8
            speed = config.SLICE_SEPARATION_SPEED
            spin_mag = 240.0
        # side -1 is the left sprite, +1 the right. Their cut edges meet on the swipe.
        for side, direction, spin in ((-1, 1.0, spin_mag), (1, -1.0, -spin_mag)):
            self.pieces.append(
                FruitPiece(
                    x=self.x + direction * nx * (half + gap),
                    y=self.y + direction * ny * (half + gap),
                    vx=self.vx * carry + direction * nx * speed,
                    vy=self.vy * carry + direction * ny * speed,
                    rotation=cut_rotation,
                    angular_velocity=spin,
                    side=side,
                )
            )
        return True

    def is_finished(self, screen_height: float) -> bool:
        """True when the object can be removed from the game."""
        margin = self.radius * 2
        if self.sliced:
            if self.age_since_slice > config.PIECE_MAX_LIFETIME:
                return True
            return all(p.y - margin > screen_height for p in self.pieces)
        return self.vy > 0 and self.y - self.radius > screen_height

    @property
    def missed(self) -> bool:
        """Unsliced fruit that fell away. A bomb that falls is not a miss."""
        return not self.sliced and not self.is_bomb

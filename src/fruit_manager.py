"""Spawning, updating and removing fruits, with difficulty scaling."""
from __future__ import annotations

import math
import random
from typing import List, Optional

from src import config
from src.fruit import Fruit


class FruitManager:
    """Owns all live fruit objects."""

    def __init__(
        self,
        screen_width: int = config.SCREEN_WIDTH,
        screen_height: int = config.SCREEN_HEIGHT,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.width = screen_width
        self.height = screen_height
        self.rng = rng or random.Random()
        self.fruits: List[Fruit] = []
        self._timer = 0.5            # first spawn shortly after start

    # -- difficulty ------------------------------------------------------
    @staticmethod
    def spawn_interval(level: int) -> float:
        rate = 1.0 + config.DIFFICULTY_SPAWN_STEP * (max(1, level) - 1)
        return max(config.MIN_SPAWN_INTERVAL, config.SPAWN_BASE_INTERVAL / rate)

    @staticmethod
    def speed_multiplier(level: int) -> float:
        return 1.0 + config.DIFFICULTY_SPEED_STEP * (max(1, level) - 1)

    @staticmethod
    def time_speed_multiplier(elapsed: float, duration: float) -> float:
        """Slow for the first 10 seconds, then one step faster every 10 seconds."""
        elapsed = max(0.0, elapsed)
        steps = int(elapsed // config.SPEED_STEP_SECONDS)
        if duration > 0:
            steps = min(steps, int((duration - 0.001) // config.SPEED_STEP_SECONDS))
        return config.SPEED_RAMP_START + steps * config.SPEED_RAMP_STEP

    @staticmethod
    def bomb_probability(level: int) -> float:
        p = config.BOMB_PROBABILITY + config.BOMB_PROBABILITY_STEP * (max(1, level) - 1)
        return min(config.BOMB_PROBABILITY_MAX, p)

    @staticmethod
    def max_burst(level: int) -> int:
        return min(config.MAX_BURST, 1 + max(1, level) // 3)

    # -- lifecycle --------------------------------------------------------
    def reset(self) -> None:
        self.fruits.clear()
        self._timer = 0.5

    @property
    def active_fruits(self) -> List[Fruit]:
        return [f for f in self.fruits if not f.sliced]

    def _pick_spec(self, level: int):
        if self.rng.random() < self.bomb_probability(level):
            return config.FRUIT_SPECS["bomb"]
        specs = [s for s in config.FRUIT_SPECS.values() if not s.is_bomb and s.weight > 0]
        return self.rng.choices(specs, weights=[s.weight for s in specs], k=1)[0]

    def spawn_one(self, level: int = 1, speed_scale: float = 1.0) -> Fruit:
        """Create one fruit launched from below the screen."""
        spec = self._pick_spec(level)
        radius = spec.radius * self.rng.uniform(*config.RADIUS_JITTER)
        mult = self.speed_multiplier(level) * speed_scale
        gravity = config.GRAVITY * mult
        apex = self.height * self.rng.uniform(config.APEX_MIN_FRACTION, config.APEX_MAX_FRACTION)
        vy = -math.sqrt(2.0 * gravity * apex)
        flight_time = 2.0 * abs(vy) / gravity
        x = self.rng.uniform(self.width * config.SPAWN_X_MARGIN, self.width * (1 - config.SPAWN_X_MARGIN))
        target = self.rng.uniform(self.width * config.TARGET_X_MIN, self.width * config.TARGET_X_MAX)
        limit = config.MAX_VX * math.sqrt(mult)
        vx = max(-limit, min(limit, (target - x) / flight_time))
        fruit = Fruit(
            spec, x, self.height + radius, vx, vy, gravity=gravity, radius=radius,
            rotation=self.rng.uniform(0, 360),
            angular_velocity=self.rng.uniform(*config.ANGULAR_SPEED_RANGE),
        )
        self.fruits.append(fruit)
        return fruit

    def update(
        self,
        dt: float,
        level: int = 1,
        spawning: bool = True,
        elapsed: float = 0.0,
        duration: float = 0.0,
    ) -> List[Fruit]:
        """Advance all objects; returns the fruits that were missed this step."""
        if dt <= 0:
            return []
        if spawning:
            self._timer -= dt
            if self._timer <= 0:
                burst = self.rng.randint(1, self.max_burst(level))
                scale = self.time_speed_multiplier(elapsed, duration)
                for _ in range(burst):
                    if len(self.active_fruits) < config.MAX_ACTIVE_OBJECTS:
                        self.spawn_one(level, scale)
                self._timer = self.spawn_interval(level) * self.rng.uniform(0.8, 1.2)

        missed: List[Fruit] = []
        keep: List[Fruit] = []
        for fruit in self.fruits:
            fruit.update(dt)
            if fruit.is_finished(self.height):
                if fruit.missed:
                    missed.append(fruit)
            else:
                keep.append(fruit)
        self.fruits = keep
        return missed

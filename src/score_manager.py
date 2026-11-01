"""Score, combos, lives, timer, levels and high score (independent of rendering)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set, Union

from src import config


@dataclass(frozen=True)
class ScoreEvent:
    """Outcome of registering one cut."""

    kind: str                  # "fruit" or "bomb"
    points: int                # points actually added (0 for bombs)
    multiplier: int
    combo: int
    critical: bool
    lives_lost: int
    leveled_up: bool


class ComboBanner:
    """Big x2 / x3 / x4 shown only when the multiplier steps up. It does not score."""

    def __init__(self, duration: float = 0.7) -> None:
        self.duration = float(duration)
        self.multiplier = 1
        self.text = ""
        self.life = 0.0

    def note(self, multiplier: int) -> bool:
        """Record the current multiplier. Returns True only on a step up past x1."""
        stepped = multiplier > self.multiplier and multiplier >= 2
        self.multiplier = int(multiplier)
        if stepped:
            self.text = f"x{multiplier}"
            self.life = self.duration
        return stepped

    def tick(self, dt: float) -> None:
        if dt <= 0 or self.life <= 0:
            return
        self.life = max(0.0, self.life - dt)
        if self.life <= 0:
            self.text = ""


class ScoreManager:
    """All game-rule bookkeeping. Time is advanced explicitly with ``tick``."""

    def __init__(
        self,
        high_score_path: Optional[Union[str, Path]] = None,
        duration: float = config.GAME_DURATION,
        lives: int = config.STARTING_LIVES,
    ) -> None:
        self.duration = float(duration)
        self.start_lives = int(lives)
        self.high_score_path = Path(high_score_path) if high_score_path else None
        self.high_score = self._load_high_score()
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.score = config.INITIAL_SCORE
        self.lives = self.start_lives
        self.combo = 0
        self.best_combo = 0
        self.time_remaining = self.duration
        self.game_time = 0.0
        self._last_cut_time = float("-inf")
        self._awarded: Set[int] = set()
        self.new_high_score = False

    # -- derived values ---------------------------------------------------
    @property
    def level(self) -> int:
        return min(config.MAX_LEVEL, 1 + max(0, self.score) // config.LEVEL_SCORE_STEP)

    @property
    def multiplier(self) -> int:
        if self.combo <= 0:
            return 1
        return min(config.MAX_COMBO_MULTIPLIER, 1 + self.combo // config.COMBO_STEP)

    @property
    def is_game_over(self) -> bool:
        return self.lives <= 0 or self.time_remaining <= 0.0

    # -- time ---------------------------------------------------------------
    def tick(self, dt: float) -> None:
        """Advance the game clock; resets the combo when it times out."""
        if dt <= 0:
            return
        self.game_time += dt
        self.time_remaining = max(0.0, self.time_remaining - dt)
        if self.combo and self.game_time - self._last_cut_time > config.COMBO_TIMEOUT:
            self.combo = 0

    # -- events ---------------------------------------------------------------
    def register_cut(self, fruit_id: int, kind: str, critical: bool = False) -> Optional[ScoreEvent]:
        """Register a slice. Returns None if this fruit was already counted."""
        if kind not in config.FRUIT_SPECS:
            raise ValueError(f"Unknown fruit kind: {kind!r}")
        if fruit_id in self._awarded:
            return None
        self._awarded.add(fruit_id)
        spec = config.FRUIT_SPECS[kind]
        old_level = self.level

        if spec.is_bomb:
            self.lives = max(0, self.lives - config.BOMB_LIFE_PENALTY)
            self.combo = 0
            return ScoreEvent("bomb", 0, 1, 0, False, config.BOMB_LIFE_PENALTY, False)

        if self.game_time - self._last_cut_time <= config.COMBO_TIMEOUT:
            self.combo += 1
        else:
            self.combo = 1
        self._last_cut_time = self.game_time
        self.best_combo = max(self.best_combo, self.combo)

        mult = self.multiplier
        points = spec.points * mult + (config.CRITICAL_BONUS if critical else 0)
        self.score += points
        return ScoreEvent("fruit", points, mult, self.combo, critical, 0, self.level > old_level)

    def register_miss(self, fruit_id: int, kind: str) -> Optional[ScoreEvent]:
        """Fruit that falls unsliced keeps its hearts and its combo. Fallen bombs are ignored."""
        if kind not in config.FRUIT_SPECS:
            raise ValueError(f"Unknown fruit kind: {kind!r}")
        if config.FRUIT_SPECS[kind].is_bomb or fruit_id in self._awarded:
            return None
        self._awarded.add(fruit_id)
        return ScoreEvent("miss", 0, self.multiplier, self.combo, False, 0, False)

    # -- high score -------------------------------------------------------------
    def finalize(self) -> bool:
        """Call once at game over. Updates and saves the high score."""
        if self.score > self.high_score:
            self.high_score = self.score
            self.new_high_score = True
            self._save_high_score()
        return self.new_high_score

    def _load_high_score(self) -> int:
        if not self.high_score_path:
            return 0
        try:
            data = json.loads(self.high_score_path.read_text(encoding="utf-8"))
            return max(0, int(data.get("high_score", 0)))
        except (OSError, ValueError, TypeError, AttributeError):
            return 0

    def _save_high_score(self) -> None:
        if not self.high_score_path:
            return
        try:
            self.high_score_path.write_text(
                json.dumps({"high_score": self.high_score}), encoding="utf-8")
        except OSError:
            pass   # saving is best-effort

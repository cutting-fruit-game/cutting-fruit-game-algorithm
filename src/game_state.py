"""Game state machine: MENU, CALIBRATION, COUNTDOWN, PLAYING, PAUSE, GAME_OVER."""
from __future__ import annotations

import math
from enum import Enum, auto
from typing import Dict, Set

from src import config


class GameState(Enum):
    MENU = auto()
    CALIBRATION = auto()
    COUNTDOWN = auto()
    PLAYING = auto()
    PAUSE = auto()
    GAME_OVER = auto()


ALLOWED_TRANSITIONS: Dict[GameState, Set[GameState]] = {
    GameState.MENU: {GameState.CALIBRATION},
    GameState.CALIBRATION: {GameState.COUNTDOWN, GameState.MENU},
    GameState.COUNTDOWN: {GameState.PLAYING, GameState.MENU},
    GameState.PLAYING: {GameState.PAUSE, GameState.GAME_OVER, GameState.COUNTDOWN},
    GameState.PAUSE: {GameState.PLAYING, GameState.COUNTDOWN, GameState.MENU},
    GameState.GAME_OVER: {GameState.COUNTDOWN, GameState.MENU},
}

MENU_PAGES = ("main", "instructions", "settings", "exit_confirm")


class GameStateMachine:
    """Holds the current state, validates transitions and runs the countdown."""

    def __init__(self) -> None:
        self.state = GameState.MENU
        self.previous = GameState.MENU
        self.menu_page = "main"
        self.countdown_remaining = float(config.COUNTDOWN_SECONDS)

    def can_transition(self, new_state: GameState) -> bool:
        return new_state in ALLOWED_TRANSITIONS[self.state]

    def transition(self, new_state: GameState) -> bool:
        """Switch state if the transition is valid; returns success."""
        if not self.can_transition(new_state):
            return False
        self.previous = self.state
        self.state = new_state
        if new_state == GameState.COUNTDOWN:
            self.countdown_remaining = float(config.COUNTDOWN_SECONDS)
        elif new_state == GameState.MENU:
            self.menu_page = "main"
        return True

    def open_menu_page(self, page: str) -> None:
        if self.state == GameState.MENU and page in MENU_PAGES:
            self.menu_page = page

    @property
    def countdown_number(self) -> int:
        return max(1, int(math.ceil(self.countdown_remaining)))

    def update(self, dt: float) -> bool:
        """Advance the countdown; returns True when it just finished."""
        if self.state != GameState.COUNTDOWN or dt <= 0:
            return False
        self.countdown_remaining -= dt
        if self.countdown_remaining <= 0:
            self.transition(GameState.PLAYING)
            return True
        return False

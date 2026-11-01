"""Sound effects and music with safe fallbacks.

Looks for files in assets/sounds/ (slice, bomb, combo, countdown, go,
gameover, click as .wav/.ogg/.mp3, and optional music.*). Any missing sound
is synthesised procedurally, and if audio is unavailable entirely every
call silently does nothing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pygame

from src import config

_EXTENSIONS = (".wav", ".ogg", ".mp3")


def find_sound_file(sound_dir: Path, stem: str) -> Optional[Path]:
    """A recorded file wins over the generated sound."""
    for ext in _EXTENSIONS:
        path = Path(sound_dir) / f"{stem}{ext}"
        if path.is_file():
            return path
    return None


def synth_samples(name: str, rate: int = 44100) -> np.ndarray:
    """Generated sound samples in -1..1. Slice is short, the bomb rumbles, combo is two notes."""
    count = lambda seconds: np.linspace(0, seconds, max(1, int(rate * seconds)), endpoint=False)
    rng = np.random.default_rng(1)
    if name == "slice":
        x = count(0.09)
        noise = rng.uniform(-1, 1, x.size)
        s = noise * np.exp(-x * 40) + 0.45 * np.sin(2 * np.pi * 1900 * x) * np.exp(-x * 45)
    elif name == "bomb":
        x = count(0.55)
        s = (0.75 * np.sin(2 * np.pi * 52 * x) + 0.4 * rng.uniform(-1, 1, x.size)) * np.exp(-x * 3.5)
    elif name == "combo":
        x = count(0.38)
        s = np.zeros_like(x)
        first = x < 0.14
        second = (x >= 0.18) & (x < 0.34)
        s[first] = np.sin(2 * np.pi * 660 * x[first]) * np.exp(-x[first] * 7)
        s[second] = np.sin(2 * np.pi * 990 * (x[second] - 0.18)) * np.exp(-(x[second] - 0.18) * 7)
    elif name == "countdown":
        x = count(0.12)
        s = np.sin(2 * np.pi * 880 * x) * np.exp(-x * 12)
    elif name == "go":
        x = count(0.3)
        s = np.sin(2 * np.pi * 1320 * x) * np.exp(-x * 7)
    elif name == "gameover":
        x = count(0.7)
        s = np.sin(2 * np.pi * (440 - 220 * x / 0.7) * x) * np.exp(-x * 3)
    elif name == "ready":
        x = count(0.35)
        s = np.sin(2 * np.pi * (520 + 180 * x / 0.35) * x) * np.exp(-x * 7)
    else:
        x = count(0.05)
        s = np.sin(2 * np.pi * 600 * x) * np.exp(-x * 40)
    return np.asarray(s, dtype=np.float64)


class AudioManager:
    def __init__(self, enabled: bool = True, sound_dir: Path = config.SOUNDS_DIR) -> None:
        self.enabled = enabled
        self.sound_dir = Path(sound_dir)
        self.available = False
        self._sounds: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self._music_playing = False
        self._music_requested = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 1, 512)
            self.available = pygame.mixer.get_init() is not None
        except pygame.error:
            self.available = False
        if self.available:
            for name in ("slice", "bomb", "combo", "countdown", "go", "gameover", "click", "ready"):
                self._sounds[name] = self._load(name)

    # ------------------------------------------------------------------
    def _find(self, stem: str) -> Optional[Path]:
        return find_sound_file(self.sound_dir, stem)

    def _load(self, name: str):
        path = self._find(name)
        if path is not None:
            try:
                return pygame.mixer.Sound(str(path))
            except pygame.error:
                pass
        return self._synth(name)

    # -- procedural fallback sounds -------------------------------------
    def _wave(self, samples: np.ndarray):
        freq, _fmt, channels = pygame.mixer.get_init()
        data = np.clip(samples, -1.0, 1.0)
        data = (data * 32767 * 0.5).astype(np.int16)
        if channels == 2:
            data = np.column_stack((data, data))
        return pygame.sndarray.make_sound(np.ascontiguousarray(data))

    def _synth(self, name: str):
        try:
            rate = pygame.mixer.get_init()[0]
            return self._wave(synth_samples(name, rate))
        except Exception:
            return None

    # ------------------------------------------------------------------
    def play(self, name: str) -> None:
        if not (self.enabled and self.available):
            return
        sound = self._sounds.get(name)
        if sound is not None:
            try:
                sound.play()
            except pygame.error:
                pass

    def start_music(self) -> None:
        """Play assets/sounds/music.* in a loop if present (no synthetic music)."""
        if not self.available:
            return
        self._music_requested = True
        if not self.enabled or self._music_playing:
            return
        path = self._find("music")
        if path is None:
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(0.25)
            pygame.mixer.music.play(-1, 0, 1200)
            self._music_playing = True
        except pygame.error:
            pass

    def stop_music(self) -> None:
        if self.available and self._music_playing:
            try:
                pygame.mixer.music.fadeout(900)
                pygame.time.wait(900)
            except pygame.error:
                pass
        self._music_playing = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.stop_music()
        elif self._music_requested:
            self.start_music()

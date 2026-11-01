"""Fruit drawings, on a hidden pygame surface. No window is opened."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.renderer import Renderer

pygame.init()


def _drawer():
    drawer = Renderer.__new__(Renderer)
    drawer._sprites = {}
    drawer._halves = {}
    return drawer


def _edge_has_flesh(half, flesh, on_right):
    pixels = pygame.surfarray.array3d(half).astype(int)
    edge = pixels[-8:, :, :] if on_right else pixels[:8, :, :]
    distance = np.abs(edge - np.array(flesh)).sum(axis=2)
    return bool(np.any(distance <= 30))


def test_each_cut_half_shows_that_fruits_flesh(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FRUITS_DIR", tmp_path)
    drawer = _drawer()
    for kind in ("apple", "watermelon", "orange", "banana"):
        spec = config.FRUIT_SPECS[kind]
        sprite = drawer._sprite(kind, spec.radius)
        assert int(np.max(pygame.surfarray.array3d(sprite))) > 0
        left, right = drawer._half_sprites(kind, spec.radius)
        assert _edge_has_flesh(left, spec.flesh_color, on_right=True)
        assert _edge_has_flesh(right, spec.flesh_color, on_right=False)

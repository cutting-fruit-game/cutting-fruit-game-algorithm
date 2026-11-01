"""Generated sounds, checked as samples. Nothing is played."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.audio_manager import find_sound_file, synth_samples

RATE = 8000


def _rumble(samples):
    alpha = np.exp(-2 * np.pi * 80 / RATE)
    acc = 0.0
    energy = 0.0
    for sample in samples:
        acc = alpha * acc + (1 - alpha) * float(sample)
        energy += acc * acc
    return energy / len(samples)


def _humps(samples):
    window = max(1, RATE // 40)
    energies = []
    for start in range(0, len(samples) - window, window):
        chunk = samples[start:start + window]
        energies.append(float(np.mean(chunk * chunk)))
    peak = max(energies)
    hot = False
    count = 0
    for energy in energies:
        if not hot and energy > peak * 0.35:
            count += 1
            hot = True
        elif hot and energy < peak * 0.15:
            hot = False
    return count


def test_slice_is_shorter_and_the_bomb_rumbles():
    slice_sound = synth_samples("slice", RATE)
    bomb = synth_samples("bomb", RATE)
    assert len(slice_sound) < len(bomb)
    assert _rumble(bomb) > _rumble(slice_sound)


def test_combo_is_two_notes():
    assert _humps(synth_samples("combo", RATE)) >= 2


def test_recorded_file_is_chosen_over_the_generated_sound(tmp_path):
    (tmp_path / "slice.wav").write_bytes(b"RIFF")
    assert find_sound_file(tmp_path, "slice") == tmp_path / "slice.wav"
    assert find_sound_file(tmp_path, "bomb") is None

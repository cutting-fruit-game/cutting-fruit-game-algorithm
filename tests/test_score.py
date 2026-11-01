"""Tests for src/score_manager.py (independent of rendering)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.fruit import Fruit
from src.score_manager import ComboBanner, ScoreManager


def fresh(**kw):
    return ScoreManager(high_score_path=None, **kw)


def test_fruit_point_values():
    expected = {"apple": 10, "watermelon": 20, "orange": 15, "banana": 15}
    assert {k: config.FRUIT_SPECS[k].points for k in expected} == expected
    for i, (kind, pts) in enumerate(expected.items()):
        sm = fresh()
        ev = sm.register_cut(i, kind)
        assert ev.points == pts and sm.score == pts


def test_score_updates_accumulate():
    sm = fresh()
    sm.register_cut(1, "apple")
    sm.tick(config.COMBO_TIMEOUT + 0.5)          # combo expires -> no multiplier
    sm.register_cut(2, "banana")
    assert sm.score == 10 + 15


def test_combo_progression_and_multiplier():
    sm = fresh()
    mults = []
    for i in range(1, 10):
        mults.append(sm.register_cut(i, "apple").multiplier)
        sm.tick(0.1)
    assert sm.combo == 9 and sm.best_combo == 9
    assert mults[0] == 1
    assert mults[config.COMBO_STEP - 1] == 2               # third cut -> x2
    assert max(mults) == min(config.MAX_COMBO_MULTIPLIER, 1 + 9 // config.COMBO_STEP)
    assert sm.score == sum(config.FRUIT_SPECS["apple"].points * m for m in mults)


def test_combo_banner_appears_only_when_the_multiplier_steps_up():
    sm = fresh()
    banner = ComboBanner()
    shown = []
    for i in range(1, 13):
        event = sm.register_cut(i, "apple")
        if banner.note(event.multiplier):
            shown.append(banner.text)
        sm.tick(0.05)
    assert shown == ["x2", "x3", "x4"]
    life = banner.life
    banner.note(4)
    assert banner.life == life
    banner.tick(0.2)
    assert banner.life < life
    banner.tick(2)
    assert banner.text == "" and banner.life == 0
    banner.note(1)
    assert banner.note(2) is True
    score_now = sm.score
    lives_now = sm.lives
    clock_now = sm.game_time
    banner.note(3)
    banner.tick(0.1)
    assert sm.score == score_now and sm.lives == lives_now and sm.game_time == clock_now


def test_combo_resets_after_timeout():
    sm = fresh()
    sm.register_cut(1, "apple")
    sm.register_cut(2, "apple")
    assert sm.combo == 2
    sm.tick(config.COMBO_TIMEOUT + 0.01)
    assert sm.combo == 0
    ev = sm.register_cut(3, "apple")
    assert ev.combo == 1


def test_multiplier_is_capped():
    sm = fresh()
    for i in range(1, 60):
        sm.register_cut(i, "apple")
        sm.tick(0.05)
    assert sm.multiplier == config.MAX_COMBO_MULTIPLIER


def test_bomb_removes_life_without_points():
    sm = fresh()
    sm.register_cut(1, "apple")
    before = sm.score
    ev = sm.register_cut(2, "bomb")
    assert ev.kind == "bomb" and ev.points == 0
    assert sm.lives == config.STARTING_LIVES - config.BOMB_LIFE_PENALTY
    assert sm.score == before
    assert sm.combo == 0


def test_missed_fruit_keeps_lives_and_combo():
    sm = fresh()
    sm.register_cut(1, "apple")
    assert sm.combo == 1
    ev = sm.register_miss(2, "apple")
    assert ev.kind == "miss" and ev.lives_lost == 0
    assert sm.lives == config.STARTING_LIVES
    assert sm.score == config.FRUIT_SPECS["apple"].points
    assert sm.combo == 1


def test_only_unsliced_fruit_counts_as_missed():
    apple = Fruit(config.FRUIT_SPECS["apple"], 0, 0)
    bomb = Fruit(config.FRUIT_SPECS["bomb"], 0, 0)
    assert apple.missed
    assert not bomb.missed
    apple.slice()
    assert not apple.missed


def test_fallen_bomb_is_not_a_miss():
    sm = fresh()
    assert sm.register_miss(1, "bomb") is None
    assert sm.lives == config.STARTING_LIVES
    assert sm.register_miss(2, "apple") is not None
    assert sm.register_miss(2, "apple") is None
    assert sm.lives == config.STARTING_LIVES


def test_lives_reaching_zero_ends_game():
    sm = fresh()
    assert not sm.is_game_over
    for i in range(config.STARTING_LIVES):
        sm.register_cut(100 + i, "bomb")
    assert sm.lives == 0
    assert sm.is_game_over
    sm.register_cut(200, "bomb")                  # lives never go negative
    assert sm.lives == 0


def test_one_fruit_cannot_award_points_twice():
    sm = fresh()
    assert sm.register_cut(7, "watermelon") is not None
    score = sm.score
    assert sm.register_cut(7, "watermelon") is None
    assert sm.score == score
    # the same applies to bombs
    sm.register_cut(8, "bomb")
    lives = sm.lives
    assert sm.register_cut(8, "bomb") is None
    assert sm.lives == lives


def test_timer_and_game_over():
    sm = fresh(duration=10)
    sm.tick(4.0)
    assert abs(sm.time_remaining - 6.0) < 1e-9
    assert not sm.is_game_over
    sm.tick(100)
    assert sm.time_remaining == 0.0 and sm.is_game_over
    sm.tick(-1)                                    # negative dt is ignored
    assert sm.time_remaining == 0.0


def test_levels_progress_with_score():
    sm = fresh()
    assert sm.level == 1
    sm.score = config.LEVEL_SCORE_STEP
    assert sm.level == 2
    sm.score = 10 ** 6
    assert sm.level == config.MAX_LEVEL


def test_critical_bonus():
    sm = fresh()
    ev = sm.register_cut(1, "apple", critical=True)
    assert ev.critical and ev.points == 10 + config.CRITICAL_BONUS


def test_strawberry_is_scored():
    ev = fresh().register_cut(1, "strawberry")
    assert ev.points == config.FRUIT_SPECS["strawberry"].points


def test_unknown_kind_raises():
    try:
        fresh().register_cut(1, "dragonfruit")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_reset_restores_initial_state():
    sm = fresh()
    sm.register_cut(1, "apple")
    sm.register_cut(2, "bomb")
    sm.tick(5)
    sm.reset()
    assert (sm.score, sm.lives, sm.combo) == (config.INITIAL_SCORE, config.STARTING_LIVES, 0)
    assert sm.time_remaining == sm.duration
    assert sm.register_cut(1, "apple") is not None       # ids are forgotten after reset


def test_high_score_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "hs.json")
        sm = ScoreManager(high_score_path=path)
        sm.register_cut(1, "watermelon")
        assert sm.finalize() is True
        assert ScoreManager(high_score_path=path).high_score == 20
        worse = ScoreManager(high_score_path=path)
        worse.register_cut(1, "apple")
        assert worse.finalize() is False and worse.high_score == 20
    assert ScoreManager(high_score_path=os.path.join(tmp, "missing.json")).high_score == 0

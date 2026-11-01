import numpy as np

from src.game_state import GameStateMachine
from src.hand_tracker import (HandObservation, count_raised_fingers, exactly_two_fingers,
                             normalized_to_screen, only_one_finger, update_one_finger_hold)


def test_normalized_point_maps_to_screen():
    point = normalized_to_screen(0.5, 0.5, 1280, 720)
    assert point == (640.0, 360.0)


def _hand(raised):
    """21 landmarks. A raised finger has its tip above the joint below it."""
    points = [(0.5, 0.8)] * 21
    joints = {8: 6, 12: 10, 16: 14, 20: 18}
    for tip in raised:
        pip = joints[tip]
        points[pip] = (0.5, 0.6)
        points[tip] = (0.5, 0.3)
    return points


def test_one_raised_finger_is_counted():
    assert count_raised_fingers(_hand([8])) == 1
    assert count_raised_fingers(_hand([8, 12, 16, 20])) == 4
    assert count_raised_fingers(_hand([])) == 0


def test_open_hand_does_not_count_as_one_finger():
    assert count_raised_fingers(_hand([8, 12, 16, 20])) == 4
    assert not only_one_finger(_hand([8, 12, 16, 20]))
    assert only_one_finger(_hand([8]))


def test_exactly_two_fingers_rejects_other_counts():
    assert exactly_two_fingers(_hand([8, 12]))
    assert count_raised_fingers(_hand([8, 12])) == 2
    assert not exactly_two_fingers(_hand([8]))
    assert not exactly_two_fingers(_hand([8, 12, 16]))
    assert not exactly_two_fingers(_hand([8, 12, 16, 20]))
    assert not only_one_finger(_hand([8, 12]))


def test_a_slightly_lifted_third_finger_still_counts_as_two():
    points = _hand([8, 12])
    points[16] = (0.5, 0.62)
    points[14] = (0.5, 0.7)
    assert exactly_two_fingers(points)
    assert not exactly_two_fingers(_hand([8, 12, 16, 20]))


def test_one_finger_hold_survives_a_flicker_and_rejects_an_open_hand():
    since, lost = update_one_finger_hold(None, None, 5.0, True, 1)
    assert since == 5.0 and lost is None
    since, lost = update_one_finger_hold(since, lost, 5.05, False, 0)
    assert since == 5.0
    since, lost = update_one_finger_hold(since, lost, 5.20, False, 0)
    assert since is None and lost is None
    assert update_one_finger_hold(5.0, None, 5.01, False, 3) == (None, None)
    assert update_one_finger_hold(5.0, None, 5.01, False, 4) == (None, None)


def test_sideways_finger_still_counts():
    points = [(0.7, 0.5)] * 21
    points[6] = (0.55, 0.5)
    points[8] = (0.25, 0.5)
    assert count_raised_fingers(points) == 1


def test_hand_observation_supports_pinch_flag():
    observation = HandObservation(detected=True, pinching=True)
    assert observation.detected and observation.pinching


def test_exit_confirmation_is_a_valid_menu_page():
    machine = GameStateMachine()
    machine.open_menu_page("exit_confirm")
    assert machine.menu_page == "exit_confirm"

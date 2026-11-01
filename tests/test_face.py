from src.face_detector import mouth_is_smiling


def test_closed_mouth_is_not_a_smile():
    # A shut mouth is very wide compared with its opening, and the corners stay level.
    assert mouth_is_smiling((0.0, 0.5), (0.1, 0.5), (0.05, 0.499), (0.05, 0.501)) is False


def test_lifted_corners_count_as_a_smile():
    assert mouth_is_smiling((0.0, 0.46), (0.1, 0.46), (0.05, 0.50), (0.05, 0.52)) is True


def test_open_mouth_without_lifted_corners_is_not_a_smile():
    assert mouth_is_smiling((0.0, 0.50), (0.1, 0.50), (0.05, 0.45), (0.05, 0.55)) is False

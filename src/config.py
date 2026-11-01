"""Centralized configuration for the Fruit Cutting Gesture Game.

Every tunable value lives here. Pure-logic modules import from this file;
this file imports nothing heavy (no pygame/cv2/mediapipe), so it is safe to
import from unit tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FRUITS_DIR = ASSETS_DIR / "fruits"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
SOUNDS_DIR = ASSETS_DIR / "sounds"
FONTS_DIR = ASSETS_DIR / "fonts"
HIGH_SCORE_FILE = PROJECT_ROOT / "highscore.json"
# Only needed when the installed MediaPipe has no legacy `mp.solutions` API.
HAND_MODEL_PATH = ASSETS_DIR / "hand_landmarker.task"

# --------------------------------------------------------------------------
# Window / timing
# --------------------------------------------------------------------------
WINDOW_TITLE = "Fruit Cutting Gesture Game"
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
TARGET_FPS = 60          # render cap; real FPS is limited by the webcam/tracker
MAX_FRAME_DT = 0.05      # clamp big frame gaps so physics never explodes

# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
MIRROR_CAMERA = True               # mirror so on-screen motion matches the hand
CAMERA_MAX_READ_FAILURES = 60      # consecutive failed reads before "camera lost"

# --------------------------------------------------------------------------
# Hand tracking
# --------------------------------------------------------------------------
PRIMARY_LANDMARK = 8               # 8 = index fingertip (MediaPipe hand model)
MAX_HANDS = 1
DETECTION_CONFIDENCE = 0.6
TRACKING_CONFIDENCE = 0.5
MODEL_COMPLEXITY = 0               # legacy API only: 0 = fastest
INPUT_MARGIN = 0.12                # ignore the outer 12% of the camera frame so
                                   # screen edges are reachable without leaving view
HAND_LOSS_TIMEOUT = 0.35           # seconds without a hand before state is reset
PINCH_THRESHOLD = 0.055            # normalized thumb/index distance for a pinch
PINCH_COOLDOWN = 0.8               # seconds before another pinch can activate a control
ONE_FINGER_HOLD = 0.22             # seconds one raised finger must hold to start
ONE_FINGER_FLICKER = 0.15          # a brief lost pose does not cancel that hold
TWO_FINGER_HOLD = 0.35             # seconds two raised fingers must hold to restart
TWO_FINGER_GAP = 0.03              # the two raised fingers must stick out past the others
FINGER_RAISE_MARGIN = 0.02         # tip must be this much farther from the wrist than the knuckle
ONE_FINGER_GAP = 0.06              # the one raised finger must stick out past the others by this much
HAND_POSE_GRACE = 0.28             # brief tracking drops do not cancel the start pose
SMILE_CORNER_LIFT = 0.18           # mouth corners must rise this far, relative to mouth width
SMILE_HOLD = 0.6                   # seconds a real smile must hold before it starts the game
SMILE_COOLDOWN = 1.5               # seconds before another smile action can start the game

# --------------------------------------------------------------------------
# Motion analysis / gesture detection (pixel units are *screen* pixels)
# --------------------------------------------------------------------------
SMOOTHING_ALPHA = 0.9              # exponential smoothing: 1.0 = no smoothing
JITTER_DEADZONE_PX = 1.5           # smoothed steps below this are treated as stillness
MOTION_HISTORY_SIZE = 32
MOTION_WINDOW_SECONDS = 0.18       # recent-history window used for speed/distance
MIN_ELAPSED_SECONDS = 0.01         # shorter windows are rejected (div-by-zero guard)
MIN_CUT_DISTANCE = 80.0            # px, net displacement inside the window
MIN_CUT_SPEED = 650.0              # px/s
CALIBRATED_SPEED_SCALE = 0.75      # practice swipe sets this fraction of the measured speed
CALIBRATED_SPEED_FLOOR = 400.0     # a slow practice swipe cannot make every twitch a cut
RECENT_STEP_MIN_DISTANCE = 48.0    # a single fast step at least this long can start a cut
SWIPE_TAIL_SECONDS = 0.12          # keep cutting briefly after the finger slows
GESTURE_END_SPEED = 350.0          # a swipe ends when speed falls below this
GESTURE_COOLDOWN = 0.15            # seconds before the next swipe may start
CRITICAL_CUT_SPEED = 2200.0        # px/s - swipes this fast earn the critical bonus

# Sensitivity presets: name -> (min_cut_distance, min_cut_speed)
SENSITIVITY_PRESETS: Dict[str, Tuple[float, float]] = {
    "low": (110.0, 900.0),
    "medium": (MIN_CUT_DISTANCE, MIN_CUT_SPEED),
    "high": (55.0, 450.0),
}

# --------------------------------------------------------------------------
# Blade
# --------------------------------------------------------------------------
BLADE_MAX_POINTS = 80
BLADE_LIFETIME = 0.42              # seconds a trail point stays visible
BLADE_TIP_LENGTH = 72.0            # minimum blade length; the point stays on the fingertip
BLADE_BASE_WIDTH = 5.0
BLADE_ACTIVE_WIDTH = 16.0
BLADE_CORE_COLOR = (240, 252, 255)
BLADE_GLOW_COLOR = (80, 200, 255)

# --------------------------------------------------------------------------
# Collision
# --------------------------------------------------------------------------
COLLISION_TOLERANCE = 14.0         # extra px added to the hitbox radius
HITBOX_SCALE = 0.9                 # hitbox radius = sprite radius * scale

# --------------------------------------------------------------------------
# Physics / spawning
# --------------------------------------------------------------------------
GRAVITY = 1500.0                   # px/s^2
SPAWN_BASE_INTERVAL = 1.0          # seconds between spawn bursts at level 1
MIN_SPAWN_INTERVAL = 0.35
SPAWN_X_MARGIN = 0.10              # fraction of width kept free at the edges
APEX_MIN_FRACTION = 0.45           # launch apex height as fraction of screen height
APEX_MAX_FRACTION = 0.80
TARGET_X_MIN = 0.20                # horizontal landing range (fraction of width)
TARGET_X_MAX = 0.80
MAX_VX = 380.0
RADIUS_JITTER = (0.9, 1.1)         # random size multiplier ("safe limits")
ANGULAR_SPEED_RANGE = (-240.0, 240.0)   # deg/s
MAX_ACTIVE_OBJECTS = 10
MAX_BURST = 3
BOMB_PROBABILITY = 0.14
BOMB_PROBABILITY_STEP = 0.012      # added per level
BOMB_PROBABILITY_MAX = 0.26
DIFFICULTY_SPEED_STEP = 0.06       # speed multiplier added per level
SPEED_RAMP_START = 0.55             # launch speed for the first 10 seconds
SPEED_STEP_SECONDS = 10.0           # how often the launch speed increases
SPEED_RAMP_STEP = 0.15              # added to launch speed every step
DIFFICULTY_SPAWN_STEP = 0.12       # spawn-rate multiplier added per level
SLICE_SEPARATION_SPEED = 320.0     # px/s pieces fly apart across the cut
PIECE_MAX_LIFETIME = 3.0

# --------------------------------------------------------------------------
# Fruit / bomb definitions (all point values are configurable here)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FruitSpec:
    name: str
    points: int
    radius: int
    color: Tuple[int, int, int]
    flesh_color: Tuple[int, int, int]
    weight: float = 1.0
    is_bomb: bool = False


FRUIT_SPECS: Dict[str, FruitSpec] = {
    "apple": FruitSpec("apple", 10, 42, (210, 40, 50), (250, 240, 200), 1.0),
    "watermelon": FruitSpec("watermelon", 20, 58, (40, 140, 60), (235, 60, 80), 0.6),
    "orange": FruitSpec("orange", 15, 44, (255, 150, 20), (255, 200, 90), 1.0),
    "banana": FruitSpec("banana", 15, 48, (250, 220, 60), (255, 245, 190), 0.8),
    "strawberry": FruitSpec("strawberry", 12, 38, (220, 45, 65), (255, 220, 190), 1.0),
    "bomb": FruitSpec("bomb", 0, 40, (35, 35, 42), (255, 120, 30), 0.0, True),
}
BOMB_LIFE_PENALTY = 1
MISS_LIFE_PENALTY = 0          # fallen fruit does not cost a heart

# --------------------------------------------------------------------------
# Scoring / rules
# --------------------------------------------------------------------------
INITIAL_SCORE = 0
STARTING_LIVES = 3
GAME_DURATION = 60.0               # seconds
COUNTDOWN_SECONDS = 3
COMBO_TIMEOUT = 1.2                # seconds allowed between cuts to keep a combo
COMBO_STEP = 3                     # every N consecutive cuts raises the multiplier
MAX_COMBO_MULTIPLIER = 4
CRITICAL_BONUS = 5                 # bonus points for a very fast cut
LEVEL_SCORE_STEP = 100             # score needed per level
MAX_LEVEL = 10

# --------------------------------------------------------------------------
# Runtime-adjustable user settings
# --------------------------------------------------------------------------
LANGUAGES = ("en", "km")
SENSITIVITY_ORDER = ("low", "medium", "high")


@dataclass
class Settings:
    """User-changeable options (modified from the Settings screen)."""

    language: str = "en"
    sound_enabled: bool = True
    debug_landmarks: bool = False
    show_camera_background: bool = False
    sensitivity: str = "medium"

    @property
    def min_cut_distance(self) -> float:
        return SENSITIVITY_PRESETS[self.sensitivity][0]

    @property
    def min_cut_speed(self) -> float:
        return SENSITIVITY_PRESETS[self.sensitivity][1]


# --------------------------------------------------------------------------
# UI text (English + Khmer). Missing keys fall back to English.
# Khmer needs a Khmer-capable font (Windows ships "Leelawadee UI"); you can
# also drop `khmer.ttf` into assets/fonts/.
# --------------------------------------------------------------------------
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Fruit Cutting",
        "start": "Start Game", "instructions": "Instructions",
        "settings": "Settings", "exit": "Exit", "back": "Back",
        "score": "Score", "lives": "Lives", "level": "Level",
        "combo": "Combo", "time": "Time",
        "resume": "Resume", "restart": "Restart", "main_menu": "Main Menu",
        "paused": "Paused", "game_over": "Game Over",
        "final_score": "Final Score", "high_score": "High Score",
        "new_high": "New high score!",
        "calibration": "Calibration",
        "hand_ok": "Hand detected - raise one finger to start",
        "hand_missing": "Show your hand to the camera",
        "calib_hint": "Raise one finger to start. Then swipe that finger to cut.",
        "camera_error": "Camera problem",
        "hand_lost": "Hand lost",
        "get_ready": "Get ready!",
        "go": "Go!",
        "language": "Language", "sound": "Sound", "sensitivity": "Sensitivity",
        "debug": "Show landmarks", "camera_bg": "Camera background",
        "on": "On", "off": "Off", "low": "Low", "medium": "Medium", "high": "High",
        "instr_1": "Hold your hand up so the camera can see it.",
        "instr_2": "Your index fingertip is the blade.",
        "instr_3": "Swipe FAST across fruits to slice them. Slow moves do not cut.",
        "instr_4": "Only a cut bomb costs a life. Fruit that falls is safe.",
        "instr_5": "Chain cuts quickly for x2, x3 and x4 combos.",
        "instr_6": "Keys: ESC pause/back, ENTER select, F3 landmarks, M mute.",
    },
    "km": {
        "title": "កាត់ផ្លែឈើ",
        "start": "ចាប់ផ្តើមហ្គេម", "instructions": "ការណែនាំ",
        "settings": "ការកំណត់", "exit": "ចាកចេញ", "back": "ត្រឡប់ក្រោយ",
        "score": "ពិន្ទុ", "lives": "ជីវិត", "level": "កម្រិត",
        "combo": "ខុមបូ", "time": "ពេលវេលា",
        "resume": "បន្ត", "restart": "ចាប់ផ្តើមឡើងវិញ", "main_menu": "ម៉ឺនុយមេ",
        "paused": "ផ្អាក", "game_over": "ហ្គេមចប់",
        "final_score": "ពិន្ទុចុងក្រោយ", "high_score": "ពិន្ទុខ្ពស់បំផុត",
        "calibration": "ការកែសម្រួល",
        "language": "ភាសា", "sound": "សំឡេង",
        "on": "បើក", "off": "បិទ",
    },
}

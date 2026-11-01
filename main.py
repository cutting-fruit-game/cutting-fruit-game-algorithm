"""Fruit Cutting Gesture Game - application entry point.

Run with:  python main.py
"""
from __future__ import annotations

import math
import sys
import threading
import time

try:
    import pygame
except ImportError:  # pragma: no cover - friendly message for missing deps
    sys.exit("pygame is not installed. Run: pip install -r requirements.txt")

from src import config
from src.audio_manager import AudioManager
from src.blade import Blade
from src.camera import Camera, CameraError
from src.collision import CollisionDetector
from src.fruit_manager import FruitManager
from src.game_state import GameState, GameStateMachine
from src.face_detector import FaceDetector, FaceObservation, FaceDetectorError
from src.gesture_detector import (GestureDetector, calibrated_cut_speed, practice_swipe_ready,
                                 swipe_segments, swipe_too_slow)
from src.hand_tracker import (HandObservation, HandTracker, HandTrackerError,
                             update_one_finger_hold, update_two_finger_hold)
from src.renderer import Renderer
from src.score_manager import ComboBanner, ScoreManager

CAMERA_STATES = (GameState.MENU, GameState.CALIBRATION, GameState.COUNTDOWN, GameState.PLAYING, GameState.PAUSE)
CALIBRATION_STABLE_SECONDS = 0.5


class Game:
    """Coordinates input, state, game logic and rendering."""

    def __init__(self) -> None:
        pygame.init()
        self.settings = config.Settings()
        self.renderer = Renderer(self.settings)
        self.audio = AudioManager(self.settings.sound_enabled)
        self.machine = GameStateMachine()
        self.score = ScoreManager(config.HIGH_SCORE_FILE)
        self.fruits = FruitManager()
        self.blade = Blade()
        self.detector = GestureDetector(min_distance=self.settings.min_cut_distance,
                                        min_speed=self.settings.min_cut_speed)
        self.collisions = CollisionDetector()
        self.camera = None
        self.tracker = None
        self.face = None
        self.observation = HandObservation()
        self.face_observation = FaceObservation()
        self.camera_error = ""
        self._pinch_was_active = False
        self._pinch_last_click = -config.PINCH_COOLDOWN
        self._smile_since = None
        self._smile_last_action = -config.SMILE_COOLDOWN
        self.selected = 0
        self.running = True
        self.clock = pygame.time.Clock()
        self.hand_ok_since = None
        self._one_finger_since = None
        self._one_finger_lost_since = None
        self._practice_ready = False
        self._slow_hint_until = 0.0
        self.combo_banner = ComboBanner()
        self._two_finger_since = None
        self._two_finger_lost_since = None
        self._restart_ready = True
        self._hand_missing_since = None
        self._last_countdown_number = None
        self._countdown_ready_pending = False
        self._countdown_ready_until = 0.0
        self._vision_stop = threading.Event()
        self._vision_thread = None
        self._vision_lock = threading.Lock()
        self._vision_frame = None
        self._vision_seq = 0
        self._vision_seen = 0
        self._vision_lost = False
        self._vision_want_face = False
        self._cut_point = None
        self.start_camera()

    # ------------------------------------------------------------------
    # camera lifecycle
    # ------------------------------------------------------------------
    def start_camera(self) -> None:
        self.camera_error = ""
        try:
            if self.camera is None:
                self.camera = Camera()
            self.camera.open()
            if self.tracker is None:
                self.tracker = HandTracker()
            if self.face is None:
                try:
                    self.face = FaceDetector()
                except FaceDetectorError as exc:
                    self.face = None
                    if not self.camera_error:
                        self.camera_error = str(exc)
        except (CameraError, HandTrackerError) as exc:
            self.camera_error = str(exc)
            self.stop_camera()
            return
        self._start_vision()

    def _start_vision(self) -> None:
        """Read the webcam off the game thread so fruit can move every frame."""
        if self.camera is None or self.tracker is None:
            return
        if self._vision_thread is not None and self._vision_thread.is_alive():
            return
        self._vision_stop.clear()
        self._vision_thread = threading.Thread(target=self._vision_loop, name="vision", daemon=True)
        self._vision_thread.start()

    def _vision_loop(self) -> None:
        screen = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        while not self._vision_stop.is_set():
            camera = self.camera
            tracker = self.tracker
            if camera is None or tracker is None:
                break
            frame = camera.read()
            if frame is None:
                with self._vision_lock:
                    self._vision_lost = camera.lost
                time.sleep(0.01)
                continue
            frame = frame.copy()
            now = time.perf_counter()
            observation = tracker.process(frame, now, screen)
            face_observation = FaceObservation()
            if self._vision_want_face and self.face is not None:
                face_observation = self.face.process(frame)
            if self.settings.debug_landmarks:
                tracker.draw_debug(frame, observation)
            with self._vision_lock:
                self.observation = observation
                self.face_observation = face_observation
                self._vision_frame = frame
                self._vision_seq += 1
                self._vision_lost = False

    def _pull_vision(self) -> bool:
        """Copy the newest camera result. Returns True when it is a new frame."""
        with self._vision_lock:
            seq = self._vision_seq
            frame = self._vision_frame
            lost = self._vision_lost
        if lost and not self.camera_error:
            self.camera_error = "The camera stopped delivering frames."
            if self.machine.state == GameState.PLAYING:
                self.go(GameState.PAUSE)
        if seq == self._vision_seen or frame is None:
            return False
        self._vision_seen = seq
        self.renderer.set_camera_frame(frame)
        return True

    def _stop_vision(self) -> None:
        self._vision_stop.set()
        thread = self._vision_thread
        self._vision_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        with self._vision_lock:
            self._vision_frame = None
            self._vision_lost = False

    def stop_camera(self) -> None:
        self._stop_vision()
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.observation = HandObservation()
        self.face_observation = FaceObservation()
        if self.face is not None:
            self.face.close()
            self.face = None
        if self.tracker is not None:
            self.tracker.close()
            self.tracker = None
        self.renderer._camera_surface = None

    # ------------------------------------------------------------------
    # state changes
    # ------------------------------------------------------------------
    def go(self, new_state: GameState) -> None:
        if not self.machine.transition(new_state):
            return
        self.selected = 0
        if new_state == GameState.CALIBRATION:
            self.detector.reset()
            self.blade.clear()
            self._reset_knife()
            self.hand_ok_since = None
            self._one_finger_since = None
            self._one_finger_lost_since = None
            self._practice_ready = False
            self.detector.configure(self.settings.min_cut_distance, self.settings.min_cut_speed)
            self._hand_missing_since = None
            self.start_camera()
        elif new_state == GameState.COUNTDOWN:
            self.new_game()
        elif new_state == GameState.MENU:
            self.start_camera()

    def new_game(self) -> None:
        self.score.reset()
        self.fruits.reset()
        self.blade.clear()
        self._reset_knife()
        self.detector.reset()
        self.combo_banner = ComboBanner()
        self.renderer.clear_effects()
        self._last_countdown_number = None
        self._countdown_ready_pending = True
        self._countdown_ready_until = 0.0

    def end_game(self) -> None:
        self.score.finalize()
        self.audio.play("gameover")
        self.go(GameState.GAME_OVER)

    # ------------------------------------------------------------------
    # menus
    # ------------------------------------------------------------------
    def labels(self):
        t = self.renderer.t
        state = self.machine.state
        if state == GameState.MENU:
            page = self.machine.menu_page
            if page == "main":
                return [t("start"), t("instructions"), t("settings"), t("exit")]
            if page == "instructions":
                return [t("back")]
            if page == "exit_confirm":
                return ["Yes, Exit", "Cancel"]
            s = self.settings
            onoff = lambda v: t("on") if v else t("off")
            return [
                f"{t('language')}: {'English' if s.language == 'en' else 'Khmer'}",
                f"{t('sound')}: {onoff(s.sound_enabled)}",
                f"{t('sensitivity')}: {t(s.sensitivity)}",
                f"{t('debug')}: {onoff(s.debug_landmarks)}",
                f"{t('camera_bg')}: {onoff(s.show_camera_background)}",
                t("back"),
            ]
        if state == GameState.PAUSE:
            return [t("resume"), t("restart"), t("main_menu")]
        if state == GameState.GAME_OVER:
            return [t("restart"), t("main_menu")]
        return []

    def activate(self) -> None:
        state, i = self.machine.state, self.selected
        self.audio.play("click")
        if state == GameState.MENU:
            page = self.machine.menu_page
            if page == "main":
                if i == 0:
                    self.audio.start_music()
                    self.go(GameState.CALIBRATION)
                elif i == 1:
                    self.machine.open_menu_page("instructions"); self.selected = 0
                elif i == 2:
                    self.machine.open_menu_page("settings"); self.selected = 0
                else:
                    self.machine.open_menu_page("exit_confirm"); self.selected = 1
            elif page == "exit_confirm":
                if i == 0:
                    self.running = False
                else:
                    self.machine.open_menu_page("main"); self.selected = 3
            elif page == "instructions":
                self.machine.menu_page = "main"; self.selected = 1
            else:
                self.change_setting(i)
        elif state == GameState.PAUSE:
            if i == 0:
                self.go(GameState.PLAYING)
            elif i == 1:
                self.go(GameState.COUNTDOWN)
            else:
                self.go(GameState.MENU)
        elif state == GameState.GAME_OVER:
            self.go(GameState.COUNTDOWN if i == 0 else GameState.MENU)

    def change_setting(self, i: int) -> None:
        s = self.settings
        if i == 0:
            s.language = config.LANGUAGES[(config.LANGUAGES.index(s.language) + 1) % len(config.LANGUAGES)]
        elif i == 1:
            s.sound_enabled = not s.sound_enabled
            self.audio.set_enabled(s.sound_enabled)
        elif i == 2:
            order = config.SENSITIVITY_ORDER
            s.sensitivity = order[(order.index(s.sensitivity) + 1) % len(order)]
            self.detector.configure(s.min_cut_distance, s.min_cut_speed)
        elif i == 3:
            s.debug_landmarks = not s.debug_landmarks
        elif i == 4:
            s.show_camera_background = not s.show_camera_background
        else:
            self.machine.menu_page = "main"; self.selected = 2

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.on_key(event.key)
            elif event.type == pygame.MOUSEMOTION and self.labels():
                idx = self.renderer.button_at(self.renderer.mouse_to_virtual(event.pos))
                if idx is not None:
                    self.selected = idx
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_pos = self.renderer.mouse_to_virtual(event.pos)
                if (self.machine.state == GameState.PLAYING
                        and self.renderer.pause_button is not None
                        and self.renderer.pause_button.collidepoint(mouse_pos)):
                    self.go(GameState.PAUSE)
                elif self.labels():
                    idx = self.renderer.button_at(mouse_pos)
                    if idx is not None:
                        self.selected = idx
                        self.activate()

    def on_key(self, key: int) -> None:
        state = self.machine.state
        if key == pygame.K_F3:
            self.settings.debug_landmarks = not self.settings.debug_landmarks
            return
        if key == pygame.K_m:
            self.settings.sound_enabled = not self.settings.sound_enabled
            self.audio.set_enabled(self.settings.sound_enabled)
            return

        labels = self.labels()
        if labels:
            if key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(labels)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(labels)
            elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                self.activate()
            elif key in (pygame.K_LEFT, pygame.K_RIGHT) and state == GameState.MENU \
                    and self.machine.menu_page == "settings":
                self.change_setting(self.selected)
            elif key == pygame.K_r and state == GameState.GAME_OVER:
                self.go(GameState.COUNTDOWN)

        if key == pygame.K_ESCAPE:
            if state == GameState.MENU:
                if self.machine.menu_page != "main":
                    self.machine.menu_page = "main"; self.selected = 0
            elif state in (GameState.CALIBRATION, GameState.COUNTDOWN, GameState.GAME_OVER):
                self.go(GameState.MENU)
            elif state == GameState.PLAYING:
                self.go(GameState.PAUSE)
            elif state == GameState.PAUSE:
                self.go(GameState.PLAYING)
        elif key == pygame.K_p and state == GameState.PLAYING:
            self.go(GameState.PAUSE)
        elif state == GameState.CALIBRATION:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) and self.calibration_ready(time.perf_counter()):
                self.go(GameState.COUNTDOWN)
            elif key == pygame.K_s and not self.camera_error:
                self.go(GameState.COUNTDOWN)       # skip calibration

    def calibration_ready(self, now: float) -> bool:
        return (self.hand_ok_since is not None and now - self.hand_ok_since >= CALIBRATION_STABLE_SECONDS)

    def _watch_two_finger_restart(self, now: float) -> bool:
        """Hold two fingers to start the round again. One or an open hand do not count."""
        raised = self.observation.raised_fingers if self.observation.detected else 0
        two = self.observation.detected and self.observation.two_fingers
        self._two_finger_since, self._two_finger_lost_since = update_two_finger_hold(
            self._two_finger_since, self._two_finger_lost_since, now, two, raised,
        )
        if self._two_finger_since is None:
            self._restart_ready = True
            return False
        if not self._restart_ready:
            return False
        if now - self._two_finger_since < config.TWO_FINGER_HOLD:
            return False
        self._restart_ready = False
        self._two_finger_since = None
        self._two_finger_lost_since = None
        self._restart_round()
        return True

    def _restart_round(self) -> None:
        if self.machine.state == GameState.COUNTDOWN:
            self.new_game()
            self.machine.countdown_remaining = float(config.COUNTDOWN_SECONDS)
            return
        self.go(GameState.COUNTDOWN)

    # ------------------------------------------------------------------
    # per-frame update
    # ------------------------------------------------------------------
    def update(self, now: float, dt: float) -> None:
        state = self.machine.state
        segments = []
        self._vision_want_face = state == GameState.MENU

        if state in CAMERA_STATES and self.camera is not None and self.tracker is not None:
            new_frame = self._pull_vision()
            if new_frame and state not in (GameState.PAUSE, GameState.MENU):
                segments = self.track_hand(self.observation.timestamp or now)

        if state == GameState.MENU:
            self.update_menu_gestures(now)
        elif state == GameState.CALIBRATION:
            if self._watch_two_finger_restart(now):
                return
            if self.observation.detected:
                self.hand_ok_since = self.hand_ok_since or now
                self._hand_missing_since = None
            else:
                self._hand_missing_since = self._hand_missing_since or now
                if now - self._hand_missing_since > config.HAND_POSE_GRACE:
                    self.hand_ok_since = None
            raised = self.observation.raised_fingers if self.observation.detected else 0
            one_finger = self.observation.detected and self.observation.one_finger
            self._one_finger_since, self._one_finger_lost_since = update_one_finger_hold(
                self._one_finger_since, self._one_finger_lost_since, now, one_finger, raised,
            )
            if not self._practice_ready:
                if (self.calibration_ready(now) and self._one_finger_since is not None
                        and now - self._one_finger_since >= config.ONE_FINGER_HOLD):
                    self._practice_ready = True
                    self.detector.reset()
            else:
                sample = self.detector.last_sample
                if sample is not None and practice_swipe_ready(sample.speed, sample.distance):
                    speed = calibrated_cut_speed(sample.speed, self.settings.min_cut_speed)
                    self.detector.configure(min_speed=speed)
                    self.go(GameState.COUNTDOWN)
                    return
        elif state == GameState.COUNTDOWN:
            if self._watch_two_finger_restart(now):
                return
            if self._countdown_ready_pending:
                self.audio.play("ready")
                self._countdown_ready_pending = False
                self._countdown_ready_until = now + 0.5
                return
            number = self.machine.countdown_number
            if now >= self._countdown_ready_until and number != self._last_countdown_number:
                self._last_countdown_number = number
                self.audio.play("countdown")
            if self.machine.update(dt):
                self.audio.play("go")
        elif state == GameState.PLAYING:
            if self._watch_two_finger_restart(now):
                return
            self.update_playing(dt, segments, now)
        elif state in (GameState.PAUSE, GameState.GAME_OVER):
            self._watch_two_finger_restart(now)

        self.renderer.update_effects(dt)

    def update_menu_gestures(self, now: float) -> None:
        page = self.machine.menu_page
        if self.observation.detected and self.observation.point is not None:
            idx = self.renderer.button_at(self.observation.point)
            if idx is not None:
                self.selected = idx

        pinch = self.observation.pinching if self.observation.detected else False
        pinch_rising = pinch and not self._pinch_was_active
        self._pinch_was_active = pinch
        if pinch_rising and now - self._pinch_last_click >= config.PINCH_COOLDOWN:
            point = self.observation.point
            idx = self.renderer.button_at(point) if point is not None else None
            if idx is not None:
                self.selected = idx
                self.activate()
                self._pinch_last_click = now

        smiling = page == "main" and self.face_observation.smiling
        if smiling:
            self._smile_since = self._smile_since or now
            held = now - self._smile_since >= config.SMILE_HOLD
            if held and now - self._smile_last_action >= config.SMILE_COOLDOWN:
                self.selected = 0
                self.activate()
                self._smile_last_action = now
                self._smile_since = None
        else:
            self._smile_since = None

    def _reset_knife(self) -> None:
        self._cut_point = None

    def track_hand(self, now: float):
        """Feed the fingertip to the gesture detector/blade; return cut segments."""
        segments = []
        obs = self.observation
        if obs.detected and obs.point is not None:
            previous = self._cut_point
            self._cut_point = obs.point
            gesture = self.detector.update(obs.point, now)
            self.blade.add_point(obs.point, now, self.detector.is_active)
            window = [(x, y) for _t, x, y in self.detector.analyzer.window()]
            segments.extend(swipe_segments(
                window, previous, obs.point, gesture is not None, self.detector.is_active,
            ))
        elif self.tracker.hand_lost(now):
            self.detector.reset()
            self.blade.break_trail()
            self._reset_knife()
        self.blade.update(now)
        return segments

    def update_playing(self, dt: float, segments, now: float) -> None:
        for fruit in self.fruits.update(
            dt, self.score.level, elapsed=self.score.game_time, duration=self.score.duration,
        ):
            event = self.score.register_miss(fruit.id, fruit.kind)
            if event is None or event.lives_lost <= 0:
                continue
            self.renderer.on_slice(fruit, f"-{event.lives_lost}", (255, 90, 60))
        speed = self.detector.current_speed
        for result in self.collisions.check(segments, self.fruits.fruits):
            fruit = result.fruit
            event = self.score.register_cut(fruit.id, fruit.kind, speed >= config.CRITICAL_CUT_SPEED)
            if event is None:
                continue
            if event.kind == "bomb":
                self.renderer.on_slice(fruit, f"BOOM! -{event.lives_lost}", (255, 90, 60))
                self.audio.play("bomb")
            else:
                text = f"+{event.points}" + (f" x{event.multiplier}" if event.multiplier > 1 else "")
                self.renderer.on_slice(fruit, text, (255, 214, 64))
                self.audio.play("slice")
                if self.combo_banner.note(event.multiplier):
                    self.renderer.combo_flash = 0.28
                    self.audio.play("combo")
            self.combo_banner.note(self.score.multiplier)
        sample = self.detector.last_sample
        if sample is not None and swipe_too_slow(
            sample.speed, sample.distance, self.detector.min_speed, self.detector.min_distance,
        ):
            self._slow_hint_until = now + 0.7
        self.score.tick(dt)
        self.combo_banner.note(self.score.multiplier)
        self.combo_banner.tick(dt)
        if self.score.is_game_over:
            self.end_game()

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------
    def draw(self, now: float) -> None:
        r, state = self.renderer, self.machine.state
        if state == GameState.MENU:
            page = self.machine.menu_page
            if page == "main":
                r.draw_menu(self.labels(), self.selected)
            elif page == "instructions":
                r.draw_instructions(self.labels(), self.selected)
            elif page == "exit_confirm":
                r.draw_exit_confirm(self.labels(), self.selected)
            else:
                r.draw_settings(self.labels(), self.selected)
            r.draw_gesture_status(self.face_observation, self.observation.detected)
            r.draw_pointer(self.observation.point, self.observation.pinching)
        elif state == GameState.CALIBRATION:
            r.draw_calibration(
                self.calibration_ready(now), self.observation.point, self.camera_error,
                self.observation.raised_fingers if self.observation.detected else 0,
                self.observation.one_finger,
                self._practice_ready,
            )
            r.draw_pointer(self.observation.point, self.observation.pinching)
            r.draw_blade(self.blade, now)
        else:
            # The webcam is always used for tracking. The picture is the
            # background only when that setting is on; otherwise the wood table.
            r.draw_background(self.settings.show_camera_background)
            r.draw_fruits(self.fruits.fruits)
            r.draw_effects()
            r.draw_blade(self.blade, now)
            tracking = self.tracker is not None and not self.tracker.hand_lost(now)
            r.draw_hand_indicator(self.observation.point if tracking else None, tracking)
            r.draw_hud(self.score, hand_lost=state == GameState.PLAYING and not tracking)
            if state == GameState.COUNTDOWN:
                r.draw_countdown(self.machine.countdown_number)
            elif state == GameState.PAUSE:
                r.draw_overlay_title(r.t("paused"), self.labels(), self.selected)
            elif state == GameState.GAME_OVER:
                lines = [f"{r.t('final_score')}: {self.score.score}",
                         f"{r.t('high_score')}: {self.score.high_score}"]
                if self.score.new_high_score:
                    lines.append(r.t("new_high"))
                lines.append("Raise 2 fingers to restart")
                r.draw_overlay_title(r.t("game_over"), self.labels(), self.selected, lines)
            if state in (GameState.CALIBRATION, GameState.COUNTDOWN, GameState.PLAYING,
                         GameState.PAUSE, GameState.GAME_OVER) and self._two_finger_since is not None:
                r.text("Hold both fingers to restart", 34, (80, 255, 120),
                       center=(r.width // 2, r.height - 90))
            if state == GameState.PLAYING and now < self._slow_hint_until:
                r.text("Swipe faster", 36, (255, 180, 60), center=(r.width // 2, r.height - 150))
            if state == GameState.PLAYING and self.combo_banner.life > 0:
                size = int(72 + 64 * (self.combo_banner.life / self.combo_banner.duration))
                r.text(self.combo_banner.text, size, (255, 214, 64),
                       center=(r.width // 2, r.height // 2 - 20))
        if self.settings.debug_landmarks:
            r.draw_debug(self.clock.get_fps(), self.tracker.backend_name if self.tracker else "-")

    # ------------------------------------------------------------------
    def run(self) -> None:
        last = time.perf_counter()
        while self.running:
            now = time.perf_counter()
            dt = max(0.0, min(config.MAX_FRAME_DT, now - last))
            last = now
            self.handle_events()
            self.update(now, dt)
            self.draw(now)
            self.renderer.flip()
            self.clock.tick(config.TARGET_FPS)

    def shutdown(self) -> None:
        """Release webcam, MediaPipe and pygame (always called on exit)."""
        try:
            self.audio.stop_music()
        except Exception:
            pass
        self._stop_vision()
        if self.tracker is not None:
            self.tracker.close()
        if self.face is not None:
            self.face.close()
        if self.camera is not None:
            self.camera.release()
        pygame.quit()


def main() -> None:
    game = None
    try:
        game = Game()
        game.run()
    except KeyboardInterrupt:
        pass
    finally:
        if game is not None:
            game.shutdown()
        else:
            pygame.quit()


if __name__ == "__main__":
    main()

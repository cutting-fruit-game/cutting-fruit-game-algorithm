"""All pygame drawing: menus, camera preview, fruits, blade, HUD, effects."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pygame

from src import config
from src.blade import Blade
from src.fruit import Fruit
from src.score_manager import ScoreManager

Color = Tuple[int, int, int]
WHITE = (255, 255, 255)
GOLD = (255, 214, 64)
RED = (235, 64, 64)


class Renderer:
    """Owns the pygame window and draws every screen."""

    def __init__(self, settings: config.Settings) -> None:
        self.settings = settings
        self.width, self.height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        info = pygame.display.Info()
        self.display_width = info.current_w
        self.display_height = info.current_h
        self.display = pygame.display.set_mode(
            (self.display_width, self.display_height), pygame.NOFRAME
        )
        self.screen = pygame.Surface((self.width, self.height))
        pygame.display.set_caption(config.WINDOW_TITLE)
        self._fonts: Dict[Tuple[str, int, bool], pygame.font.Font] = {}
        self._sprites: Dict[Tuple[str, int], pygame.Surface] = {}
        self._halves: Dict[Tuple[str, int], Tuple[pygame.Surface, pygame.Surface]] = {}
        self._overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._background = self._make_wood_background()
        self._camera_surface: Optional[pygame.Surface] = None
        self.pause_button: Optional[pygame.Rect] = None
        self.buttons: List[Tuple[pygame.Rect, int]] = []
        self.calibration_button: Optional[pygame.Rect] = None
        self.particles: List[list] = []
        self.popups: List[list] = []
        self.splashes: List[dict] = []
        self.blasts: List[dict] = []
        self.flash = 0.0
        self.combo_flash = 0.0
        self.shake = 0.0

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def t(self, key: str) -> str:
        table = config.TRANSLATIONS.get(self.settings.language, {})
        return table.get(key) or config.TRANSLATIONS["en"].get(key, key)

    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        lang = self.settings.language
        key = (lang, size, bold)
        if key not in self._fonts:
            font = None
            custom = config.FONTS_DIR / ("khmer.ttf" if lang == "km" else "main.ttf")
            if custom.exists():
                try:
                    font = pygame.font.Font(str(custom), size)
                except (pygame.error, OSError):
                    font = None
            if font is None:
                names = ("leelawadeeui,khmerui,nirmalaui,notosanskhmer,khmerossystem"
                         if lang == "km" else "segoeui,arial,helveticaneue,dejavusans")
                font = pygame.font.SysFont(names, size, bold=bold)
            self._fonts[key] = font
        return self._fonts[key]

    def text(self, msg: str, size: int, color: Color = WHITE, center: Optional[Tuple[int, int]] = None,
             topleft: Optional[Tuple[int, int]] = None, topright: Optional[Tuple[int, int]] = None,
             bold: bool = True, shadow: bool = True) -> pygame.Rect:
        font = self.font(size, bold)
        surf = font.render(msg, True, color)
        rect = surf.get_rect()
        if center:
            rect.center = center
        elif topleft:
            rect.topleft = topleft
        elif topright:
            rect.topright = topright
        if shadow:
            self.screen.blit(font.render(msg, True, (0, 0, 0)), rect.move(2, 2))
        self.screen.blit(surf, rect)
        return rect

    def _make_wood_background(self) -> pygame.Surface:
        """Load the realistic wood asset, or build a wood table fallback."""
        for name in ("wood.png", "wood.jpg", "wood.jpeg"):
            path = config.BACKGROUNDS_DIR / name
            if path.exists():
                try:
                    image = pygame.image.load(str(path)).convert()
                    return pygame.transform.smoothscale(image, (self.width, self.height))
                except (pygame.error, OSError):
                    pass

        surf = pygame.Surface((self.width, self.height))
        rng = random.Random(2026)
        plank_height = max(100, self.height // 5)
        for plank_top in range(0, self.height, plank_height):
            tone = rng.randint(-18, 18)
            base = (112 + tone, 67 + tone // 2, 35 + tone // 3)
            for y in range(plank_top, min(plank_top + plank_height, self.height)):
                shade = int(7 * math.sin(y / 22.0) + rng.randint(-2, 2))
                color = tuple(max(0, min(255, c + shade)) for c in base)
                pygame.draw.line(surf, color, (0, y), (self.width, y))
            if plank_top > 0:
                pygame.draw.line(surf, (55, 29, 14), (0, plank_top), (self.width, plank_top), 5)
                pygame.draw.line(surf, (190, 138, 82), (0, plank_top + 3), (self.width, plank_top + 3), 2)

        rng = random.Random(99)
        for _ in range(max(450, self.width // 3)):
            x = rng.randrange(self.width)
            y = rng.randrange(self.height)
            length = rng.randint(12, 90)
            color = rng.choice(((155, 105, 58), (82, 45, 24), (190, 135, 78)))
            pygame.draw.line(surf, color, (x, y), (min(self.width, x + length), y), 1)
        for cx, cy in ((self.width * 0.32, self.height * 0.48), (self.width * 0.78, self.height * 0.24)):
            for radius in range(20, 130, 12):
                rect = pygame.Rect(int(cx - radius * 1.5), int(cy - radius * 0.35),
                                   int(radius * 3), max(2, int(radius * 0.7)))
                pygame.draw.ellipse(surf, (95, 52, 27), rect, 2)
        return surf

    # ------------------------------------------------------------------
    # camera / background
    # ------------------------------------------------------------------
    def set_camera_frame(self, frame_bgr) -> None:
        """Convert a BGR numpy frame to a screen-sized surface (stretched, so
        normalised hand coordinates line up with the picture)."""
        if frame_bgr is None:
            return
        try:
            rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
            h, w = rgb.shape[:2]
            surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
            self._camera_surface = pygame.transform.scale(surf, (self.width, self.height))
        except (ValueError, pygame.error):
            pass

    def draw_background(self, use_camera: bool, dim: int = 0) -> None:
        if use_camera and self._camera_surface is not None:
            self.screen.blit(self._camera_surface, (0, 0))
        else:
            self.screen.blit(self._background, (0, 0))
        if dim > 0:
            self._dim.fill((0, 0, 0, dim))
            self.screen.blit(self._dim, (0, 0))

    # ------------------------------------------------------------------
    # procedural fruit sprites
    # ------------------------------------------------------------------
    def _sprite(self, kind: str, radius: int) -> pygame.Surface:
        key = (kind, radius)
        if key in self._sprites:
            return self._sprites[key]
        size = radius * 2
        surf = None
        path = config.FRUITS_DIR / f"{kind}.png"
        if path.exists():
            try:
                img = pygame.image.load(str(path)).convert_alpha()
                surf = pygame.transform.smoothscale(img, (size, size))
            except (pygame.error, OSError):
                surf = None
        if surf is None:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            getattr(self, f"_draw_{kind}", self._draw_generic)(surf, radius, config.FRUIT_SPECS[kind])
        self._sprites[key] = surf
        return surf

    def _draw_generic(self, s, r, spec) -> None:
        pygame.draw.circle(s, spec.color, (r, r), int(r * 0.92))

    def _draw_apple(self, s, r, spec) -> None:
        pygame.draw.circle(s, spec.flesh_color, (r, r), int(r * 0.72))
        pygame.draw.circle(s, spec.color, (r, int(r * 1.02)), int(r * 0.9))
        pygame.draw.circle(s, spec.flesh_color, (r, r), int(r * 0.34))
        pygame.draw.circle(s, (255, 170, 170), (int(r * 0.62), int(r * 0.62)), int(r * 0.16))
        pygame.draw.line(s, (110, 70, 30), (r, int(r * 0.28)), (int(r * 1.05), int(r * 0.02)), 4)
        pygame.draw.ellipse(s, (60, 160, 55), (int(r * 1.02), int(r * 0.02), int(r * 0.55), int(r * 0.28)))

    def _draw_orange(self, s, r, spec) -> None:
        pygame.draw.circle(s, spec.color, (r, r), int(r * 0.92))
        pygame.draw.circle(s, spec.flesh_color, (r, r), int(r * 0.62))
        for deg in range(0, 360, 45):
            a = math.radians(deg)
            pygame.draw.line(s, (255, 170, 40), (r, r),
                             (r + int(r * 0.58 * math.cos(a)), r + int(r * 0.58 * math.sin(a))), 2)
        pygame.draw.circle(s, (255, 220, 140), (int(r * 0.62), int(r * 0.58)), int(r * 0.14))
        pygame.draw.circle(s, (70, 150, 50), (r, int(r * 0.12)), 5)

    def _draw_watermelon(self, s, r, spec) -> None:
        pygame.draw.circle(s, (20, 110, 45), (r, r), int(r * 0.95))
        pygame.draw.circle(s, (230, 245, 210), (r, r), int(r * 0.78))
        pygame.draw.circle(s, spec.flesh_color, (r, r), int(r * 0.68))
        for deg in (20, 70, 120, 200, 250, 310):
            a = math.radians(deg)
            pygame.draw.circle(s, (40, 20, 25),
                               (int(r + r * 0.32 * math.cos(a)), int(r + r * 0.32 * math.sin(a))),
                               max(2, r // 12))
        pygame.draw.circle(s, (140, 210, 120), (int(r * 0.55), int(r * 0.4)), int(r * 0.12))

    def _draw_banana(self, s, r, spec) -> None:
        outer, inner = [], []
        flesh_outer, flesh_inner = [], []
        for deg in range(25, 156, 5):
            a = math.radians(deg)
            outer.append((r + 0.95 * r * math.cos(a), 0.15 * r + 0.95 * r * math.sin(a)))
            inner.append((r + 0.55 * r * math.cos(a), 0.22 * r + 0.55 * r * math.sin(a)))
            flesh_outer.append((r + 0.82 * r * math.cos(a), 0.18 * r + 0.82 * r * math.sin(a)))
            flesh_inner.append((r + 0.64 * r * math.cos(a), 0.2 * r + 0.64 * r * math.sin(a)))
        skin = outer + inner[::-1]
        flesh = flesh_outer + flesh_inner[::-1]
        pygame.draw.polygon(s, spec.color, skin)
        pygame.draw.polygon(s, spec.flesh_color, flesh)
        pygame.draw.polygon(s, (170, 130, 20), skin, 3)
        pygame.draw.circle(s, (90, 60, 20), (int(outer[0][0]), int(outer[0][1])), 4)
        pygame.draw.circle(s, (90, 60, 20), (int(outer[-1][0]), int(outer[-1][1])), 4)

    def _draw_bomb(self, s, r, spec) -> None:
        c = (r, int(r * 1.1))
        pygame.draw.circle(s, spec.color, c, int(r * 0.82))
        pygame.draw.circle(s, (200, 40, 40), c, int(r * 0.45), 4)
        pygame.draw.circle(s, (90, 90, 105), (int(r * 0.7), int(r * 0.8)), int(r * 0.15))
        pygame.draw.line(s, (60, 45, 30), (int(r * 1.25), int(r * 0.4)), (int(r * 1.5), int(r * 0.15)), 5)
        pygame.draw.circle(s, (255, 200, 40), (int(r * 1.55), int(r * 0.12)), 6)
        pygame.draw.circle(s, (255, 90, 30), (int(r * 1.55), int(r * 0.12)), 3)

    def _half_sprites(self, kind: str, radius: int):
        key = (kind, radius)
        if key not in self._halves:
            base = self._sprite(kind, radius)
            spec = config.FRUIT_SPECS[kind]
            left = base.subsurface((0, 0, radius, radius * 2)).copy()
            right = base.subsurface((radius, 0, radius, radius * 2)).copy()
            lo, hi_y = int(radius * 0.08), int(radius * 1.92)
            if not spec.is_bomb:
                flesh_w = max(7, int(radius * 0.28))
                flesh = spec.flesh_color
                shine = tuple(min(255, c + 50) for c in flesh)
                pygame.draw.rect(left, flesh, (radius - flesh_w, lo, flesh_w, hi_y - lo))
                pygame.draw.line(left, shine, (radius - 2, lo), (radius - 2, hi_y), 2)
                pygame.draw.rect(right, flesh, (0, lo, flesh_w, hi_y - lo))
                pygame.draw.line(right, shine, (1, lo), (1, hi_y), 2)
                for dot_y in (int(radius * 0.55), int(radius), int(radius * 1.45)):
                    pygame.draw.circle(left, shine, (radius - flesh_w // 2, dot_y), max(2, radius // 14))
                    pygame.draw.circle(right, shine, (flesh_w // 2, dot_y), max(2, radius // 14))
            self._halves[key] = (left, right)
        return self._halves[key]

    def _blit_rotated(self, surf: pygame.Surface, x: float, y: float, rotation: float,
                      scale: float = 1.0) -> None:
        if abs(scale - 1.0) > 0.01:
            w, h = surf.get_size()
            surf = pygame.transform.smoothscale(surf, (max(1, int(w * scale)), max(1, int(h * scale))))
        rotated = pygame.transform.rotate(surf, -rotation)
        self.screen.blit(rotated, rotated.get_rect(center=(int(x), int(y))))

    # ------------------------------------------------------------------
    # gameplay drawing
    # ------------------------------------------------------------------
    def draw_fruits(self, fruits: Sequence[Fruit]) -> None:
        for f in fruits:
            r = max(8, int(round(f.radius)))
            if not f.sliced:
                self._blit_rotated(self._sprite(f.kind, r), f.x, f.y, f.rotation)
            else:
                if f.is_bomb:
                    continue
                halves = self._half_sprites(f.kind, r)
                pop = 1.0 + 0.14 * max(0.0, 1.0 - f.age_since_slice / 0.14)
                for piece in f.pieces:
                    self._blit_rotated(
                        halves[0 if piece.side < 0 else 1], piece.x, piece.y, piece.rotation, pop,
                    )

    def draw_blade(self, blade: Blade, now: float) -> None:
        trail = self._smooth_trail(blade.trail(now))
        if len(trail) < 2:
            return
        self._overlay.fill((0, 0, 0, 0))
        stroke = [trail[0]]
        for point in trail[1:]:
            if point.stroke != stroke[-1].stroke:
                self._draw_knife(stroke)
                stroke = [point]
            else:
                stroke.append(point)
        self._draw_knife(stroke)
        self.screen.blit(self._overlay, (0, 0))

    def _draw_knife(self, points) -> None:
        """Tapered blade. The sharp end is the last point, which is the fingertip."""
        if len(points) < 2:
            return
        pts = list(points)
        dx = dy = span = 0.0
        for i in range(len(pts) - 1, 0, -1):
            dx = pts[i].x - pts[i - 1].x
            dy = pts[i].y - pts[i - 1].y
            span = math.hypot(dx, dy)
            if span >= 1:
                break
        if span < 1:
            return
        length = 0.0
        for i in range(1, len(pts)):
            length += math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)
        slashing = pts[-1].width >= (config.BLADE_BASE_WIDTH + config.BLADE_ACTIVE_WIDTH) * 0.35
        reach = config.BLADE_TIP_LENGTH if slashing else config.BLADE_TIP_LENGTH * 0.55
        if length < reach:
            back = reach - length
            head = pts[0]
            tail = type(head)(
                head.x - dx / span * back, head.y - dy / span * back,
                head.alpha, head.width, head.stroke,
            )
            pts = [tail] + pts
        left, right, glow_l, glow_r = [], [], [], []
        count = len(pts)
        for i, point in enumerate(pts):
            if i == 0:
                vx, vy = pts[1].x - point.x, pts[1].y - point.y
            elif i == count - 1:
                vx, vy = point.x - pts[i - 1].x, point.y - pts[i - 1].y
            else:
                vx, vy = pts[i + 1].x - pts[i - 1].x, pts[i + 1].y - pts[i - 1].y
            norm = math.hypot(vx, vy) or 1.0
            nx, ny = -vy / norm, vx / norm
            along = i / (count - 1)
            if along > 0.84:
                taper = (1.0 - along) / 0.16
            else:
                taper = 0.22 + 0.78 * along
            half = max(1.0, point.width * 0.62 * taper)
            left.append((point.x + nx * half, point.y + ny * half))
            right.append((point.x - nx * half, point.y - ny * half))
            glow = half * 2.3 + 3
            glow_l.append((point.x + nx * glow, point.y + ny * glow))
            glow_r.append((point.x - nx * glow, point.y - ny * glow))
        for i in range(count - 1):
            along = i / (count - 1)
            alpha = int(255 * min(pts[i].alpha, pts[i + 1].alpha) * (0.45 + 0.55 * along))
            glow_quad = [glow_l[i], glow_l[i + 1], glow_r[i + 1], glow_r[i]]
            core_quad = [left[i], left[i + 1], right[i + 1], right[i]]
            pygame.draw.polygon(self._overlay, (*config.BLADE_GLOW_COLOR, max(18, alpha // 3)), glow_quad)
            pygame.draw.polygon(self._overlay, (*config.BLADE_CORE_COLOR, alpha), core_quad)
        center = [(int(p.x), int(p.y)) for p in pts]
        pygame.draw.aalines(self._overlay, (*config.BLADE_CORE_COLOR, 230), False, center)

    @staticmethod
    def _smooth_trail(trail):
        """Fill gaps between camera samples so the slash reads as one curve."""
        if len(trail) < 3:
            return trail
        steps = 4
        dense = []
        for i in range(len(trail) - 1):
            a, b = trail[i], trail[i + 1]
            if a.stroke != b.stroke:
                dense.append(a)
                continue
            p0 = trail[i - 1] if i > 0 and trail[i - 1].stroke == a.stroke else a
            p3 = trail[i + 2] if i + 2 < len(trail) and trail[i + 2].stroke == b.stroke else b
            for step in range(steps):
                t = step / steps
                t2, t3 = t * t, t * t * t
                x = 0.5 * (
                    (2 * a.x)
                    + (-p0.x + b.x) * t
                    + (2 * p0.x - 5 * a.x + 4 * b.x - p3.x) * t2
                    + (-p0.x + 3 * a.x - 3 * b.x + p3.x) * t3
                )
                y = 0.5 * (
                    (2 * a.y)
                    + (-p0.y + b.y) * t
                    + (2 * p0.y - 5 * a.y + 4 * b.y - p3.y) * t2
                    + (-p0.y + 3 * a.y - 3 * b.y + p3.y) * t3
                )
                fade = a.alpha + (b.alpha - a.alpha) * t
                width = a.width + (b.width - a.width) * t
                dense.append(type(a)(x, y, fade, width, a.stroke))
        dense.append(trail[-1])
        return dense

    def draw_hand_indicator(self, point: Optional[Tuple[float, float]], tracking: bool) -> None:
        if point is None:
            return
        color = (80, 255, 120) if tracking else (255, 180, 60)
        x, y = int(point[0]), int(point[1])
        pygame.draw.circle(self.screen, color, (x, y), 16, 3)
        pygame.draw.circle(self.screen, color, (x, y), 4)

    def draw_hud(self, score: ScoreManager, hand_lost: bool = False) -> None:
        # Subtle readable panels keep HUD information clear over the scenery.
        pygame.draw.rect(self.screen, (52, 32, 18, 210), pygame.Rect(14, 10, 250, 118), border_radius=16)
        self.text(f"{self.t('score')}: {score.score}", 40, GOLD, topleft=(24, 14))
        self.text(f"{self.t('level')}: {score.level}", 28, WHITE, topleft=(26, 62))
        if score.combo >= 2:
            self.text(f"{self.t('combo')} {score.combo}  x{score.multiplier}", 32,
                      (255, 140, 60), topleft=(26, 98))

        secs = int(math.ceil(score.time_remaining))
        timer_rect = pygame.Rect(0, 8, 210, 58)
        timer_rect.centerx = self.width // 2
        pygame.draw.rect(self.screen, (20, 55, 38, 190), timer_rect, border_radius=16)
        self.text(f"{self.t('time')}: {secs // 60}:{secs % 60:02d}", 38,
                  RED if secs <= 10 else WHITE, center=timer_rect.center)

        hearts_width = max(150, score.start_lives * 46 + 20)
        lives_rect = pygame.Rect(self.width - hearts_width - 14, 10, hearts_width, 58)
        pygame.draw.rect(self.screen, (20, 55, 38, 190), lives_rect, border_radius=16)
        for i in range(score.start_lives):
            self._heart(lives_rect.right - 24 - i * 46, 34, i < score.lives)

        if hand_lost:
            self.text(self.t("hand_lost"), 28, (255, 180, 60), center=(self.width // 2, 80))

        self.text("2 fingers: restart", 22, (230, 236, 220), topleft=(24, self.height - 40), bold=False)

        pause_size = 58
        self.pause_button = pygame.Rect(self.width - pause_size - 24, self.height - pause_size - 24,
                                        pause_size, pause_size)
        pygame.draw.rect(self.screen, (32, 82, 52), self.pause_button, border_radius=14)
        pygame.draw.rect(self.screen, WHITE, self.pause_button, 2, border_radius=14)
        pygame.draw.rect(self.screen, WHITE, (self.pause_button.left + 18, self.pause_button.top + 16, 7, 26))
        pygame.draw.rect(self.screen, WHITE, (self.pause_button.left + 33, self.pause_button.top + 16, 7, 26))

    def _heart(self, cx: int, cy: int, filled: bool) -> None:
        color = (230, 50, 70) if filled else (90, 90, 100)
        w = 0 if filled else 3
        pygame.draw.circle(self.screen, color, (cx - 8, cy - 4), 10, w)
        pygame.draw.circle(self.screen, color, (cx + 8, cy - 4), 10, w)
        pygame.draw.polygon(self.screen, color, [(cx - 17, cy), (cx + 17, cy), (cx, cy + 20)], w)

    # ------------------------------------------------------------------
    # effects
    # ------------------------------------------------------------------
    def on_slice(self, fruit: Fruit, text: str = "", text_color: Color = WHITE) -> None:
        """Juice burst along a fruit cut, or a fireball when a bomb is cut."""
        if fruit.is_bomb:
            self._explode_bomb(fruit, text, text_color)
            return
        spec = fruit.spec
        theta = math.radians(fruit.slice_angle)
        nx, ny = -math.sin(theta), math.cos(theta)
        tx, ty = math.cos(theta), math.sin(theta)
        colors = [spec.flesh_color, spec.color, (255, 255, 255)]
        self.splashes.append({
            "x": fruit.x, "y": fruit.y, "angle": fruit.slice_angle,
            "length": fruit.radius * 2.7, "life": 0.2, "max": 0.2,
        })
        for i in range(28):
            along = random.uniform(-0.85, 0.85) * fruit.radius
            side = 1.0 if i % 2 == 0 else -1.0
            spread = random.uniform(-0.55, 0.55)
            speed = random.uniform(160, 480)
            vx = side * nx * speed + tx * spread * 220
            vy = side * ny * speed + ty * spread * 220 - 60
            life = random.uniform(0.28, 0.7)
            self.particles.append([
                fruit.x + tx * along, fruit.y + ty * along, vx, vy, life, life,
                random.choice(colors), random.uniform(3.0, 8.0), 900.0,
            ])
        if text:
            self.popups.append([text, fruit.x, fruit.y - fruit.radius, 0.9, text_color])

    def _explode_bomb(self, fruit: Fruit, text: str, text_color: Color) -> None:
        self.blasts.append({
            "x": fruit.x, "y": fruit.y, "radius": fruit.radius,
            "life": 0.5, "max": 0.5,
        })
        self.flash = 0.22
        self.shake = 0.28
        spark_colors = [(255, 244, 180), (255, 196, 40), (255, 110, 20), (255, 60, 20)]
        for _ in range(48):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(280, 860)
            life = random.uniform(0.25, 0.65)
            self.particles.append([
                fruit.x, fruit.y,
                math.cos(ang) * speed, math.sin(ang) * speed - 40,
                life, life, random.choice(spark_colors), random.uniform(2.5, 6.5), 420.0,
            ])
        for _ in range(16):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(40, 180)
            life = random.uniform(0.45, 0.9)
            self.particles.append([
                fruit.x, fruit.y,
                math.cos(ang) * speed, math.sin(ang) * speed - 30,
                life, life, random.choice(((70, 70, 74), (40, 40, 44), (110, 110, 114))),
                random.uniform(10.0, 18.0), 40.0,
            ])
        if text:
            self.popups.append([text, fruit.x, fruit.y - fruit.radius, 1.1, text_color])

    def update_effects(self, dt: float) -> None:
        for p in self.particles:
            p[4] -= dt
            p[3] += p[8] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for pop in self.popups:
            pop[3] -= dt
            pop[2] -= 60 * dt
        self.popups = [p for p in self.popups if p[3] > 0]
        for splash in self.splashes:
            splash["life"] -= dt
        self.splashes = [s for s in self.splashes if s["life"] > 0]
        for blast in self.blasts:
            blast["life"] -= dt
        self.blasts = [b for b in self.blasts if b["life"] > 0]
        self.flash = max(0.0, self.flash - dt)
        self.combo_flash = max(0.0, self.combo_flash - dt)
        self.shake = max(0.0, self.shake - dt)

    def draw_effects(self) -> None:
        for x, y, vx, vy, life, max_life, color, size, _gravity in self.particles:
            fade = max(0.0, life / max_life)
            radius = max(1, int(size * fade))
            pygame.draw.circle(self.screen, color, (int(x), int(y)), radius)
            speed = math.hypot(vx, vy)
            if speed > 80 and radius > 1 and size < 10:
                tail = min(22.0, speed * 0.02) * fade
                pygame.draw.line(
                    self.screen, color,
                    (int(x), int(y)),
                    (int(x - vx / speed * tail), int(y - vy / speed * tail)),
                    max(1, radius // 2),
                )
        if self.splashes or self.blasts:
            self._overlay.fill((0, 0, 0, 0))
            for splash in self.splashes:
                t = max(0.0, splash["life"] / splash["max"])
                ang = math.radians(splash["angle"])
                half = splash["length"] * 0.5
                dx, dy = math.cos(ang) * half, math.sin(ang) * half
                x, y = splash["x"], splash["y"]
                width = max(2, int(14 * t))
                pygame.draw.line(
                    self._overlay, (255, 255, 255, int(80 * t)),
                    (x - dx, y - dy), (x + dx, y + dy), width + 10,
                )
                pygame.draw.line(
                    self._overlay, (255, 255, 245, int(235 * t)),
                    (x - dx, y - dy), (x + dx, y + dy), max(2, width // 2),
                )
            for blast in self.blasts:
                self._draw_blast(blast)
            self.screen.blit(self._overlay, (0, 0))
        for msg, x, y, life, color in self.popups:
            self.text(msg, 34, color, center=(int(x), int(y)))
        if self.flash > 0:
            self._dim.fill((255, 170, 60, int(110 * self.flash / 0.22)))
            self.screen.blit(self._dim, (0, 0))
        if self.combo_flash > 0:
            self._dim.fill((255, 214, 64, int(100 * self.combo_flash / 0.28)))
            self.screen.blit(self._dim, (0, 0))

    def _draw_blast(self, blast: dict) -> None:
        t = max(0.0, blast["life"] / blast["max"])
        age = 1.0 - t
        x, y = int(blast["x"]), int(blast["y"])
        base = blast["radius"]
        fire = max(4, int(base * (0.45 + 2.6 * age)))
        pygame.draw.circle(self._overlay, (255, 90, 16, int(170 * t)), (x, y), fire)
        core = max(3, int(base * (0.7 - 0.35 * age)))
        pygame.draw.circle(self._overlay, (255, 210, 50, int(230 * t)), (x, y), core)
        if age < 0.4:
            hot = max(2, int(base * 0.42 * (1.0 - age / 0.4)))
            pygame.draw.circle(self._overlay, (255, 255, 240, int(240 * (1.0 - age / 0.4))), (x, y), hot)
        ring = max(fire + 4, int(base * (1.1 + 4.0 * age)))
        pygame.draw.circle(self._overlay, (255, 190, 60, int(150 * t)), (x, y), ring, 4)
        smoke_ring = max(6, int(base * (0.6 + 3.1 * age)))
        pygame.draw.circle(self._overlay, (50, 50, 54, int(80 * t)), (x, y), smoke_ring, 7)

    def clear_effects(self) -> None:
        self.particles.clear()
        self.popups.clear()
        self.splashes.clear()
        self.blasts.clear()
        self.flash = 0.0
        self.combo_flash = 0.0
        self.shake = 0.0

    # ------------------------------------------------------------------
    # menus / screens
    # ------------------------------------------------------------------
    def _draw_buttons(self, labels: Sequence[str], selected: int, top: int, width: int = 460) -> None:
        self.buttons = []
        for i, label in enumerate(labels):
            rect = pygame.Rect(0, 0, width, 58)
            rect.centerx = self.width // 2
            rect.top = top + i * 74
            active = i == selected
            pygame.draw.rect(self.screen, (255, 190, 50) if active else (50, 56, 90), rect, border_radius=14)
            pygame.draw.rect(self.screen, WHITE if active else (110, 120, 170), rect, 2, border_radius=14)
            self.text(label, 30, (30, 20, 0) if active else WHITE, center=rect.center, shadow=False)
            self.buttons.append((rect, i))

    def button_at(self, pos: Tuple[int, int]) -> Optional[int]:
        for rect, idx in self.buttons:
            if rect.collidepoint(pos):
                return idx
        return None

    def draw_exit_confirm(self, labels: Sequence[str], selected: int) -> None:
        self.draw_background(False)
        self.text("Exit Game?", 64, GOLD, center=(self.width // 2, 180))
        self._draw_buttons(labels, selected, 280, width=360)

    def draw_gesture_status(self, face_observation, hand_detected: bool) -> None:
        smile = getattr(face_observation, "smiling", False)
        face_detected = getattr(face_observation, "detected", False)
        if smile:
            text, colour = "Smile detected!", (80, 255, 120)
        elif face_detected:
            text, colour = "Face detected - hold a smile to start", (255, 220, 120)
        else:
            text, colour = "Looking for face...", (255, 180, 60)
        self.text(text, 22, colour, topleft=(20, 20), bold=False)
        hand_text = "Hand detected - pinch to select" if hand_detected else "No hand detected"
        self.text(hand_text, 22, (80, 255, 120) if hand_detected else (255, 180, 60),
                  topleft=(20, 48), bold=False)

    def draw_pointer(self, point, pinching: bool = False) -> None:
        if point is None:
            return
        x, y = int(point[0]), int(point[1])
        pygame.draw.circle(self.screen, (255, 255, 255), (x, y), 13, 3)
        pygame.draw.circle(self.screen, (255, 210, 60) if pinching else (80, 220, 255),
                           (x, y), 7)

    def draw_menu(self, labels: Sequence[str], selected: int) -> None:
        self.draw_background(False)
        self.text(self.t("title"), 96, GOLD, center=(self.width // 2, 150))
        self._draw_buttons(labels, selected, 270)

    def draw_instructions(self, labels: Sequence[str], selected: int) -> None:
        self.draw_background(False)
        self.text(self.t("instructions"), 64, GOLD, center=(self.width // 2, 90))
        for i in range(1, 7):
            self.text(self.t(f"instr_{i}"), 30, WHITE, center=(self.width // 2, 190 + i * 56), bold=False)
        self._draw_buttons(labels, selected, 580)

    def draw_settings(self, rows: Sequence[str], selected: int) -> None:
        self.draw_background(False)
        self.text(self.t("settings"), 64, GOLD, center=(self.width // 2, 90))
        self._draw_buttons(rows, selected, 170, width=640)

    def calibration_button_at(self, pos: Tuple[int, int]) -> bool:
        return self.calibration_button is not None and self.calibration_button.collidepoint(pos)

    def draw_calibration(self, hand_ok: bool, hand_point, error: str = "", fingers: int = 0,
                         one_finger: bool = False, practice: bool = False) -> None:
        self.draw_background(False, dim=45)
        self.text(self.t("calibration"), 56, GOLD, center=(self.width // 2, 60))
        if error:
            self.text(self.t("camera_error"), 40, RED, center=(self.width // 2, 280))
            for i, line in enumerate(error.split("\n")[:6]):
                self.text(line, 24, WHITE, center=(self.width // 2, 340 + i * 34), bold=False)
        else:
            if fingers == 2:
                msg, color = "Hold both fingers to restart", (80, 255, 120)
            elif practice:
                msg, color = "Swipe once to set your cut speed", (80, 255, 120)
            elif not hand_ok:
                msg, color = self.t("hand_missing"), (255, 180, 60)
            elif one_finger:
                msg, color = "Hold that one finger", (80, 255, 120)
            elif fingers > 1:
                msg, color = f"{fingers} fingers up — curl the others", (255, 120, 80)
            else:
                msg, color = "Raise one finger. Keep the others down.", (255, 214, 64)
            self.text(msg, 38, color, center=(self.width // 2, self.height - 150))
            hovered = hand_point is not None and self.calibration_button_at(hand_point)
            self.calibration_button = pygame.Rect(0, 0, 360, 68)
            self.calibration_button.center = (self.width // 2, self.height - 80)
            pygame.draw.rect(self.screen, (255, 190, 50) if hovered else (50, 56, 90),
                             self.calibration_button, border_radius=14)
            pygame.draw.rect(self.screen, WHITE if hovered else (110, 120, 170),
                             self.calibration_button, 3, border_radius=14)
            self.text("CONTINUE", 34, (30, 20, 0) if hovered else WHITE,
                      center=self.calibration_button.center, shadow=False)
            self.draw_hand_indicator(hand_point, hand_ok)
        self.text("ESC: " + self.t("back"), 24, WHITE, topleft=(20, self.height - 44), bold=False)

    def draw_countdown(self, number: int) -> None:
        self.text(str(number), 220, GOLD, center=(self.width // 2, self.height // 2))
        self.text(self.t("get_ready"), 48, WHITE, center=(self.width // 2, self.height // 2 - 170))

    def draw_overlay_title(self, title: str, labels: Sequence[str], selected: int, lines: Sequence[str] = ()) -> None:
        self._dim.fill((0, 0, 0, 170))
        self.screen.blit(self._dim, (0, 0))
        self.text(title, 80, GOLD, center=(self.width // 2, 130))
        for i, line in enumerate(lines):
            self.text(line, 40 if i == 0 else 30, WHITE, center=(self.width // 2, 230 + i * 52))
        self._draw_buttons(labels, selected, 230 + max(1, len(lines)) * 52 + 40)

    def draw_debug(self, fps: float, backend: str) -> None:
        self.text(f"FPS {fps:4.1f}  [{backend}]", 20, (180, 255, 180), topleft=(self.width - 230, self.height - 28),
                  bold=False, shadow=False)

    def flip(self) -> None:
        scale = min(
            self.display_width / self.width,
            self.display_height / self.height,
        )
        scaled_width = int(self.width * scale)
        scaled_height = int(self.height * scale)
        offset_x = (self.display_width - scaled_width) // 2
        offset_y = (self.display_height - scaled_height) // 2
        scaled = pygame.transform.smoothscale(
            self.screen, (scaled_width, scaled_height)
        )
        jx = jy = 0
        if self.shake > 0:
            mag = 14 * min(1.0, self.shake / 0.28)
            jx = int(random.uniform(-mag, mag))
            jy = int(random.uniform(-mag, mag))
        self.display.fill((0, 0, 0))
        self.display.blit(scaled, (offset_x + jx, offset_y + jy))
        pygame.display.flip()

    def mouse_to_virtual(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        scale = min(
            self.display_width / self.width,
            self.display_height / self.height,
        )
        scaled_width = int(self.width * scale)
        scaled_height = int(self.height * scale)
        offset_x = (self.display_width - scaled_width) // 2
        offset_y = (self.display_height - scaled_height) // 2
        x = (pos[0] - offset_x) / scale
        y = (pos[1] - offset_y) / scale
        return int(x), int(y)

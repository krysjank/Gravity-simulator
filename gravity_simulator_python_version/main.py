"""
Gravity simulator v3.2 – přepis ze Scratche do Pythonu (pygame).

Spuštění:   pip install pygame
            python main.py

Ovládání (stejné jako ve Scratchi):
  * myš  – tlačítka, posuvníky, přepínače, přetahování koulí před startem
  * MEZERNÍK – spustit / zastavit simulaci

Souřadnice uvnitř programu jsou scratchovské: scéna 480 × 360 bodů,
střed (0, 0), osa y míří nahoru. Okno je SCALE-krát větší.
"""
import json
import math
import os
import sys

import pygame

# ----------------------------------------------------------------------------
# Základní nastavení
# ----------------------------------------------------------------------------
STAGE_W, STAGE_H = 480, 360
SCALE = 2            # 2 => okno 960 × 720; můžeš změnit na 1 nebo 1.5
FPS = 30             # Scratch běží 30 snímků za sekundu
FADE_STEPS = 25      # přechod mezi obrazovkami: 25 snímků ztmavení + 25 rozjasnění
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

BALL_NAMES = ("Ball1", "Ball2", "Ball3")
DEFAULT_MASS = {"Ball1": 20, "Ball2": 70, "Ball3": 30}
# pozice koulí na obrazovkách s nastavením (hmotnost, pohyb, rychlost)
MENU_POS = {"Ball1": (-147, 55), "Ball2": (-147, -10), "Ball3": (-147, -75)}
# startovní pozice v simulaci (hodnoty uložené v původním projektu)
START_POS = {"Ball1": (-95.4687, 66.8277), "Ball2": (-58.9050, -63.1343), "Ball3": (98.4954, 31.6864)}
BALL_LAYER_ORDER = ("Ball1", "Ball3", "Ball2")  # pořadí vykreslení (Ball2 je navrchu)


def to_screen(x, y):
    """Scratch souřadnice -> pixely okna."""
    return (x + STAGE_W / 2) * SCALE, (STAGE_H / 2 - y) * SCALE


def to_stage(px, py):
    """Pixely okna -> Scratch souřadnice."""
    return px / SCALE - STAGE_W / 2, STAGE_H / 2 - py / SCALE


def fmt_value(v):
    """Formát čísla jako ve Scratch monitoru (max. 6 desetinných míst)."""
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return f"{round(v, 6):.6f}".rstrip("0").rstrip(".")
    return str(v)


# ----------------------------------------------------------------------------
# Kostýmy a sprajty
# ----------------------------------------------------------------------------
class Costume:
    """Obrázek kostýmu + střed otáčení (jako ve Scratchi)."""

    def __init__(self, info):
        self.image = pygame.image.load(os.path.join(ASSETS, info["file"])).convert_alpha()
        self.cx, self.cy, self.res = info["cx"], info["cy"], info["res"]
        self._cache = {}

    def get(self, size):
        """Vrátí (surface, mask, posun levého horního rohu od středu) pro danou velikost v %."""
        key = round(size, 3)
        if key not in self._cache:
            k = SCALE * size / 100
            w = max(1, round(self.image.get_width() / self.res * k))
            h = max(1, round(self.image.get_height() / self.res * k))
            surf = pygame.transform.smoothscale(self.image, (w, h))
            self._cache[key] = (surf, pygame.mask.from_surface(surf, 50), (-self.cx * k, -self.cy * k))
        return self._cache[key]


class Sprite:
    def __init__(self, game, name, x=0.0, y=0.0, size=100, visible=False, costume=None):
        self.game = game
        self.name = name
        self.costumes = game.costumes_of(name)
        self.costume = costume or next(iter(self.costumes))
        self.x, self.y = x, y
        self.size = size
        self.visible = visible
        self.ghost = 0  # průhlednost 0–100 jako efekt "duch"

    def _render(self):
        surf, mask, (ox, oy) = self.costumes[self.costume].get(self.size)
        sx, sy = to_screen(self.x, self.y)
        return surf, mask, (round(sx + ox), round(sy + oy))

    def draw(self, screen):
        if not self.visible or self.ghost >= 100:
            return
        surf, _, pos = self._render()
        if self.ghost:
            surf = surf.copy()
            surf.set_alpha(round(255 * (100 - self.ghost) / 100))
        screen.blit(surf, pos)

    def touching_mouse(self):
        """Pixelově přesný test „dotýká se ukazatele myši?“."""
        if not self.visible:
            return False
        _, mask, (left, top) = self._render()
        mx, my = self.game.mouse_px
        ix, iy = int(mx - left), int(my - top)
        w, h = mask.get_size()
        return 0 <= ix < w and 0 <= iy < h and mask.get_at((ix, iy))

    def next_costume(self):
        names = list(self.costumes)
        self.costume = names[(names.index(self.costume) + 1) % len(names)]


class Button(Sprite):
    """Tlačítko se dvěma kostýmy (normální / pod myší) a zvětšením pod myší.

    trigger = "release": akce při puštění myši nad tlačítkem (Next, Back, …)
    trigger = "press":   akce hned při stisknutí (Start, +, -, reset settings)
    """

    def __init__(self, game, name, x, y, normal, hover=None, size=100, hover_size=110,
                 trigger="release", action=None, enabled=lambda: True):
        super().__init__(game, name, x, y, size, False, normal)
        self.normal, self.hover = normal, hover
        self.base_size, self.hover_size = size, hover_size
        self.trigger, self.action, self.enabled = trigger, action, enabled
        self.armed = False

    def update(self):
        if not self.visible:
            self.armed = False
            return
        g = self.game
        over = self.touching_mouse()
        if self.hover:
            self.costume = self.hover if over else self.normal
        self.size = self.hover_size if over else self.base_size
        if g.mouse_pressed and over and self.enabled():
            if self.trigger == "press":
                self.action()
                return
            self.armed = True
        if g.mouse_released:
            if self.armed and over and self.enabled():
                self.action()
            self.armed = False


class Monitor:
    """Zobrazení proměnné jako ve Scratchi: 'default', 'slider' nebo 'large'."""

    BG, BORDER, LABEL = (230, 240, 255), (195, 204, 222), (87, 94, 117)
    ORANGE, BLUE, TRACK = (255, 140, 26), (0, 117, 255), (200, 205, 215)

    def __init__(self, game, label, getter, setter=None, mode="default", left=0, top=0,
                 vmin=0, vmax=100):
        self.game, self.label = game, label
        self.get, self.set = getter, setter
        self.mode, self.left, self.top = mode, left, top
        self.vmin, self.vmax = vmin, vmax
        self.visible = False
        self.dragging = False
        self.slider_rect = None

    def _px(self, v):
        return round(v * SCALE)

    def draw(self, screen):
        if not self.visible:
            return
        g = self.game
        x, y = self._px(self.left), self._px(self.top)
        value = g.font_value.render(fmt_value(self.get()), True, (255, 255, 255))
        if self.mode == "large":
            w = max(value.get_width() + self._px(10), self._px(40))
            h = self._px(22)
            pygame.draw.rect(screen, self.ORANGE, (x, y, w, h), border_radius=self._px(4))
            pygame.draw.rect(screen, (230, 120, 10), (x, y, w, h), 1, border_radius=self._px(4))
            screen.blit(value, value.get_rect(center=(x + w / 2, y + h / 2)))
            return
        label = g.font_label.render(self.label, True, self.LABEL)
        pad = self._px(5)
        pill_w = max(value.get_width() + self._px(10), self._px(40))
        pill_h = self._px(16)
        head_w = pad + label.get_width() + self._px(6) + pill_w + pad
        w = max(head_w, self._px(140)) if self.mode == "slider" else head_w
        h = self._px(37) if self.mode == "slider" else self._px(24)
        pygame.draw.rect(screen, self.BG, (x, y, w, h), border_radius=self._px(4))
        pygame.draw.rect(screen, self.BORDER, (x, y, w, h), 1, border_radius=self._px(4))
        row_cy = y + self._px(12)
        screen.blit(label, label.get_rect(midleft=(x + pad, row_cy)))
        pill = pygame.Rect(0, 0, pill_w, pill_h)
        pill.midleft = (x + pad + label.get_width() + self._px(6), row_cy)
        pygame.draw.rect(screen, self.ORANGE, pill, border_radius=self._px(4))
        screen.blit(value, value.get_rect(center=pill.center))
        if self.mode == "slider":
            track = pygame.Rect(x + pad + self._px(3), y + self._px(27), w - 2 * pad - self._px(6), self._px(4))
            self.slider_rect = track.inflate(self._px(4), self._px(14))
            frac = (self.get() - self.vmin) / (self.vmax - self.vmin)
            frac = max(0.0, min(1.0, frac))
            knob_x = track.left + frac * track.width
            pygame.draw.rect(screen, self.TRACK, track, border_radius=self._px(2))
            pygame.draw.rect(screen, self.BLUE, (track.left, track.top, knob_x - track.left, track.height),
                             border_radius=self._px(2))
            pygame.draw.circle(screen, self.BLUE, (knob_x, track.centery), self._px(6))

    def update(self):
        if not self.visible or self.mode != "slider" or self.slider_rect is None:
            self.dragging = False
            return
        g = self.game
        if g.mouse_pressed and self.slider_rect.collidepoint(g.mouse_px):
            self.dragging = True
        if not g.mouse_down:
            self.dragging = False
        if self.dragging:
            r = self.slider_rect.inflate(-self._px(4), 0)
            frac = max(0.0, min(1.0, (g.mouse_px[0] - r.left) / r.width))
            self.set(round(self.vmin + frac * (self.vmax - self.vmin)))  # celá čísla (isDiscrete)


# ----------------------------------------------------------------------------
# Fyzika (stejný výpočet jako bloky v Ball1/Ball2/Ball3)
# ----------------------------------------------------------------------------
class Ball(Sprite):
    RADIUS = 12  # kostým 24 × 24 px

    def __init__(self, game, name):
        super().__init__(game, name, *MENU_POS[name], visible=False)
        self.mass = DEFAULT_MASS[name]
        self.vx = self.vy = 0.0
        self.mem_v = (0.0, 0.0)          # rychlost nastavená před simulací (Mem_BallX_speed)
        self.before = START_POS[name]    # pozice před simulací (BallX_X/Y_Pos_before_simulation)
        self.movable = True
        self.running = False
        self.crashed = False
        self.frozen = False              # nepohyblivá koule čeká na reset
        self.can_change_before = True
        self.draggable = False

    @property
    def size(self):
        return self.mass * 1.5 + 50

    @size.setter
    def size(self, _):  # velikost je vždy odvozená z hmotnosti
        pass

    @property
    def radius(self):
        return self.RADIUS * self.size / 100

    def touching_ball(self, other):
        return other.visible and math.hypot(self.x - other.x, self.y - other.y) < self.radius + other.radius

    def keep_in_fence(self):
        """Scratch nedovolí sprajtu úplně opustit scénu."""
        inset = min(15, self.radius)
        lim_x = STAGE_W / 2 - inset + self.radius
        lim_y = STAGE_H / 2 - inset + self.radius
        self.x = max(-lim_x, min(lim_x, self.x))
        self.y = max(-lim_y, min(lim_y, self.y))


def gravity_acceleration(ball, others):
    """Zrychlení koule: součet  m_druhé / d²  ve směru ke každé druhé kouli."""
    ax = ay = 0.0
    for o in others:
        dx, dy = o.x - ball.x, o.y - ball.y
        d = math.hypot(dx, dy)
        if d == 0:
            continue
        k = o.mass / (d * d)
        ax += k * dx / d
        ay += k * dy / d
    return ax, ay


# ----------------------------------------------------------------------------
# Hra / obrazovky
# ----------------------------------------------------------------------------
BACKGROUND = {
    "start": "start_menu", "tutorial": "tutorial",
    "guide1": "1/5", "guide2": "2/5", "guide3": "3/5", "guide4": "4/5", "guide5": "5/5",
    "letsgo": "let's go", "mass": "mass", "move": "mass", "speed": "mass",
    "sim": "space_screen", "settings1": "settings", "settings2": "settings",
}
NEXT = {"tutorial": "guide1", "guide1": "guide2", "guide2": "guide3", "guide3": "guide4",
        "guide4": "guide5", "guide5": "letsgo", "letsgo": "mass", "mass": "move",
        "move": "speed", "speed": "sim", "settings1": "settings2"}
BACK = {"guide1": "tutorial", "guide2": "guide1", "guide3": "guide2", "guide4": "guide3",
        "guide5": "guide4", "letsgo": "guide5", "mass": "letsgo", "move": "mass",
        "speed": "move", "sim": "speed", "settings1": "sim", "settings2": "settings1"}
SKIP_SCREENS = {"tutorial", "guide1", "guide2", "guide3", "guide4", "guide5"}


class Game:
    def __init__(self):
        pygame.display.set_caption("Gravity simulator v3.2")
        self.screen = pygame.display.set_mode((round(STAGE_W * SCALE), round(STAGE_H * SCALE)))
        self.clock = pygame.time.Clock()
        font_path = os.path.join(ASSETS, "NotoSans-Medium.ttf")
        self.font_label = pygame.font.Font(font_path, round(11 * SCALE))
        self.font_value = pygame.font.Font(font_path, round(11 * SCALE))

        with open(os.path.join(ASSETS, "costumes.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        self._costumes = {}
        for key, info in manifest.items():
            sprite, costume = key.split("|", 1)
            self._costumes.setdefault(sprite, {})[costume] = Costume(info)

        # vstup
        self.mouse_px = (0, 0)
        self.mouse_down = self.mouse_pressed = self.mouse_released = False
        self.space_down = False
        self.space_armed = False   # mezerník byl stisknut, když nic neběželo -> start při puštění
        self.frame = 0
        self.quit = False

        # nastavení
        self.shadows_on = True
        self.shadow_transparency = 80
        self.shadow_lifetime = 1.0
        self.show_speed = [False] * 6  # Ball1 x, Ball1 y, Ball2 x, Ball2 y, Ball3 x, Ball3 y
        self.shadows = []              # [jméno koule, x, y, velikost, snímek zániku]

        self._build()
        self.state = None
        self.fade = None               # {"frame": n, "target": obrazovka}
        self.enter("start")
        self.fade_ghost = 100

    def costumes_of(self, name):
        return self._costumes[name]

    # ------------------------------------------------------------------ sestavení
    def _build(self):
        S = self
        self.bg = Sprite(self, "menus/screens", 0, 0, visible=True, costume="start_menu")
        self.overlay = Sprite(self, "Shade", 0, 0, visible=True)
        self.balls = {n: Ball(self, n) for n in BALL_NAMES}
        self.shade_sprites = {n: Sprite(self, f"{n}_Shade") for n in BALL_NAMES}

        self.btn_start = Button(self, "Startbutton", 0, -30, "not_presseed", "pressed",
                                trigger="press", action=lambda: S.go("tutorial"))
        self.btn_next = Button(self, "Nextbutton", 214, -143, "not_pressed", "pressed",
                               action=lambda: S.go(NEXT[S.state]),
                               enabled=lambda: S.state != "move" or any(b.movable for b in S.balls.values()))
        self.btn_back = Button(self, "Backbutton", -214, -143, "not_pressed", "pressed",
                               action=lambda: S.go(BACK[S.state]),
                               enabled=lambda: S.state != "sim" or not S.any_running())
        self.btn_skip = Button(self, "skip button", 202, 158, "not_pressed", "pressed",
                               action=lambda: S.go("letsgo"))
        self.btn_reset = Button(self, "Reset_position_button", 205, -145, "not_pressed", "pressed",
                                action=self.reset_simulation, enabled=lambda: not S.any_running())
        self.btn_settings = Button(self, "settings", 222, 164, "not_pressed", "pressed",
                                   action=lambda: S.go("settings1"), enabled=lambda: not S.any_running())
        self.btn_reset_settings = Button(self, "reset settings", 0, -130, "not_pressed", "pressed",
                                         size=120, hover_size=130, trigger="press",
                                         action=self.reset_settings)
        self.btn_plus = Button(self, "+", 95, -59, "costume1", size=100, hover_size=100, trigger="press",
                               action=lambda: S._change_lifetime(+0.1),
                               enabled=lambda: S.shadow_lifetime < 2 - 1e-9)
        self.btn_minus = Button(self, "-", -10, -59, "costume1", size=100, hover_size=100, trigger="press",
                                action=lambda: S._change_lifetime(-0.1),
                                enabled=lambda: S.shadow_lifetime > 0.2 + 1e-9)
        self.chk_shadows = Button(self, "Shadow manager", -73, 29, "clicked",
                                  action=self._toggle_shadows)
        self.chk_speed = []
        for i in range(6):
            b = Button(self, "Speed_showing_manager", 35 * (i + 1), 30, "unclicked",
                       action=lambda i=i: S._toggle_speed(i))
            self.chk_speed.append(b)
        self.toggles = {}
        for n, y in zip(BALL_NAMES, (16, -48, -112)):
            t = Button(self, "movable" + n, 60, y, "move", hover_size=100, trigger="press",
                       action=lambda n=n: S._toggle_movable(n))
            self.toggles[n] = t
        self.text = Sprite(self, "additional_texts", 0, -149)
        self.helper = Sprite(self, "small_helper", 0, 0, costume="to run")

        self.buttons = [self.btn_start, self.btn_next, self.btn_back, self.btn_skip, self.btn_reset,
                        self.btn_settings, self.btn_reset_settings, self.btn_plus, self.btn_minus,
                        self.chk_shadows, *self.chk_speed, *self.toggles.values()]

        # monitory proměnných (pozice = levý horní roh ve Scratch pixelech)
        self.mon_mass = []
        for n, top in zip(BALL_NAMES, (105, 172, 236)):
            b = self.balls[n]
            self.mon_mass.append(Monitor(self, n, lambda b=b: b.mass,
                                         lambda v, b=b: setattr(b, "mass", v), "slider", 188, top, 1, 100))
        self.mon_speed_set = {}
        pos = {"Ball1": ((139, 106), (302, 106)), "Ball2": ((139, 172), (301, 172)),
               "Ball3": ((139, 237), (301, 237))}
        for n in BALL_NAMES:
            b = self.balls[n]
            mx = Monitor(self, f"{n}_xspeed", lambda b=b: b.vx, lambda v, b=b: setattr(b, "vx", v),
                         "slider", *pos[n][0], -5, 5)
            my = Monitor(self, f"{n}_yspeed", lambda b=b: b.vy, lambda v, b=b: setattr(b, "vy", v),
                         "slider", *pos[n][1], -5, 5)
            self.mon_speed_set[n] = (mx, my)
        self.mon_speed_show = []
        for i, (n, axis, (left, top)) in enumerate(zip(
                ("Ball1", "Ball1", "Ball2", "Ball2", "Ball3", "Ball3"), "xyxyxy",
                ((2, 63), (3, 95), (3, 127), (3, 159), (3, 191), (3, 224)))):
            b = self.balls[n]
            self.mon_speed_show.append(Monitor(self, f"{n}{axis.upper()}Speed",
                                               lambda b=b, a=axis: getattr(b, "v" + a), left=left, top=top))
        self.mon_transparency = Monitor(self, "shadow transparency", lambda: S.shadow_transparency,
                                        lambda v: setattr(S, "shadow_transparency", v), "slider",
                                        277, 175, 1, 99)
        self.mon_lifetime = Monitor(self, "shadow lifetime", lambda: round(S.shadow_lifetime, 6),
                                    mode="large", left=258, top=227)
        self.monitors = [*self.mon_mass, *(m for pair in self.mon_speed_set.values() for m in pair),
                         *self.mon_speed_show, self.mon_transparency, self.mon_lifetime]

    # ------------------------------------------------------------------ akce tlačítek
    def _toggle_movable(self, n):
        t = self.toggles[n]
        t.next_costume()
        self.balls[n].movable = t.costume == "move"

    def _toggle_shadows(self):
        self.chk_shadows.next_costume()
        self.shadows_on = self.chk_shadows.costume == "clicked"

    def _toggle_speed(self, i):
        self.chk_speed[i].next_costume()
        self.show_speed[i] = self.chk_speed[i].costume == "clicked"

    def _change_lifetime(self, d):
        self.shadow_lifetime = round(self.shadow_lifetime + d, 6)

    def reset_settings(self):
        if self.state == "settings1":
            self.shadows_on = True
            self.chk_shadows.costume = "clicked"
            self.shadow_lifetime = 1.0
            self.shadow_transparency = 80
        else:
            self.show_speed = [False] * 6
            for c in self.chk_speed:
                c.costume = "unclicked"

    def any_running(self):
        return any(b.running for b in self.balls.values())

    # ------------------------------------------------------------------ obrazovky
    def go(self, target):
        """Spustí přechod (ztmavení -> změna obrazovky -> rozjasnění)."""
        if self.fade is None:
            if self.state == "speed":            # při odchodu si zapamatuj zvolené rychlosti
                for b in self.balls.values():
                    b.mem_v = (b.vx, b.vy)
            self.fade = {"frame": 0, "target": target}

    def enter(self, name):
        """Rozmístí prvky pro obrazovku `name` (odpovídá zprávám 'show …' ve Scratchi)."""
        self.state = name
        self.bg.costume = BACKGROUND[name]
        for s in self.buttons:
            s.visible = False
        for m in self.monitors:
            m.visible = False
        for b in self.balls.values():
            b.visible = False
            b.running = False
            b.draggable = False
        self.text.visible = self.helper.visible = False
        self.shadows.clear()
        self.space_armed = False

        nav_next = name in NEXT
        nav_back = name in BACK
        self.btn_next.visible = nav_next
        self.btn_back.visible = nav_back
        self.btn_skip.visible = name in SKIP_SCREENS
        self.btn_start.visible = name == "start"

        if name in ("mass", "move", "speed"):
            for n, b in self.balls.items():
                b.visible = True
                b.x, b.y = MENU_POS[n]
        if name == "mass":
            for m in self.mon_mass:
                m.visible = True
        elif name == "move":
            for t in self.toggles.values():
                t.visible = True
        elif name == "speed":
            self.text.costume, self.text.x, self.text.y = "(optional)", 0, -149
            self.text.visible = True
            for n, b in self.balls.items():
                if b.movable:
                    b.vx, b.vy = b.mem_v
                    for m in self.mon_speed_set[n]:
                        m.visible = True
                else:
                    b.mem_v = (0.0, 0.0)
                    b.vx = b.vy = 0.0
        elif name == "sim":
            self.btn_reset.visible = self.btn_settings.visible = True
            self.helper.visible = True
            self.helper.costume = "to run"
            self.started = False
            for i, m in enumerate(self.mon_speed_show):
                m.visible = self.show_speed[i]
            for b in self.balls.values():
                b.visible = True
                b.vx, b.vy = b.mem_v
                b.x, b.y = b.before
                b.can_change_before = True
                b.draggable = True
                b.frozen = False
            for n, s in self.shade_sprites.items():
                s.size = self.balls[n].size
            self.dragged = None
        elif name == "settings1":
            self.text.costume, self.text.x, self.text.y = "shadowtexts", 0, 0
            self.text.visible = True
            self.chk_shadows.visible = True
            self.btn_reset_settings.visible = True
        elif name == "settings2":
            self.text.costume, self.text.x, self.text.y = "show variables", 0, 0
            self.text.visible = True
            for c in self.chk_speed:
                c.visible = True
            self.btn_reset_settings.visible = True

    # ------------------------------------------------------------------ simulace
    def start_run(self):
        """Puštění mezerníku: koule se rozjedou (nepohyblivé zamrznou do resetu)."""
        self.started = True
        for b in self.balls.values():
            if b.frozen:
                continue
            b.draggable = False
            if b.can_change_before:
                b.before = (b.x, b.y)
                b.can_change_before = False
            if b.movable:
                b.crashed = False
                b.running = not any(b.touching_ball(o) for o in self.balls.values() if o is not b)
                if not b.running:
                    b.crashed = True
            else:
                b.crashed = True
                b.frozen = True
        self.dragged = None

    def stop_run(self):
        for b in self.balls.values():
            b.running = False

    def reset_simulation(self):
        for b in self.balls.values():
            b.x, b.y = b.before
            b.vx, b.vy = b.mem_v
            b.can_change_before = True
            b.draggable = True
            b.frozen = False
        self.started = False
        self.shadows.clear()

    def physics_step(self):
        balls = list(self.balls.values())
        active = [b for b in balls if b.running]
        if not active:
            return
        if self.shadows_on:
            expire = self.frame + max(1, round(self.shadow_lifetime * FPS))
            for b in active:
                self.shadows.append([b.name, b.x, b.y, b.size, expire])
        acc = {b.name: gravity_acceleration(b, [o for o in balls if o is not b]) for b in active}
        for b in active:
            ax, ay = acc[b.name]
            b.vx += ax
            b.vy += ay
            b.x += b.vx
            b.y += b.vy
            b.keep_in_fence()
        for b in active:
            if any(b.touching_ball(o) for o in balls if o is not b):
                b.running = False
                b.crashed = True

    def update_helper(self):
        if not self.started:
            self.helper.costume = "to run"
        elif self.any_running():
            self.helper.costume = "to stop"
        elif all(b.crashed for b in self.balls.values()):
            self.helper.costume = "to restart"
        else:
            self.helper.costume = "to run and restart"

    def update_dragging(self):
        if self.mouse_pressed and self.dragged is None:
            mx, my = to_stage(*self.mouse_px)
            for n in reversed(BALL_LAYER_ORDER):
                b = self.balls[n]
                if b.draggable and b.touching_mouse():
                    self.dragged, self.grab = b, (b.x - mx, b.y - my)
                    break
        if self.dragged is not None:
            if not self.mouse_down or not self.dragged.draggable:
                self.dragged = None
            else:
                mx, my = to_stage(*self.mouse_px)
                self.dragged.x, self.dragged.y = mx + self.grab[0], my + self.grab[1]
                self.dragged.keep_in_fence()

    # ------------------------------------------------------------------ smyčka
    def handle_events(self, events):
        self.mouse_pressed = self.mouse_released = False
        space_pressed = space_released = False
        for e in events:
            if e.type == pygame.QUIT:
                self.quit = True
            elif e.type == pygame.MOUSEMOTION:
                self.mouse_px = e.pos
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self.mouse_px, self.mouse_down, self.mouse_pressed = e.pos, True, True
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                self.mouse_px, self.mouse_down, self.mouse_released = e.pos, False, True
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                self.space_down, space_pressed = True, True
            elif e.type == pygame.KEYUP and e.key == pygame.K_SPACE:
                self.space_down, space_released = False, True
        return space_pressed, space_released

    def step(self, events):
        """Jeden snímek: vstup -> logika -> vykreslení."""
        space_pressed, space_released = self.handle_events(events)
        self.frame += 1

        if self.fade is not None:
            self.fade["frame"] += 1
            f = self.fade["frame"]
            if f == FADE_STEPS:
                self.enter(self.fade["target"])
            if f >= 2 * FADE_STEPS:
                self.fade = None
        else:
            for m in self.monitors:
                m.update()
            for b in self.buttons:
                b.update()
                if self.fade is not None:      # tlačítko právě spustilo přechod
                    break

        if self.state in ("mass", "move", "speed"):
            pass  # velikost koulí se počítá z hmotnosti automaticky
        if self.state == "move":
            nobody = not any(b.movable for b in self.balls.values())
            self.text.costume, self.text.x, self.text.y = "nothing is moving", 0, -149
            self.text.visible = nobody
        if self.state == "sim" and self.fade is None:
            if space_pressed and self.any_running():
                self.stop_run()
            elif space_pressed:
                self.space_armed = True
            if space_released and self.space_armed:
                self.space_armed = False
                self.start_run()
            self.update_dragging()
        if self.state == "sim":
            self.physics_step()
            self.update_helper()
            self.shadows = [s for s in self.shadows if s[4] > self.frame]
        self.draw()

    def draw(self):
        scr = self.screen
        scr.fill((0, 0, 0))
        self.bg.draw(scr)
        for name, x, y, size, _ in self.shadows:
            s = self.shade_sprites[name]
            s.x, s.y, s.size, s.visible = x, y, size, True
            s.ghost = self.shadow_transparency
            s.draw(scr)
        for t in self.toggles.values():
            t.draw(scr)
        for n in BALL_LAYER_ORDER:
            self.balls[n].draw(scr)
        self.text.draw(scr)
        self.helper.draw(scr)
        for b in (self.chk_shadows, *self.chk_speed):
            b.draw(scr)
        if self.state == "settings1" and self.shadows_on:
            self.btn_plus.visible = self.btn_minus.visible = True
            self.mon_transparency.visible = self.mon_lifetime.visible = True
        elif self.state == "settings1":
            self.btn_plus.visible = self.btn_minus.visible = False
            self.mon_transparency.visible = self.mon_lifetime.visible = False
        self.btn_plus.draw(scr)
        self.btn_minus.draw(scr)
        for m in self.monitors:
            m.draw(scr)
        for b in (self.btn_start, self.btn_next, self.btn_back, self.btn_skip, self.btn_reset,
                  self.btn_settings, self.btn_reset_settings):
            b.draw(scr)
        if self.fade is not None:
            f = self.fade["frame"]
            ghost = 100 - 4 * f if f <= FADE_STEPS else 4 * (f - FADE_STEPS)
            self.overlay.ghost = max(0, min(100, ghost))
            self.overlay.draw(scr)

    def run(self):
        while not self.quit:
            self.step(pygame.event.get())
            pygame.display.flip()
            self.clock.tick(FPS)


def main():
    pygame.init()
    Game().run()
    pygame.quit()


if __name__ == "__main__":
    sys.exit(main())

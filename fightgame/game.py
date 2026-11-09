"""App loop and scenes: title, character select, fight."""
import random

import pygame

from .ai import CPUController, LEVELS
from .characters import CHARACTERS
from .config import WIDTH, HEIGHT, FPS, GROUND_Y, STAGE_LEFT, STAGE_RIGHT, ROUND_TIME, \
    ROUNDS_TO_WIN, MAX_HEALTH
from .fighter import Fighter, Input, NO_INPUT, PUSH_W
from .moves import PROJECTILE_HIT
from .sprites import FighterSprites, ensure_assets, asset, load_blast, load_stage

WHITE = (245, 245, 250)
GOLD = (255, 214, 90)
DIM = (150, 150, 170)

MOVE_KEYS = {
    "left": (pygame.K_LEFT, pygame.K_a),
    "right": (pygame.K_RIGHT, pygame.K_d),
    "up": (pygame.K_UP, pygame.K_w),
    "down": (pygame.K_DOWN, pygame.K_s),
}
ATTACK_KEYS = {
    pygame.K_j: "lp", pygame.K_z: "lp",
    pygame.K_k: "hp", pygame.K_x: "hp",
    pygame.K_l: "kick", pygame.K_c: "kick",
}
CONFIRM = (pygame.K_RETURN, pygame.K_SPACE, pygame.K_j, pygame.K_z)


class KeyboardController:
    """Reads the keyboard. Button presses are buffered for a few frames so
    inputs pressed slightly early (or during hit-stop) still come out."""
    BUFFER = 4

    def __init__(self):
        self.buffer = {}

    def reset(self):
        self.buffer.clear()

    def feed(self, events):
        for e in events:
            if e.type == pygame.KEYDOWN and e.key in ATTACK_KEYS:
                self.buffer[ATTACK_KEYS[e.key]] = self.BUFFER

    def get_input(self, me, opp, scene):
        keys = pygame.key.get_pressed()
        held = {k: any(keys[c] for c in codes) for k, codes in MOVE_KEYS.items()}
        pressed = set(self.buffer)
        self.buffer = {b: n - 1 for b, n in self.buffer.items() if n > 1}
        return Input(held["left"], held["right"], held["up"], held["down"], pressed)


# ---------------------------------------------------------------------------
class Scene:
    def __init__(self, app):
        self.app = app

    def handle(self, events):
        pass

    def update(self):
        pass

    def draw(self, screen):
        pass


def text(screen, font, msg, pos, color=WHITE, center=True, shadow=True):
    img = font.render(msg, True, color)
    r = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    if shadow:
        screen.blit(font.render(msg, True, (20, 16, 30)), r.move(3, 3))
    screen.blit(img, r)
    return r


class TitleScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0

    def handle(self, events):
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.app.running = False
                elif e.key in CONFIRM:
                    self.app.scene = SelectScene(self.app)

    def update(self):
        self.t += 1

    def draw(self, screen):
        a = self.app
        screen.blit(a.stage, (0, 0))
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((10, 6, 24, 140))
        screen.blit(shade, (0, 0))
        text(screen, a.font_huge, "PIXEL BRAWL", (WIDTH // 2, 150), GOLD)
        text(screen, a.font_small, "a tiny 2D fighting game", (WIDTH // 2, 215), DIM)
        if (self.t // 30) % 2 == 0:
            text(screen, a.font_big, "PRESS ENTER", (WIDTH // 2, 300))
        lines = ["Move: Arrow keys / WASD     Jump: Up     Block: hold Back",
                 "Light punch: J / Z     Heavy punch: K / X     Kick: L / C",
                 "Sweep: Down + Kick     Blast: Down, Down-Forward, Forward + Punch",
                 "Enter: pause     F1: show hitboxes     F11: fullscreen     Esc: back"]
        for i, ln in enumerate(lines):
            text(screen, a.font_small, ln, (WIDTH // 2, 380 + i * 30), WHITE)


class SelectScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.choice = 0
        self.levels = list(LEVELS)
        self.level = self.levels.index(app.level)
        self.t = 0

    def handle(self, events):
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_ESCAPE:
                self.app.scene = TitleScene(self.app)
            elif e.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                self.choice = 1 - self.choice
            elif e.key in (pygame.K_UP, pygame.K_w):
                self.level = (self.level - 1) % len(self.levels)
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self.level = (self.level + 1) % len(self.levels)
            elif e.key in CONFIRM:
                self.app.level = self.levels[self.level]
                p1 = CHARACTERS[self.choice]
                p2 = CHARACTERS[1 - self.choice]
                self.app.scene = FightScene(self.app, p1, p2, self.app.level)

    def update(self):
        self.t += 1

    def draw(self, screen):
        a = self.app
        screen.blit(a.stage, (0, 0))
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((10, 6, 24, 160))
        screen.blit(shade, (0, 0))
        text(screen, a.font_big, "CHOOSE YOUR FIGHTER", (WIDTH // 2, 60), GOLD)
        for i, ch in enumerate(CHARACTERS):
            cx = WIDTH // 2 + (-200 if i == 0 else 200)
            sel = i == self.choice
            box = pygame.Rect(0, 0, 230, 270)
            box.center = (cx, 250)
            pygame.draw.rect(screen, (40, 30, 70), box, border_radius=8)
            pygame.draw.rect(screen, GOLD if sel else (90, 80, 120), box, 4, border_radius=8)
            anim = "idle" if sel else "idle"
            img = a.sprites[ch.key].get(anim, (self.t // 9) % 4 if sel else 0, 1 if i == 0 else -1)
            screen.blit(img, img.get_rect(midbottom=(cx, box.bottom - 10)))
            text(screen, a.font_big, ch.name, (cx, box.bottom + 30), GOLD if sel else WHITE)
            text(screen, a.font_small, ch.blurb, (cx, box.bottom + 62), DIM)
        text(screen, a.font_med, f"CPU:  < {self.levels[self.level]} >   (Up/Down)",
             (WIDTH // 2, 490))
        text(screen, a.font_small, "Left/Right to choose, Enter to fight", (WIDTH // 2, 522), DIM)


# ---------------------------------------------------------------------------
class Spark:
    def __init__(self, x, y, blocked):
        self.x, self.y, self.t = x, y, 0
        self.blocked = blocked
        self.rays = [(random.uniform(0, 6.283), random.uniform(10, 28)) for _ in range(7)]

    def draw(self, surf, ox, oy):
        import math
        k = self.t / 12
        col = (150, 210, 255) if self.blocked else (255, 236, 140)
        for ang, ln in self.rays:
            r1, r2 = ln * k * 0.5, ln * (0.4 + k)
            a = (self.x + math.cos(ang) * r1 + ox, self.y + math.sin(ang) * r1 + oy)
            b = (self.x + math.cos(ang) * r2 + ox, self.y + math.sin(ang) * r2 + oy)
            pygame.draw.line(surf, col, a, b, 3)
        pygame.draw.circle(surf, WHITE, (self.x + ox, self.y + oy), max(1, int(10 * (1 - k))))


class FightScene(Scene):
    def __init__(self, app, p1_char, p2_char, level, p1_cpu=False, seed=None):
        super().__init__(app)
        self.f1 = Fighter(p1_char, app.sprites[p1_char.key], app.blasts[p1_char.key])
        self.f2 = Fighter(p2_char, app.sprites[p2_char.key], app.blasts[p2_char.key])
        rng = random.Random(seed)
        self.c1 = CPUController(level, rng) if p1_cpu else KeyboardController()
        self.c2 = CPUController(level, rng)
        self.wins = [0, 0]
        self.round = 0
        self.paused = False
        self.show_boxes = False
        self.start_round()

    # ------------------------------------------------------------ rounds ----
    def start_round(self):
        self.round += 1
        self.f1.reset(WIDTH // 2 - 170, 1)
        self.f2.reset(WIDTH // 2 + 170, -1)
        self.c1.reset()
        self.c2.reset()
        self.projectiles = []
        self.sparks = []
        self.phase = "intro"
        self.phase_t = 0
        self.time_left = ROUND_TIME
        self.clock = 0
        self.hitstop = 0
        self.shake = 0
        self.combo_msg = None
        self.banner = None
        self.round_winner = None

    def handle(self, events):
        if isinstance(self.c1, KeyboardController):
            self.c1.feed(events)
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_F1:
                self.show_boxes = not self.show_boxes
            elif e.key == pygame.K_ESCAPE:
                self.app.scene = SelectScene(self.app)
            elif self.phase == "match_over" and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.app.scene = FightScene(self.app, self.f1.char, self.f2.char, self.app.level)
            elif e.key in (pygame.K_RETURN, pygame.K_p) and self.phase == "fight":
                self.paused = not self.paused

    # ------------------------------------------------------------ update ----
    def update(self):
        if self.paused:
            return
        self.phase_t += 1
        for f in (self.f1, self.f2):
            f.shown_health += (f.health - f.shown_health) * 0.06 if self.hitstop == 0 else 0
        if self.shake:
            self.shake -= 1
        if self.combo_msg:
            self.combo_msg[2] -= 1
            if self.combo_msg[2] <= 0:
                self.combo_msg = None

        if self.hitstop > 0:
            self.hitstop -= 1
            return

        ph = self.phase
        if ph == "intro":
            self.banner = f"ROUND {self.round}" if self.phase_t < 70 else "FIGHT!"
            self._step(NO_INPUT, NO_INPUT)
            if self.phase_t >= 100:
                self.phase, self.phase_t, self.banner = "fight", 0, None
        elif ph == "fight":
            i1 = self.c1.get_input(self.f1, self.f2, self)
            i2 = self.c2.get_input(self.f2, self.f1, self)
            self._step(i1, i2)
            self.clock += 1
            if self.clock % FPS == 0 and self.time_left > 0:
                self.time_left -= 1
            if self.f1.health <= 0 or self.f2.health <= 0:
                self._end_round("K.O.")
            elif self.time_left == 0:
                self._end_round("TIME")
        elif ph == "ko":
            # slow motion for the first moments of a KO
            if self.phase_t > 40 or self.phase_t % 3 == 0:
                self._step(NO_INPUT, NO_INPUT)
            if self.phase_t == 120 and self.round_winner is not None:
                w = (self.f1, self.f2)[self.round_winner]
                if w.state not in ("ko", "down", "knockdown"):
                    w.set_state("win")
                    w.vx = 0
            if self.phase_t >= 230:
                if max(self.wins) >= ROUNDS_TO_WIN:
                    self.phase, self.phase_t = "match_over", 0
                else:
                    self.start_round()
        elif ph == "match_over":
            self._step(NO_INPUT, NO_INPUT)

    def _end_round(self, why):
        self.phase, self.phase_t, self.banner = "ko", 0, why
        h1, h2 = self.f1.health, self.f2.health
        if h1 == h2:
            self.round_winner = None
            self.banner = "DOUBLE K.O." if h1 == 0 else "DRAW"
        else:
            self.round_winner = 0 if h1 > h2 else 1
            self.wins[self.round_winner] += 1

    def _step(self, i1, i2):
        f1, f2 = self.f1, self.f2
        f1.update(i1, f2, self)
        f2.update(i2, f1, self)
        self._push_apart()
        for p in self.projectiles:
            p.update()
        self._resolve_hits()
        self.projectiles = [p for p in self.projectiles if p.alive]
        for f in (f1, f2):
            if f.projectile is not None and not f.projectile.alive:
                f.projectile = None
        for s in self.sparks:
            s.t += 1
        self.sparks = [s for s in self.sparks if s.t < 12]

    def _push_apart(self):
        a, b = self.f1, self.f2
        if a.state in ("down", "ko") or b.state in ("down", "ko"):
            return
        dx = b.x - a.x
        if abs(dx) < PUSH_W and abs(a.y - b.y) < 140:
            overlap = (PUSH_W - abs(dx)) / 2
            s = 1 if dx >= 0 else -1
            if dx == 0:
                s = a.facing
            a.x -= s * overlap
            b.x += s * overlap
            for f, o in ((a, b), (b, a)):
                if f.x < STAGE_LEFT:
                    o.x += STAGE_LEFT - f.x
                    f.x = STAGE_LEFT
                if f.x > STAGE_RIGHT:
                    o.x -= f.x - STAGE_RIGHT
                    f.x = STAGE_RIGHT

    def _resolve_hits(self):
        hits = []
        for att, dfn in ((self.f1, self.f2), (self.f2, self.f1)):
            hb, hurt = att.hitbox(), dfn.hurtbox()
            if hb and hurt and hb.colliderect(hurt):
                hits.append((att, dfn, att.move, hb.clip(hurt)))
        for att, dfn, move, clip in hits:   # resolved together so trades are possible
            att.hit_this_move = True
            att.connected = True
            result = dfn.receive(move, att.x, att.char.damage_mult)
            self._on_contact(att, dfn, move, result, clip.center)
            at_wall = dfn.x <= STAGE_LEFT + 4 or dfn.x >= STAGE_RIGHT - 4
            if at_wall and dfn.on_ground and att.on_ground:
                att.vx = -att.facing * move.pushback * 0.8

        ps = self.projectiles
        for i, p in enumerate(ps):
            for q in ps[i + 1:]:
                if p.alive and q.alive and p.owner is not q.owner and p.rect().colliderect(q.rect()):
                    p.alive = q.alive = False
                    self.sparks.append(Spark((p.x + q.x) / 2, p.y, True))
        for p in ps:
            if not p.alive:
                continue
            dfn = self.f2 if p.owner is self.f1 else self.f1
            hurt = dfn.hurtbox()
            if hurt and p.rect().colliderect(hurt):
                p.alive = False
                result = dfn.receive(PROJECTILE_HIT, p.x - p.vx * 10, p.owner.char.damage_mult)
                self._on_contact(p.owner, dfn, PROJECTILE_HIT, result, (p.x, p.y))

    def _on_contact(self, att, dfn, move, result, pos):
        self.sparks.append(Spark(pos[0], pos[1], result == "block"))
        if result == "hit":
            self.hitstop = 9 if move.damage >= 80 else 7
            self.shake = 8 if move.damage >= 80 else 4
            if dfn.combo >= 2:
                side = 0 if att is self.f1 else 1
                self.combo_msg = [side, f"{dfn.combo} HIT COMBO!", 70]
        else:
            self.hitstop = 5

    # -------------------------------------------------------------- draw ----
    def draw(self, screen):
        a = self.app
        ox = oy = 0
        if self.shake:
            ox, oy = random.randint(-4, 4), random.randint(-3, 3)
        screen.blit(a.stage, (ox, oy))
        for f in (self.f1, self.f2):
            w = max(30, 90 - int((GROUND_Y - f.y) * 0.2))
            sh = pygame.Surface((w, 14), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 90), sh.get_rect())
            screen.blit(sh, (f.x - w / 2 + ox, GROUND_Y - 7 + oy))
        order = sorted((self.f1, self.f2), key=lambda f: f.state == "attack")
        for f in order:
            f.draw(screen, ox, oy)
        for p in self.projectiles:
            p.draw(screen, ox, oy)
        for s in self.sparks:
            s.draw(screen, ox, oy)
        if self.show_boxes:
            self._draw_boxes(screen)
        self._draw_hud(screen)

    def _draw_boxes(self, screen):
        for f in (self.f1, self.f2):
            hurt, hit = f.hurtbox(), f.hitbox()
            if hurt:
                pygame.draw.rect(screen, (60, 140, 255), hurt, 2)
            if hit:
                pygame.draw.rect(screen, (255, 60, 60), hit, 2)
            pygame.draw.line(screen, (60, 255, 120), (f.x - PUSH_W / 2, f.y), (f.x + PUSH_W / 2, f.y), 3)
        for p in self.projectiles:
            pygame.draw.rect(screen, (255, 60, 60), p.rect(), 2)

    def _draw_hud(self, screen):
        a = self.app
        bw, bh, top = 370, 26, 24
        for side, f in enumerate((self.f1, self.f2)):
            x = 30 if side == 0 else WIDTH - 30 - bw
            pygame.draw.rect(screen, (20, 16, 30), (x - 3, top - 3, bw + 6, bh + 6), border_radius=4)
            pygame.draw.rect(screen, (70, 20, 30), (x, top, bw, bh))
            for val, col in ((f.shown_health, (230, 60, 50)), (f.health, (250, 210, 70))):
                w = int(bw * max(0, val) / MAX_HEALTH)
                rx = x + bw - w if side == 0 else x
                pygame.draw.rect(screen, col, (rx, top, w, bh))
            name = f.char.name + ("  (YOU)" if side == 0 and not isinstance(self.c1, CPUController)
                                  else "  (CPU)")
            if side == 0:
                text(screen, a.font_small, name, (x, top + bh + 8), center=False)
            else:
                img = a.font_small.render(name, True, WHITE)
                text(screen, a.font_small, name, (x + bw - img.get_width(), top + bh + 8), center=False)
            for r in range(ROUNDS_TO_WIN):
                cx = (x + bw - 14 - r * 24) if side == 0 else (x + 14 + r * 24)
                col = GOLD if self.wins[side] > r else (60, 50, 80)
                pygame.draw.circle(screen, col, (cx, top + bh + 20), 8)
                pygame.draw.circle(screen, (20, 16, 30), (cx, top + bh + 20), 8, 2)
        pygame.draw.rect(screen, (20, 16, 30), (WIDTH // 2 - 40, 12, 80, 56), border_radius=6)
        text(screen, a.font_big, f"{self.time_left:02d}", (WIDTH // 2, 41),
             (255, 90, 80) if self.time_left <= 10 else WHITE)

        if self.combo_msg:
            side, msg, _ = self.combo_msg
            pos = (170, 130) if side == 0 else (WIDTH - 170, 130)
            text(screen, a.font_med, msg, pos, GOLD)
        if self.banner:
            text(screen, a.font_huge, self.banner, (WIDTH // 2, 210), GOLD)
        if self.phase == "match_over":
            won = self.wins[0] > self.wins[1]
            title = "YOU WIN!" if won else "YOU LOSE"
            if isinstance(self.c1, CPUController):
                title = f"{(self.f1 if won else self.f2).char.name} WINS"
            text(screen, a.font_huge, title, (WIDTH // 2, 190), GOLD)
            text(screen, a.font_med, "Enter: rematch     Esc: character select",
                 (WIDTH // 2, 270))
        if self.paused:
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 140))
            screen.blit(shade, (0, 0))
            text(screen, a.font_huge, "PAUSED", (WIDTH // 2, 230), GOLD)
            text(screen, a.font_med, "Enter: resume     Esc: quit match", (WIDTH // 2, 300))


# ---------------------------------------------------------------------------
class App:
    def __init__(self, demo=False):
        pygame.init()
        pygame.display.set_caption("Pixel Brawl")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        keys = [c.key for c in CHARACTERS]
        ensure_assets(keys)
        self.sprites = {k: FighterSprites(asset(f"{k}.png")) for k in keys}
        self.blasts = {k: load_blast(asset(f"{k}_blast.png")) for k in keys}
        self.stage = load_stage((WIDTH, HEIGHT))
        self.font_huge = pygame.font.Font(None, 96)
        self.font_big = pygame.font.Font(None, 56)
        self.font_med = pygame.font.Font(None, 38)
        self.font_small = pygame.font.Font(None, 26)
        self.level = "NORMAL"
        self.running = True
        if demo:
            self.scene = FightScene(self, CHARACTERS[0], CHARACTERS[1], self.level, p1_cpu=True)
        else:
            self.scene = TitleScene(self)

    def run(self):
        while self.running:
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
            self.scene.handle(events)
            self.scene.update()
            self.scene.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()

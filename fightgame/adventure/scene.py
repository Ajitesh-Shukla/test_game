"""Adventure mode: a side-scrolling platformer with fights along the way."""
import os
import random

import pygame

from ..characters import CHARACTERS
from ..config import WIDTH, HEIGHT
from ..game import Scene, KeyboardController, Spark, text, WHITE, GOLD, DIM, CONFIRM
from ..moves import PROJECTILE_HIT
from ..sprites import asset
from ..spritegen import TILE_INDEX
from .actors import Hero, Grunt, EnemyFighter, Pickup
from .level import Level, TILE

LEVEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "levels")
LEVEL_FILES = ["level1.txt", "level2.txt", "level3.txt"]
START_LIVES = 3
GEMS_PER_LIFE = 50


def load_art():
    """Tiles, enemy and goal art, scaled 2x."""
    sheet = pygame.image.load(asset("tiles.png")).convert_alpha()
    tiles = {}
    for name, i in TILE_INDEX.items():
        sub = sheet.subsurface(((i % 8) * 16, (i // 8) * 16, 16, 16))
        tiles[name] = pygame.transform.scale(sub, (TILE, TILE))
    g = pygame.image.load(asset("grunt.png")).convert_alpha()
    grunt = [pygame.transform.scale(g.subsurface((i * 16, 0, 16, 16)), (32, 32))
             for i in range(g.get_width() // 16)]
    goal = pygame.transform.scale_by(pygame.image.load(asset("goal.png")).convert_alpha(), 2)
    bg = pygame.transform.scale(pygame.image.load(asset("adventure_bg.png")).convert(), (WIDTH, HEIGHT))
    return tiles, grunt, goal, bg


class AdventureScene(Scene):
    def __init__(self, app, char):
        super().__init__(app)
        self.char = char
        self.rival = next(c for c in CHARACTERS if c.key != char.key)
        self.tiles, self.grunt_frames, self.goal_img, self.bg = load_art()
        self.ctrl = KeyboardController()
        self.lives = START_LIVES
        self.score = 0
        self.gems = 0
        self.level_index = 0
        self.checkpoint = None
        self.paused = False
        self.load_level()

    # ------------------------------------------------------------ levels ----
    def load_level(self):
        self.level = lv = Level(os.path.join(LEVEL_DIR, LEVEL_FILES[self.level_index]))
        self.static = self._render_static()
        a = self.app
        self.grunts, self.enemies, self.pickups, self.shots = [], [], [], []
        self.checkpoints, self.sparks, self.debris, self.popups = [], [], [], []
        self.goal = None
        start = (2, lv.rows - 3)
        for ch, cx, cy in lv.spawns:
            bx, by = cx * TILE + TILE / 2, (cy + 1) * TILE
            if ch == "P":
                start = (cx, cy)
            elif ch == "g":
                self.grunts.append(Grunt(bx, by, self.grunt_frames))
            elif ch == "f":
                self.enemies.append(EnemyFighter(bx, by, a.small_sprites["shade"], a.small_blasts["shade"]))
            elif ch == "K":
                self.enemies.append(EnemyFighter(bx, by, a.small_sprites[self.rival.key],
                                                 a.small_blasts[self.rival.key], boss=True,
                                                 name=self.rival.name))
            elif ch in "oH":
                self.pickups.append(Pickup("gem" if ch == "o" else "heart", bx, by - TILE / 2))
            elif ch == "C":
                self.checkpoints.append(dict(cx=cx, cy=cy, lit=(cx, cy) == self.checkpoint))
            elif ch == "E":
                self.goal = pygame.Rect(cx * TILE, (cy + 1) * TILE - 128, 96, 128)
        sx, sy = self.checkpoint or start
        self.hero = Hero(self.char, a.small_sprites[self.char.key], a.small_blasts[self.char.key],
                         sx * TILE + TILE / 2, (sy + 1) * TILE)
        self.cam_x = max(0, min(self.hero.x - WIDTH * 0.4, lv.width - WIDTH))
        self.cam_y = max(0, lv.height - HEIGHT)
        self.phase = "intro"
        self.phase_t = 0
        self.hitstop = 0
        self.ctrl.reset()

    def _render_static(self):
        lv = self.level
        surf = pygame.Surface((lv.width, lv.height), pygame.SRCALPHA)
        for cy in range(lv.rows):
            for cx in range(lv.cols):
                self._draw_tile(surf, cx, cy)
        return surf

    def _draw_tile(self, surf, cx, cy):
        lv, t = self.level, self.tiles
        ch = lv.grid[cy][cx]
        img = None
        if ch == "#":
            img = t["dirt"] if lv.at(cx, cy - 1) == "#" else t["grass"]
        elif ch == "S":
            img = t["stone"]
        elif ch == "X":
            img = t["crate"]
        elif ch == "=":
            img = t["plank"]
        elif ch == "^":
            img = t["spikes"]
        surf.fill((0, 0, 0, 0), (cx * TILE, cy * TILE, TILE, TILE))
        if img:
            surf.blit(img, (cx * TILE, cy * TILE))

    def break_crate(self, cx, cy):
        self.level.grid[cy][cx] = "."
        self._draw_tile(self.static, cx, cy)
        x, y = cx * TILE + TILE / 2, cy * TILE + TILE / 2
        self.pickups.append(Pickup("gem", x, y, pop=True))
        for _ in range(8):
            self.debris.append([x, y, random.uniform(-4, 4), random.uniform(-9, -3), 0])
        self.score += 20

    def bump_tile(self, cx, cy):
        """The hero hit a tile with their head."""
        if self.level.at(cx, cy) == "X":
            self.break_crate(cx, cy)

    # ------------------------------------------------------------ events ----
    def handle(self, events):
        self.ctrl.feed(events)
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_ESCAPE:
                from ..game import TitleScene
                self.app.scene = TitleScene(self.app)
            elif self.phase in ("gameover", "victory") and e.key in CONFIRM and self.phase_t > 60:
                from ..game import TitleScene
                self.app.scene = TitleScene(self.app)
            elif self.phase == "intro" and e.key in CONFIRM and self.phase_t > 20:
                self.phase, self.phase_t = "play", 0
            elif self.phase == "play" and e.key in (pygame.K_RETURN, pygame.K_p):
                self.paused = not self.paused

    # ------------------------------------------------------------ update ----
    def update(self):
        if self.paused:
            return
        self.phase_t += 1
        if self.phase == "intro":
            if self.phase_t > 150:
                self.phase, self.phase_t = "play", 0
            return
        if self.phase in ("gameover", "victory"):
            return
        if self.hitstop:
            self.hitstop -= 1
            return

        inp = self.ctrl.get_input(self.hero, None, self)
        hero, lv = self.hero, self.level
        hero.update(inp, self)
        for e in self.enemies:
            if abs(e.x - self.cam_x - WIDTH / 2) < WIDTH:
                e.update(self)
        for g in self.grunts:
            if not g.awake and abs(g.x - hero.x) < WIDTH * 0.75:
                g.awake = True
            if g.awake:
                g.update(lv)
        for s in self.shots:
            s.update(lv)
        for p in self.pickups:
            p.update(lv)
        if self.phase == "play":
            self._separate()
            self._interact(inp)
        self._cleanup()
        self._update_effects()
        self._update_camera()

        if self.phase == "play":
            if hero.state != "dead" and hero.y > lv.height + 40:
                hero.die()
                hero.vy = 0
            if hero.state == "dead":
                self.phase, self.phase_t = "dead", 0
        elif self.phase == "dead" and self.phase_t > 120:
            self.lives -= 1
            if self.lives < 0:
                self.phase, self.phase_t = "gameover", 0
            else:
                self.load_level()
        elif self.phase == "clear" and self.phase_t > 200:
            self.level_index += 1
            self.checkpoint = None
            if self.level_index >= len(LEVEL_FILES):
                self.phase, self.phase_t = "victory", 0
            else:
                self.load_level()

    def _separate(self):
        """Fighters are solid: the hero can't walk through them."""
        hero, lv = self.hero, self.level
        if hero.state in ("dead", "clear"):
            return
        for e in self.enemies:
            if e.hurtbox() is None or abs(hero.y - e.y) > 90:
                continue
            gap = (hero.w + e.w) / 2
            dx = hero.x - e.x
            if abs(dx) < gap:
                side = 1 if dx > 0 else -1
                if dx == 0:
                    side = -hero.facing
                new_x = e.x + side * gap
                if any(lv.solid(cx, cy) for cx, cy, _ in lv.tiles_in(
                        pygame.Rect(int(new_x - hero.w / 2), int(hero.y - hero.h), hero.w, hero.h - 1))):
                    e.x = hero.x - side * gap      # hero is against a wall: push the enemy instead
                else:
                    hero.x = new_x

    def _interact(self, inp):
        hero, lv = self.hero, self.level
        hurt = hero.hurtbox()

        # hero's punches and kicks
        hb = hero.hitbox()
        if hb:
            for g in self.grunts:
                if g.alive and hb.colliderect(g.rect):
                    g.kill()
                    hero.connected = True
                    self._reward(g.SCORE, g.x, g.y - 30)
                    self._spark(hb.clip(g.rect).center, False, stop=5)
            for e in self.enemies:
                eh = e.hurtbox()
                if id(e) not in hero.hit_ids and eh and hb.colliderect(eh):
                    hero.hit_ids.add(id(e))
                    hero.connected = True
                    res = e.receive(hero.move, hero.x, hero.char.damage_mult)
                    self._spark(hb.clip(eh).center, res == "block",
                                stop=9 if res == "hit" else 5)
                    if e.hp == 0:
                        self._reward(e.score, e.x, e.y - 130)
            for cx, cy, t in lv.tiles_in(hb):
                if t == "X":
                    self.break_crate(cx, cy)

        # enemy fighters' attacks
        for e in self.enemies:
            ehb = e.hitbox()
            if ehb and hurt and ehb.colliderect(hurt):
                e.hit_this_move = True
                dmg = 2 if (e.boss and e.move.name == "hp") else 1
                res = hero.take_hit(dmg, e.x)
                if res:
                    self._spark(ehb.clip(hurt).center, res == "block", stop=8 if res == "hit" else 4)

        # energy blasts
        for s in self.shots:
            if not s.alive:
                if getattr(s, "hit_tile", None):
                    pass
                continue
            if s.owner is hero:
                for g in self.grunts:
                    if g.alive and s.rect.colliderect(g.rect):
                        g.kill()
                        s.alive = False
                        self._reward(g.SCORE, g.x, g.y - 30)
                for e in self.enemies:
                    eh = e.hurtbox()
                    if s.alive and eh and s.rect.colliderect(eh):
                        s.alive = False
                        res = e.receive(PROJECTILE_HIT, s.x - s.vx * 10, hero.char.damage_mult)
                        self._spark((s.x, s.y - 14), res == "block", stop=7)
                        if e.hp == 0:
                            self._reward(e.score, e.x, e.y - 130)
                for cx, cy, t in lv.tiles_in(s.rect.inflate(8, 0)):
                    if t == "X" and s.alive:
                        self.break_crate(cx, cy)
                        s.alive = False
            elif hurt and s.rect.colliderect(hurt):
                s.alive = False
                res = hero.take_hit(1, s.x - s.vx * 10)
                self._spark((s.x, s.y - 14), res == "block", stop=6)
        for i, a in enumerate(self.shots):
            for b in self.shots[i + 1:]:
                if a.alive and b.alive and a.owner is not b.owner and a.rect.colliderect(b.rect):
                    a.alive = b.alive = False
                    self._spark(((a.x + b.x) / 2, a.y - 14), True)

        # grunts: stomp or get hurt
        hurt = hero.hurtbox()
        for g in self.grunts:
            if g.alive and hurt and hurt.colliderect(g.rect):
                if hero.vy > 0 and hero.y - hero.vy <= g.rect.top + 10:
                    g.kill()
                    hero.bounce(inp.up)
                    self._reward(g.SCORE, g.x, g.y - 30)
                else:
                    hero.take_hit(1, g.x, blockable=False)

        # spikes
        if hurt and not hero.invuln:
            feet = pygame.Rect(hurt.x + 4, hurt.bottom - 10, hurt.w - 8, 10)
            for cx, cy, t in lv.tiles_in(feet):
                if t == "^" and feet.colliderect((cx * TILE, cy * TILE + 14, TILE, TILE - 14)):
                    hero.take_hit(1, hero.x + hero.facing, blockable=False)
                    if hero.state != "dead":
                        hero.vy = -11
                    break

        # pickups
        for p in self.pickups:
            if not p.taken and hero.rect.colliderect(p.rect):
                p.taken = True
                if p.kind == "gem":
                    self.gems += 1
                    self.score += 10
                    if self.gems % GEMS_PER_LIFE == 0:
                        self.lives += 1
                        self.popups.append([p.x, p.y - 20, "1-UP!", 0])
                else:
                    hero.hp = min(hero.MAX_HP, hero.hp + 1)
                    self.score += 50

        # checkpoints
        for c in self.checkpoints:
            r = pygame.Rect(c["cx"] * TILE - 8, (c["cy"] - 2) * TILE, TILE + 16, 3 * TILE)
            if not c["lit"] and hero.rect.colliderect(r):
                c["lit"] = True
                self.checkpoint = (c["cx"], c["cy"])
                self.popups.append([r.centerx, r.top - 10, "CHECKPOINT", 0])

        # goal
        if self.goal and hero.rect.colliderect(self.goal.inflate(-50, 0)):
            if self.boss_alive():
                pass
            else:
                hero.state = "clear"
                hero.anim_tick = 0
                bonus = hero.hp * 200
                self.score += bonus
                self.popups.append([hero.x, hero.y - 150, f"HEART BONUS +{bonus}", -40])
                self.phase, self.phase_t = "clear", 0

    def boss_alive(self):
        return any(e.boss and e.hp > 0 for e in self.enemies)

    def _reward(self, points, x, y):
        self.score += points
        self.popups.append([x, y, str(points), 0])

    def _spark(self, pos, blocked, stop=0):
        self.sparks.append(Spark(pos[0], pos[1], blocked))
        self.hitstop = max(self.hitstop, stop)

    def _cleanup(self):
        self.grunts = [g for g in self.grunts if g.alive or g.dead_timer < 45]
        self.grunts = [g for g in self.grunts if g.y < self.level.height + 100]
        self.enemies = [e for e in self.enemies if not e.removed]
        self.shots = [s for s in self.shots if s.alive]
        for owner in [self.hero] + self.enemies:
            if owner.shot is not None and not owner.shot.alive:
                owner.shot = None
        self.pickups = [p for p in self.pickups if not p.taken and p.y < self.level.height + 50]

    def _update_effects(self):
        for s in self.sparks:
            s.t += 1
        self.sparks = [s for s in self.sparks if s.t < 12]
        for d in self.debris:
            d[0] += d[2]
            d[1] += d[3]
            d[3] += 0.6
            d[4] += 1
        self.debris = [d for d in self.debris if d[4] < 50]
        for p in self.popups:
            p[1] -= 0.8
            p[3] += 1
        self.popups = [p for p in self.popups if p[3] < 60]

    def _update_camera(self):
        lv, hero = self.level, self.hero
        if hero.state == "dead":
            return
        target = hero.x - WIDTH * 0.42 + hero.facing * 50
        self.cam_x += (target - self.cam_x) * 0.1
        self.cam_x = max(0, min(self.cam_x, lv.width - WIDTH))
        ty = max(0, min(hero.y - 420, lv.height - HEIGHT))
        self.cam_y += (ty - self.cam_y) * 0.1

    # -------------------------------------------------------------- draw ----
    def draw(self, screen):
        cam = (int(self.cam_x), int(self.cam_y))
        off = int(self.cam_x * 0.3) % WIDTH
        screen.blit(self.bg, (-off, 0))
        screen.blit(self.bg, (WIDTH - off, 0))
        # dark abyss below ground level so pits read as pits
        pit_top = (self.level.rows - 2) * TILE - cam[1]
        pygame.draw.rect(screen, (34, 26, 52), (0, pit_top, WIDTH, HEIGHT - pit_top))
        screen.blit(self.static, (0, 0), area=pygame.Rect(cam[0], cam[1], WIDTH, HEIGHT))

        for c in self.checkpoints:
            x, bottom = c["cx"] * TILE + TILE // 2 - cam[0], (c["cy"] + 1) * TILE - cam[1]
            pygame.draw.line(screen, (60, 40, 34), (x, bottom), (x, bottom - 70), 4)
            lamp = self.tiles["lantern_on" if c["lit"] else "lantern_off"]
            screen.blit(lamp, lamp.get_rect(midtop=(x, bottom - 76)))
        if self.goal:
            screen.blit(self.goal_img, (self.goal.x - cam[0], self.goal.y - cam[1]))
            if self.boss_alive():
                barrier = pygame.Surface((54, 104), pygame.SRCALPHA)
                barrier.fill((170, 80, 255, 90 + (self.phase_t // 4) % 2 * 30))
                screen.blit(barrier, (self.goal.x + 21 - cam[0], self.goal.y + 24 - cam[1]))

        for p in self.pickups:
            p.draw(screen, cam, self.tiles)
        for g in self.grunts:
            g.draw(screen, cam)
        for e in self.enemies:
            e.draw(screen, cam)
        self.hero.draw(screen, cam)
        for s in self.shots:
            s.draw(screen, cam)
        for s in self.sparks:
            s.draw(screen, -cam[0], -cam[1])
        for d in self.debris:
            pygame.draw.rect(screen, (150, 96, 50), (d[0] - cam[0], d[1] - cam[1], 6, 6))
        for x, y, msg, t in self.popups:
            if t >= 0:
                text(self.app.screen, self.app.font_small, msg, (x - cam[0], y - cam[1]), GOLD)
        self._draw_hud(screen)

    def _draw_hud(self, screen):
        a = self.app
        for i in range(self.hero.MAX_HP):
            img = self.tiles["heart" if i < self.hero.hp else "heart_empty"]
            screen.blit(img, (16 + i * 34, 12))
        text(screen, a.font_med, f"x{max(0, self.lives)}", (16, 50), WHITE, center=False)
        text(screen, a.font_small, "LIVES", (62, 58), WHITE, center=False)
        screen.blit(self.tiles["gem0"], (WIDTH // 2 - 60, 14))
        text(screen, a.font_med, f"{self.gems:03d}", (WIDTH // 2 - 22, 18), WHITE, center=False)
        sc = a.font_med.render(f"{self.score:07d}", True, WHITE)
        text(screen, a.font_med, f"{self.score:07d}", (WIDTH - 20 - sc.get_width(), 18), WHITE, center=False)

        boss = next((e for e in self.enemies if e.boss and e.aggro and e.state != "dead"), None)
        if boss:
            bw = 500
            x = WIDTH // 2 - bw // 2
            pygame.draw.rect(screen, (20, 16, 30), (x - 3, HEIGHT - 43, bw + 6, 26), border_radius=4)
            pygame.draw.rect(screen, (70, 20, 30), (x, HEIGHT - 40, bw, 20))
            pygame.draw.rect(screen, (230, 60, 50), (x, HEIGHT - 40, int(bw * boss.shown_hp / boss.max_hp), 20))
            pygame.draw.rect(screen, (250, 210, 70), (x, HEIGHT - 40, int(bw * boss.hp / boss.max_hp), 20))
            text(screen, a.font_small, f"RIVAL: {boss.name}", (WIDTH // 2, HEIGHT - 58), GOLD)

        shade = None
        if self.phase in ("intro", "gameover", "victory") or self.paused:
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((8, 6, 20, 210 if self.phase != "intro" or self.paused else 230))
            screen.blit(shade, (0, 0))
        if self.paused:
            text(screen, a.font_huge, "PAUSED", (WIDTH // 2, 230), GOLD)
            text(screen, a.font_med, "Enter: resume     Esc: quit to title", (WIDTH // 2, 300))
        elif self.phase == "intro":
            text(screen, a.font_med, f"LEVEL {self.level_index + 1}", (WIDTH // 2, 190), DIM)
            text(screen, a.font_huge, self.level.name.upper(), (WIDTH // 2, 250), GOLD)
            text(screen, a.font_med, f"{self.char.name}  x{self.lives}", (WIDTH // 2, 320))
            if self.level_index == len(LEVEL_FILES) - 1:
                text(screen, a.font_small, f"Your rival {self.rival.name} awaits at the end.",
                     (WIDTH // 2, 370), DIM)
        elif self.phase == "clear":
            text(screen, a.font_huge, "STAGE CLEAR!", (WIDTH // 2, 200), GOLD)
        elif self.phase == "gameover":
            text(screen, a.font_huge, "GAME OVER", (WIDTH // 2, 210), (255, 90, 80))
            text(screen, a.font_med, f"Score {self.score}", (WIDTH // 2, 280))
            text(screen, a.font_small, "Press Enter", (WIDTH // 2, 330), DIM)
        elif self.phase == "victory":
            text(screen, a.font_huge, "YOU WIN!", (WIDTH // 2, 190), GOLD)
            text(screen, a.font_med, f"{self.rival.name} has been defeated.", (WIDTH // 2, 260))
            text(screen, a.font_med, f"Final score {self.score}   Gems {self.gems}", (WIDTH // 2, 305))
            text(screen, a.font_small, "Press Enter", (WIDTH // 2, 360), DIM)
        elif self.phase == "play" and self.goal and self.boss_alive() \
                and abs(self.hero.x - self.goal.centerx) < 300:
            text(screen, a.font_med, "Defeat your rival to open the gate!", (WIDTH // 2, 110), GOLD)

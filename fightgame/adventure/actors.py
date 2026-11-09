"""Everything that moves in Adventure mode: the hero, enemies, shots, pickups."""
import random

import pygame

from ..config import FRAME_W, ANCHOR_X, FOOT_ROW
from ..moves import MOVES
from .level import Body, TILE

ASCALE = 2                  # fighters are drawn at 2x in Adventure mode
BOX_SCALE = ASCALE / 3      # moves.py hitboxes are authored for 3x

GRAVITY = 0.75
GRAVITY_CUT = 1.6           # extra gravity when the jump button is released early
MAX_FALL = 14
RUN_SPEED = 5.0
JUMP_SPEED = -15.5


def scaled_box(box):
    return tuple(int(v * BOX_SCALE) for v in box)


def facing_rect(x, y, facing, box):
    bx, by, bw, bh = box
    if facing == -1:
        bx = -bx - bw
    return pygame.Rect(int(x + bx), int(y + by), bw, bh)


def draw_fighter(surf, sprites, anim, idx, facing, x, y, cam):
    img = sprites.get(anim, idx, facing)
    anchor = ANCHOR_X if facing == 1 else FRAME_W - 1 - ANCHOR_X
    surf.blit(img, (x - (anchor + 0.5) * ASCALE - cam[0], y - FOOT_ROW * ASCALE - cam[1]))


def attack_frame(move, move_frame):
    if move.air:
        return ("jump_kick", 0) if move_frame >= move.startup else ("jump", 1)
    if move_frame < move.startup:
        return move.anim, 0
    if move_frame < move.startup + move.active:
        return move.anim, 1
    return move.anim, 2


# --------------------------------------------------------------------------
class Shot(Body):
    """An energy blast. Travels until it hits something or flies too far."""

    def __init__(self, owner, x, y, direction, speed, frames):
        super().__init__(x, y + 14, 36, 28)
        self.owner = owner
        self.vx = direction * speed
        self.frames = frames
        self.alive = True
        self.travel = 0
        self.tick = 0

    def update(self, level):
        self.x += self.vx
        self.travel += abs(self.vx)
        self.tick += 1
        r = self.rect
        if self.travel > 750 or any(level.solid(cx, cy) for cx, cy, _ in level.tiles_in(r)):
            self.alive = False

    def draw(self, surf, cam):
        img = self.frames[(self.tick // 4) % len(self.frames)]
        if self.vx < 0:
            img = pygame.transform.flip(img, True, False)
        surf.blit(img, img.get_rect(center=(self.x - cam[0], self.y - 14 - cam[1])))


# --------------------------------------------------------------------------
class Hero(Body):
    MAX_HP = 5

    def __init__(self, char, sprites, blast, x, y):
        super().__init__(x, y, 34, 104)
        self.char, self.sprites, self.blast = char, sprites, blast
        self.hp = self.MAX_HP
        self.facing = 1
        self.state = "normal"          # normal, attack, hurt, dead, clear
        self.timer = 0
        self.anim_tick = 0
        self.move = None
        self.move_frame = 0
        self.hit_ids = set()
        self.connected = False
        self.attack_id = 0
        self.crouching = False
        self.invuln = 0
        self.coyote = 0
        self.jump_buffer = 0
        self.prev_up = False
        self.air_attack_used = False
        self.history = []
        self.shot = None

    # ---------------------------------------------------------- input ----
    def _qcf_dir(self):
        """Quarter circle (down, down-forward, forward) toward either side.
        Returns +1 / -1 for the direction it was done in, or 0."""
        for direction, seq in ((1, (2, 3, 6)), (-1, (2, 1, 4))):
            step = 0
            for d in self.history[-18:]:
                if d == seq[step]:
                    step += 1
                    if step == 3:
                        return direction
        return 0

    def start_move(self, name):
        self.move = MOVES[name]
        self.move_frame = 0
        self.hit_ids = set()
        self.connected = False
        self.attack_id += 1
        self.state = "attack"

    def update(self, inp, scene):
        self.anim_tick += 1
        self.timer += 1
        if self.invuln:
            self.invuln -= 1
        x_in = (1 if inp.right else 0) - (1 if inp.left else 0)
        y_in = 1 if inp.up else (-1 if inp.down else 0)
        self.history.append(5 + x_in + 3 * y_in)    # absolute numpad direction
        del self.history[:-30]
        jump_pressed = inp.up and not self.prev_up
        self.prev_up = inp.up
        if jump_pressed:
            self.jump_buffer = 7
        elif self.jump_buffer:
            self.jump_buffer -= 1

        if self.state == "dead":
            self.vy = min(self.vy + GRAVITY, MAX_FALL)
            self.y += self.vy
            return
        if self.state == "clear":
            self.vx = 0
            self._physics(scene, holding_jump=True)
            return

        if self.state == "hurt":
            if self.timer > 22:
                self.state = "normal"
        elif self.state == "attack":
            self._attack(inp, scene)
        if self.state == "normal":
            self._normal(inp, x_in, scene)

        holding_jump = inp.up or self.state != "normal"
        self._physics(scene, holding_jump)

    def _normal(self, inp, x_in, scene):
        p = inp.pressed
        self.crouching = inp.down and self.on_ground
        if p:
            q = self._qcf_dir()
            if self.on_ground:
                if p & {"lp", "hp"} and q and self.shot is None:
                    self.facing = q
                    self.start_move("special")
                elif "kick" in p and inp.down:
                    self.start_move("sweep")
                elif "hp" in p:
                    self.start_move("hp")
                elif "lp" in p:
                    self.start_move("lp")
                elif "kick" in p:
                    self.start_move("kick")
            elif not self.air_attack_used:
                self.air_attack_used = True
                self.start_move("jump_kick")
            if self.state == "attack":
                self.crouching = False
                return

        if self.crouching:
            self.vx *= 0.7
        else:
            accel = 0.7 if self.on_ground else 0.45
            target = x_in * RUN_SPEED
            self.vx += max(-accel, min(accel, target - self.vx))
            if not x_in and self.on_ground:
                self.vx *= 0.75
        if x_in and not self.crouching:
            self.facing = x_in

        if self.jump_buffer and (self.on_ground or self.coyote):
            if inp.down and self.on_ground and scene.level.at(
                    int(self.x // TILE), int(self.y // TILE)) == "=":
                self.drop_through = 12                 # Down + Jump: drop through a plank
                self.y += 2
            else:
                self.vy = JUMP_SPEED
                self.crouching = False
            self.jump_buffer = 0
            self.coyote = 0

    def _attack(self, inp, scene):
        m = self.move
        self.move_frame += 1
        if self.on_ground and not m.air:
            self.vx *= 0.75
        if m.projectile and self.move_frame == m.startup:
            self.shot = Shot(self, self.x + self.facing * 48, self.y - 80, self.facing,
                             self.char.projectile_speed + 1, self.blast)
            scene.shots.append(self.shot)
        q = self._qcf_dir()
        if self.connected and m.cancelable and inp.pressed & {"lp", "hp"} and q and self.shot is None:
            self.facing = q
            self.start_move("special")
            return
        if not m.air and self.move_frame >= m.total:
            self.move = None
            self.state = "normal"

    def _physics(self, scene, holding_jump):
        g = GRAVITY if (holding_jump or self.vy > 0) else GRAVITY_CUT
        self.vy = min(self.vy + g, MAX_FALL)
        self.h = 70 if self.crouching else 104
        self.move_body(scene)

    def move_body(self, scene):
        bumped = self.step(scene.level)
        if bumped:
            scene.bump_tile(*bumped)
        if self.on_ground:
            self.coyote = 6
            self.air_attack_used = False
            if self.state == "attack" and self.move.air:
                self.move = None
                self.state = "normal"
        elif self.coyote:
            self.coyote -= 1

    # ------------------------------------------------------- combat ----
    def hurtbox(self):
        if self.state in ("dead", "clear"):
            return None
        return self.rect

    def hitbox(self):
        m = self.move
        if self.state != "attack" or not m.hitbox:
            return None
        if m.startup <= self.move_frame < m.startup + m.active:
            return facing_rect(self.x, self.y, self.facing, scaled_box(m.hitbox))
        return None

    def take_hit(self, damage, from_x, blockable=True):
        """Returns 'hit', 'block' or None (ignored)."""
        if self.invuln or self.state in ("dead", "clear"):
            return None
        toward = 1 if from_x > self.x else -1
        if blockable and self.crouching and self.on_ground and self.facing == toward:
            self.vx = -toward * 4
            return "block"
        self.hp = max(0, self.hp - damage)
        self.move = None
        self.crouching = False
        self.state = "hurt"
        self.timer = 0
        self.vx = -toward * 5
        self.vy = -6
        self.invuln = 75
        if self.hp == 0:
            self.die()
        return "hit"

    def die(self):
        self.state = "dead"
        self.vx = 0
        self.vy = -12
        self.timer = 0
        self.invuln = 0

    def bounce(self, holding_jump):
        self.vy = -13 if holding_jump else -9
        self.air_attack_used = False

    # -------------------------------------------------------- drawing ----
    def frame(self):
        st, t = self.state, self.anim_tick
        if st == "dead":
            return "knockdown", 0
        if st == "clear":
            return "win", (t // 20) % 2
        if st == "hurt":
            return "hit", 0 if self.timer < 8 else 1
        if st == "attack":
            return attack_frame(self.move, self.move_frame)
        if not self.on_ground:
            return "jump", 0 if self.vy < -5 else 1
        if self.crouching:
            return "crouch", 0
        if abs(self.vx) > 0.6:
            return "walk", (t // 6) % 4
        return "idle", (t // 9) % 4

    def draw(self, surf, cam):
        if self.invuln and (self.anim_tick // 3) % 2 and self.state != "dead":
            return
        anim, idx = self.frame()
        draw_fighter(surf, self.sprites, anim, idx, self.facing, self.x, self.y, cam)


# --------------------------------------------------------------------------
class Grunt(Body):
    """Small walking blob. Stomp it, punch it, or avoid it."""
    SCORE = 100

    def __init__(self, x, y, frames):
        super().__init__(x, y, 28, 28)
        self.frames = frames
        self.vx = -1.1
        self.alive = True
        self.dead_timer = 0
        self.tick = random.randint(0, 20)
        self.awake = False

    def update(self, level):
        self.tick += 1
        if not self.alive:
            self.dead_timer += 1
            return
        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        direction = 1 if self.vx > 0 else -1
        if self.on_ground and not self.ground_ahead(level, direction):
            self.vx = -self.vx
        speed = self.vx
        self.step(level)
        if self.hit_wall:
            self.vx = -speed

    def kill(self):
        self.alive = False
        self.vx = 0

    def draw(self, surf, cam):
        if not self.alive:
            if self.dead_timer > 30 and (self.dead_timer // 3) % 2:
                return
            img = self.frames[2]
        else:
            img = self.frames[(self.tick // 10) % 2]
        if self.vx > 0:
            img = pygame.transform.flip(img, True, False)
        surf.blit(img, img.get_rect(midbottom=(self.x - cam[0], self.y - cam[1] + 2)))


# --------------------------------------------------------------------------
class EnemyFighter(Body):
    """A martial artist enemy (or the boss). Walks up, blocks, attacks."""

    def __init__(self, x, y, sprites, blast, boss=False, name="SHADE"):
        super().__init__(x, y, 34, 104)
        self.sprites, self.blast = sprites, blast
        self.boss = boss
        self.name = name
        self.max_hp = 900 if boss else 220
        self.hp = self.max_hp
        self.shown_hp = float(self.max_hp)
        self.score = 5000 if boss else 500
        self.facing = -1
        self.state = "idle"
        self.timer = 0
        self.anim_tick = 0
        self.move = None
        self.move_frame = 0
        self.hit_this_move = False
        self.stun = 0
        self.cooldown = 30
        self.aggro = False
        self.seen_attack = None
        self.shot = None
        self.walk_speed = 2.6 if boss else 2.0
        self.block_chance = 0.45 if boss else 0.25
        self.removed = False

    def set_state(self, s):
        self.state = s
        self.timer = 0

    def start_move(self, name):
        self.move = MOVES[name]
        self.move_frame = 0
        self.hit_this_move = False
        self.set_state("attack")

    def update(self, scene):
        hero, level = scene.hero, scene.level
        self.timer += 1
        self.anim_tick += 1
        self.shown_hp += (self.hp - self.shown_hp) * 0.08
        dx = hero.x - self.x
        dist = abs(dx)
        st = self.state

        if st in ("idle", "walk"):
            if not self.aggro and dist < 560 and abs(hero.y - self.y) < 220:
                self.aggro = True
            if self.aggro and hero.state not in ("dead", "clear"):
                self._think(scene, hero, dx, dist, level)
            else:
                self.vx = 0
        elif st == "block":
            self.vx = 0
            if self.timer > self.stun:
                self.set_state("idle")
        elif st == "attack":
            self.vx *= 0.8
            self.move_frame += 1
            m = self.move
            if m.projectile and self.move_frame == m.startup:
                self.shot = Shot(self, self.x + self.facing * 48, self.y - 80, self.facing, 6.0, self.blast)
                scene.shots.append(self.shot)
            if self.move_frame >= m.total:
                self.move = None
                self.set_state("idle")
        elif st == "hitstun":
            self.vx *= 0.85
            if self.timer > self.stun:
                self.set_state("idle")
        elif st == "down":
            self.vx = 0
            if self.timer > 45:
                self.set_state("getup")
        elif st == "getup":
            if self.timer > 20:
                self.set_state("idle")
        elif st == "dead":
            self.vx = 0
            if self.timer > 90:
                self.removed = True

        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        self.step(level)
        if self.on_ground and self.state == "knockdown":
            self.set_state("dead" if self.hp <= 0 else "down")
        if self.y > level.height + 200:
            self.hp = 0
            self.removed = True

    def _think(self, scene, hero, dx, dist, level):
        self.facing = 1 if dx > 0 else -1
        # react to the hero's attacks
        if hero.state == "attack" and hero.attack_id != self.seen_attack and dist < 170:
            self.seen_attack = hero.attack_id
            if random.random() < self.block_chance:
                self.set_state("block")
                self.stun = hero.move.total + 4
                return
        if self.cooldown > 0:
            self.cooldown -= 1
        reach = 58          # matches the reach of the punch/kick hitboxes at 2x
        same_level = abs(hero.y - self.y) < 40
        if not same_level and dist < 120:
            # hero is on a ledge above/below: wait for them instead of punching air
            self.vx = 0
            if self.state != "idle":
                self.set_state("idle")
            return
        if dist > reach:
            if (self.boss and self.shot is None and dist > 240 and self.cooldown == 0
                    and random.random() < 0.03):
                self.start_move("special")
                self.cooldown = 50
                return
            if self.ground_ahead(level, self.facing) and abs(hero.y - self.y) < 160:
                self.vx = self.walk_speed * self.facing
                if self.state != "walk":
                    self.set_state("walk")
            else:
                self.vx = 0
                if self.state != "idle":
                    self.set_state("idle")
        else:
            self.vx = 0
            if self.state != "idle":
                self.set_state("idle")
            if self.cooldown == 0:
                self.start_move(random.choice(["lp", "lp", "hp", "kick"]))
                lo, hi = (22, 50) if self.boss else (40, 80)
                self.cooldown = random.randint(lo, hi)

    # ------------------------------------------------------- combat ----
    @property
    def alive(self):
        return self.state not in ("dead",) and self.hp > 0

    def hurtbox(self):
        if self.state in ("knockdown", "down", "getup", "dead"):
            return None
        return self.rect

    def hitbox(self):
        m = self.move
        if self.state != "attack" or not m.hitbox or self.hit_this_move:
            return None
        if m.startup <= self.move_frame < m.startup + m.active:
            return facing_rect(self.x, self.y, self.facing, scaled_box(m.hitbox))
        return None

    def receive(self, move, from_x, damage_mult):
        toward = 1 if from_x > self.x else -1
        self.aggro = True
        if self.state == "block" and self.facing == toward and move.hit_type != "low":
            self.vx = -toward * 3
            return "block"
        self.hp = max(0, self.hp - int(move.damage * damage_mult))
        self.move = None
        if self.hp == 0 or move.knockdown:
            self.set_state("knockdown")
            self.vy = -8
            self.vx = -toward * 3
            self.y -= 1
        else:
            self.set_state("hitstun")
            self.stun = move.hitstun
            self.vx = -toward * move.pushback * 0.6
        return "hit"

    # -------------------------------------------------------- drawing ----
    def frame(self):
        st, t = self.state, self.anim_tick
        if st == "attack":
            return attack_frame(self.move, self.move_frame)
        if st == "walk":
            return "walk", (t // 7) % 4
        if st == "block":
            return "block", 0
        if st == "hitstun":
            return "hit", 0 if self.timer < 6 else 1
        if st == "knockdown":
            return "knockdown", 0
        if st in ("down", "dead"):
            return "knockdown", 1
        if st == "getup":
            return "crouch", 0
        return "idle", (t // 9) % 4

    def draw(self, surf, cam):
        if self.state == "dead" and self.timer > 40 and (self.timer // 3) % 2:
            return
        anim, idx = self.frame()
        draw_fighter(surf, self.sprites, anim, idx, self.facing, self.x, self.y, cam)


# --------------------------------------------------------------------------
class Pickup:
    def __init__(self, kind, x, y, pop=False):
        self.kind = kind             # "gem" or "heart"
        self.x, self.y = x, y        # centre
        self.vy = -9 if pop else 0
        self.base_y = y
        self.pop = pop
        self.taken = False
        self.tick = random.randint(0, 30)

    @property
    def rect(self):
        return pygame.Rect(int(self.x - 12), int(self.y - 12), 24, 24)

    def update(self, level):
        self.tick += 1
        if self.pop:
            self.vy += GRAVITY
            self.y += self.vy
            below = int((self.y + 12) // TILE)
            if self.vy > 0 and level.standable(int(self.x // TILE), below):
                self.y = below * TILE - 14
                self.pop = False
                self.base_y = self.y

    def draw(self, surf, cam, tiles):
        if self.kind == "gem":
            img = tiles["gem1" if (self.tick // 12) % 4 == 0 else "gem0"]
        else:
            img = tiles["heart"]
        bob = 0 if self.pop else ((self.tick // 10) % 2) * 2
        surf.blit(img, img.get_rect(center=(self.x - cam[0], self.y - cam[1] - bob)))

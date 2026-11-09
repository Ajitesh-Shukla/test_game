"""Fighter state machine, physics, hit/hurt boxes and projectiles."""
import pygame

from .config import (FRAME_W, FRAME_H, ANCHOR_X, FOOT_ROW, SCALE, GROUND_Y,
                     STAGE_LEFT, STAGE_RIGHT, GRAVITY, MAX_HEALTH, WIDTH)
from .moves import MOVES, PROJECTILE_HIT

# Hurtboxes (x, y, w, h) relative to the feet, facing right.
STAND_HURT = (-27, -165, 54, 165)
CROUCH_HURT = (-30, -108, 60, 108)
AIR_HURT = (-27, -160, 54, 130)
PUSH_W = 46

NEUTRAL_STATES = ("idle", "walk", "crouch")


class Input:
    """One frame of controller input. `pressed` holds 'lp', 'hp', 'kick'."""
    __slots__ = ("left", "right", "up", "down", "pressed")

    def __init__(self, left=False, right=False, up=False, down=False, pressed=()):
        self.left, self.right, self.up, self.down = left, right, up, down
        self.pressed = set(pressed)


NO_INPUT = Input()


class Projectile:
    def __init__(self, owner, x, y, vx, sheet):
        self.owner, self.x, self.y, self.vx = owner, x, y, vx
        self.sheet = sheet
        self.alive = True
        self.tick = 0

    def rect(self):
        return pygame.Rect(int(self.x - 22), int(self.y - 16), 44, 32)

    def update(self):
        self.x += self.vx
        self.tick += 1
        if self.x < -60 or self.x > WIDTH + 60:
            self.alive = False

    def draw(self, surf, ox=0, oy=0):
        img = self.sheet[(self.tick // 4) % len(self.sheet)]
        if self.vx < 0:
            img = pygame.transform.flip(img, True, False)
        surf.blit(img, (self.x - img.get_width() / 2 + ox, self.y - img.get_height() / 2 + oy))


class Fighter:
    def __init__(self, char, sprites, blast_frames):
        self.char = char
        self.sprites = sprites
        self.blast_frames = blast_frames
        self.reset(200, 1)

    # ------------------------------------------------------------ setup ----
    def reset(self, x, facing):
        self.x, self.y = float(x), float(GROUND_Y)
        self.vx = self.vy = 0.0
        self.facing = facing
        self.health = MAX_HEALTH
        self.shown_health = float(MAX_HEALTH)   # lags behind for the red drain bar
        self.state = "idle"
        self.timer = 0
        self.anim_tick = 0
        self.move = None
        self.move_frame = 0
        self.hit_this_move = False
        self.connected = False
        self.stun = self.stun_total = 0
        self.block_low = False
        self.combo = 0
        self.history = []
        self.invuln = 0
        self.holding_back = self.holding_down = False
        self.projectile = None
        self.walk_dir = 0
        self.attack_id = 0

    # ---------------------------------------------------------- helpers ----
    @property
    def on_ground(self):
        return self.y >= GROUND_Y and self.vy >= 0

    def set_state(self, state):
        self.state = state
        self.timer = 0

    def dir_num(self, inp):
        """Numpad notation relative to facing: 6 = forward, 4 = back, 2 = down..."""
        x = (1 if inp.right else 0) - (1 if inp.left else 0)
        fwd = x * self.facing
        y = 1 if inp.up else (-1 if inp.down else 0)
        return 5 + fwd + 3 * y

    def face(self, opp):
        if abs(opp.x - self.x) > 2:
            self.facing = 1 if opp.x > self.x else -1

    def qcf(self):
        """Quarter-circle forward (down, down-forward, forward) in recent input."""
        seq, step = (2, 3, 6), 0
        for d in self.history[-18:]:
            if d == seq[step]:
                step += 1
                if step == 3:
                    return True
        return False

    def is_crouching(self):
        if self.state == "crouch":
            return True
        if self.state == "blockstun":
            return self.block_low
        if self.state == "attack" and self.move.crouching:
            return True
        return False

    def _rect(self, box):
        x, y, w, h = box
        if self.facing == -1:
            x = -x - w
        return pygame.Rect(int(self.x + x), int(self.y + y), w, h)

    def hurtbox(self):
        if self.invuln or self.state in ("knockdown", "down", "getup", "ko"):
            return None
        if not self.on_ground:
            return self._rect(AIR_HURT)
        return self._rect(CROUCH_HURT if self.is_crouching() else STAND_HURT)

    def hitbox(self):
        m = self.move
        if self.state != "attack" or not m.hitbox or self.hit_this_move:
            return None
        if m.startup <= self.move_frame < m.startup + m.active:
            return self._rect(m.hitbox)
        return None

    def start_move(self, name):
        self.move = MOVES[name]
        self.attack_id += 1
        self.move_frame = 0
        self.hit_this_move = False
        self.connected = False
        self.set_state("attack")
        if not self.move.air:
            self.vx = 0

    # ----------------------------------------------------------- update ----
    def update(self, inp, opp, scene):
        self.timer += 1
        self.anim_tick += 1
        if self.invuln:
            self.invuln -= 1

        if self.state in NEUTRAL_STATES and self.on_ground:
            self.face(opp)
        d = self.dir_num(inp)
        self.history.append(d)
        del self.history[:-30]
        self.holding_back = d in (1, 4, 7)
        self.holding_down = d in (1, 2, 3)

        st = self.state
        if st in NEUTRAL_STATES:
            self._neutral(inp, d, scene)
        elif st == "jump":
            if inp.pressed and not self.move:
                self.start_move("jump_kick")
        elif st == "attack":
            self._attack(inp, scene)
        elif st in ("hitstun", "blockstun"):
            self.stun -= 1
            if self.stun <= 0:
                self.set_state("crouch" if self.holding_down else "idle")
        elif st == "down":
            if self.timer > 40:
                self.set_state("getup")
        elif st == "getup":
            if self.timer > 18:
                self.set_state("idle")
                self.invuln = 8

        self._physics()

    def _neutral(self, inp, d, scene):
        p = inp.pressed
        if p:
            if p & {"lp", "hp"} and self.qcf() and self.projectile is None:
                self.start_move("special")
            elif "kick" in p and self.holding_down:
                self.start_move("sweep")
            elif "hp" in p:
                self.start_move("hp")
            elif "lp" in p:
                self.start_move("lp")
            elif "kick" in p:
                self.start_move("kick")
            if self.state == "attack":
                return
        if d in (7, 8, 9):
            self.vy = self.char.jump_vy
            self.vx = {7: -1, 8: 0, 9: 1}[d] * self.char.jump_vx * self.facing
            self.y -= 1
            self.move = None
            self.set_state("jump")
        elif d in (1, 2, 3):
            if self.state != "crouch":
                self.set_state("crouch")
            self.vx = 0
        elif d in (4, 6):
            if self.state != "walk":
                self.set_state("walk")
            self.walk_dir = 1 if d == 6 else -1
            speed = self.char.walk_speed if d == 6 else self.char.back_speed
            self.vx = speed * self.walk_dir * self.facing
        else:
            if self.state != "idle":
                self.set_state("idle")
            self.vx = 0

    def _attack(self, inp, scene):
        m = self.move
        self.move_frame += 1
        if m.projectile and self.move_frame == m.startup:
            proj = Projectile(self, self.x + self.facing * 72, self.y - 118,
                              self.char.projectile_speed * self.facing, self.blast_frames)
            self.projectile = proj
            scene.projectiles.append(proj)
        # Special cancel: on contact, a quarter-circle + punch cancels into the blast.
        if (self.connected and m.cancelable and inp.pressed & {"lp", "hp"}
                and self.qcf() and self.projectile is None):
            self.start_move("special")
            return
        if not m.air and self.move_frame >= m.total:
            self.move = None
            self.set_state("crouch" if self.holding_down else "idle")

    def _physics(self):
        airborne = self.y < GROUND_Y or self.vy < 0
        if airborne:
            self.vy += GRAVITY
            self.y += self.vy
            if self.y >= GROUND_Y:
                self.y = GROUND_Y
                self.vy = 0
                self._land()
        elif self.state in ("hitstun", "blockstun", "down", "getup", "ko", "attack", "win"):
            self.vx *= 0.8
            if abs(self.vx) < 0.1:
                self.vx = 0
        self.x += self.vx
        self.x = max(STAGE_LEFT, min(STAGE_RIGHT, self.x))

    def _land(self):
        if self.state in ("jump", "attack"):
            self.move = None
            self.vx = 0
            self.set_state("idle")
        elif self.state == "knockdown":
            self.vx *= 0.3
            self.set_state("ko" if self.health <= 0 else "down")
        elif self.state == "hitstun":
            self.vx = 0

    # -------------------------------------------------------- receiving ----
    def receive(self, move, attacker_x, damage_mult):
        """Apply an attack. Returns 'hit' or 'block'."""
        away = 1 if attacker_x < self.x else -1
        can_block = (self.state in NEUTRAL_STATES + ("blockstun",)
                     and self.on_ground and self.holding_back)
        if can_block and move.hit_type == "low" and not self.holding_down:
            can_block = False
        if can_block and move.hit_type == "overhead" and self.holding_down:
            can_block = False

        if can_block:
            if move.projectile:
                self.health = max(1, self.health - int(move.damage * 0.12))
            self.block_low = self.holding_down
            self.set_state("blockstun")
            self.stun = move.blockstun
            self.vx = away * move.pushback * 0.8
            return "block"

        self.combo = self.combo + 1 if self.state in ("hitstun", "knockdown") else 1
        scale = max(0.4, 1 - 0.12 * (self.combo - 1))
        self.health = max(0, self.health - int(move.damage * damage_mult * scale))
        self.move = None
        if self.health == 0 or move.knockdown or not self.on_ground:
            self.set_state("knockdown")
            self.vy = -9 if self.health else -11
            self.vx = away * 4
            self.y = min(self.y, GROUND_Y - 1)
        else:
            self.set_state("hitstun")
            self.stun = self.stun_total = move.hitstun
            self.vx = away * move.pushback
        return "hit"

    # ---------------------------------------------------------- drawing ----
    def frame(self):
        st, t = self.state, self.anim_tick
        if st == "idle":
            return "idle", (t // 9) % 4
        if st == "walk":
            i = (t // 7) % 4
            return "walk", i if self.walk_dir > 0 else 3 - i
        if st in ("crouch", "getup"):
            return "crouch", 0
        if st == "jump":
            return "jump", 0 if self.vy < -6 else 1
        if st == "attack":
            m = self.move
            if m.air:
                return ("jump_kick", 0) if self.move_frame >= m.startup else ("jump", 1)
            if self.move_frame < m.startup:
                return m.anim, 0
            if self.move_frame < m.startup + m.active:
                return m.anim, 1
            return m.anim, 2
        if st == "blockstun":
            return "block", 1 if self.block_low else 0
        if st == "hitstun":
            return "hit", 0 if self.stun_total - self.stun < 6 else 1
        if st == "knockdown":
            return "knockdown", 0
        if st in ("down", "ko"):
            return "knockdown", 1
        if st == "win":
            return "win", (t // 20) % 2
        return "idle", 0

    def draw(self, surf, ox=0, oy=0):
        anim, idx = self.frame()
        img = self.sprites.get(anim, idx, self.facing)
        anchor = ANCHOR_X if self.facing == 1 else FRAME_W - 1 - ANCHOR_X
        x = self.x - (anchor + 0.5) * SCALE + ox
        y = self.y - FOOT_ROW * SCALE + oy
        if self.invuln and (self.anim_tick // 2) % 2:
            return
        surf.blit(img, (x, y))

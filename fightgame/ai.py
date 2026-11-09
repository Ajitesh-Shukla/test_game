"""CPU opponent. It produces the same Input objects a keyboard would."""
import random

from .fighter import Input

LEVELS = {
    "EASY":   dict(block=0.20, jump_blast=0.25, aggro=0.35, think=(26, 45), combo=0.0),
    "NORMAL": dict(block=0.50, jump_blast=0.45, aggro=0.55, think=(14, 30), combo=0.3),
    "HARD":   dict(block=0.80, jump_blast=0.65, aggro=0.70, think=(8, 18), combo=0.7),
}

N = ()                                      # no directions held
QCF = [(("down",), ()), (("down",), ()), (("down", "fwd"), ()), (("down", "fwd"), ())]


class CPUController:
    def __init__(self, level="NORMAL", rng=None):
        self.cfg = LEVELS[level]
        self.rng = rng or random.Random()
        self.plan = []
        self.think = 40
        self.block_frames = 0
        self.block_low = False
        self.seen_attack = None
        self.seen_proj = set()

    def _input(self, me, dirs, pressed=()):
        fwd, back = "fwd" in dirs, "back" in dirs
        right = (fwd and me.facing == 1) or (back and me.facing == -1)
        left = (fwd and me.facing == -1) or (back and me.facing == 1)
        return Input(left, right, "up" in dirs, "down" in dirs, pressed)

    def reset(self):
        self.plan, self.think, self.block_frames = [], 40, 0

    def get_input(self, me, opp, scene):
        r, cfg = self.rng, self.cfg
        dist = abs(opp.x - me.x)
        can_act = me.state in ("idle", "walk", "crouch", "blockstun")

        # React to attacks (decided once per attack, at its first frame).
        if can_act and opp.state == "attack" and opp.move and not opp.move.projectile:
            key = (id(opp), opp.attack_id)
            if key != self.seen_attack:
                self.seen_attack = key
                if dist < 230 and r.random() < cfg["block"]:
                    self.plan = []
                    self.block_frames = opp.move.total + 6
                    self.block_low = opp.move.hit_type == "low"
        # React to incoming blasts.
        for p in scene.projectiles:
            if p.owner is opp and id(p) not in self.seen_proj:
                toward = (p.vx > 0) == (me.x > p.x)
                if toward and abs(p.x - me.x) < 300 and can_act:
                    self.seen_proj.add(id(p))
                    if r.random() < cfg["jump_blast"]:
                        self.plan = [(("up", "fwd"), ())] + [(N, ())] * 14 + [(N, ("kick",))]
                    else:
                        self.block_frames = 40
                        self.block_low = False

        if self.block_frames > 0 and can_act:
            self.block_frames -= 1
            return self._input(me, ("back", "down") if self.block_low else ("back",))
        self.block_frames = 0

        if self.plan:
            dirs, pressed = self.plan.pop(0)
            return self._input(me, dirs, pressed)

        self.think -= 1
        if self.think > 0 or me.state not in ("idle", "walk", "crouch"):
            return self._input(me, N)
        self.think = r.randint(*cfg["think"])
        self.plan = self._decide(me, opp, dist)
        return self._input(me, N)

    def _decide(self, me, opp, dist):
        r, cfg = self.rng, self.cfg
        if opp.state in ("down", "knockdown", "getup"):
            return [(("fwd",), ())] * r.randint(5, 15) if dist > 140 else [(N, ())] * 10
        if dist > 380:
            if me.projectile is None and r.random() < 0.5:
                return QCF + [(("fwd",), ("lp",))]
            return [(("fwd",), ())] * r.randint(15, 35)
        if dist > 170:
            roll = r.random()
            if roll < 0.2 * cfg["aggro"] * 2:
                return [(("up", "fwd"), ())] + [(N, ())] * r.randint(10, 16) + [(N, ("kick",))]
            if roll < 0.55 and me.projectile is None:
                return QCF + [(("fwd",), ("hp",))]
            if roll < 0.85:
                return [(("fwd",), ())] * r.randint(10, 25)
            return [(N, ())] * 15
        # close range
        if r.random() > cfg["aggro"]:
            return [(("back",), ())] * r.randint(10, 20)
        if r.random() < cfg["combo"] and me.projectile is None:
            # crouching jab cancelled into a blast
            return [(("down",), ("lp",))] + [(("down",), ())] * 2 + \
                   [(("down", "fwd"), ())] * 2 + [(("fwd",), ("lp",))]
        choice = r.choice(["lp", "lp", "hp", "kick", "sweep"])
        if choice == "sweep":
            return [(("down",), ("kick",))]
        if choice == "lp":
            return [(N, ("lp",))] + [(N, ())] * 10 + [(N, ("lp",))]
        return [(N, (choice,))]

"""Frame data for every attack.

All timings are in frames (60 per second). Hitboxes are (x, y, w, h) in screen
pixels relative to the fighter's feet, for a fighter facing right; they are
mirrored automatically when facing left.
"""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Move:
    name: str
    anim: str
    startup: int
    active: int
    recovery: int
    damage: int
    hitstun: int
    blockstun: int
    hitbox: Optional[Tuple[int, int, int, int]]
    hit_type: str = "mid"        # "mid", "low" (block crouching) or "overhead" (block standing)
    knockdown: bool = False
    pushback: float = 6.0
    cancelable: bool = False     # can be cancelled into the special on contact
    projectile: bool = False
    air: bool = False
    crouching: bool = False

    @property
    def total(self):
        return self.startup + self.active + self.recovery


MOVES = {
    "lp": Move("lp", "lp", startup=4, active=3, recovery=7, damage=45,
               hitstun=15, blockstun=10, hitbox=(25, -140, 50, 28),
               pushback=5, cancelable=True),
    "hp": Move("hp", "hp", startup=8, active=4, recovery=16, damage=105,
               hitstun=20, blockstun=14, hitbox=(25, -142, 62, 32),
               pushback=8, cancelable=True),
    "kick": Move("kick", "kick", startup=7, active=4, recovery=14, damage=85,
                 hitstun=18, blockstun=12, hitbox=(30, -110, 65, 32),
                 pushback=7),
    "sweep": Move("sweep", "sweep", startup=8, active=4, recovery=20, damage=75,
                  hitstun=0, blockstun=12, hitbox=(25, -28, 70, 28),
                  hit_type="low", knockdown=True, pushback=5, crouching=True),
    "jump_kick": Move("jump_kick", "jump_kick", startup=5, active=40, recovery=0,
                      damage=80, hitstun=18, blockstun=12, hitbox=(15, -75, 60, 45),
                      hit_type="overhead", pushback=5, air=True),
    "special": Move("special", "special", startup=12, active=4, recovery=28,
                    damage=0, hitstun=0, blockstun=0, hitbox=None, projectile=True),
}

# Used when a projectile connects.
PROJECTILE_HIT = Move("blast", "special", startup=0, active=0, recovery=0,
                      damage=85, hitstun=20, blockstun=14, hitbox=None,
                      pushback=6, projectile=True)

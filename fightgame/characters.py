"""Playable characters. Sprite sheets live in assets/<key>.png."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Character:
    key: str
    name: str
    blurb: str
    walk_speed: float
    back_speed: float
    jump_vx: float
    jump_vy: float
    damage_mult: float
    projectile_speed: float


CHARACTERS = [
    Character("kai", "KAI", "Quick and balanced. Fast blasts.",
              walk_speed=4.4, back_speed=3.4, jump_vx=4.6, jump_vy=-17.0,
              damage_mult=1.0, projectile_speed=8.0),
    Character("rhea", "RHEA", "Slower, but every hit hurts.",
              walk_speed=3.7, back_speed=3.0, jump_vx=4.2, jump_vy=-16.5,
              damage_mult=1.15, projectile_speed=6.5),
]

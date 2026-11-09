"""Loads sprite sheets from assets/ (generating placeholders if missing)."""
import os

import pygame

from .anims import ANIMS
from .config import FRAME_W, FRAME_H, SCALE

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def asset(name):
    return os.path.join(ASSETS, name)


def ensure_assets(keys):
    needed = ["stage.png"] + [f"{k}.png" for k in keys] + [f"{k}_blast.png" for k in keys]
    if not all(os.path.exists(asset(n)) for n in needed):
        from .spritegen import generate_all
        generate_all(ASSETS)


class FighterSprites:
    def __init__(self, path):
        sheet = pygame.image.load(path).convert_alpha()
        self.frames = {}
        for row, (name, count) in enumerate(ANIMS):
            frames = []
            for col in range(count):
                sub = sheet.subsurface((col * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H))
                big = pygame.transform.scale(sub, (FRAME_W * SCALE, FRAME_H * SCALE))
                frames.append((big, pygame.transform.flip(big, True, False)))
            self.frames[name] = frames

    def get(self, anim, idx, facing):
        frames = self.frames[anim]
        pair = frames[idx % len(frames)]
        return pair[0] if facing == 1 else pair[1]


def load_blast(path):
    sheet = pygame.image.load(path).convert_alpha()
    w, h = sheet.get_height() * 3 // 2, sheet.get_height()
    return [pygame.transform.scale(sheet.subsurface((i * w, 0, w, h)), (w * SCALE, h * SCALE))
            for i in range(sheet.get_width() // w)]


def load_stage(size):
    return pygame.transform.scale(pygame.image.load(asset("stage.png")).convert(), size)

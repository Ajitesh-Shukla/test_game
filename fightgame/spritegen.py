"""Generates the placeholder pixel art in assets/.

The PNGs it writes are plain sprite sheets: open them in LibreSprite, repaint
them, and the game picks up your edits. Re-running this script OVERWRITES them,
so only run it if you want the placeholders back:

    python tools/generate_sprites.py
"""
import math
import os

import pygame

from .anims import ANIMS, MAX_FRAMES

FW, FH = 48, 64
OUTLINE = (18, 16, 24)

PALETTES = {
    "kai": dict(gi=(58, 112, 214), belt=(30, 30, 36), skin=(236, 188, 146),
                hair=(28, 24, 30), accent=(220, 40, 48), wrap=(240, 240, 240),
                hair_style="spiky", sleeves=True),
    "rhea": dict(gi=(214, 90, 44), belt=(250, 214, 70), skin=(200, 140, 100),
                 hair=(96, 52, 120), accent=(250, 214, 70), wrap=(70, 70, 84),
                 hair_style="ponytail", sleeves=False),
    # masked enemy fighter used in Adventure mode
    "shade": dict(gi=(74, 64, 104), belt=(220, 220, 230), skin=(222, 180, 140),
                  hair=(30, 28, 40), accent=(235, 235, 245), wrap=(40, 40, 48),
                  hair_style="spiky", sleeves=True, mask=True),
}

PROJECTILE_COLORS = {
    "kai": ((235, 250, 255), (120, 200, 255), (40, 110, 230)),
    "rhea": ((255, 250, 220), (255, 190, 70), (230, 90, 30)),
    "shade": ((250, 230, 255), (200, 120, 255), (110, 40, 180)),
}


def _dark(c, f=0.72):
    return tuple(int(v * f) for v in c)


# ---------------------------------------------------------------- poses ----
# Joint positions inside a 48x64 frame for a fighter facing right.
# head, neck, hip, front/back elbow (fe/be), hand (fh/bh), knee (fk/bk), foot (ff/bf)
BASE = dict(head=(22, 11), neck=(21, 19), hip=(19, 37),
            fe=(28, 27), fh=(31, 20), be=(17, 28), bh=(25, 24),
            fk=(26, 48), ff=(29, 62), bk=(14, 49), bf=(11, 62))

CROUCH = dict(head=(24, 31), neck=(22, 38), hip=(18, 51),
              fe=(29, 43), fh=(32, 37), be=(19, 45), bh=(26, 42),
              fk=(28, 50), ff=(30, 62), bk=(10, 53), bf=(10, 62))


def P(base=BASE, **kw):
    d = dict(base)
    d.update(kw)
    return d


def shift_upper(p, dx=0, dy=0):
    d = dict(p)
    for k in ("head", "neck", "hip", "fe", "fh", "be", "bh"):
        d[k] = (p[k][0] + dx, p[k][1] + dy)
    for k in ("fk", "bk"):
        d[k] = (p[k][0] + dx // 2, p[k][1] + dy // 2)
    return d


KICK_PREP = P(head=(20, 11), neck=(19, 19), hip=(19, 37), fk=(28, 40), ff=(27, 50),
              bk=(17, 49), bf=(16, 62), fe=(25, 26), fh=(28, 20), be=(14, 27), bh=(20, 24))
SPECIAL_OUT = dict(head=(24, 13), neck=(23, 21), hip=(19, 37), fe=(33, 25), fh=(42, 26),
                   be=(31, 27), bh=(41, 29), fk=(29, 48), ff=(33, 62), bk=(13, 49), bf=(8, 62))
WIN = P(fe=(26, 9), fh=(27, 2), be=(16, 28), bh=(20, 34))

POSES = {
    "idle": [shift_upper(BASE, 0, 0), shift_upper(BASE, 0, 1),
             shift_upper(BASE, 0, 2), shift_upper(BASE, 0, 1)],
    "walk": [P(fk=(27, 48), ff=(31, 62), bk=(14, 48), bf=(9, 62)),
             shift_upper(P(fk=(23, 48), ff=(22, 62), bk=(19, 49), bf=(17, 61)), 0, -1),
             P(fk=(22, 48), ff=(14, 62), bk=(22, 48), bf=(28, 62)),
             shift_upper(P(fk=(19, 49), ff=(18, 62), bk=(22, 48), bf=(23, 61)), 0, -1)],
    "crouch": [CROUCH],
    "jump": [dict(head=(22, 9), neck=(21, 17), hip=(19, 35), fe=(27, 24), fh=(30, 17),
                  be=(16, 25), bh=(23, 21), fk=(26, 43), ff=(25, 55), bk=(14, 44), bf=(16, 56)),
             dict(head=(23, 14), neck=(21, 21), hip=(19, 37), fe=(28, 28), fh=(31, 22),
                  be=(17, 30), bh=(25, 27), fk=(29, 36), ff=(24, 46), bk=(25, 42), bf=(17, 48))],
    "lp": [P(fe=(26, 26), fh=(30, 22), bh=(25, 25)),
           shift_upper(P(fe=(33, 21), fh=(43, 20), be=(16, 28), bh=(22, 26)), 1, 0),
           P(fe=(30, 23), fh=(36, 21))],
    "hp": [shift_upper(P(be=(13, 27), bh=(16, 22), fe=(27, 26), fh=(30, 20)), -1, 0),
           P(head=(25, 12), neck=(23, 20), be=(33, 20), bh=(45, 19), fe=(24, 28), fh=(24, 22),
             fk=(27, 48), ff=(31, 62), bk=(13, 49), bf=(9, 62)),
           P(head=(24, 11), neck=(22, 19), be=(28, 23), bh=(35, 21))],
    "kick": [KICK_PREP,
             P(head=(16, 12), neck=(17, 20), hip=(20, 37), fk=(31, 33), ff=(45, 30),
               bk=(18, 49), bf=(17, 62), fe=(22, 26), fh=(26, 21), be=(11, 28), bh=(9, 34)),
             KICK_PREP],
    "sweep": [P(CROUCH, fk=(26, 54), ff=(32, 61)),
              dict(head=(13, 36), neck=(15, 43), hip=(18, 53), fe=(10, 50), fh=(8, 58),
                   be=(20, 50), bh=(22, 58), fk=(31, 58), ff=(46, 61), bk=(10, 55), bf=(8, 62)),
              CROUCH],
    "jump_kick": [dict(head=(18, 12), neck=(19, 20), hip=(21, 36), fe=(25, 27), fh=(28, 22),
                       be=(14, 27), bh=(12, 33), fk=(32, 40), ff=(44, 47), bk=(18, 44), bf=(14, 52))],
    "special": [dict(head=(19, 12), neck=(19, 20), hip=(20, 37), fe=(14, 31), fh=(11, 35),
                     be=(14, 32), bh=(12, 36), fk=(28, 48), ff=(32, 62), bk=(14, 49), bf=(9, 62)),
                SPECIAL_OUT,
                P(SPECIAL_OUT, fh=(38, 26), bh=(37, 29), fe=(31, 26), be=(29, 28))],
    "block": [P(head=(19, 12), neck=(19, 20), fe=(25, 24), fh=(25, 14), be=(23, 27), bh=(27, 17),
                fk=(25, 48), ff=(27, 62)),
              P(CROUCH, head=(22, 32), neck=(21, 39), fe=(26, 38), fh=(26, 29), be=(24, 41), bh=(28, 32))],
    "hit": [P(head=(15, 13), neck=(17, 20), hip=(20, 37), fe=(22, 27), fh=(26, 31),
              be=(12, 26), bh=(8, 22), fk=(26, 48), ff=(28, 62), bk=(15, 49), bf=(13, 62)),
            P(head=(17, 14), neck=(18, 21), fe=(24, 28), fh=(28, 30), be=(13, 28), bh=(10, 24))],
    "knockdown": [dict(head=(10, 30), neck=(15, 32), hip=(28, 40), fe=(18, 24), fh=(20, 17),
                       be=(12, 38), bh=(6, 40), fk=(36, 34), ff=(43, 28), bk=(35, 44), bf=(43, 42)),
                  dict(head=(6, 56), neck=(12, 58), hip=(28, 58), fe=(16, 55), fh=(21, 52),
                       be=(11, 60), bh=(17, 61), fk=(36, 54), ff=(44, 60), bk=(37, 58), bf=(45, 61))],
    "win": [WIN, P(WIN, fe=(26, 10), fh=(28, 4), head=(22, 12), neck=(21, 20))],
}


# -------------------------------------------------------------- drawing ----
def _seg(surf, a, b, col, w):
    pygame.draw.line(surf, col, a, b, w)
    r = max(1, w // 2)
    pygame.draw.circle(surf, col, a, r)
    pygame.draw.circle(surf, col, b, r)


def _foot(surf, pt, col):
    pygame.draw.rect(surf, col, (pt[0] - 1, pt[1] - 2, 5, 3))


def _head(surf, p, pal):
    hx, hy = p["head"]
    skin, hair = pal["skin"], pal["hair"]
    _seg(surf, p["neck"], (hx - 1, hy + 4), skin, 3)
    if pal["hair_style"] == "ponytail":
        _seg(surf, (hx - 4, hy - 3), (hx - 10, hy + 1), hair, 3)
        _seg(surf, (hx - 10, hy + 1), (hx - 11, hy + 8), hair, 3)
        pygame.draw.circle(surf, hair, (hx - 1, hy - 1), 5)
        pygame.draw.circle(surf, skin, (hx + 1, hy + 1), 4)
        pygame.draw.circle(surf, pal["accent"], (hx - 5, hy - 2), 1)
    else:
        for tip in ((hx - 6, hy - 8), (hx - 2, hy - 9), (hx - 8, hy - 3)):
            pygame.draw.polygon(surf, hair, [(hx - 3, hy - 4), tip, (hx + 1, hy - 4)])
        pygame.draw.circle(surf, hair, (hx - 1, hy - 1), 5)
        pygame.draw.circle(surf, skin, (hx + 1, hy + 1), 4)
        pygame.draw.line(surf, pal["accent"], (hx - 5, hy - 3), (hx + 5, hy - 3), 2)
        pygame.draw.line(surf, pal["accent"], (hx - 5, hy - 2), (hx - 10, hy + 1), 2)
        pygame.draw.line(surf, pal["accent"], (hx - 5, hy - 2), (hx - 9, hy + 4), 1)
    if pal.get("mask"):
        pygame.draw.rect(surf, _dark(pal["gi"], 0.6), (hx - 2, hy + 1, 7, 4))
    surf.set_at((hx + 3, hy), OUTLINE)  # eye


def draw_pose(surf, p, pal):
    gi, skin = pal["gi"], pal["skin"]
    gd, sd = _dark(gi), _dark(skin)
    neck, hip = p["neck"], p["hip"]
    sh = (neck[0], neck[1] + 2)

    # back arm + back leg (darker, behind the body)
    _seg(surf, sh, p["be"], gd if pal["sleeves"] else sd, 4)
    _seg(surf, p["be"], p["bh"], sd, 3)
    pygame.draw.circle(surf, _dark(pal["wrap"]), p["bh"], 2)
    _seg(surf, hip, p["bk"], gd, 5)
    _seg(surf, p["bk"], p["bf"], gd, 4)
    _foot(surf, p["bf"], sd)

    # torso
    dx, dy = hip[0] - neck[0], hip[1] - neck[1]
    ln = math.hypot(dx, dy) or 1
    nx, ny = -dy / ln, dx / ln
    pts = [(neck[0] + nx * 5, neck[1] + ny * 5), (neck[0] - nx * 5, neck[1] - ny * 5),
           (hip[0] - nx * 4, hip[1] - ny * 4), (hip[0] + nx * 4, hip[1] + ny * 4)]
    pygame.draw.polygon(surf, gi, pts)
    pygame.draw.polygon(surf, skin, [(neck[0] - 1, neck[1]), (neck[0] + 3, neck[1]),
                                     (neck[0] + 1 + dx * 0.25, neck[1] + dy * 0.25)])

    # front leg
    _seg(surf, hip, p["fk"], gi, 5)
    _seg(surf, p["fk"], p["ff"], gi, 4)
    _foot(surf, p["ff"], skin)

    # belt
    bx, by = hip[0] - dx * 0.1, hip[1] - dy * 0.1
    pygame.draw.line(surf, pal["belt"], (bx + nx * 4, by + ny * 4), (bx - nx * 4, by - ny * 4), 2)
    pygame.draw.line(surf, pal["belt"], (bx, by), (bx + 2 - dx * 0.0, by + 5), 1)

    _head(surf, p, pal)

    # front arm
    _seg(surf, sh, p["fe"], gi if pal["sleeves"] else skin, 4)
    _seg(surf, p["fe"], p["fh"], skin, 3)
    pygame.draw.circle(surf, pal["wrap"], p["fh"], 2)


def _outlined(draw_fn, size):
    tmp = pygame.Surface(size, pygame.SRCALPHA)
    draw_fn(tmp)
    sil = pygame.mask.from_surface(tmp).to_surface(setcolor=OUTLINE + (255,),
                                                   unsetcolor=(0, 0, 0, 0))
    out = pygame.Surface(size, pygame.SRCALPHA)
    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        out.blit(sil, (ox, oy))
    out.blit(tmp, (0, 0))
    return out


def make_fighter_sheet(pal):
    sheet = pygame.Surface((FW * MAX_FRAMES, FH * len(ANIMS)), pygame.SRCALPHA)
    for row, (name, count) in enumerate(ANIMS):
        poses = POSES[name]
        assert len(poses) == count, name
        for col, pose in enumerate(poses):
            frame = _outlined(lambda s, p=pose: draw_pose(s, p, pal), (FW, FH))
            sheet.blit(frame, (col * FW, row * FH))
    return sheet


def make_projectile_sheet(colors):
    core, mid, glow = colors
    sheet = pygame.Surface((48, 16), pygame.SRCALPHA)
    for i in range(2):
        f = pygame.Surface((24, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(f, glow + (150,), (1 + i, 2 - i, 21 - i, 12 + 2 * i))
        pygame.draw.circle(f, glow + (120,), (4, 8), 2 + i)
        pygame.draw.ellipse(f, mid, (7, 4, 14, 8))
        pygame.draw.ellipse(f, core, (12, 5, 8, 6))
        sheet.blit(f, (i * 24, 0))
    return sheet


def make_stage():
    w, h = 320, 180
    s = pygame.Surface((w, h))
    top, bottom = (36, 26, 74), (250, 146, 92)
    for y in range(130):
        t = y / 129
        s.fill(tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)), (0, y, w, 1))
    pygame.draw.circle(s, (255, 214, 140), (232, 92), 22)
    pygame.draw.circle(s, (255, 236, 190), (232, 92), 16)
    for i, (x, y) in enumerate(((20, 14), (70, 30), (130, 10), (180, 24), (290, 18), (300, 44))):
        s.set_at((x, y), (255, 255, 230) if i % 2 else (200, 200, 255))
    far = [(0, 112), (30, 84), (62, 104), (100, 70), (140, 100), (178, 80), (214, 108),
           (256, 76), (296, 98), (320, 86), (320, 130), (0, 130)]
    pygame.draw.polygon(s, (118, 72, 120), far)
    near = [(0, 122), (40, 102), (80, 118), (126, 96), (170, 120), (220, 100), (268, 122),
            (320, 104), (320, 130), (0, 130)]
    pygame.draw.polygon(s, (78, 46, 92), near)
    # rooftop railing
    s.fill((60, 34, 40), (0, 128, w, 32))
    for x in range(0, w, 20):
        s.fill((92, 52, 52), (x + 2, 132, 4, 26))
    s.fill((140, 60, 50), (0, 128, w, 4))
    s.fill((110, 48, 42), (0, 144, w, 2))
    # lanterns
    for x in (40, 160, 280):
        pygame.draw.line(s, (40, 20, 20), (x, 112), (x, 118))
        pygame.draw.ellipse(s, (232, 64, 52), (x - 5, 117, 11, 13))
        pygame.draw.ellipse(s, (255, 170, 90), (x - 2, 120, 5, 7))
    # wooden floor
    s.fill((150, 98, 60), (0, 160, w, 20))
    s.fill((104, 64, 40), (0, 160, w, 2))
    for y in (166, 173):
        s.fill((124, 80, 50), (0, y, w, 1))
    for i, x in enumerate(range(0, w, 26)):
        yy = 162 if i % 2 else 167
        s.fill((118, 76, 48), (x, yy, 1, 5))
    return s


# ------------------------------------------------------- adventure art ----
T = 16  # tile size in the tileset (drawn x2 in game)

# Tileset layout (8 columns x 2 rows of 16x16 tiles), see README.
TILE_INDEX = dict(grass=0, dirt=1, stone=2, plank=3, crate=4, spikes=5, gem0=6, gem1=7,
                  heart=8, lantern_off=9, lantern_on=10, heart_empty=11)


def _tile_rect(i):
    return pygame.Rect((i % 8) * T, (i // 8) * T, T, T)


def make_tiles():
    s = pygame.Surface((8 * T, 2 * T), pygame.SRCALPHA)
    dirt, dirt_d, dirt_l = (138, 86, 52), (104, 62, 38), (160, 106, 66)

    def dirt_fill(r):
        s.fill(dirt, r)
        for (x, y) in ((2, 3), (9, 2), (12, 9), (4, 11), (7, 7), (13, 14), (1, 14), (10, 12)):
            s.set_at((r.x + x, r.y + y), dirt_d)
        for (x, y) in ((5, 5), (11, 6), (3, 9), (14, 3)):
            s.set_at((r.x + x, r.y + y), dirt_l)

    r = _tile_rect(0)                                   # grass top
    dirt_fill(r)
    s.fill((84, 170, 70), (r.x, r.y, T, 5))
    s.fill((126, 206, 92), (r.x, r.y, T, 2))
    for x in range(0, T, 3):
        s.fill((84, 170, 70), (r.x + x, r.y + 5, 1, 1 + (x * 7) % 3))
    dirt_fill(_tile_rect(1))                            # dirt

    r = _tile_rect(2)                                   # stone block
    s.fill((128, 124, 140), r)
    s.fill((160, 156, 172), (r.x, r.y, T, 1))
    s.fill((160, 156, 172), (r.x, r.y, 1, T))
    s.fill((84, 80, 96), (r.x, r.y + T - 1, T, 1))
    s.fill((84, 80, 96), (r.x + T - 1, r.y, 1, T))
    s.fill((96, 92, 108), (r.x, r.y + 7, T, 1))
    s.fill((96, 92, 108), (r.x + 8, r.y, 1, 7))
    s.fill((96, 92, 108), (r.x + 4, r.y + 8, 1, 8))

    r = _tile_rect(3)                                   # one-way wooden plank
    s.fill((176, 116, 62), (r.x, r.y, T, 6))
    s.fill((214, 152, 88), (r.x, r.y, T, 1))
    s.fill((120, 74, 40), (r.x, r.y + 5, T, 1))
    s.fill((120, 74, 40), (r.x + 7, r.y + 1, 1, 4))
    s.set_at((r.x + 2, r.y + 3), (90, 60, 40))
    s.set_at((r.x + 12, r.y + 3), (90, 60, 40))

    r = _tile_rect(4)                                   # crate
    s.fill((196, 136, 70), r)
    pygame.draw.rect(s, (110, 66, 34), r, 2)
    pygame.draw.line(s, (130, 82, 42), (r.x + 2, r.y + 2), (r.right - 3, r.bottom - 3), 2)
    pygame.draw.line(s, (130, 82, 42), (r.right - 3, r.y + 2), (r.x + 2, r.bottom - 3), 2)
    s.fill((226, 170, 100), (r.x + 2, r.y + 2, T - 4, 1))

    r = _tile_rect(5)                                   # spikes
    for i in range(4):
        x = r.x + i * 4
        pygame.draw.polygon(s, (210, 214, 226), [(x, r.bottom - 1), (x + 2, r.y + 7), (x + 3, r.bottom - 1)])
        pygame.draw.line(s, (120, 124, 140), (x + 2, r.y + 8), (x + 3, r.bottom - 1))
    s.fill((90, 92, 104), (r.x, r.bottom - 2, T, 2))

    for i, shine in ((6, False), (7, True)):            # gem (2 frames)
        r = _tile_rect(i)
        pts = [(r.x + 8, r.y + 2), (r.x + 13, r.y + 7), (r.x + 8, r.y + 14), (r.x + 3, r.y + 7)]
        pygame.draw.polygon(s, OUTLINE, pts, 0)
        inner = [(r.x + 8, r.y + 3), (r.x + 12, r.y + 7), (r.x + 8, r.y + 13), (r.x + 4, r.y + 7)]
        pygame.draw.polygon(s, (60, 210, 230), inner)
        pygame.draw.polygon(s, (170, 245, 255), [(r.x + 8, r.y + 3), (r.x + 10, r.y + 7), (r.x + 6, r.y + 7)])
        if shine:
            s.set_at((r.x + 6, r.y + 5), (255, 255, 255))
            s.set_at((r.x + 7, r.y + 4), (255, 255, 255))

    for i, col in ((8, (232, 50, 70)), (11, (70, 50, 70))):   # heart full / empty
        r = _tile_rect(i)
        pygame.draw.circle(s, OUTLINE, (r.x + 5, r.y + 6), 4)
        pygame.draw.circle(s, OUTLINE, (r.x + 10, r.y + 6), 4)
        pygame.draw.polygon(s, OUTLINE, [(r.x + 1, r.y + 7), (r.x + 14, r.y + 7), (r.x + 8, r.y + 14)])
        pygame.draw.circle(s, col, (r.x + 5, r.y + 6), 3)
        pygame.draw.circle(s, col, (r.x + 10, r.y + 6), 3)
        pygame.draw.polygon(s, col, [(r.x + 2, r.y + 7), (r.x + 13, r.y + 7), (r.x + 8, r.y + 13)])
        s.set_at((r.x + 4, r.y + 5), (255, 220, 220))

    for i, lit in ((9, False), (10, True)):              # checkpoint lantern
        r = _tile_rect(i)
        body = (236, 70, 56) if lit else (110, 90, 100)
        glow = (255, 210, 120) if lit else (150, 130, 140)
        s.fill((50, 34, 30), (r.x + 7, r.y, 2, 3))
        pygame.draw.ellipse(s, OUTLINE, (r.x + 2, r.y + 2, 12, 14))
        pygame.draw.ellipse(s, body, (r.x + 3, r.y + 3, 10, 12))
        pygame.draw.ellipse(s, glow, (r.x + 6, r.y + 6, 4, 6))
        s.fill(OUTLINE, (r.x + 4, r.y + 8, 8, 1))
    return s


def make_grunt():
    """Small horned blob enemy: walk 1, walk 2, squashed (16x16 each)."""
    s = pygame.Surface((48, 16), pygame.SRCALPHA)
    body, dark = (110, 186, 84), (70, 130, 56)
    for i in range(3):
        f = pygame.Surface((16, 16), pygame.SRCALPHA)
        if i < 2:
            pygame.draw.polygon(f, (240, 230, 200), [(4, 5), (3, 1), (6, 4)])
            pygame.draw.polygon(f, (240, 230, 200), [(11, 4), (13, 1), (12, 5)])
            pygame.draw.ellipse(f, body, (1, 3, 14, 11))
            pygame.draw.ellipse(f, dark, (2, 9, 12, 5))
            f.fill(OUTLINE, (3 + 2 * i, 13, 3, 3))
            f.fill(OUTLINE, (10 - 2 * i, 13, 3, 3))
            f.fill((255, 255, 255), (4, 6, 3, 3))
            f.fill((255, 255, 255), (9, 6, 3, 3))
            f.set_at((4, 7), OUTLINE)
            f.set_at((9, 7), OUTLINE)
            f.fill(OUTLINE, (6, 11, 4, 1))
        else:
            pygame.draw.ellipse(f, body, (0, 10, 16, 6))
            f.fill(OUTLINE, (4, 12, 2, 1))
            f.fill(OUTLINE, (10, 12, 2, 1))
        out = _outlined(lambda t, src=f: t.blit(src, (0, 0)), (16, 16))
        s.blit(out, (i * 16, 0))
    return s


def make_goal():
    """Shrine gate the hero walks through to finish a level (48x64)."""
    def draw(f):
        red, red_d, black = (214, 52, 44), (150, 30, 30), (34, 28, 34)
        f.fill(red, (9, 12, 5, 52))
        f.fill(red, (34, 12, 5, 52))
        f.fill(red_d, (12, 12, 2, 52))
        f.fill(red_d, (37, 12, 2, 52))
        f.fill(black, (8, 58, 7, 6))
        f.fill(black, (33, 58, 7, 6))
        pygame.draw.polygon(f, black, [(0, 4), (48, 4), (46, 9), (2, 9)])
        f.fill(red, (2, 9, 44, 4))
        f.fill(red, (6, 20, 36, 4))
        f.fill((250, 220, 120), (20, 13, 8, 7))
        f.fill(black, (22, 15, 4, 3))
    return _outlined(draw, (48, 64))


def make_adventure_bg():
    """Seamlessly tiling sky + hills (320x180), scrolled with parallax."""
    w, h = 320, 180
    s = pygame.Surface((w, h))
    top, bottom = (92, 150, 230), (250, 206, 160)
    for y in range(h):
        t = min(1, y / 140)
        s.fill(tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)), (0, y, w, 1))
    for cx, cy, r in ((40, 30, 10), (54, 26, 13), (70, 31, 9), (200, 50, 9), (214, 46, 12), (228, 51, 8)):
        pygame.draw.circle(s, (250, 250, 255), (cx, cy), r)
    tau = 2 * math.pi
    for x in range(w):
        far = 96 + 14 * math.sin(tau * x / w * 2) + 8 * math.sin(tau * x / w * 5 + 1)
        near = 128 + 10 * math.sin(tau * x / w * 3 + 2) + 5 * math.sin(tau * x / w * 7)
        s.fill((150, 140, 196), (x, int(far), 1, h))
        s.fill((96, 150, 110), (x, int(near), 1, h))
        if (x * 37) % 23 == 0:   # little trees on the near hills
            pygame.draw.circle(s, (70, 120, 84), (x, int(near) + 2), 4)
    return s


def generate_all(assets_dir, only_missing=False):
    """Write all art. With only_missing=True, existing files (your edits) are kept."""
    os.makedirs(assets_dir, exist_ok=True)
    jobs = {}
    for key, pal in PALETTES.items():
        jobs[f"{key}.png"] = lambda pal=pal: make_fighter_sheet(pal)
        jobs[f"{key}_blast.png"] = lambda key=key: make_projectile_sheet(PROJECTILE_COLORS[key])
    jobs.update({"stage.png": make_stage, "tiles.png": make_tiles, "grunt.png": make_grunt,
                 "goal.png": make_goal, "adventure_bg.png": make_adventure_bg})
    for name, make in jobs.items():
        path = os.path.join(assets_dir, name)
        if only_missing and os.path.exists(path):
            continue
        pygame.image.save(make(), path)

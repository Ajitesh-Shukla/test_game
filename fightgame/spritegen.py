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
}

PROJECTILE_COLORS = {
    "kai": ((235, 250, 255), (120, 200, 255), (40, 110, 230)),
    "rhea": ((255, 250, 220), (255, 190, 70), (230, 90, 30)),
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


def generate_all(assets_dir):
    os.makedirs(assets_dir, exist_ok=True)
    for key, pal in PALETTES.items():
        pygame.image.save(make_fighter_sheet(pal), os.path.join(assets_dir, f"{key}.png"))
        pygame.image.save(make_projectile_sheet(PROJECTILE_COLORS[key]),
                          os.path.join(assets_dir, f"{key}_blast.png"))
    pygame.image.save(make_stage(), os.path.join(assets_dir, "stage.png"))

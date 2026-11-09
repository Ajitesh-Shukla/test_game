"""Text-file levels and tile collision.

Levels are plain text in levels/*.txt, one character per 32x32 tile.
Lines starting with ';' are comments; '; name: ...' sets the level title.

    .  empty            #  ground            S  stone block
    =  wooden platform (jump up through it, Down + Jump drops through)
    X  crate (solid, punch it for a gem)
    ^  spikes           o  gem               H  heart
    g  grunt            f  masked fighter    K  boss (your rival)
    C  checkpoint       P  player start      E  goal gate (bottom-left tile)
"""
import pygame

TILE = 32
SOLID = set("#SX")
ONE_WAY = "="
ENTITY_CHARS = set("ogHfKCPE")


class Level:
    def __init__(self, path):
        self.name = "Untitled"
        rows = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n").rstrip("\r")
                if line.startswith(";"):
                    if line[1:].strip().lower().startswith("name:"):
                        self.name = line.split(":", 1)[1].strip()
                    continue
                rows.append(line)
        self.cols = max(len(r) for r in rows)
        self.rows = len(rows)
        self.grid = [list(r.ljust(self.cols, ".")) for r in rows]
        self.width = self.cols * TILE
        self.height = self.rows * TILE
        self.spawns = []
        for y, row in enumerate(self.grid):
            for x, ch in enumerate(row):
                if ch in ENTITY_CHARS:
                    self.spawns.append((ch, x, y))
                    row[x] = "."

    def at(self, cx, cy):
        if cx < 0 or cx >= self.cols:
            return "S"                     # invisible walls at the level edges
        if cy < 0 or cy >= self.rows:
            return "."
        return self.grid[cy][cx]

    def solid(self, cx, cy):
        return self.at(cx, cy) in SOLID

    def standable(self, cx, cy):
        return self.at(cx, cy) in SOLID or self.at(cx, cy) == ONE_WAY

    def tiles_in(self, rect):
        """Yield (cx, cy, char) for every tile touching rect."""
        for cy in range(int(rect.top // TILE), int((rect.bottom - 1) // TILE) + 1):
            for cx in range(int(rect.left // TILE), int((rect.right - 1) // TILE) + 1):
                yield cx, cy, self.at(cx, cy)


class Body:
    """Axis-aligned box: x is the horizontal centre, y is the bottom (feet)."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = float(x), float(y), w, h
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.hit_wall = False
        self.drop_through = 0

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w / 2), int(self.y - self.h), self.w, self.h)

    def step(self, level):
        """Move by (vx, vy), stopping at solid tiles. Returns the tile bumped from below."""
        self.hit_wall = False
        bumped = None
        # horizontal
        self.x += self.vx
        top, bottom = self.y - self.h, self.y
        rows = range(int(top // TILE), int((bottom - 0.01) // TILE) + 1)
        if self.vx > 0:
            cx = int((self.x + self.w / 2 - 0.01) // TILE)
            if any(level.solid(cx, cy) for cy in rows):
                self.x = cx * TILE - self.w / 2
                self.vx, self.hit_wall = 0, True
        elif self.vx < 0:
            cx = int((self.x - self.w / 2) // TILE)
            if any(level.solid(cx, cy) for cy in rows):
                self.x = (cx + 1) * TILE + self.w / 2
                self.vx, self.hit_wall = 0, True
        # vertical
        prev_bottom = self.y
        self.y += self.vy
        self.on_ground = False
        cols = range(int((self.x - self.w / 2) // TILE), int((self.x + self.w / 2 - 0.01) // TILE) + 1)
        if self.vy > 0:
            cy = int(self.y // TILE)
            land = False
            for cx in cols:
                t = level.at(cx, cy)
                if t in SOLID:
                    land = True
                elif t == ONE_WAY and not self.drop_through and prev_bottom <= cy * TILE + 0.5:
                    land = True
            if land:
                self.y = cy * TILE
                self.vy = 0
                self.on_ground = True
        elif self.vy < 0:
            cy = int((self.y - self.h) // TILE)
            for cx in cols:
                if level.solid(cx, cy):
                    self.y = (cy + 1) * TILE + self.h
                    self.vy = 0
                    bumped = (cx, cy)
                    break
        if self.drop_through:
            self.drop_through -= 1
        return bumped

    def ground_ahead(self, level, direction):
        """Is there floor just in front of the feet? Used by enemies to avoid ledges."""
        fx = self.x + direction * (self.w / 2 + 4)
        return level.standable(int(fx // TILE), int((self.y + 2) // TILE))

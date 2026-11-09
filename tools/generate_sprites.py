"""Regenerate the placeholder art in assets/ (overwrites your edits!)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from fightgame.spritegen import generate_all  # noqa: E402

if __name__ == "__main__":
    pygame.init()
    out = os.path.join(ROOT, "assets")
    generate_all(out)
    print(f"Wrote sprite sheets to {out}")

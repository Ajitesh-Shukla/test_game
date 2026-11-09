"""Sprite sheet layout, shared by the game and the sprite generator.

Each row of a fighter sheet is one animation; each column is one frame
(FRAME_W x FRAME_H pixels). Keep this layout when editing sheets in LibreSprite.
"""

ANIMS = [
    ("idle", 4),
    ("walk", 4),
    ("crouch", 1),
    ("jump", 2),        # 0 = rising, 1 = tucked
    ("lp", 3),          # light punch: startup, active, recovery
    ("hp", 3),          # heavy punch
    ("kick", 3),
    ("sweep", 3),       # crouching kick (hits low)
    ("jump_kick", 1),
    ("special", 3),     # energy blast
    ("block", 2),       # 0 = standing, 1 = crouching
    ("hit", 2),
    ("knockdown", 2),   # 0 = falling, 1 = lying down
    ("win", 2),
]

ANIM_ROW = {name: row for row, (name, _) in enumerate(ANIMS)}
MAX_FRAMES = max(count for _, count in ANIMS)

"""Global constants for Pixel Brawl."""

WIDTH, HEIGHT = 960, 540
FPS = 60

# Sprites are authored small (pixel art) and scaled up by SCALE when drawn.
SCALE = 3
FRAME_W, FRAME_H = 48, 64       # size of one frame in the sprite sheets
ANCHOR_X = 21                   # frame column that sits on the fighter's x position
FOOT_ROW = 63                   # frame row just under the fighter's feet

GROUND_Y = 480                  # screen y of the floor
STAGE_LEFT, STAGE_RIGHT = 40, WIDTH - 40

GRAVITY = 0.85
MAX_HEALTH = 1000
ROUND_TIME = 99                 # seconds
ROUNDS_TO_WIN = 2               # best of 3

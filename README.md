# Pixel Brawl

A small, original 2D action game made with **Python + Pygame**, with two modes:

- **Adventure**: a side-scrolling platformer. Run and jump through 3 levels while
  stomping enemies, breaking crates, collecting gems, dodging spikes and pits, and
  fighting masked martial artists. Your rival waits at the end of level 3.
- **Versus CPU**: a one-on-one fighting game, best of 3 rounds.

## Run it

You need Python 3.9 or newer.

```bash
pip install -r requirements.txt
python main.py
```

On macOS, use `python3` and `python3 -m pip install --user pygame`.

Watch the CPU fight itself in versus mode: `python main.py --demo`

## Controls

| Action | Keys |
|---|---|
| Move | ← → or A / D |
| Jump (hold for higher) | ↑, W or **Space** |
| Crouch | ↓ or S |
| Light punch / Heavy punch / Kick | **J / K / L** (or Z / X / C) |
| Sweep (hits low) | ↓ + Kick |
| Jump kick | Kick (or punch) in the air |
| **Energy blast** | ↓ ↘ → + Punch (or ↓ ↙ ← + Punch to fire left) |
| Pause / Fullscreen / Back | Enter / F11 / Esc |

### Adventure tips

- **Stomp** small horned blobs by landing on them, or punch them.
- **Block** a fighter's attacks by **crouching while facing them**.
- **Crates**: jump into them from below, kick them, or sweep the low ones. Each one holds a gem.
- **Down + Jump** drops you through a wooden plank.
- Every **50 gems** gives you an extra life. Hearts restore health.
- Light lanterns (**checkpoints**) so you respawn there if you lose a life.
- The gate at the end of level 3 stays sealed until you beat your rival.

### Versus tips

Hold **back** to block (down-back against sweeps). A punch that connects can be
cancelled into the blast.

## Making your own levels

Levels are plain text in `levels/`, edited in any text editor. One character
is one 32×32 tile, and the ground's top row is row 15 of 17.

```
.  empty            #  ground            S  stone block
=  wooden plank (jump up through it)     X  crate (holds a gem)
^  spikes           o  gem               H  heart
g  blob enemy       f  masked fighter    K  boss (your rival)
C  checkpoint       P  player start      E  goal gate (its bottom-left tile)
```

Put enemies, pickups, `P`, `C` and `E` on the row just above a surface. The hero
is about 3¼ tiles tall and jumps about 5 tiles high, so leave at least 4 empty rows
under solid blocks they should walk beneath. To add a level, add its file name
to `LEVEL_FILES` in `fightgame/adventure/scene.py`.

## Editing the art in LibreSprite

All art is plain PNG in `assets/`. The game only creates files that are
**missing**, so your edits are never overwritten when it starts.

| File | Contents |
|---|---|
| `kai.png`, `rhea.png`, `shade.png` | Fighter sheets: hero / rival, and the masked enemy |
| `*_blast.png` | Energy blast, 2 frames of 24×16 |
| `tiles.png` | 16×16 tiles in an 8×2 grid: grass, dirt, stone, plank, crate, spikes, gem×2 / heart, lantern off, lantern on, empty heart |
| `grunt.png` | Blob enemy, 3 frames of 16×16 (walk, walk, squashed) |
| `goal.png` | Goal gate, 48×64 |
| `adventure_bg.png` | Adventure background, 320×180. It scrolls, so keep the left and right edges matching |
| `stage.png` | Versus background, 320×180 |

Fighter sheets are a grid of **48×64 frames**. Each row is one animation, each
column one frame, and fighters are drawn **facing right** with feet on y = 62:

| Row | Animation | Frames |
|---|---|---|
| 0 | idle | 4 |
| 1 | walk | 4 |
| 2 | crouch | 1 |
| 3 | jump (rising, tucked) | 2 |
| 4 | light punch (startup, hit, recovery) | 3 |
| 5 | heavy punch | 3 |
| 6 | kick | 3 |
| 7 | sweep | 3 |
| 8 | jump kick | 1 |
| 9 | energy blast | 3 |
| 10 | block (standing, crouching) | 2 |
| 11 | hit | 2 |
| 12 | knockdown (falling, lying) | 2 |
| 13 | win | 2 |

In LibreSprite, set *View → Grid → Grid Settings* to 48×64 (or 16×16 for tiles).
`python tools/generate_sprites.py` regenerates **all** placeholder art and
**overwrites** your edits.

## Project layout

```
main.py                     entry point
levels/level1-3.txt         Adventure levels (plain text)
fightgame/
  game.py                   app loop, title & select screens, Versus fight scene
  fighter.py                Versus fighter: states, physics, hit/hurt boxes
  moves.py                  frame data shared by both modes
  characters.py             fighter stats
  ai.py                     Versus CPU opponent
  adventure/
    scene.py                Adventure mode: level flow, camera, interactions, HUD
    actors.py               hero, blob enemy, enemy fighter / boss, blasts, pickups
    level.py                level file loader and tile collision
  anims.py, sprites.py      sprite sheet layout and loading
  spritegen.py              placeholder art generator
tests/
  smoke_test.py             Versus mode, CPU vs CPU
  adventure_test.py         Adventure mechanics, plus a bot that clears every level
```

## Test

```bash
python tests/adventure_test.py
python tests/smoke_test.py
```

"""Headless checks for Adventure mode.

    python tests/adventure_test.py
"""
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fightgame.adventure.actors import Grunt  # noqa: E402
from fightgame.adventure.level import TILE  # noqa: E402
from fightgame.adventure.scene import AdventureScene, LEVEL_FILES  # noqa: E402
from fightgame.characters import CHARACTERS  # noqa: E402
from fightgame.fighter import Input  # noqa: E402
from fightgame.game import App  # noqa: E402


class Scripted:
    """Stands in for the keyboard: returns whatever input we set."""

    def __init__(self):
        self.next = Input()

    def feed(self, events):
        pass

    def reset(self):
        pass

    def get_input(self, *args):
        return self.next


def new_scene(app, level=0):
    sc = AdventureScene(app, CHARACTERS[0])
    sc.ctrl = Scripted()
    if level:
        sc.level_index = level
        sc.load_level()
        sc.ctrl = Scripted()
    sc.phase = "play"
    return sc


def run(sc, frames, inp=None):
    for _ in range(frames):
        if inp is not None:
            sc.ctrl.next = inp
        sc.update()
        sc.draw(sc.app.screen)


def settle(sc):
    run(sc, 30, Input())


def test_stomp(app):
    sc = new_scene(app)
    settle(sc)
    h = sc.hero
    g = Grunt(h.x, h.y, sc.grunt_frames)
    g.awake = False
    sc.grunts = [g]
    h.y -= 200
    h.vy = 2
    score = sc.score
    run(sc, 30, Input())
    assert not g.alive, "grunt should be stomped"
    assert h.hp == h.MAX_HP, "stomping must not hurt"
    assert sc.score > score


def test_grunt_hurts_from_side(app):
    sc = new_scene(app)
    settle(sc)
    h = sc.hero
    g = Grunt(h.x + 30, h.y, sc.grunt_frames)
    sc.grunts = [g]
    run(sc, 3, Input())
    assert h.hp == h.MAX_HP - 1, h.hp


def test_crate_bump_and_punch(app):
    sc = new_scene(app)
    lv = sc.level
    crates = [(cx, cy) for cy in range(lv.rows) for cx in range(lv.cols) if lv.grid[cy][cx] == "X"]
    cx, cy = crates[0]                       # level 1's first crates are overhead
    settle(sc)
    sc.hero.x = cx * TILE + TILE / 2
    run(sc, 2, Input(up=True))
    run(sc, 30, Input())
    assert lv.grid[cy][cx] == ".", "jumping into a crate should break it"
    assert any(p.kind == "gem" for p in sc.pickups)
    # sweep (Down + Kick) a single crate standing on the ground
    gx, gy = next((x, y) for x, y in crates if y == 14)
    sc.hero.x = gx * TILE - 30
    sc.hero.facing = 1
    run(sc, 1, Input(down=True, pressed={"kick"}))
    run(sc, 25, Input())
    assert lv.grid[gy][gx] == ".", "sweeping a crate should break it"


def test_fight_enemy(app):
    sc = new_scene(app)
    settle(sc)
    e = next(e for e in sc.enemies if not e.boss)
    sc.enemies = [e]
    e.block_chance = 0
    sc.hero.x = e.x - 70
    sc.hero.facing = 1
    for i in range(400):
        run(sc, 1, Input(pressed={"hp"} if i % 20 == 0 else ()))
        sc.hero.hp = sc.hero.MAX_HP
        sc.hero.x = e.x - 70
        if not sc.enemies or e.hp == 0:
            break
    assert e.hp == 0, f"enemy should be beaten, hp={e.hp}"


def test_enemy_hits_and_block(app):
    sc = new_scene(app)
    settle(sc)
    e = next(e for e in sc.enemies if not e.boss)
    sc.enemies = [e]
    h = sc.hero
    h.x = e.x - 70
    run(sc, 200, Input())
    assert h.hp < h.MAX_HP, "standing still next to a fighter should get you hit"
    sc2 = new_scene(app)
    settle(sc2)
    e2 = next(e for e in sc2.enemies if not e.boss)
    sc2.enemies = [e2]
    h2 = sc2.hero
    h2.x = e2.x - 70
    h2.facing = 1
    run(sc2, 200, Input(down=True))
    assert h2.hp == h2.MAX_HP, "crouching toward the fighter should block everything"


def test_spikes(app):
    sc = new_scene(app)
    lv = sc.level
    sx, sy = next((x, y) for y in range(lv.rows) for x in range(lv.cols) if lv.grid[y][x] == "^")
    settle(sc)
    sc.hero.x = sx * TILE + TILE / 2
    sc.hero.y = (sy + 1) * TILE - 40
    run(sc, 10, Input())
    assert sc.hero.hp == sc.hero.MAX_HP - 1


def test_pit_death_and_checkpoint(app):
    sc = new_scene(app)
    settle(sc)
    c = sc.checkpoints[0]
    sc.hero.x = c["cx"] * TILE + TILE / 2
    run(sc, 5, Input())
    assert sc.checkpoint == (c["cx"], c["cy"]), "checkpoint should activate"
    lives = sc.lives
    sc.hero.y = sc.level.height + 100
    run(sc, 140, Input())
    assert sc.lives == lives - 1
    assert sc.phase == "intro"
    assert abs(sc.hero.x - (c["cx"] * TILE + TILE / 2)) < 1, "should respawn at checkpoint"


def test_goal_and_boss_gate(app):
    sc = new_scene(app)
    settle(sc)
    sc.hero.x, sc.hero.y = sc.goal.centerx, sc.goal.bottom
    run(sc, 2, Input())
    assert sc.phase == "clear"
    run(sc, 205, Input())
    assert sc.level_index == 1 and sc.phase == "intro"

    sc = new_scene(app, level=len(LEVEL_FILES) - 1)
    settle(sc)
    sc.hero.x, sc.hero.y = sc.goal.centerx, sc.goal.bottom
    sc.hero.invuln = 999
    run(sc, 5, Input())
    assert sc.phase == "play", "gate must stay shut while the boss is alive"
    for e in sc.enemies:
        e.hp = 0
        e.set_state("dead")
    run(sc, 5, Input())
    assert sc.phase == "clear"
    run(sc, 205, Input())
    assert sc.phase == "victory"


def test_special(app):
    sc = new_scene(app)
    settle(sc)
    for inp in (Input(down=True), Input(down=True, left=True), Input(left=True, pressed={"lp"})):
        run(sc, 1, inp)
    run(sc, 15, Input())
    assert sc.shots and sc.shots[0].vx < 0, "blast should fire to the left"


def bot_run(app, level, seed):
    """A dumb bot holds right, jumps at walls/gaps/enemies and punches.
    It is kept alive (hp refilled) to check every level can be traversed."""
    rng = random.Random(seed)
    sc = new_scene(app, level)
    lv = sc.level
    best = 0
    for f in range(60 * 90):
        h = sc.hero
        boss = next((e for e in sc.enemies if e.boss and e.hp > 0), None)
        d = -1 if (boss and h.x > boss.x + 40) else 1      # go back for the boss if we passed it
        ahead_x = int((h.x + 40 * d) // TILE)
        foot_row = int((h.y + 2) // TILE)
        wall = lv.solid(ahead_x, foot_row - 1) or lv.solid(ahead_x, foot_row - 2)
        gap = not lv.standable(ahead_x, foot_row) and not lv.standable(ahead_x + d, foot_row)
        spikes = lv.at(ahead_x, foot_row - 1) == "^" or lv.at(ahead_x + d, foot_row - 1) == "^"
        near = any(abs(e.x - h.x) < 110 and abs(e.y - h.y) < 40 and e.hp > 0 for e in sc.enemies) or \
            any(g.alive and 0 < (g.x - h.x) * d < 120 and abs(g.y - h.y) < 40 for g in sc.grunts)
        jump = h.on_ground and (wall or gap or spikes or rng.random() < 0.01)
        if near and h.on_ground and not (wall or gap):
            jump = False
        press = {"hp"} if (near and f % 14 == 0) else ()
        if not h.on_ground and f % 3 == 0:
            jump = True        # keep holding to jump full height
        sc.ctrl.next = Input(right=d == 1, left=d == -1, up=jump or (not h.on_ground and h.vy < 0), pressed=press)
        sc.update()
        if f % 5 == 0:
            sc.draw(app.screen)
        sc.hero.hp = sc.hero.MAX_HP
        if sc.phase == "intro":
            sc.phase = "play"
        best = max(best, sc.hero.x)
        if sc.phase in ("clear", "victory") or sc.level_index != level:
            return True, best, lv.width
        if sc.phase == "gameover":
            break
    return False, best, lv.width


if __name__ == "__main__":
    app = App()
    tests = [test_stomp, test_grunt_hurts_from_side, test_crate_bump_and_punch, test_fight_enemy,
             test_enemy_hits_and_block, test_spikes, test_pit_death_and_checkpoint,
             test_goal_and_boss_gate, test_special]
    for t in tests:
        t(app)
        print("pass", t.__name__)
    for level in range(len(LEVEL_FILES)):
        done = False
        for seed in range(6):
            ok, best, width = bot_run(app, level, seed)
            if ok:
                done = True
                break
        print(f"bot level {level + 1}: {'cleared' if done else 'STUCK'} (reached x={best:.0f}/{width})")
        assert done, f"bot could not clear level {level + 1}"
    print("OK")

"""Headless check: plays several CPU-vs-CPU matches and a scripted player input
sequence, asserting nothing crashes and matches finish.

    python tests/smoke_test.py
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from fightgame.characters import CHARACTERS  # noqa: E402
from fightgame.fighter import Input  # noqa: E402
from fightgame.game import App, FightScene  # noqa: E402


def play_match(app, seed, level, shots=None):
    scene = FightScene(app, CHARACTERS[seed % 2], CHARACTERS[1 - seed % 2], level,
                       p1_cpu=True, seed=seed)
    app.scene = scene
    for frame in range(60 * 60 * 6):
        scene.handle([])
        scene.update()
        scene.draw(app.screen)
        if shots and frame in shots:
            pygame.image.save(app.screen, shots[frame])
        if scene.phase == "match_over":
            return scene.wins, frame
    raise AssertionError("match never finished")


def test_special_input(app):
    """Down, down-forward, forward + punch must throw a blast."""
    scene = FightScene(app, CHARACTERS[0], CHARACTERS[1], "EASY")
    scene.phase = "fight"
    f = scene.f1
    seq = [Input(down=True), Input(down=True, right=True), Input(right=True, pressed={"lp"})]
    for inp in seq:
        f.update(inp, scene.f2, scene)
    assert f.state == "attack" and f.move.name == "special", (f.state, f.move)
    for _ in range(20):
        f.update(Input(), scene.f2, scene)
    assert scene.projectiles, "blast was not spawned"


if __name__ == "__main__":
    app = App()
    test_special_input(app)
    out = sys.argv[1] if len(sys.argv) > 1 else None
    for seed, level in enumerate(["EASY", "NORMAL", "HARD", "NORMAL"]):
        shots = None
        if out and seed == 1:
            shots = {f: os.path.join(out, f"shot_{f}.png") for f in (90, 400, 900, 1500)}
        wins, frames = play_match(app, seed, level, shots)
        print(f"match {seed} ({level}): wins={wins} in {frames / 60:.0f}s")
    print("OK")

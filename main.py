"""Pixel Brawl - run with:  python main.py   (add --demo to watch CPU vs CPU)"""
import sys

from fightgame.game import App

if __name__ == "__main__":
    App(demo="--demo" in sys.argv).run()

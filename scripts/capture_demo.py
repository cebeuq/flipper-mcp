"""Capture a sequence of real Flipper framebuffer frames while navigating the
menu, and assemble them into an animated GIF.

Usage: python scripts/capture_demo.py assets/demo.gif
"""

import io
import os
import sys
import time

from PIL import Image

from flipper_mcp.device import FlipperDevice

# (key, description) — open the main menu and scroll the app list, then back home.
STEPS = [
    (None, "home"), ("OK", "open menu"),
    ("DOWN", "scroll"), ("DOWN", "scroll"), ("DOWN", "scroll"),
    ("DOWN", "scroll"), ("UP", "scroll back"),
    ("BACK", "home"), (None, "rest"),
]


def frame(dev):
    return Image.open(io.BytesIO(dev.screenshot_png(scale=4))).convert("P")


def main(out="assets/demo.gif"):
    dev = FlipperDevice(prefer="auto")
    dev.connect()
    frames = [frame(dev)]
    for key, _ in STEPS:
        if key:
            dev.press(key, "SHORT")
            time.sleep(0.35)
        frames.append(frame(dev))
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=650, loop=0, optimize=True)
    print(f"wrote {out}: {len(frames)} frames")


if __name__ == "__main__":
    os.makedirs("assets", exist_ok=True)
    main(*(sys.argv[1:] or []))

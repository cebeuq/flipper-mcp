"""Prove the MCP talks to a real Flipper on this machine (any OS).

Usage: python scripts/verify_device.py [out.png]
"""

import sys

from flipper_mcp.device import FlipperDevice


def main(out="flipper_screenshot.png"):
    dev = FlipperDevice(prefer="auto")
    print("status:", dev.status())
    dev.connect()
    info = dev.device_info()
    print("device_info keys:", sorted(info)[:8], "...")
    print("model:", info.get("hardware_model") or info.get("hardware_name"))
    png = dev.screenshot_png(scale=4)
    with open(out, "wb") as f:
        f.write(png)
    print(f"screenshot: {len(png)} bytes -> {out}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

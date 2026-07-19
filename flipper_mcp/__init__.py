"""flipper-mcp: an MCP server + Python toolkit for the Flipper Zero.

Talks to a Flipper Zero over its USB virtual-COM CLI, using either a real serial
port (pyserial) or a raw WinUSB/libusb transport (pyusb) when no COM port exists.
"""

__version__ = "0.1.0"

FLIPPER_VID = 0x0483
FLIPPER_PID = 0x5740

__all__ = ["__version__", "FLIPPER_VID", "FLIPPER_PID"]

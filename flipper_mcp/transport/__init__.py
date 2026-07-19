"""Transport layer: byte-stream links to a Flipper Zero (serial or raw USB)."""

from .base import Transport, TransportError
from .discovery import (
    find_serial_ports,
    open_transport,
    usb_present,
    describe_available,
)

__all__ = [
    "Transport",
    "TransportError",
    "find_serial_ports",
    "open_transport",
    "usb_present",
    "describe_available",
]

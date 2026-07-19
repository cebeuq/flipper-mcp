"""Length-delimited protobuf framing over a byte transport.

Frames are ``varint(len) || Main`` — identical to protobuf's writeDelimitedTo /
parseDelimitedFrom. A single desync is unrecoverable, so keep varint handling exact.
"""

from __future__ import annotations

import time

from ..transport.base import Transport, TransportError


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint must be non-negative")
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


class FrameReader:
    """Buffers a transport and reads exact byte counts / varints with timeouts."""

    def __init__(self, transport: Transport):
        self._t = transport
        self._buf = bytearray()

    def _fill(self, timeout_ms: int = 150) -> bool:
        chunk = self._t.read(4096, timeout_ms)
        if chunk:
            self._buf += chunk
            return True
        return False

    def read_exact(self, n: int, timeout_s: float) -> bytes:
        start = time.monotonic()
        while len(self._buf) < n:
            if time.monotonic() - start > timeout_s:
                raise TransportError(f"timeout reading {n} bytes (have {len(self._buf)})")
            self._fill()
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    def read_varint(self, timeout_s: float) -> int:
        start = time.monotonic()
        result = shift = 0
        while True:
            if not self._buf:
                if time.monotonic() - start > timeout_s:
                    raise TransportError("timeout reading varint length prefix")
                self._fill()
                continue
            b = self._buf[0]
            del self._buf[:1]
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                return result & 0xFFFFFFFF
            shift += 7

    def discard(self, seconds: float) -> bytes:
        """Read and drop bytes for a fixed time (used to eat the CLI echo)."""
        out = bytearray(self._buf)
        self._buf.clear()
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            chunk = self._t.read(4096, 100)
            if chunk:
                out += chunk
        return bytes(out)

"""Abstract byte-stream transport to a Flipper Zero."""

from __future__ import annotations

import abc


class TransportError(Exception):
    """Raised when a transport cannot be opened or a link operation fails."""


class Transport(abc.ABC):
    """A raw, bidirectional byte pipe to the Flipper's CDC endpoint.

    Implementations carry exactly the same byte stream the USB virtual COM port
    would: the text CLI and, after ``start_rpc_session``, the protobuf RPC frames.
    """

    #: short transport kind, e.g. "serial" or "usb"
    kind: str = "transport"

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        """Write all bytes to the device."""

    @abc.abstractmethod
    def read(self, size: int = 4096, timeout_ms: int = 200) -> bytes:
        """Return up to ``size`` bytes, waiting at most ``timeout_ms``.

        Returns ``b""`` on timeout (never raises for an idle link). Partial
        reads are fine; callers loop until they have what they need.
        """

    def set_control_lines(self, dtr: bool = True, rts: bool = True) -> None:
        """Assert DTR/RTS. The Flipper CLI only starts once DTR is active."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release the underlying handle."""

    @property
    def description(self) -> str:
        return self.kind

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

"""Flipper Zero text-CLI protocol driver.

Drives the interactive serial CLI: sends commands, reads until the ``>: `` prompt
returns, strips ANSI, recovers from nested sub-shells (``nfc`` opens ``[nfc]>: ``),
and stops streaming commands (``log``, ``subghz rx``, ``ir rx``) with Ctrl+C.
"""

from __future__ import annotations

import re
import time

from .transport.base import Transport, TransportError

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SUBSHELL_LINE = re.compile(r"^\[[^\]]+\]\s*>:$")
_CTRL_C = b"\x03"
PROMPT = ">: "


def _clean(raw: bytes) -> str:
    return _ANSI.sub("", raw.decode("utf-8", errors="replace")).replace("\r", "")


def _last_line(cleaned: str) -> str:
    lines = cleaned.rstrip().split("\n")
    return lines[-1].strip() if lines else ""


def _at_prompt(cleaned: str) -> bool:
    return _last_line(cleaned).endswith(">:")


def _is_subshell(cleaned: str) -> bool:
    return bool(_SUBSHELL_LINE.match(_last_line(cleaned)))


class FlipperCLI:
    """Owns a transport and speaks the Flipper text CLI over it."""

    def __init__(self, transport: Transport):
        self.transport = transport
        self._opened = False

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> "FlipperCLI":
        self.transport.set_control_lines(dtr=True, rts=True)
        self._drain(1.0, quiet_s=0.4)  # consume the welcome banner
        self.ensure_prompt()
        self._opened = True
        return self

    def close(self) -> None:
        try:
            self.transport.close()
        finally:
            self._opened = False

    # -- low-level read helpers ---------------------------------------------

    def _drain(self, hard_s: float, quiet_s: float = 0.25) -> bytes:
        out = bytearray()
        start = last = time.monotonic()
        while True:
            now = time.monotonic()
            if now - start > hard_s or (out and now - last > quiet_s):
                break
            chunk = self.transport.read(4096, 120)
            if chunk:
                out += chunk
                last = time.monotonic()
        return bytes(out)

    def _read_until_prompt(self, timeout_s: float, quiet_s: float = 0.15) -> bytes:
        out = bytearray()
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            chunk = self.transport.read(4096, 120)
            if chunk:
                out += chunk
                if _at_prompt(_clean(bytes(out))):
                    extra = self.transport.read(4096, 60)
                    if extra:
                        out += extra
                    break
        return bytes(out)

    @staticmethod
    def _extract(raw: bytes, command: str) -> str:
        cleaned = _clean(raw)
        lines = cleaned.split("\n")
        if lines and lines[0].strip() == command.strip():
            lines = lines[1:]
        while lines and (lines[-1].strip() in ("", "^C") or lines[-1].strip().endswith(">:")):
            lines.pop()
        return "\n".join(lines).strip()

    # -- prompt / sub-shell management --------------------------------------

    def ensure_prompt(self, tries: int = 12) -> bool:
        """Return the CLI to the main ``>: `` prompt, exiting any sub-shell."""
        for _ in range(tries):
            self.transport.write(b"\r\n")
            cleaned = _clean(self._drain(0.7))
            if _is_subshell(cleaned):
                self.transport.write(b"exit\r\n")
                self._drain(0.8)
            elif _at_prompt(cleaned):
                return True
            else:
                self.transport.write(_CTRL_C)
                self._drain(0.5)
        return False

    # -- command execution ---------------------------------------------------

    def command(self, text: str, timeout_s: float = 4.0) -> str:
        """Run one CLI command and return its cleaned text output."""
        self.transport.write((text + "\r\n").encode())
        raw = self._read_until_prompt(timeout_s)
        if not _at_prompt(_clean(raw)):
            # Command may have entered a sub-shell or a streamer; recover.
            self.transport.write(_CTRL_C)
            raw += self._drain(0.5)
            self.ensure_prompt()
        return self._extract(raw, text)

    def stream(self, text: str, duration_s: float = 3.0) -> str:
        """Run a streaming command for a fixed time, then Ctrl+C and return output."""
        self.transport.write((text + "\r\n").encode())
        out = bytearray()
        start = time.monotonic()
        while time.monotonic() - start < duration_s:
            chunk = self.transport.read(4096, 150)
            if chunk:
                out += chunk
        self.transport.write(_CTRL_C)
        out += self._drain(0.8)
        self.ensure_prompt()
        return self._extract(bytes(out), text)

    def raw(self, data: bytes) -> None:
        self.transport.write(data)

    def abort(self) -> None:
        self.transport.write(_CTRL_C)
        self._drain(0.4)

    # -- storage helpers (text CLI) -----------------------------------------

    @staticmethod
    def _q(path: str) -> str:
        # The CLI splits args on spaces; the Flipper has no quoting, but paths
        # with spaces are uncommon. Guard against obvious injection of newlines.
        if "\n" in path or "\r" in path:
            raise TransportError("path must not contain newlines")
        return path

    def storage_list(self, path: str = "/ext") -> list[dict]:
        out = self.command(f"storage list {self._q(path)}", timeout_s=6.0)
        entries = []
        for line in out.split("\n"):
            s = line.strip()
            m = re.match(r"^\[([DF])\]\s+(.*?)(?:\s+(\d+)b)?$", s)
            if m:
                entries.append({
                    "type": "dir" if m.group(1) == "D" else "file",
                    "name": m.group(2),
                    "size": int(m.group(3)) if m.group(3) else None,
                })
        return entries

    def storage_stat(self, path: str) -> str:
        return self.command(f"storage stat {self._q(path)}")

    def storage_info(self, path: str = "/ext") -> str:
        return self.command(f"storage info {self._q(path)}")

    def storage_read_text(self, path: str) -> str:
        return self.command(f"storage read {self._q(path)}", timeout_s=8.0)

    def storage_md5(self, path: str) -> str:
        out = self.command(f"storage md5 {self._q(path)}")
        m = re.search(r"\b([0-9a-fA-F]{32})\b", out)
        return m.group(1) if m else out

    def storage_mkdir(self, path: str) -> str:
        return self.command(f"storage mkdir {self._q(path)}")

    def storage_remove(self, path: str) -> str:
        return self.command(f"storage remove {self._q(path)}")

    def storage_rename(self, old: str, new: str) -> str:
        return self.command(f"storage rename {self._q(old)} {self._q(new)}")

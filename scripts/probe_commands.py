"""Introspect the live Flipper CLI over USB to capture exact command syntax.

v3: robust sub-shell recovery. Some commands (nfc, rfid, ir, ...) open a nested
CLI whose prompt is like "[nfc]>: ". We always Ctrl+C after a command and then
send `exit` until we are back at the main ">: " prompt.
Runs only safe, read-only / usage commands.
"""
import re
import sys
import time

import usb.core
import usb.util

VID, PID = 0x0483, 0x5740
ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
CTRL_C = b"\x03"
SUBSHELL_RE = re.compile(r"^\[[^\]]+\]\s*>:")


def backend():
    try:
        import libusb_package
        return libusb_package.get_libusb1_backend()
    except Exception:
        return None


def _clean(raw: bytes) -> str:
    return ANSI.sub(b"", raw).decode("utf-8", errors="replace").replace("\r", "")


def _tail(txt: str) -> str:
    lines = [ln for ln in txt.split("\n")]
    return lines[-1].strip() if lines else ""


def _classify(tail: str) -> str:
    t = tail.strip()
    if SUBSHELL_RE.match(t) or (t.startswith("[") and t.endswith("]")):
        return "subshell"
    if t.endswith(">:"):
        return "main"
    return "other"


class UsbCli:
    def __init__(self):
        self.dev = usb.core.find(idVendor=VID, idProduct=PID, backend=backend())
        if self.dev is None:
            raise SystemExit("Flipper not found")
        try:
            self.dev.set_configuration()
        except Exception:
            pass
        cfg = self.dev.get_active_configuration()
        self.ep_in = self.ep_out = None
        comm = 0
        for intf in cfg:
            if intf.bInterfaceClass == 0x02:
                comm = intf.bInterfaceNumber
            for ep in intf:
                if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK:
                    if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                        self.ep_in = ep
                    else:
                        self.ep_out = ep
        self.dev.ctrl_transfer(0x21, 0x22, 0x03, comm, None)  # DTR|RTS
        self._drain(1.0)
        self.ensure_main()

    def _write(self, data: bytes):
        self.ep_out.write(data, timeout=1000)

    def _drain(self, hard_s, quiet_s=0.3):
        out = bytearray()
        start = last = time.time()
        while True:
            now = time.time()
            if now - start > hard_s or (out and now - last > quiet_s):
                break
            try:
                data = self.ep_in.read(64, timeout=120)
                if data:
                    out += bytes(data)
                    last = time.time()
            except usb.core.USBError:
                pass
        return bytes(out)

    def ensure_main(self, tries=10) -> bool:
        for _ in range(tries):
            self._write(b"\r\n")
            tail = _tail(_clean(self._drain(0.7)))
            kind = _classify(tail)
            if kind == "main":
                return True
            if kind == "subshell":
                self._write(b"exit\r\n")
                self._drain(0.8)
            else:
                self._write(CTRL_C)
                self._drain(0.5)
        return False

    def cmd(self, text, hard_s=2.0):
        self._write((text + "\r\n").encode())
        raw = self._drain(hard_s)
        self._write(CTRL_C)  # abort any streamer
        raw += self._drain(0.4)
        txt = _clean(raw)
        lines = txt.split("\n")
        if lines and lines[0].strip() == text.strip():
            lines = lines[1:]
        # drop trailing prompt / ^C lines
        while lines and (_classify(lines[-1]) in ("main", "subshell")
                         or lines[-1].strip() in ("", "^C")):
            lines.pop()
        self.ensure_main()
        return "\n".join(lines).strip()


def main():
    cli = UsbCli()
    commands = [
        "device_info", "info", "top", "power", "loader", "led", "ir",
        "rfid", "input", "bt", "vibro", "i2c", "js", "buzzer", "onewire",
        "ikey", "sysctl", "crypto", "log", "storage stat /ext",
        "storage info /ext",
    ]
    for c in commands:
        print("\n" + "=" * 70)
        print(f"$ {c}")
        print("-" * 70)
        try:
            print(cli.cmd(c))
        except Exception as e:  # noqa: BLE001
            print(f"<error: {e}>")
    usb.util.dispose_resources(cli.dev)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Probe the Flipper Zero over raw USB (WinUSB) using pyusb + libusb.

Works even when the CDC interface is bound to WinUSB (no COM port), which is the
current state on this machine. Confirms we can find the bulk endpoints and drive
the text CLI directly over USB. Prints device/endpoint info and a device_info dump.
"""
import sys
import time

import usb.core
import usb.util

FLIPPER_VID = 0x0483
FLIPPER_PID = 0x5740

CDC_SET_CONTROL_LINE_STATE = 0x22  # bRequest
DTR = 0x01
RTS = 0x02


def get_backend():
    try:
        import libusb_package
        be = libusb_package.get_libusb1_backend()
        if be:
            return be
    except Exception as e:  # noqa: BLE001
        print(f"[warn] libusb_package backend unavailable: {e}")
    return None  # fall back to system libusb on PATH


def clean(b: bytes) -> str:
    """Strip ANSI escape sequences for readable console output."""
    import re
    txt = b.decode("utf-8", errors="replace")
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", txt)


def main() -> int:
    backend = get_backend()
    dev = usb.core.find(idVendor=FLIPPER_VID, idProduct=FLIPPER_PID, backend=backend)
    if dev is None:
        print("[FAIL] Flipper (0483:5740) not found via libusb.")
        return 2

    print("[OK] Found Flipper device 0483:5740")
    for attr, label in (("iManufacturer", "Manufacturer"),
                        ("iProduct", "Product"),
                        ("iSerialNumber", "Serial")):
        try:
            idx = getattr(dev, attr)
            if idx:
                print(f"  {label}: {usb.util.get_string(dev, idx)}")
        except Exception as e:  # noqa: BLE001
            print(f"  {label}: <err {e}>")

    # Try to (re)set configuration; harmless if already configured.
    try:
        dev.set_configuration()
    except Exception as e:  # noqa: BLE001
        print(f"[info] set_configuration skipped: {e}")

    cfg = dev.get_active_configuration()
    ep_in = ep_out = None
    comm_iface = data_iface = None
    print("Interfaces / endpoints:")
    for intf in cfg:
        print(f"  IF {intf.bInterfaceNumber} class=0x{intf.bInterfaceClass:02x} "
              f"sub=0x{intf.bInterfaceSubClass:02x} proto=0x{intf.bInterfaceProtocol:02x}")
        if intf.bInterfaceClass == 0x02:  # CDC Communications / control
            comm_iface = intf.bInterfaceNumber
        if intf.bInterfaceClass == 0x0A:  # CDC Data
            data_iface = intf.bInterfaceNumber
        for ep in intf:
            ttype = usb.util.endpoint_type(ep.bmAttributes)
            direction = usb.util.endpoint_direction(ep.bEndpointAddress)
            tname = {0: "control", 1: "iso", 2: "bulk", 3: "interrupt"}.get(ttype, "?")
            dname = "IN" if direction == usb.util.ENDPOINT_IN else "OUT"
            print(f"      EP 0x{ep.bEndpointAddress:02x} {tname} {dname}")
            if tname == "bulk":
                if direction == usb.util.ENDPOINT_IN and ep_in is None:
                    ep_in = ep
                elif direction == usb.util.ENDPOINT_OUT and ep_out is None:
                    ep_out = ep

    if ep_in is None or ep_out is None:
        print("[FAIL] Could not locate bulk IN/OUT endpoints.")
        return 3
    print(f"[OK] bulk OUT=0x{ep_out.bEndpointAddress:02x}  bulk IN=0x{ep_in.bEndpointAddress:02x}")

    # Assert DTR so the Flipper CLI treats us as a connected terminal.
    try:
        idx = comm_iface if comm_iface is not None else 0
        dev.ctrl_transfer(0x21, CDC_SET_CONTROL_LINE_STATE, DTR | RTS, idx, None)
        print("[OK] Asserted DTR/RTS (SET_CONTROL_LINE_STATE)")
    except Exception as e:  # noqa: BLE001
        print(f"[info] control line state not accepted (often fine): {e}")

    def drain(total_ms=800):
        chunks = []
        deadline = time.time() + total_ms / 1000.0
        while time.time() < deadline:
            try:
                data = ep_in.read(ep_in.wMaxPacketSize or 64, timeout=200)
                if data:
                    chunks.append(bytes(data))
            except usb.core.USBError:
                pass
        return b"".join(chunks)

    # Consume the welcome banner / prompt.
    banner = drain(1200)
    if banner:
        print("---- banner ----")
        print(clean(banner).strip()[:1200])

    # Send a command and read the response.
    ep_out.write(b"device_info\r\n", timeout=1000)
    time.sleep(0.2)
    resp = drain(1500)
    print("---- device_info ----")
    print(clean(resp).strip()[:4000] if resp else "<no response>")

    usb.util.dispose_resources(dev)
    return 0 if resp else 4


if __name__ == "__main__":
    sys.exit(main())

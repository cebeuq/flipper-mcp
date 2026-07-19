"""Raw USB (WinUSB/libusb) transport via pyusb.

Works when the Flipper's CDC interface is bound to WinUSB and no COM port
exists (the common Windows "Android ADB Interface" situation). libusb speaks
WinUSB natively, so we open the device, find the CDC-Data bulk endpoints, and
exchange the same byte stream usbser.sys would carry. No admin, no driver change.
"""

from __future__ import annotations

import usb.core
import usb.util

from .base import Transport, TransportError

FLIPPER_VID = 0x0483
FLIPPER_PID = 0x5740

# CDC class request: SET_CONTROL_LINE_STATE (asserts DTR/RTS).
_CDC_SET_CONTROL_LINE_STATE = 0x22
_DTR = 0x01
_RTS = 0x02


def get_backend():
    """Return a libusb backend, preferring the bundled libusb-package DLL."""
    try:
        import libusb_package
        import usb.backend.libusb1
        be = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
        if be is not None:
            return be
    except Exception:
        pass
    try:
        import libusb_package
        return libusb_package.get_libusb1_backend()
    except Exception:
        return None  # fall back to a system libusb on PATH


def find_device():
    """Return the pyusb device for the Flipper, or None."""
    return usb.core.find(idVendor=FLIPPER_VID, idProduct=FLIPPER_PID, backend=get_backend())


class UsbTransport(Transport):
    kind = "usb"

    def __init__(self, dev=None):
        self._dev = dev if dev is not None else find_device()
        if self._dev is None:
            raise TransportError(
                "Flipper not found on USB (0483:5740). Is it plugged in and powered on?"
            )
        # The device is already configured by usbccgp on Windows; reconfiguring a
        # composite child fails. Only configure if there is no active config yet.
        try:
            cfg = self._dev.get_active_configuration()
        except (usb.core.USBError, NotImplementedError):
            try:
                self._dev.set_configuration()
            except Exception as e:  # noqa: BLE001
                raise TransportError(f"could not configure Flipper USB device: {e}")
            cfg = self._dev.get_active_configuration()

        data_if = usb.util.find_descriptor(cfg, bInterfaceClass=0x0A)  # CDC Data
        comm_if = usb.util.find_descriptor(cfg, bInterfaceClass=0x02)  # CDC Control
        if data_if is None:
            raise TransportError("CDC data interface (class 0x0A) not found")
        self._comm_ifnum = comm_if.bInterfaceNumber if comm_if is not None else 0

        self._ep_out = usb.util.find_descriptor(
            data_if,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_OUT,
        )
        self._ep_in = usb.util.find_descriptor(
            data_if,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_IN,
        )
        if self._ep_out is None or self._ep_in is None:
            raise TransportError("CDC bulk IN/OUT endpoints not found")

        self._data_ifnum = data_if.bInterfaceNumber
        try:
            usb.util.claim_interface(self._dev, self._data_ifnum)
        except Exception:
            pass  # libusb auto-claims on first transfer on Windows
        self._read_sz = int(self._ep_in.wMaxPacketSize) or 64

    def write(self, data: bytes) -> None:
        if data:
            self._ep_out.write(data, timeout=3000)

    def read(self, size: int = 4096, timeout_ms: int = 200) -> bytes:
        # Read a single max-packet; libusb loses partial data on a timeout, so
        # never request more than one packet per call. Callers loop.
        try:
            data = self._ep_in.read(self._read_sz, timeout=timeout_ms)
            return bytes(data)
        except usb.core.USBTimeoutError:
            return b""
        except usb.core.USBError as e:
            msg = str(e).lower()
            if "timeout" in msg or "timed out" in msg or e.errno in (110, None):
                return b""
            raise TransportError(f"USB read failed: {e}")

    def set_control_lines(self, dtr: bool = True, rts: bool = True) -> None:
        value = (_DTR if dtr else 0) | (_RTS if rts else 0)
        try:
            self._dev.ctrl_transfer(0x21, _CDC_SET_CONTROL_LINE_STATE, value,
                                    self._comm_ifnum, None)
        except Exception:
            pass  # some stacks reject it; the CLI usually still works

    def close(self) -> None:
        try:
            self.set_control_lines(dtr=False, rts=False)
        except Exception:
            pass
        try:
            usb.util.release_interface(self._dev, self._data_ifnum)
        except Exception:
            pass
        try:
            usb.util.dispose_resources(self._dev)
        except Exception:
            pass

    @property
    def description(self) -> str:
        try:
            name = usb.util.get_string(self._dev, self._dev.iProduct)
            return f"USB {name} (WinUSB/libusb, 0483:5740)"
        except Exception:
            return "USB Flipper Zero (WinUSB/libusb, 0483:5740)"

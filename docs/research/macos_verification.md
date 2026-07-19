# macOS live-device verification

Recorded 2026-07-19 on a real Flipper Zero, proving the serial transport and the
protobuf-RPC screenshot path work natively on macOS (no COM port, no driver changes).

## Environment

- OS: `Darwin 25.5.0 arm64` (macOS, Apple Silicon)
- Python: 3.14
- Device port (auto-detected by VID:PID `0483:5740`): `/dev/cu.usbmodemflip_Ali5aree1`
- qFlipper: closed (only one program may hold the port)

## `flipper_status`

```json
{
  "serial_ports": ["/dev/cu.usbmodemflip_Ali5aree1"],
  "usb_winusb": true,
  "recommended": "serial:/dev/cu.usbmodemflip_Ali5aree1",
  "connected": false
}
```

Both transports detect the device on macOS: the native serial port (used) and the raw
USB path (`usb_winusb: true`) as a fallback.

## `flipper_device_info` (excerpt — 60 fields total)

| Field | Value |
|---|---|
| hardware_model | Flipper Zero |
| hardware_name | Ali5aree |
| firmware_commit | 7432d21a |
| firmware_target | 7 |
| radio_stack_type | 3 |
| protobuf_version | 0.25 |
| uptime | 1h5m24s |

## `flipper_screenshot`

Captured the 128×64 framebuffer over protobuf RPC and decoded it to a PNG:
`2460 bytes`, `PNG image data, 512 x 256, 8-bit grayscale` (128×64 scaled 4×). The image
showed the live desktop (dolphin + status bar), confirming an end-to-end RPC round trip.

## Conclusion

`flipper-mcp` works on macOS out of the box via the serial transport — device info,
power/uptime telemetry, and framebuffer screenshots all verified against real hardware.
The Windows raw-USB/WinUSB path is unchanged (non-regression).

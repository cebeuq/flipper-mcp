# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-07-19 — Initial public release

### Added
- MCP server exposing **35 tools** to control a Flipper Zero over USB (FastMCP).
- **Auto transport selection**: native serial port (macOS/Linux/Windows) with a raw
  **WinUSB/libusb** fallback so it works on Windows even when no `COMx` exists.
- Device info, power/battery telemetry, uptime, ping.
- SD-card storage: list, stat, read, write, upload, mkdir, delete, rename, free space —
  binary-safe chunked transfer over protobuf RPC, md5-verified.
- **Screenshots** (128×64 framebuffer → PNG) and reliable **virtual button presses**.
- Subsystems via CLI: Sub-GHz, NFC, RFID, Infrared (+ universal remotes), GPIO, LED,
  vibro, plus a raw CLI passthrough.
- App control (start/exit/list) and **FAP development**: `fap_scaffold` → `fap_build`
  → `fap_deploy` (build with `ufbt`, upload over USB, launch) — no COM port required.
- Cross-platform verification script and a demo captured from a real device.
- PyPI packaging, CI matrix (macOS/Linux/Windows × Python 3.10–3.13), MIT license.

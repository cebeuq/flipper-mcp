# Setup guide

`flipper-mcp` runs the same on **macOS, Linux, and Windows**. The only real
difference is how the Flipper's USB interface shows up to the OS.

## 1. Install

```bash
# Instant, no install (once published to PyPI):
uvx flipper-mcp

# or into an environment:
pip install flipper-mcp
```

### From source (for development)

```bash
git clone https://github.com/yairhdz24/flipper-mcp.git
cd flipper-mcp
python3 -m venv .venv
# macOS/Linux:
./.venv/bin/python -m pip install -e . pytest ruff
# Windows (PowerShell):
# .\.venv\Scripts\python.exe -m pip install -e . pytest ruff
```

## 2. Connect the Flipper

### macOS

The Flipper appears automatically as `/dev/tty.usbmodemflip_<serial>` — no driver,
no admin. **Close qFlipper first**: only one program can hold the serial port at a
time (otherwise you'll get `Resource busy`).

### Linux

It appears as `/dev/ttyACM0` (or similar). Add yourself to the `dialout` group if you
hit a permissions error:

```bash
sudo usermod -aG dialout "$USER"   # then log out/in
```

Close qFlipper before using `flipper-mcp`.

### Windows

Two cases, both handled automatically (`FLIPPER_TRANSPORT=auto`):

1. A real `COMx` port exists → the serial transport is used (works with qFlipper too).
2. The USB interface is bound to **WinUSB** (Google's ADB driver, no `COMx`) → the raw
   USB transport (`pyusb`/`libusb`) is used directly on the bulk endpoints. **No admin,
   no driver change.**

If you *want* a real COM port back (for qFlipper / `ufbt launch`), run the diagnostic:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\fix-flipper-driver.ps1
# Apply the fix (self-elevates):
powershell -ExecutionPolicy Bypass -File scripts\fix-flipper-driver.ps1 -Apply
```

See [`docs/research/driver_fix.md`](research/driver_fix.md) for the full story.

## 3. Register with Claude Code

**macOS / Linux:**

```bash
claude mcp add --transport stdio --scope user \
  --env FLIPPER_TRANSPORT=auto \
  flipper -- flipper-mcp
```

**Windows (PowerShell):**

```powershell
claude mcp add --transport stdio --scope user `
  --env FLIPPER_TRANSPORT=auto `
  flipper -- flipper-mcp
```

Check `/mcp` inside Claude Code. If you cloned from source instead of installing the
console script, point the command at the venv interpreter and module, e.g.
`-- /abs/path/.venv/bin/python -m flipper_mcp` (macOS/Linux) or
`-- C:\abs\path\.venv\Scripts\python.exe -m flipper_mcp` (Windows), adding
`--env PYTHONPATH=/abs/path` so the package is importable.

## 4. Environment overrides

| Variable | Values | Meaning |
|---|---|---|
| `FLIPPER_TRANSPORT` | `auto` (default), `serial`, `usb` | Force a transport, or auto-select serial → raw USB |
| `FLIPPER_COM_PORT` | e.g. `COM5`, `/dev/tty.usbmodemflip_xxxx` | Force a specific serial port |

## 5. Verify it works

```bash
./.venv/bin/python scripts/verify_device.py /tmp/flipper.png
```

Expected: a `status` dict listing your serial port, a `device_info` model line, and a
saved PNG screenshot.

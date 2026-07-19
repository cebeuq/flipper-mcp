# flipper-mcp Standalone — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Flipper Zero MCP server into a polished, cross-platform (macOS + Windows + Linux), PyPI-ready public GitHub repo built to attract stars.

**Architecture:** Copy the working Python package from the original Windows-built folder into the fresh repo at `/Users/mac/Desktop/flipper-mcp/` (git already initialized), verify it live on macOS against the connected Flipper, record a real demo GIF from the device framebuffer, polish the 35-tool MCP interface, add PyPI packaging + CI, then publish public as `github.com/yairhdz24/flipper-mcp`. The Python code's internal structure is NOT restructured (don't break what works); changes are packaging, docs, interface copy, and cross-platform polish.

**Tech Stack:** Python ≥3.10, FastMCP (`mcp>=1.27,<2`), pyserial (cross-platform serial), pyusb + libusb-package (Windows WinUSB fallback), protobuf, Pillow (screenshots + GIF), ufbt (FAP builds), pytest + ruff (dev), GitHub Actions (CI), `gh` CLI (publish).

## Global Constraints

- **Source of truth (original code):** `/Users/mac/Desktop/flipper-zero-Utils/flipper-mcp/` — copy from here; leave it untouched (non-destructive).
- **Target repo:** `/Users/mac/Desktop/flipper-mcp/` (git already initialized, user `yairhdz24` / yairhdz107@gmail.com, 2 spec commits present).
- **Author identity everywhere:** `Yair Hernández`, GitHub `@yairhdz24`, repo `github.com/yairhdz24/flipper-mcp`.
- **License:** MIT © 2026 Yair Hernández.
- **Windows non-regression:** never modify `transport/usb.py` logic or `scripts/fix-flipper-driver.ps1` in a way that breaks the Windows WinUSB/serial path. Windows cannot be tested live this session; guarantee by non-regression + docs.
- **macOS live device:** Flipper connected at `/dev/tty.usbmodemflip_Ali5aree1` (VID 0x0483, PID 0x5740). Use the serial transport (default auto-select).
- **35 tools** — exact count; the smoke test asserts this number.
- **Never commit:** `.venv/`, `dist/`, `build/`, `__pycache__/`, `.DS_Store` (already in `.gitignore`).
- **PyPI upload is manual** (Yair's token) — plan prepares everything; does not run the upload.
- **No third-party payloads / no `D4rkDr4gon` content** in this repo.

---

### Task 1: Import and restructure the source tree

**Files:**
- Create (copy): `flipper_mcp/` (whole package), `proto/`, `scripts/`, `pyproject.toml`, `requirements.txt`, `run_server.py`
- Create (copy): `docs/research/` (5 protocol notes)
- Create (move): `examples/mcp_demo/` (from original `apps/mcp_demo/`)
- Do NOT copy: `.venv/`, `.mcp.json` (empty), any `__pycache__/`, `apps/` (working dir, created on demand by `fap_scaffold`)

**Interfaces:**
- Produces: the repo now contains an importable `flipper_mcp` package at repo root, so `_APPS_DIR` in `server.py:34` resolves to `<repo>/apps` (created on demand). The demo lives at `examples/mcp_demo/` for README showcase.

- [ ] **Step 1: Copy the package and support files (excluding venv/pycache)**

```bash
SRC=/Users/mac/Desktop/flipper-zero-Utils/flipper-mcp
DST=/Users/mac/Desktop/flipper-mcp
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  "$SRC/flipper_mcp" "$SRC/proto" "$SRC/scripts" "$DST/"
cp "$SRC/pyproject.toml" "$SRC/requirements.txt" "$SRC/run_server.py" "$DST/"
mkdir -p "$DST/docs/research"
cp "$SRC/docs/research/"*.md "$DST/docs/research/"
```

- [ ] **Step 2: Move the demo app into examples/**

```bash
DST=/Users/mac/Desktop/flipper-mcp
mkdir -p "$DST/examples"
rsync -a --exclude '__pycache__' --exclude 'dist' \
  "/Users/mac/Desktop/flipper-zero-Utils/flipper-mcp/apps/mcp_demo" "$DST/examples/"
```

- [ ] **Step 3: Verify the tree looks right**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp && find . -path ./.git -prune -o -type f -print | grep -v __pycache__ | sort
```
Expected: `flipper_mcp/server.py`, `flipper_mcp/rpc/proto/*_pb2.py` present, `examples/mcp_demo/mcp_demo.c` present, NO `.venv`, NO `.pyc`.

- [ ] **Step 4: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add -A
git commit -m "feat: import flipper_mcp package, proto, scripts, demo, research notes"
```

---

### Task 2: Recreate the venv on macOS and prove the package imports

**Files:**
- Create: `.venv/` (gitignored)

**Interfaces:**
- Produces: `.venv/bin/python` with all deps, able to `import flipper_mcp.server` — the interpreter every later device/test step uses.

- [ ] **Step 1: Create venv and install (editable)**

```bash
cd /Users/mac/Desktop/flipper-mcp
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e . pytest ruff
```

- [ ] **Step 2: Verify import + entry point resolve (no device needed)**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
./.venv/bin/python -c "import flipper_mcp.server as s; print('tools:', len(s.mcp._tool_manager.list_tools()))"
```
Expected: prints `tools: 35` (server imports cleanly; connection is lazy so no device required).

> If the attribute path `mcp._tool_manager.list_tools()` differs in the installed FastMCP version, discover the correct accessor with `./.venv/bin/python -c "import flipper_mcp.server as s; print([a for a in dir(s.mcp) if 'tool' in a.lower()])"` and use it consistently in Task 3.

- [ ] **Step 3: No commit** (venv is gitignored; nothing to commit here).

---

### Task 3: Tool-registration smoke test (interface guardrail)

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_tools.py`

**Interfaces:**
- Consumes: `flipper_mcp.server.mcp` (the FastMCP instance).
- Produces: `pytest` target that asserts 35 tools exist, each has a name and a non-empty description — the CI smoke test and the interface-polish guardrail.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools.py
"""Smoke tests: the MCP server registers all tools with usable descriptions.
Runs without a Flipper attached (connections are lazy)."""
import flipper_mcp.server as server


def _tools():
    # FastMCP exposes registered tools via the tool manager.
    return server.mcp._tool_manager.list_tools()


def test_registers_exactly_35_tools():
    assert len(_tools()) == 35


def test_every_tool_has_name_and_nonempty_description():
    for t in _tools():
        assert t.name, "a tool is missing a name"
        assert t.description and len(t.description.strip()) >= 20, (
            f"tool {t.name!r} has a too-short/empty description"
        )


def test_expected_core_tools_present():
    names = {t.name for t in _tools()}
    for expected in {
        "flipper_status", "flipper_connect", "flipper_device_info",
        "flipper_screenshot", "flipper_press", "flipper_cli",
        "fap_scaffold", "fap_build", "fap_deploy",
    }:
        assert expected in names, f"missing tool {expected}"
```

- [ ] **Step 2: Run to verify it passes (import already works from Task 2)**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp && ./.venv/bin/python -m pytest tests/test_tools.py -v
```
Expected: 3 passed. If `test_registers_exactly_35_tools` fails with a different count, reconcile the count in the Global Constraints and README before proceeding (it must be internally consistent).

- [ ] **Step 3: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add tests/
git commit -m "test: smoke test asserting 35 tools registered with descriptions"
```

---

### Task 4: Live macOS device verification (acceptance gate A)

**Files:**
- Create: `scripts/verify_device.py`
- Create: `docs/research/macos_verification.md` (evidence)

**Interfaces:**
- Consumes: `flipper_mcp.device.FlipperDevice` (facade: `.connect()`, `.status()`, `.device_info()`, `.screenshot_png()`).
- Produces: proof the serial transport works on macOS + a saved screenshot PNG.

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_device.py
"""Prove the MCP talks to a real Flipper on this machine (any OS).
Usage: python scripts/verify_device.py [out.png]"""
import sys
from flipper_mcp.device import FlipperDevice


def main(out="flipper_screenshot.png"):
    dev = FlipperDevice(prefer="auto")
    print("status:", dev.status())
    dev.connect()
    info = dev.device_info()
    print("device_info keys:", sorted(info)[:8], "...")
    print("model:", info.get("hardware_model") or info.get("hardware_name"))
    png = dev.screenshot_png(scale=4)
    with open(out, "wb") as f:
        f.write(png)
    print(f"screenshot: {len(png)} bytes -> {out}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
```

- [ ] **Step 2: Run it against the connected Flipper**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
./.venv/bin/python scripts/verify_device.py /tmp/flipper_verify.png && file /tmp/flipper_verify.png
```
Expected: prints a `status` dict showing `serial_ports` including `/dev/tty.usbmodemflip_Ali5aree1`, a `device_info` model line, `screenshot: <N> bytes`, and `file` reports `PNG image data`. If it errors with "could not open ... holding it", ensure qFlipper is closed and retry.

- [ ] **Step 3: Record evidence**

Write `docs/research/macos_verification.md` containing: the OS (`macOS`, `uname -a` output), the exact `status`/`device_info`/`model`/`firmware` values printed, and a note that the screenshot decoded to a valid PNG. (Real captured values — no placeholders.)

- [ ] **Step 4: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add scripts/verify_device.py docs/research/macos_verification.md
git commit -m "feat: macOS live device verification script + evidence"
```

---

### Task 5: Capture the real demo GIF (acceptance gate B)

**Files:**
- Create: `scripts/capture_demo.py`
- Create: `assets/demo.gif`

**Interfaces:**
- Consumes: `FlipperDevice.connect()`, `.press(key, type)`, `.screenshot_png(scale)`; Pillow.
- Produces: `assets/demo.gif` — the README hero, built from real framebuffer frames.

- [ ] **Step 1: Write the capture+assemble script**

```python
# scripts/capture_demo.py
"""Capture a sequence of real Flipper framebuffer frames while navigating the
menu, and assemble them into an animated GIF. Usage: python scripts/capture_demo.py assets/demo.gif"""
import io, sys, time
from PIL import Image
from flipper_mcp.device import FlipperDevice

# (key, description) — a short, legible tour of the UI.
STEPS = [
    (None, "home"), ("DOWN", "menu"), ("DOWN", "menu"), ("OK", "enter"),
    ("BACK", "back"), ("RIGHT", "nav"), ("LEFT", "nav"), (None, "rest"),
]


def frame(dev):
    return Image.open(io.BytesIO(dev.screenshot_png(scale=4))).convert("P")


def main(out="assets/demo.gif"):
    dev = FlipperDevice(prefer="auto")
    dev.connect()
    frames = [frame(dev)]
    for key, _ in STEPS:
        if key:
            dev.press(key, "SHORT")
            time.sleep(0.35)
        frames.append(frame(dev))
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=650, loop=0, optimize=True)
    print(f"wrote {out}: {len(frames)} frames")


if __name__ == "__main__":
    import os
    os.makedirs("assets", exist_ok=True)
    main(*(sys.argv[1:] or []))
```

- [ ] **Step 2: Run it against the device**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp && ./.venv/bin/python scripts/capture_demo.py assets/demo.gif && file assets/demo.gif
```
Expected: `wrote assets/demo.gif: 9 frames` and `file` reports `GIF image data`. Open it to confirm it shows real menu movement; if frames look identical, increase `time.sleep` or vary `STEPS`.

- [ ] **Step 3: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add scripts/capture_demo.py assets/demo.gif
git commit -m "feat: demo GIF captured from the real device + capture script"
```

---

### Task 6: Polish the MCP interface (acceptance gate C2)

**Files:**
- Modify: `flipper_mcp/server.py` (tool descriptions/instructions only — not behavior)
- Modify: `flipper_mcp/fap.py:17-30` (add macOS/Linux ufbt path fallback)

**Interfaces:**
- Consumes/Produces: same 35 tool names and signatures (no renames — the smoke test and README table depend on them). Only docstrings/`instructions` text and one PATH fallback change.

- [ ] **Step 1: Add macOS/Linux ufbt fallback in fap.py**

In `_ufbt_exe()`, after the existing `shutil.which("ufbt")` check and before the Windows candidates, add POSIX fallbacks so FAP builds find a user-pip-installed ufbt on Mac/Linux:

```python
    # POSIX user-install fallbacks (Mac/Linux)
    for cand in (
        os.path.expanduser("~/.local/bin/ufbt"),
        "/opt/homebrew/bin/ufbt",
        "/usr/local/bin/ufbt",
    ):
        if os.path.exists(cand):
            return cand
```

- [ ] **Step 2: Tighten tool descriptions where they assume Windows**

In `flipper_mcp/server.py`, review each `@mcp.tool()` docstring so no description implies Windows-only behavior. Specifically update the two connection tools to be OS-neutral:

```python
@mcp.tool()
def flipper_connect() -> dict:
    """Open the connection to the Flipper (auto-selects a serial/COM port on any OS, or the raw WinUSB path on Windows when no port exists). Returns connection status."""
```
```python
@mcp.tool()
def flipper_status() -> dict:
    """Report how the Flipper can be reached (serial ports on macOS/Linux/Windows, plus the WinUSB fallback) and whether it is connected. Does not open a connection."""
```

Leave all other descriptions as-is (they are already clear and OS-neutral). Do NOT rename tools or change parameters.

- [ ] **Step 3: Re-run the smoke test (interface still valid)**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp && ./.venv/bin/python -m pytest tests/test_tools.py -v && ./.venv/bin/python -c "import flipper_mcp.fap as f; print('ufbt lookup ok (import)')"
```
Expected: 3 passed; import ok.

- [ ] **Step 4: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add flipper_mcp/server.py flipper_mcp/fap.py
git commit -m "polish: OS-neutral tool descriptions + POSIX ufbt path fallback"
```

---

### Task 7: PyPI-ready packaging metadata

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: a wheel/sdist buildable with `python -m build`, installable via `uvx flipper-mcp` once published. Entry point `flipper-mcp = flipper_mcp.server:main` (already present) is preserved.

- [ ] **Step 1: Rewrite the `[project]` metadata block**

Replace the `[project]` table in `pyproject.toml` with (keep `[build-system]`, `[project.scripts]`, `[project.optional-dependencies]`, and `[tool.setuptools.*]` sections intact):

```toml
[project]
name = "flipper-mcp"
version = "0.1.0"
description = "Control a Flipper Zero from Claude over USB — no COM port needed. Screenshots, RF/NFC/IR/GPIO, and build+deploy your own FAPs, all over USB."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Yair Hernández", email = "yairhdz107@gmail.com" }]
keywords = ["flipper-zero", "flipper", "mcp", "model-context-protocol", "claude", "anthropic", "usb", "protobuf", "ufbt", "nfc", "subghz"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Embedded Systems",
    "Topic :: System :: Hardware",
]
dependencies = [
    "pyserial>=3.5",
    "pyusb>=1.2",
    "libusb-package>=1.0",
    "mcp>=1.27,<2",
    "protobuf>=5",
    "pillow>=10",
]

[project.urls]
Homepage = "https://github.com/yairhdz24/flipper-mcp"
Repository = "https://github.com/yairhdz24/flipper-mcp"
Issues = "https://github.com/yairhdz24/flipper-mcp/issues"
```

- [ ] **Step 2: Build and verify the artifacts**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
./.venv/bin/python -m pip install build twine
./.venv/bin/python -m build
./.venv/bin/python -m twine check dist/*
```
Expected: builds `flipper_mcp-0.1.0-py3-none-any.whl` + `.tar.gz`; `twine check` reports `PASSED` for both.

- [ ] **Step 3: Check the PyPI name is free**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/flipper-mcp/json
```
Expected: `404` (name free). If `200`, set `name = "flipper-zero-mcp"` in `pyproject.toml` (repo name stays `flipper-mcp`) and note it in the README install section; re-run Step 2.

- [ ] **Step 4: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add pyproject.toml
git commit -m "build: complete PyPI metadata (authors, urls, keywords, classifiers)"
```

---

### Task 8: The killer README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: `assets/demo.gif` (Task 5), tool names from `server.py`, package name from `pyproject.toml`.
- Produces: the repo's front page.

- [ ] **Step 1: Write README.md with this exact structure and copy**

Sections, in order (fill the tool table from `server.py`'s 35 tools, grouped by domain):

1. **Title + hero + badges**
   ```markdown
   # flipper-mcp 🐬

   > Control your **Flipper Zero** from **Claude** (or any MCP client) over USB —
   > **no COM port needed**. Screenshots, RF / NFC / IR / GPIO, and **build & deploy
   > your own apps (FAPs)** — all over USB. Works on **macOS, Linux, and Windows**.

   ![PyPI](https://img.shields.io/pypi/v/flipper-mcp)
   ![Python](https://img.shields.io/pypi/pyversions/flipper-mcp)
   ![License](https://img.shields.io/github/license/yairhdz24/flipper-mcp)
   ![CI](https://github.com/yairhdz24/flipper-mcp/actions/workflows/ci.yml/badge.svg)

   ![demo](assets/demo.gif)
   ```
2. **Why it's different** — bullet the 3 validated differentiators: (a) works with no COM port (raw WinUSB/libusb on Windows; native serial on macOS/Linux), (b) build + deploy your own FAPs over USB with `ufbt`, (c) screenshots + reliable virtual button presses + 35 tools with auto transport selection.
3. **Install (30 seconds)**
   ```markdown
   # Run instantly (no install) once published to PyPI:
   uvx flipper-mcp
   # or with pip:
   pip install flipper-mcp
   ```
4. **Register with Claude Code** — three fenced blocks, one each for macOS/Linux and Windows, using the console entry point after `pip install`:
   - macOS/Linux: `claude mcp add --transport stdio --scope user flipper -- flipper-mcp`
   - Windows: same with the venv/py launcher note.
   - Env overrides table: `FLIPPER_TRANSPORT` = `auto|serial|usb`, `FLIPPER_COM_PORT`.
5. **Tools (35)** — a Markdown table grouped by domain with a one-line purpose each:
   - Connection: `flipper_status`, `flipper_connect`, `flipper_disconnect`
   - System/info: `flipper_device_info`, `flipper_power_info`, `flipper_uptime`, `flipper_ping`, `flipper_reboot`, `flipper_find_my_flipper`
   - CLI: `flipper_cli`, `flipper_cli_stream`
   - Storage: `flipper_list_dir`, `flipper_stat`, `flipper_storage_space`, `flipper_read_file`, `flipper_write_file`, `flipper_upload_file`, `flipper_mkdir`, `flipper_delete`, `flipper_rename`
   - GUI: `flipper_screenshot`, `flipper_press`
   - Radio/subsystems: `flipper_led`, `flipper_vibro`, `flipper_gpio`, `flipper_ir_send`, `flipper_ir_universal`, `flipper_subghz_tx_file`, `flipper_subghz_rx`
   - Apps: `flipper_list_apps`, `flipper_app_start`, `flipper_app_exit`
   - FAP dev: `fap_scaffold`, `fap_build`, `fap_deploy`
6. **Build your own app (FAP)** — the `fap_scaffold → fap_deploy` flow, pointing at `examples/mcp_demo/` as the worked example.
7. **How it works** — 3 sentences: serial CLI + protobuf RPC over USB; auto transport (serial → WinUSB); framebuffer decode. Link `docs/research/`.
8. **Safety & legality** — the RF-transmit warning (verbatim intent from `server.py` instructions): only transmit on frequencies/hardware you are legally authorized to use.
9. **Author** — `Made by [Yair Hernández (@yairhdz24)](https://github.com/yairhdz24)` + License MIT.

- [ ] **Step 2: Verify no Windows-only paths and links resolve**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
grep -n 'C:\\\\' README.md && echo "FAIL: windows path present" || echo "OK: no windows-only paths"
test -f assets/demo.gif && echo "OK: demo gif exists"
grep -c 'yairhdz24' README.md
```
Expected: `OK: no windows-only paths`, `OK: demo gif exists`, and the `@yairhdz24` grep count ≥ 3.

- [ ] **Step 3: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add README.md
git commit -m "docs: killer cross-platform README with demo, install, tools table"
```

---

### Task 9: Supporting docs + project-scope MCP registration

**Files:**
- Create: `docs/setup.md`
- Create: `CONTRIBUTING.md`
- Create: `CHANGELOG.md`
- Create: `LICENSE`
- Create: `.mcp.json`

**Interfaces:**
- Produces: cloneable project-scope MCP registration + standard OSS meta files.

- [ ] **Step 1: LICENSE (MIT)**

Write the standard MIT license text with `Copyright (c) 2026 Yair Hernández`.

- [ ] **Step 2: docs/setup.md**

Cross-platform setup: (a) clone, (b) `python3 -m venv .venv` + install, (c) macOS/Linux vs Windows notes (macOS uses `/dev/tty.usbmodemflip_*` automatically; Windows may need the driver fix — link `scripts/fix-flipper-driver.ps1` and `docs/research/driver_fix.md`), (d) Claude registration for each OS, (e) env overrides.

- [ ] **Step 3: .mcp.json (project scope)**

```json
{
  "mcpServers": {
    "flipper": {
      "type": "stdio",
      "command": "flipper-mcp",
      "env": { "FLIPPER_TRANSPORT": "auto" }
    }
  }
}
```

- [ ] **Step 4: CONTRIBUTING.md + CHANGELOG.md**

CONTRIBUTING: how to set up the dev venv, run `pytest`, run `ruff check`, and the safety expectation for RF tools; credit maintainer `@yairhdz24`. CHANGELOG: `## [0.1.0] - 2026-07-19 — Initial public release` listing the validated features.

- [ ] **Step 5: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add docs/setup.md CONTRIBUTING.md CHANGELOG.md LICENSE .mcp.json
git commit -m "docs: setup guide, contributing, changelog, MIT license, project .mcp.json"
```

---

### Task 10: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `tests/test_tools.py`, `pyproject.toml`.
- Produces: the CI badge referenced in the README.

- [ ] **Step 1: Write ci.yml**

```yaml
name: CI
on:
  push: { branches: [main] }
  pull_request:
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.10", "3.11", "3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python }}" }
      - run: python -m pip install --upgrade pip
      - run: pip install -e . pytest ruff
      - run: ruff check flipper_mcp
      - run: pytest -v
```

- [ ] **Step 2: Verify the smoke test and ruff pass locally (what CI will run)**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
./.venv/bin/ruff check flipper_mcp || echo "review ruff findings; fix or add minimal per-line ignores, do not disable broadly"
./.venv/bin/python -m pytest -v
```
Expected: pytest passes. If `ruff` flags issues, fix them minimally (imports/whitespace) and re-run; keep changes behavior-neutral.

- [ ] **Step 3: Commit**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add .github/workflows/ci.yml
git commit -m "ci: matrix smoke test on macOS/Linux/Windows × py3.10-3.13"
```

---

### Task 11: Secret scan + publish public

**Files:** none created; publishes the repo.

**Interfaces:**
- Consumes: authenticated `gh` CLI (account `yairhdz24`).
- Produces: `github.com/yairhdz24/flipper-mcp` (public) with topics.

- [ ] **Step 1: Scan tracked files for secrets**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
git ls-files -z | xargs -0 grep -nEI '(gho_|ghp_|github_pat_|pypi-AgEI|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|BEGIN (RSA |OPENSSH )?PRIVATE KEY)' && echo "FAIL: potential secret above" || echo "OK: no secrets in tracked files"
git ls-files | grep -E '(^|/)\.env' && echo "FAIL: .env tracked" || echo "OK: no .env tracked"
```
Expected: `OK: no secrets in tracked files` and `OK: no .env tracked`. If anything is flagged, STOP, remove it, and re-run before publishing.

- [ ] **Step 2: Confirm venv/dist are not tracked**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
git ls-files | grep -E '(^\.venv/|^dist/|__pycache__|\.DS_Store)' && echo "FAIL: junk tracked" || echo "OK: clean tree"
```
Expected: `OK: clean tree`.

- [ ] **Step 3: Create the public repo and push**

Run:
```bash
cd /Users/mac/Desktop/flipper-mcp
gh repo create yairhdz24/flipper-mcp --public --source . --remote origin \
  --description "Control your Flipper Zero from Claude over USB — no COM port needed. Screenshots, RF/NFC/IR/GPIO, and build+deploy your own FAPs." --push
```
Expected: repo created, `main` pushed. Confirm with `gh repo view yairhdz24/flipper-mcp --web` (or `--json url`).

- [ ] **Step 4: Add discovery topics**

Run:
```bash
gh repo edit yairhdz24/flipper-mcp --add-topic flipper-zero --add-topic mcp \
  --add-topic model-context-protocol --add-topic claude --add-topic anthropic \
  --add-topic usb --add-topic protobuf --add-topic ufbt
```
Expected: topics set (verify with `gh repo view yairhdz24/flipper-mcp --json repositoryTopics`).

---

### Task 12: Distribution kit (deliverable for the second round)

**Files:**
- Create: `docs/distribution.md`

**Interfaces:**
- Produces: ready-to-paste submission texts + a checklist Yair executes to promote the repo.

- [ ] **Step 1: Write docs/distribution.md**

Include, with actual copy (not placeholders):
- **Registries** (with URLs + submission method): `punkpeye/awesome-mcp-servers` (GitHub PR — draft the one-line entry), `glama.ai/mcp/servers` (auto-indexes GitHub topic `mcp`), `smithery.ai`, `mcp.so`, `PulseMCP`.
- **Community**: a short r/flipperzero post draft, a Flipper Discord `#projects` message draft, and a note to add the repo to `awesome-flipperzero` lists.
- **PyPI publish** (Yair runs it): `./.venv/bin/python -m twine upload dist/*` (or `uv publish`) using his PyPI token; then verify `uvx flipper-mcp` works from a clean shell.
- A one-line differentiator sentence to reuse across all posts.

- [ ] **Step 2: Commit and push**

```bash
cd /Users/mac/Desktop/flipper-mcp
git add docs/distribution.md
git commit -m "docs: distribution + PyPI publish kit"
git push
```

---

## Manual follow-ups for Yair (documented, not executed here)

1. **PyPI upload:** `./.venv/bin/python -m twine upload dist/*` with your PyPI token (see `docs/distribution.md`). Then test `uvx flipper-mcp` from a clean shell.
2. **Submit to registries + community** using `docs/distribution.md`.
3. **`flipper-lab`** (separate repo, later): your payloads + the vendored `D4rkDr4gon` content with attribution — intentionally NOT in this repo.

---

## Self-Review

**Spec coverage:**
- §1 Objetivo / diferenciadores → Tasks 6, 8 (interface + README headline the 3 differentiators). ✓
- §2 Alcance A–F → Task 1 (separate), 2–4 (verify Mac), 5 (GIF), 8–9 (README/docs), 6+C2 (interface), 7+10 (PyPI+CI), 11 (publish), 12 (distribution). ✓
- §3 Estructura → Task 1 (tree) + Tasks 8–10 (README/docs/CI files). ✓ (Deviation: demo at `examples/mcp_demo/`, user FAPs at on-demand `apps/` — rationale in Task 1 to avoid breaking `_APPS_DIR`.)
- §4 Fase A Windows parity → Global Constraints + Task 6 (no usb.py behavior change; OS-neutral copy). ✓
- §4 Fase C2 interface polish → Task 6 + Task 3 smoke test. ✓
- §4 Fase C @yairhdz24 placement → Tasks 7 (pyproject authors/urls), 8 (README author + badges), 9 (contributing/license). ✓
- §5 Risks (device fail, libusb on Mac, secrets, PyPI creds, name collision) → Task 4 gate, Global Constraints (serial on Mac needs no libusb), Task 11 scan, manual follow-up, Task 7 Step 3. ✓
- §6 Non-destructive → Global Constraints + Task 1 copies (never moves) from source. ✓

**Placeholder scan:** No "TBD/TODO". Doc tasks (8, 9, 12) specify exact sections + real copy rather than full verbatim prose; each has concrete acceptance greps. Test/config tasks contain complete code. ✓

**Type/name consistency:** Tool names identical across Tasks 3, 6, 8. `FlipperDevice` methods (`connect`, `status`, `device_info`, `screenshot_png`, `press`) match `device.py`/`server.py` usage. `_tool_manager.list_tools()` accessor introduced in Task 2 Step 2 and reused in Task 3 (with a discovery fallback noted). Package/console name `flipper-mcp` consistent across pyproject, .mcp.json, README. ✓

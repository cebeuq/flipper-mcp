"""Build Flipper apps (FAPs) with ufbt, and read manifests.

ufbt is invoked as a subprocess (it manages its own SDK + ARM toolchain under
~/.ufbt). Building needs no device; deploying a built .fap can go over USB via
FlipperDevice.upload_and_launch, so it works even without a COM port.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess


def _ufbt_exe() -> str:
    exe = shutil.which("ufbt")
    if exe:
        return exe
    # Common fallback: the user's global Scripts dir.
    for cand in (
        os.path.expandvars(r"%APPDATA%\Python\Python312\Scripts\ufbt.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\Scripts\ufbt.exe"),
    ):
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(
        "ufbt not found on PATH. Install it with: python -m pip install --user ufbt"
    )


def run_ufbt(args: list[str], cwd: str, timeout: int = 900) -> dict:
    exe = _ufbt_exe()
    proc = subprocess.run(
        [exe, *args], cwd=cwd, capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "ok": proc.returncode == 0,
    }


def find_fap(app_dir: str) -> str | None:
    faps = glob.glob(os.path.join(app_dir, "dist", "*.fap"))
    return faps[0] if faps else None


def read_manifest(app_dir: str) -> dict:
    """Best-effort parse of application.fam (a Python App(...) call)."""
    path = os.path.join(app_dir, "application.fam")
    if not os.path.exists(path):
        return {}
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    fields = {}
    for key in ("appid", "name", "fap_category", "entry_point", "fap_version",
                "fap_description", "fap_author"):
        m = re.search(rf'{key}\s*=\s*["\']([^"\']*)["\']', text)
        if m:
            fields[key] = m.group(1)
    return fields


def create_app(base_dir: str, appid: str) -> dict:
    """Scaffold a new FAP with `ufbt create` into base_dir/<appid>."""
    if not re.match(r"^[a-z0-9_]+$", appid):
        raise ValueError("appid must match ^[a-z0-9_]+$ (lowercase, digits, underscore)")
    app_dir = os.path.join(base_dir, appid)
    os.makedirs(app_dir, exist_ok=True)
    result = run_ufbt(["create", f"APPID={appid}"], cwd=app_dir, timeout=300)
    result["app_dir"] = app_dir
    result["manifest"] = read_manifest(app_dir)
    return result


def build_app(app_dir: str) -> dict:
    """Build the FAP in app_dir; returns build log + path to the produced .fap."""
    if not os.path.exists(os.path.join(app_dir, "application.fam")):
        raise FileNotFoundError(f"no application.fam in {app_dir}")
    result = run_ufbt([], cwd=app_dir, timeout=900)  # bare `ufbt` builds
    result["fap"] = find_fap(app_dir)
    result["manifest"] = read_manifest(app_dir)
    return result

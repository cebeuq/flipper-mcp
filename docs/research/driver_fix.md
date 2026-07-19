# Flipper Zero on Windows 11 — un-binding WinUSB ("Android ADB Interface") from `USB\VID_0483&PID_5740&MI_00` and restoring `usbser.sys` (COM port)

## 0. Diagnosis — confirmed live on this machine

The exact broken state was verified on this PC (read-only queries, no elevation needed):

| Property | Observed value |
|---|---|
| Instance ID | `USB\VID_0483&PID_5740&MI_00\6&28EDC802&0&0000` |
| Composite parent | `USB\VID_0483&PID_5740\FLIP_ALI5AREE` (service `usbccgp`, OK) |
| FriendlyName | `Android ADB Interface` |
| Class / GUID | `AndroidUsbDeviceClass` / `{3f966bd9-fa04-4ec5-991c-d326973b5128}` |
| Service (driver) | `WinUSB` (stack: `WINUSB` ← parent `usbccgp`) |
| Bad INF | **`oem89.inf`** (original name `android_winusb.inf`, provider "Google, Inc.", v16.0.0.0, 04/28/2016, signed "Euro - Server s.r.o." — a repacked "universal ADB driver") |
| Hardware IDs | `USB\VID_0483&PID_5740&REV_0100&MI_00`, `USB\VID_0483&PID_5740&MI_00` |
| Compatible IDs | `USB\Class_02&SubClass_02&Prot_00`, `USB\Class_02&SubClass_02`, … (CDC ACM) |
| `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` | empty → no COM port exists |

**Why Windows keeps picking the wrong driver:** `pnputil /enum-devices /instanceid "…" /drivers` shows both `oem89.inf` (Best-ranked / Installed) and inbox `usbser.inf` (Outranked) matched on the *same* compatible ID `USB\Class_02&SubClass_02` with the *same* rank `00FF2004`. The tie is broken by driver date/version: 2016 (Google) beats the symbolic inbox date 06/21/2006. **Therefore unplug/replug or plain device uninstall will NOT fix it — Windows re-picks the ADB driver every time until `oem89.inf` is deleted from the driver store, or you manually pick usbser.** Note: since MI_00 is an IAD-grouped CDC *function* (interface 0 = CDC control + interface 1 = CDC data as one child PDO), there is no separate `MI_01` devnode — WinUSB currently owns the bulk endpoints too (relevant for the pyusb fallback, §4).

---

## 1. Cleanest GUI fix (Device Manager)

Requires an administrator account; Windows shows a UAC consent prompt when the change is applied if Device Manager isn't already elevated.

1. Plug in the Flipper (normal mode, not DFU). Open **Device Manager** (`Win+X` → Device Manager, or run `devmgmt.msc`).
2. Expand the ADB category (shows as **"Android Device"**, **"Android Phone"**, or **"AndroidUsbDeviceClass"**) → right-click **"Android ADB Interface"** → **Update driver**.
3. Choose **"Browse my computer for drivers"**.
4. Choose **"Let me pick from a list of available drivers on my computer"**.
5. Keep **"Show compatible hardware"** CHECKED. Because the device reports compatible ID `USB\Class_02&SubClass_02`, the list will contain both:
   - `Android ADB Interface` (Google, Inc., version 16.0.0.0) ← current, wrong
   - **`USB Serial Device`** (Microsoft, version 10.0.26100.x, driver date **6/21/2006**) ← **pick this one**
   
   The 6/21/2006 date is normal — all Windows inbox drivers carry that symbolic date; the version number is the real one. If two Microsoft "USB Serial Device" entries appear, pick the highest version.
6. Click **Next** → driver installs → the device jumps to **Ports (COM & LPT)** as **"USB Serial Device (COMx)"**.
7. Verify: `Ports (COM & LPT)` shows `USB Serial Device (COM5)` (number varies) and qFlipper/pyserial now see it.

**Important:** this manual pick wins only for this device instance. To prevent Windows re-binding ADB after a future re-enumeration (different USB port ⇒ new instance ID), also delete `oem89.inf` from the driver store (§2.2). Alternatively, Zadig itself can do the GUI fix: Zadig → Options → List All Devices → select the Flipper interface → choose **"USB Serial (CDC)"** as target driver → Replace Driver.

---

## 2. Command-line / scriptable fixes

### 2.1 Enumerate current state (no elevation required)

```powershell
# Which driver is bound right now + all candidate drivers with ranking:
pnputil /enum-devices /deviceid "USB\VID_0483&PID_5740&MI_00" /drivers /stack

# Or with the full instance ID:
pnputil /enum-devices /instanceid "USB\VID_0483&PID_5740&MI_00\6&28EDC802&0&0000" /drivers /stack

# List third-party driver packages in the driver store (find the oem#.inf):
pnputil /enum-drivers
pnputil /enum-drivers /class AndroidUsbDeviceClass    # narrower

# PowerShell equivalent — get the exact instance ID and offending INF programmatically:
$dev = Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_0483&PID_5740&MI_00*'
$inf = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_DriverInfPath').Data
$dev.InstanceId; $inf   # -> oem89.inf on this machine
```

Windows 11 `pnputil /enum-devices` supports `/instanceid`, `/deviceid` (filter by hardware/compatible ID), `/drivers` (matching + installed drivers with rank), `/stack` (driver stack/service), `/services`, `/properties`, `/problem` — all verified present on this build.

### 2.2 The fix: delete the bad driver package, remove the device, rescan (Administrator required)

`pnputil` **cannot** directly assign a chosen INF to a chosen device — there is no "update-device-with-this-inf" verb. `/add-driver x.inf /install` installs a package on all *matching* devices but ranking still decides the winner; `/remove-device` deletes the devnode; `/restart-device` just restarts it with the *same* driver (useless here). The correct pnputil strategy is: **remove the competing package so inbox `usbser.inf` becomes the only match**, then force re-enumeration:

```powershell
# ELEVATED PowerShell:

# 1) Identify device + bad INF (as in 2.1)
$dev = Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_0483&PID_5740&MI_00*'
$inf = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_DriverInfPath').Data  # oem89.inf

# 2) Delete the package from the driver store AND uninstall it from devices using it.
#    /uninstall = detach from live devices; /force = proceed even though it's in use.
pnputil /delete-driver $inf /uninstall /force

# 3) Remove the stale devnode and rescan (or just unplug/replug the cable):
pnputil /remove-device "$($dev.InstanceId)"
pnputil /scan-devices

# 4) Verify (5–10 s later): service must be usbser, class Ports, and SERIALCOMM populated:
pnputil /enum-devices /deviceid "USB\VID_0483&PID_5740&MI_00" /stack
Get-ItemProperty 'HKLM:\HARDWARE\DEVICEMAP\SERIALCOMM'
[System.IO.Ports.SerialPort]::GetPortNames()
```

Why this works: with `oem89.inf` gone, the only remaining match for compatible ID `USB\Class_02&SubClass_02` is inbox `C:\Windows\INF\usbser.inf` (Microsoft, class Ports `{4d36e978-e325-11ce-bfc1-08002be10318}`), so PnP installs "USB Serial Device (COMx)" automatically. Inbox drivers cannot be deleted by `pnputil`, so nothing can go missing. Caution: if that same universal-ADB package also serves a real Android phone you use, deleting it breaks ADB for the phone until reinstalled — check `pnputil /enum-drivers /devices` first.

GUI equivalent of step 2–3: Device Manager → right-click "Android ADB Interface" → **Uninstall device** → tick **"Attempt to remove the driver for this device"** → Uninstall → **Action ▸ Scan for hardware changes**. (The checkbox removes the oem INF only if no other device uses it.)

### 2.3 `devcon.exe` alternative

`devcon` is **not shipped with Windows 11** — it comes with the WDK (`C:\Program Files (x86)\Windows Kits\10\Tools\<arch>\devcon.exe`). Unlike pnputil, it CAN force a specific INF onto matching devices:

```bat
:: Elevated cmd:
devcon update C:\Windows\INF\usbser.inf "USB\VID_0483&PID_5740&MI_00"
:: other useful verbs:
devcon find "USB\VID_0483&PID_5740*"
devcon remove "@USB\VID_0483&PID_5740&MI_00\6&28EDC802&0&0000"
devcon rescan
```

`devcon update` performs a forced install of the named INF on every device whose hardware ID matches — this is the one-liner that pnputil lacks. Still delete `oem89.inf` afterwards or the ADB driver may win again on the next fresh enumeration.

### 2.4 Direct registry editing — possible, but do NOT rely on it

The device's Enum key (verified on this machine):

```
HKLM\SYSTEM\CurrentControlSet\Enum\USB\VID_0483&PID_5740&MI_00\6&28edc802&0&0000
    Service    = "WinUSB"                                   -> would need "usbser"
    ClassGUID  = "{3f966bd9-fa04-4ec5-991c-d326973b5128}"   -> would need "{4d36e978-e325-11ce-bfc1-08002be10318}" (Ports)
    Driver     = "{3f966bd9-...}\0000"                      -> points at the software key HKLM\SYSTEM\CurrentControlSet\Control\Class\{ClassGUID}\00nn
    Device Parameters\PortName                              -> "COMx" (created by the Ports class installer, currently absent)
```

Why hand-editing is a bad idea:
- **ACLs:** the `Enum` tree is writable only by SYSTEM. Even elevated regedit/PowerShell gets *Access denied* unless you take ownership or run as SYSTEM (`psexec -s regedit`). Taking ownership of Enum keys is itself a way to break PnP.
- **Incomplete install:** flipping `Service`/`ClassGUID` skips everything `usbser.inf`'s DDInstall section does: creating the Ports software key, and — critically — the **msports** class installer assigning `PortName=COMx` (allocated from the COM Name Arbiter bitmap at `HKLM\SYSTEM\CurrentControlSet\Control\COM Name Arbiter\ComDB`) and populating `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` when usbser starts. Result of a hand edit: usbser may load but with no/garbage COM name; pyserial still sees nothing.
- **UpperFilters:** none are needed. Modern (Win10/11) `usbser.inf` does not use `serenum` or any filter driver — do not add `UpperFilters` values; if a leftover `UpperFilters=serenum` exists on the device key, delete it, since serenum no longer ships.

Verdict: registry surgery "works" only as service rebinding, not as a full install. Use §2.2 (or devcon) instead; the INF-based path does all of the above atomically.

---

## 3. Elevation requirements matrix

| Action | Elevation? |
|---|---|
| `pnputil /enum-devices`, `/enum-drivers`, `Get-PnpDevice`, `Get-PnpDeviceProperty` | **No** |
| Read `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM`, read Enum keys | **No** |
| `pnputil /delete-driver`, `/add-driver`, `/remove-device`, `/restart-device`, `/disable-device`, `/enable-device` | **Yes (Administrator)** — fail with access denied otherwise |
| `pnputil /scan-devices` | Usually works non-elevated; run elevated as part of the fix script anyway |
| Device Manager driver update/uninstall | Administrator account; UAC consent on apply |
| `devcon update/remove` | **Yes** |
| Writing `HKLM\SYSTEM\CurrentControlSet\Enum\...` | **Beyond admin — SYSTEM only** (e.g. `psexec -s`) |
| pyusb/libusb fallback (§4), pyserial (§5) | **No** — WinUSB and COM ports are user-mode accessible |

Detect elevation in PowerShell:

```powershell
$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
```

In a script: put `#Requires -RunAsAdministrator` at the top (hard-fails if not elevated). Self-elevate: `Start-Process powershell -Verb RunAs -ArgumentList '-File', $PSCommandPath`. From cmd/Python: `whoami /groups | findstr S-1-16-12288` (High Mandatory Level) or in Python `ctypes.windll.shell32.IsUserAnAdmin()`.

---

## 4. Fallback WITHOUT fixing the driver: pyusb + libusb over WinUSB

**Feasible, confirmed by the observed topology.** Flipper's CDC function uses an IAD, so usbccgp exposes interface 0 (CDC Communications, class 0x02) *and* interface 1 (CDC Data, class 0x0A, with the bulk IN/OUT endpoints) as the single `MI_00` child — the very devnode WinUSB is bound to. libusb speaks WinUSB natively, so pyusb can open the device, claim the data interface, and exchange the same CLI/RPC byte stream usbser would carry. No elevation, no driver change.

Setup: `pip install pyusb libusb-package` (`libusb-package` bundles `libusb-1.0.dll`; otherwise drop the DLL next to python.exe or on PATH).

```python
import usb.core, usb.util
import libusb_package  # provides the libusb backend DLL on Windows
import usb.backend.libusb1

be  = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
dev = usb.core.find(idVendor=0x0483, idProduct=0x5740, backend=be)
if dev is None:
    raise SystemExit("Flipper not found")

# Do NOT call dev.set_configuration() — device is already configured by usbccgp,
# and re-configuring a composite child fails on Windows.
cfg = dev.get_active_configuration()

# CDC Data interface (class 0x0A) carries the bulk endpoints:
data_if = usb.util.find_descriptor(cfg, bInterfaceClass=0x0A)
comm_if = usb.util.find_descriptor(cfg, bInterfaceClass=0x02)  # CDC control
usb.util.claim_interface(dev, data_if.bInterfaceNumber)

ep_out = usb.util.find_descriptor(data_if, custom_match=lambda e:
    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
ep_in  = usb.util.find_descriptor(data_if, custom_match=lambda e:
    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
print(f"bulk OUT=0x{ep_out.bEndpointAddress:02x}  bulk IN=0x{ep_in.bEndpointAddress:02x}")

# CDC SET_CONTROL_LINE_STATE: assert DTR|RTS on the *control* interface.
# Flipper gates CLI output on DTR — without this you may read nothing.
dev.ctrl_transfer(0x21, 0x22, 0x0003, comm_if.bInterfaceNumber, None)

ep_out.write(b"\r\n")                       # poke the CLI
try:
    while True:
        chunk = ep_in.read(512, timeout=300)  # read until timeout drains the banner/prompt
        print(bytes(chunk).decode(errors="replace"), end="")
except usb.core.USBTimeoutError:
    pass

ep_out.write(b"device_info\r")              # any CLI command; RPC: b"start_rpc_session\r"
```

Caveats:
- **Interfaces:** write/read only on the **data** interface's bulk endpoints; the comm interface's interrupt IN endpoint just carries CDC notifications — ignore it. Endpoint addresses vary with firmware/mode (dual-CDC "USB channel" mode adds a second CDC pair), so always discover them as above rather than hardcoding.
- **DTR is load-bearing:** the `ctrl_transfer(0x21, 0x22, 0x0003, ...)` line replaces what usbser/pyserial does with `dtr=True`. Send `0x0000` to drop the session cleanly on exit, then `usb.util.release_interface(dev, data_if.bInterfaceNumber)` and `usb.util.dispose_resources(dev)`.
- **Packetization:** bulk EPs are 64-byte full-speed packets; a read returns at most what's queued — loop with timeouts. When writing exactly 64·n bytes of RPC data, some stacks need a ZLP (`ep_out.write(b"")`) to flush; the CLI's `\r`-terminated lines never hit this.
- **Exclusivity:** only one process can claim the interface; close qFlipper first (it can't use the device anyway while WinUSB is bound). This whole fallback stops working the moment you fix the driver (usbser is not libusb-accessible) — it's a stopgap, not a destination.

---

## 5. Detecting the Flipper COM port from Python once fixed (pyserial)

```python
from serial.tools import list_ports

def find_flipper_port():
    for p in list_ports.comports():
        if p.vid == 0x0483 and p.pid == 0x5740:
            return p.device          # e.g. "COM5"
    return None

# equivalent one-liner using hwid matching:
port = next(list_ports.grep(r"VID:PID=0483:5740"), None)  # ListPortInfo or None
```

`p.serial_number` contains the Flipper's name-derived serial (`FLIP_ALI5AREE` on this device) if you must disambiguate multiple Flippers. Then `serial.Serial(port, timeout=1)` — baudrate is irrelevant for USB CDC; pyserial asserts DTR by default, which starts the CLI. Note: in DFU/recovery mode the Flipper enumerates as PID `0xDF11` (no COM port — that's normal, not this bug).

**Recommended order:** §2.2 elevated script (delete `oem89.inf` → remove device → rescan) is the complete, permanent, scriptable fix; §1 GUI pick fixes this instance but leaves the bad INF able to win again; §4 is the no-admin stopgap; §2.4 registry editing is a last resort that should be avoided.
<#
.SYNOPSIS
    Restore the Flipper Zero's USB serial (COM) port on Windows.

.DESCRIPTION
    On this machine the Flipper's CDC interface (USB\VID_0483&PID_5740&MI_00) is
    bound to WinUSB via Google's universal ADB driver (android_winusb.inf), so no
    COM port exists. flipper-mcp works fine over raw WinUSB without this fix. Run
    this ONLY if you also want qFlipper / `ufbt launch` / other tools that need a
    real COM port.

    By default this script only DIAGNOSES (no changes). Pass -Apply to fix it:
    it deletes the offending driver package from the driver store and re-scans, so
    Windows re-installs the in-box usbser.sys ("USB Serial Device (COMx)").

    WARNING: the offending package is a *generic* Android ADB/WinUSB driver. If you
    use ADB with an Android phone that relies on this same generic driver, deleting
    it will break that until you reinstall it. Prefer the manual Device Manager
    method (see README) if you are unsure.

.PARAMETER Apply
    Actually perform the fix (requires Administrator; the script self-elevates).
#>
[CmdletBinding()]
param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$VID_PID = 'USB\VID_0483&PID_5740&MI_00'

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Host "== Flipper Zero driver diagnosis ==" -ForegroundColor Cyan

$dev = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object InstanceId -like "$VID_PID*" | Select-Object -First 1
if (-not $dev) {
    Write-Host "Flipper CDC interface not found. Is it plugged in and powered on?" -ForegroundColor Yellow
    $ports = [System.IO.Ports.SerialPort]::GetPortNames()
    if ($ports) { Write-Host "Existing COM ports: $($ports -join ', ')" }
    return
}

$inf = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_DriverInfPath' -ErrorAction SilentlyContinue).Data
$svc = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_Service' -ErrorAction SilentlyContinue).Data
Write-Host "  InstanceId : $($dev.InstanceId)"
Write-Host "  Friendly   : $($dev.FriendlyName)"
Write-Host "  Service    : $svc"
Write-Host "  Driver INF : $inf"

$serial = [System.IO.Ports.SerialPort]::GetPortNames()
if ($svc -eq 'usbser' -or $serial) {
    Write-Host "Looks healthy: usbser is bound / COM ports present ($($serial -join ', '))." -ForegroundColor Green
    if (-not $Apply) { return }
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "To FIX (re-run with -Apply, or do it by hand in Device Manager):" -ForegroundColor Cyan
    Write-Host "  Device Manager -> '$($dev.FriendlyName)' -> Update driver ->"
    Write-Host "  Browse -> Let me pick -> 'USB Serial Device' -> Next."
    Write-Host ""
    Write-Host "  Scripted:  .\fix-flipper-driver.ps1 -Apply"
    Write-Host "  (deletes '$inf' from the driver store, then re-scans)"
    return
}

if (-not (Test-Admin)) {
    Write-Host "Elevating (approve the UAC prompt)..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList @(
        '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Apply')
    return
}

Write-Host ""
Write-Host "Applying fix (deleting $inf, removing device, re-scanning)..." -ForegroundColor Cyan
& pnputil /delete-driver $inf /uninstall /force
& pnputil /remove-device $dev.InstanceId
& pnputil /scan-devices
Start-Sleep -Seconds 4

$serial = [System.IO.Ports.SerialPort]::GetPortNames()
if ($serial) {
    Write-Host "Success. COM ports now present: $($serial -join ', ')" -ForegroundColor Green
} else {
    Write-Host "No COM port yet. Unplug/replug the Flipper, or use the Device Manager method." -ForegroundColor Yellow
}

# Installs rackmon as a Windows service using NSSM (https://nssm.cc).
# The service starts before anyone logs in and restarts itself if it crashes.
#
# 1. Download nssm (nssm.cc/download), unzip, copy win64\nssm.exe to C:\rackmon\
# 2. Right-click PowerShell -> Run as Administrator
# 3. cd C:\rackmon\scripts\windows ; .\install_service.ps1

$root   = "C:\rackmon"
$python = "$root\.venv\Scripts\python.exe"
$nssm   = "$root\nssm.exe"

if (-not (Test-Path $nssm))   { Write-Error "nssm.exe not found at $nssm — see comments above"; exit 1 }
if (-not (Test-Path $python)) { Write-Error "venv python not found at $python — run the setup steps in docs\SETUP.md first"; exit 1 }

New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

& $nssm install RackMon $python "-m" "rackmon" "--config" "$root\config\config.yaml"
& $nssm set RackMon AppDirectory $root
& $nssm set RackMon DisplayName "RackMon dashboards"
& $nssm set RackMon Description "Livestream rack monitoring dashboards (screens 1-3)"
& $nssm set RackMon Start SERVICE_AUTO_START

# auto-restart on crash, 5s delay
& $nssm set RackMon AppExitAction Restart
& $nssm set RackMon AppRestartDelay 5000

# log files with rotation (10 MB)
& $nssm set RackMon AppStdout "$root\logs\rackmon.log"
& $nssm set RackMon AppStderr "$root\logs\rackmon.err.log"
& $nssm set RackMon AppRotateFiles 1
& $nssm set RackMon AppRotateOnline 1
& $nssm set RackMon AppRotateBytes 10485760

& $nssm start RackMon
Write-Host ""
Write-Host "Done. Check http://localhost:8080/screen1 in a browser."
Write-Host "Manage with:  nssm restart RackMon   /  nssm stop RackMon  /  services.msc"

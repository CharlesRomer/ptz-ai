# One-command first-time setup on the mini PC.
# Right-click PowerShell -> Run as Administrator, then:
#   cd C:\rackmon
#   powershell -ExecutionPolicy Bypass -File scripts\windows\setup.ps1
#
# It creates the Python environment, installs rackmon, and puts a starter
# config in place. It does NOT need git — download the project as a ZIP.

$root = "C:\rackmon"
if ((Get-Location).Path -ne $root) {
    Write-Host "NOTE: expected to run from $root — paths in the other scripts assume it." -ForegroundColor Yellow
}

# 1. find Python 3.11+
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error ("Python not found. Install it from python.org/downloads " +
        "and TICK 'Add python.exe to PATH' in the installer, then re-run this.")
    exit 1
}
$ver = & python -c "import sys; print('{}.{}'.format(*sys.version_info[:2]))"
Write-Host "Found Python $ver"
if ([version]$ver -lt [version]"3.11") {
    Write-Error "Python 3.11 or newer is required (found $ver)."
    exit 1
}

# 2. virtual environment + install
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment…"
    python -m venv .venv
}
Write-Host "Installing rackmon and its libraries (takes a minute)…"
& .venv\Scripts\pip install -q -e .
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed — see output above."; exit 1 }

# 3. starter config
if (-not (Test-Path "config\config.yaml")) {
    Copy-Item "config\config.example.yaml" "config\config.yaml"
    Write-Host "Created config\config.yaml from the example." -ForegroundColor Green
} else {
    Write-Host "config\config.yaml already exists — leaving it alone."
}

Write-Host ""
Write-Host "Setup done. Next steps:" -ForegroundColor Green
Write-Host "  1. Test the demo:   .venv\Scripts\python -m rackmon --mock"
Write-Host "     then open http://localhost:8080/screen1 in a browser"
Write-Host "  2. Fill in YOUR values:   notepad config\config.yaml"
Write-Host "     (what to gather: docs\GATHER-FIRST.md)"
Write-Host "  3. Install as auto-starting service:  scripts\windows\install_service.ps1"
Write-Host "  4. Kiosk screens:  docs\KIOSK.md"

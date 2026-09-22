# Relaunches any kiosk window that has died (crashed Chrome, closed by
# accident, etc). Schedule it every 5 minutes:
#   Task Scheduler -> Create Basic Task -> repeat every 5 minutes ->
#   powershell -ExecutionPolicy Bypass -File C:\rackmon\scripts\windows\kiosk_watchdog.ps1

$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$flags  = "--kiosk --noerrdialogs --disable-session-crashed-bubble --disable-infobars"

# Keep these in sync with launch_kiosks.bat
$kiosks = @(
    @{ dir = "C:\rackmon\kiosk1"; pos = "1920,0"; url = "http://localhost:8080/screen1" },
    @{ dir = "C:\rackmon\kiosk2"; pos = "2944,0"; url = "http://localhost:8080/screen2" },
    @{ dir = "C:\rackmon\kiosk3"; pos = "3968,0"; url = "http://localhost:8080/screen3" }
)

foreach ($k in $kiosks) {
    # each kiosk has a unique --user-data-dir, so its Chrome processes
    # are identifiable by command line
    $running = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
        Where-Object { $_.CommandLine -like "*$($k.dir)*" }
    if (-not $running) {
        Write-Host "Kiosk $($k.url) not running - relaunching"
        Start-Process $chrome -ArgumentList "$flags --user-data-dir=$($k.dir) --window-position=$($k.pos) --app=$($k.url)"
        Start-Sleep -Seconds 2
    }
}

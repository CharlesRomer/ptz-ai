# Prints every display's position and size so you can fill in the
# --window-position values in launch_kiosks.bat.
# Run:  powershell -ExecutionPolicy Bypass -File find_monitors.ps1

Add-Type -AssemblyName System.Windows.Forms

Write-Host "Displays found:"
$i = 0
foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) {
    $b = $screen.Bounds
    $primary = if ($screen.Primary) { " (primary)" } else { "" }
    Write-Host ("  Display {0}{1}: position X={2} Y={3}   size {4}x{5}   [{6}]" -f
        $i, $primary, $b.X, $b.Y, $b.Width, $b.Height, $screen.DeviceName)
    $i++
}
Write-Host ""
Write-Host "The three 7-inch screens are usually the 1024x600 ones."
Write-Host "Use each screen's X,Y as --window-position=X,Y in launch_kiosks.bat."
Write-Host "Tip: to tell the screens apart, drag a window around in Windows"
Write-Host "display settings (System -> Display -> Identify)."

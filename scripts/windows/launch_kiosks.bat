@echo off
rem Opens the three dashboards as fullscreen Chrome kiosks, one per touchscreen.
rem
rem Put a SHORTCUT to this file in the Startup folder (Win+R -> shell:startup)
rem and enable Windows auto-logon so it runs after every reboot.
rem
rem >>> EDIT THE --window-position VALUES BELOW <<<
rem Run find_monitors.ps1 to get each 7" screen's X,Y origin, then put those
rem coordinates here. Each kiosk MUST have its own --user-data-dir, otherwise
rem Chrome reuses one process and ignores the positions.

rem wait for the DisplayLink screens and the RackMon service to come up
timeout /t 20 /nobreak >nul

set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
set FLAGS=--kiosk --noerrdialogs --disable-session-crashed-bubble --disable-infobars --autoplay-policy=no-user-gesture-required

start "" %CHROME% %FLAGS% --user-data-dir=C:\rackmon\kiosk1 --window-position=1920,0 --app=http://localhost:8080/screen1
timeout /t 3 /nobreak >nul
start "" %CHROME% %FLAGS% --user-data-dir=C:\rackmon\kiosk2 --window-position=2944,0 --app=http://localhost:8080/screen2
timeout /t 3 /nobreak >nul
start "" %CHROME% %FLAGS% --user-data-dir=C:\rackmon\kiosk3 --window-position=3968,0 --app=http://localhost:8080/screen3

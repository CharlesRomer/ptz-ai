@echo off
cd /d C:\ptz-ai
echo Downloading updates from Mac...
curl -o server.js http://192.168.100.100:8080/server.js
curl -o public\index.html http://192.168.100.100:8080/public/index.html
curl -o lib\atem.js http://192.168.100.100:8080/lib/atem.js
curl -o lib\obs.js http://192.168.100.100:8080/lib/obs.js
echo.
echo Restarting server...
taskkill /F /IM node.exe 2>nul
timeout /t 2 /nobreak >nul
start "PTZ Camera Controller" node server.js
echo.
echo Done! Check localhost:3000
pause

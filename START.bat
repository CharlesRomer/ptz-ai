@echo off
cd /d "%~dp0"
title PTZ Camera Controller
echo Starting PTZ Camera Controller (with auto-update)...
echo The app will open in your browser automatically.
echo Keep this window open while using the app.
echo.
start http://localhost:3000
node updater.js

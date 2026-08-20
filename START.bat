@echo off
cd /d "%~dp0"
title PTZ Camera Controller
echo Starting PTZ Camera Controller...
start http://localhost:3000/gamepad.html
node updater.js

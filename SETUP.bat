@echo off
cd /d "%~dp0"
title PTZ Camera Controller - Setup
echo.
echo ============================================
echo   PTZ Camera Controller - First Time Setup
echo ============================================
echo.

:: Check for Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Node.js is not installed.
    echo.
    echo Opening the Node.js download page now...
    echo   1. Download the LTS version ^(big green button^)
    echo   2. Run the installer with all default settings
    echo   3. Come back and double-click SETUP.bat again
    echo.
    start https://nodejs.org
    pause
    exit /b
)

echo Node.js found:
node --version

:: Check for Git
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Git is not installed.
    echo Opening the Git download page now...
    echo   1. Download and install with all default settings
    echo   2. Come back and double-click SETUP.bat again
    echo.
    start https://git-scm.com
    pause
    exit /b
)

echo Git found:
git --version

:: Install dependencies
echo.
echo Installing dependencies...
npm install

:: Check for .env
if not exist .env (
    echo.
    echo ============================================
    echo   IMPORTANT: .env file not found
    echo ============================================
    echo Copy the .env file from the SD card into this folder,
    echo then double-click SETUP.bat again.
    echo.
    pause
    exit /b
)

echo.
echo All good! Starting PTZ Camera Controller...
echo Opening browser to http://localhost:3000
echo.
start http://localhost:3000
node updater.js

@echo off
rem Starts the rackmon backend by hand (for testing).
rem For unattended auto-start use install_service.ps1 (NSSM) or rackmon_task.xml.
cd /d C:\rackmon
call .venv\Scripts\activate.bat
python -m rackmon --config C:\rackmon\config\config.yaml
pause

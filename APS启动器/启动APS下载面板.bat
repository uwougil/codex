@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo Python was not found in PATH. Please install Python or add it to PATH.
  pause
  exit /b 1
)

python "%~dp0prl_downloader_webui.py"

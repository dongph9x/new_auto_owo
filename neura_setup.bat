@echo off
setlocal enabledelayedexpansion
title NeuraSelf-UwU Setup
cd /d "%~dp0"
chcp 65001 >nul

set "PYTHON_VER=3.10.11"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VER%/python-%PYTHON_VER%-amd64.exe"

color 0B
echo.
echo  [SYSTEM] Initializing NeuraSelf-UwU Auto-Setup...
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] WARNING: Script is not running as Administrator.
    echo  [!] Automatic Python installation might fail.
    echo.
)


set "PY_CMD="
py -3.10 --version >nul 2>&1 && set "PY_CMD=py -3.10"
if not defined PY_CMD (
    python --version >nul 2>&1 && (
        for /f "tokens=2" %%v in ('python --version 2^>^&1') do (
            echo %%v | findstr /r "^3\.10\." >nul && set "PY_CMD=python"
        )
    )
)
if not defined PY_CMD (
    python3 --version >nul 2>&1 && (
        for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do (
            echo %%v | findstr /r "^3\.10\." >nul && set "PY_CMD=python3"
        )
    )
)

if not defined PY_CMD (
    echo  [!] Python 3.10 not found. Starting Auto-Installation...
    echo  [#] Downloading Python Installer...
    curl -L -o py_inst.exe %PYTHON_URL%
    if !errorlevel! neq 0 (
        echo  [X] Download failed. Please install Python 3.10 manually.
        pause
        exit /b 1
    )
    echo  [#] Installing Python - please wait...
    start /wait py_inst.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    if !errorlevel! neq 0 (
        echo  [X] Installation failed or cancelled.
        del py_inst.exe
        pause
        exit /b 1
    )
    del py_inst.exe
    echo  [OK] Python installation completed.
    

    set "PY_CMD=python"
) else (
    echo  [OK] Found Python 3.10: !PY_CMD!
)

echo.
echo  [#] Environment verified. Launching Neura Setup...
timeout /t 2 >nul
!PY_CMD! neura_setup.py
if !errorlevel! neq 0 (
    echo  [X] Neura Setup exited with an error.
    pause
    exit /b 1
)

echo.
echo  [OK] Setup complete.
pause
exit /b 0

#!/bin/bash

clear
echo -e "\033[1;36mInitializing NeuraSelf-UwU Auto-Setup for Linux/Termux...\033[0m"
echo

if command -v python3.10 &>/dev/null; then
    PYTHON="python3.10"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo -e "\033[1;31m[X] Python not found. Please install Python 3.10+ manually.\033[0m"
    exit 1
fi

echo -e "\033[1;32m[OK] Found Python: $($PYTHON --version)\033[0m"

echo -e "\033[1;36m[#] Enviroment verified. Running Neura Setup...\033[0m"
sleep 2
$PYTHON neura_setup.py
exit 0

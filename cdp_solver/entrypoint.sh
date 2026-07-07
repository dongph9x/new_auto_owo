#!/bin/bash
set -e

Xvfb :99 -screen 0 1920x1080x16 -nolisten tcp &
XVFB_PID=$!

# Give Xvfb a moment to actually bind the display before Chrome tries to use it.
sleep 1

cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

exec python3 service.py

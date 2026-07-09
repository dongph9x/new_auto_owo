#!/bin/bash
set -e

DISPLAY_NUM=":99"
LOCK_FILE="/tmp/.X99-lock"
SOCKET_FILE="/tmp/.X11-unix/X99"
XVFB_PID=""

# If a stale lock/socket is left behind from a previous crash, clear it so Xvfb
# can bind cleanly. If an X server is already alive on :99, just reuse it.
if xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1; then
    echo "X display $DISPLAY_NUM already active. Reusing existing X server."
else
    if [ -f "$LOCK_FILE" ]; then
        LOCK_PID="$(tr -cd '0-9' < "$LOCK_FILE" || true)"
        if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" >/dev/null 2>&1; then
            echo "Xvfb lock exists with live PID $LOCK_PID. Reusing current X server."
        else
            echo "Removing stale Xvfb lock/socket for $DISPLAY_NUM."
            rm -f "$LOCK_FILE" "$SOCKET_FILE"
        fi
    fi

    if ! xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1; then
        Xvfb "$DISPLAY_NUM" -screen 0 1920x1080x16 -nolisten tcp &
        XVFB_PID=$!
    fi
fi

# Give Xvfb a moment to actually bind the display before Chrome tries to use it.
sleep 1

cleanup() {
    if [ -n "${XVFB_PID}" ]; then
        kill "$XVFB_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

exec python3 service.py

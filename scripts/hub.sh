#!/usr/bin/env bash
# Run the telemetry hub in the background, on the robot or on a Mac. It keeps running after the terminal or
# VS Code closes, until stopped.
#
#   scripts/hub.sh start     start it and print the address to open
#   scripts/hub.sh stop      stop it
#   scripts/hub.sh restart   stop it, then start it
#   scripts/hub.sh status    say whether it is running
#
# The hub is found by the port it listens on (HUB_PORT, default 8710), so one started by hand (VS Code F5, a
# terminal) is managed too; anything else on that port is never touched. On the robot it listens on the home
# network and reads the robot's own daemon, so anyone on the network can open the page, conversation transcripts
# included. Anywhere else it listens on this machine only and takes REACHY_HOST from the environment or .env.
# Log: $HUB_STATE_DIR/hub.log (default ~/.local/share/reachy-tools).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${HUB_PORT:-8710}"
STATE="${HUB_STATE_DIR:-$HOME/.local/share/reachy-tools}"
LOG_FILE="$STATE/hub.log"
PYTHON=.venv/bin/python
if [[ "$(uname)" == Linux ]]; then  # the robot
    export REACHY_HOST="${REACHY_HOST:-127.0.0.1}"
    HUB_HOST="${HUB_HOST:-0.0.0.0}"
fi
export HUB_HOST="${HUB_HOST:-127.0.0.1}" HUB_PORT="$PORT"

usage() { sed -n '4,7p' "$0" | sed 's/^# *//' >&2; exit 2; }

listening_pid() {  # whatever listens on the port, hub or not
    if command -v lsof >/dev/null; then
        lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1
    else
        ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -n 1 | cut -d= -f2
    fi
}

hub_pid() {  # the listener, if it is the hub
    local pid
    pid=$(listening_pid || true)
    [[ -n "$pid" ]] && ps -p "$pid" -o command= | grep -q -- "-m reachy_hub" && echo "$pid"
}

address() {
    if [[ "$HUB_HOST" == 0.0.0.0 ]]; then
        echo "http://reachy-mini.local:$PORT  (or http://$(hostname -I | awk '{print $1}'):$PORT)"
    else
        echo "http://$HUB_HOST:$PORT"
    fi
}

start() {
    local pid
    if pid=$(hub_pid); then
        echo "Already running (process $pid). Open $(address)"
        return 0
    fi
    if [[ -n "$(listening_pid || true)" ]]; then
        echo "Port $PORT is in use by something that is not the hub." >&2
        return 1
    fi
    [[ -x "$PYTHON" ]] || { echo "No project .venv: create it first (docs/development_setup.md)." >&2; return 1; }
    mkdir -p "$STATE"
    local detach=(nohup)
    command -v setsid >/dev/null && detach=(setsid nohup)  # macOS has no setsid
    "${detach[@]}" "$PYTHON" -m reachy_hub >"$LOG_FILE" 2>&1 </dev/null &
    for _ in $(seq 20); do
        hub_pid >/dev/null && { echo "Started. Open $(address)"; return 0; }
        sleep 0.25
    done
    echo "The hub did not start. Last lines of $LOG_FILE:" >&2
    tail -n 20 "$LOG_FILE" >&2
    return 1
}

stop() {
    local pid
    if ! pid=$(hub_pid); then
        echo "Not running."
        return 0
    fi
    kill "$pid"
    for _ in $(seq 50); do
        kill -0 "$pid" 2>/dev/null || { echo "Stopped."; return 0; }
        sleep 0.1
    done
    kill -9 "$pid"
    echo "Stopped (it had to be forced)."
}

status() {
    local pid
    if pid=$(hub_pid); then
        echo "Running (process $pid). Open $(address)"
    else
        echo "Not running. Start it with: scripts/hub.sh start"
        return 1
    fi
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    *) usage ;;
esac

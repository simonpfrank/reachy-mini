#!/usr/bin/env bash
# Run the telemetry hub on the robot in the background, viewable from any browser on the home network.
# It keeps running after the terminal or VS Code closes, until stopped or the robot restarts.
#
#   scripts/hub.sh start    start it and print the address to open
#   scripts/hub.sh stop     stop it
#   scripts/hub.sh status   say whether it is running
#
# While running, anyone on the home network can open the page, including conversation transcripts.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${HUB_PORT:-8710}"
STATE="$HOME/.local/share/reachy-tools"
PID_FILE="$STATE/hub.pid"
LOG_FILE="$STATE/hub.log"

usage() { sed -n '5,7p' "$0" | sed 's/^# *//' >&2; exit 2; }

running_pid() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid=$(cat "$PID_FILE")
    if tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q "reachy_hub"; then
        echo "$pid"
    else
        return 1
    fi
}

port_in_use() { ss -ltn | awk '{print $4}' | grep -q ":$PORT\$"; }

address() {
    local ip
    ip=$(hostname -I | awk '{print $1}')
    echo "http://reachy-mini.local:$PORT  (or http://$ip:$PORT)"
}

case "${1:-}" in
    start)
        if pid=$(running_pid); then
            echo "Already running (process $pid). Open $(address)"
            exit 0
        fi
        if port_in_use; then
            echo "Port $PORT is already in use, probably a hub started from VS Code (F5). Stop that first." >&2
            exit 1
        fi
        mkdir -p "$STATE"
        HUB_HOST=0.0.0.0 HUB_PORT="$PORT" REACHY_HOST=127.0.0.1 \
            setsid nohup .venv/bin/python -m reachy_hub >"$LOG_FILE" 2>&1 </dev/null &
        echo $! >"$PID_FILE"
        for _ in $(seq 20); do
            port_in_use && { echo "Started. Open $(address)"; exit 0; }
            sleep 0.25
        done
        echo "The hub did not start. Last lines of $LOG_FILE:" >&2
        tail -n 20 "$LOG_FILE" >&2
        exit 1
        ;;
    stop)
        if pid=$(running_pid); then
            kill "$pid"
            rm -f "$PID_FILE"
            echo "Stopped."
        else
            rm -f "$PID_FILE"
            echo "Not running."
        fi
        ;;
    status)
        if pid=$(running_pid); then
            echo "Running (process $pid). Open $(address)"
        else
            echo "Not running. Start it with: scripts/hub.sh start"
        fi
        ;;
    *)
        usage
        ;;
esac

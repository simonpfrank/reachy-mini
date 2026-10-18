#!/usr/bin/env bash
# Install or check the packages the robot tools need, in the conversation app's environment.
# Uses the same command Pollen's app manager uses to install app packages; no sudo needed.
#
#   scripts/tool_deps.sh install   install robot_tools/requirements.txt into /venvs/apps_venv, then check
#   scripts/tool_deps.sh check     confirm each package imports there
#
# Run install again if a Pollen update or reinstall ever replaces /venvs/apps_venv.
set -euo pipefail
cd "$(dirname "$0")/.."

APP_PYTHON="${APP_PYTHON:-/venvs/apps_venv/bin/python}"
REQUIREMENTS=robot_tools/requirements.txt

usage() { sed -n '5,6p' "$0" | sed 's/^# *//' >&2; exit 2; }

check() {
    "$APP_PYTHON" - <<'PY'
import importlib.metadata as metadata
import bs4

print(f"OK: beautifulsoup4 {metadata.version('beautifulsoup4')} is installed in the app environment.")
PY
}

case "${1:-}" in
    install)
        "$APP_PYTHON" -m pip install -r "$REQUIREMENTS"
        check
        ;;
    check)
        check || { echo "Missing: run scripts/tool_deps.sh install" >&2; exit 1; }
        ;;
    *)
        usage
        ;;
esac

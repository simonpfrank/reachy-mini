#!/usr/bin/env bash
# Manage the robot tools' API keys. The work is done by robot_tools/reachy_lib/keys.py, so it is the same on the
# robot (systemd-creds), a Mac (login Keychain) and Windows (scripts/keys.bat). Keys are never in Git. No sudo.
#
#   scripts/keys.sh add NAME      paste the key (hidden) and store it; replaces an existing one
#   scripts/keys.sh remove NAME   delete the key
#   scripts/keys.sh list          show stored key names, never the keys (robot only)
#   scripts/keys.sh check NAME    confirm the key is stored and readable, without showing it
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || { echo "No project .venv: create it first (docs/development_setup.md)." >&2; exit 1; }
exec "$PYTHON" "$ROOT/robot_tools/reachy_lib/keys.py" "$@"

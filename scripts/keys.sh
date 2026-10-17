#!/usr/bin/env bash
# Manage the robot tools' API keys. Each key is stored encrypted by systemd for the pollen user: a copy
# taken off the robot cannot be decrypted, and keys are never in Git. Run on the robot; no sudo needed.
#
#   scripts/keys.sh add NAME      paste the key (hidden) and store it; replaces an existing one
#   scripts/keys.sh remove NAME   delete the key
#   scripts/keys.sh list          show stored key names, never the keys
#   scripts/keys.sh check NAME    confirm the key decrypts, without showing it
set -euo pipefail

DIR="${REACHY_TOOLS_KEYS_DIR:-$HOME/.config/reachy_tools/keys}"

usage() { sed -n '5,8p' "$0" | sed 's/^# *//' >&2; exit 2; }

need_name() {
    [[ "${1:-}" =~ ^[a-z0-9_]+$ ]] || { echo "Give a key name: lower-case letters, digits or _ (e.g. tavily)." >&2; exit 2; }
}

check() {
    if systemd-creds --user --name="$1" decrypt "$DIR/$1.cred" - >/dev/null 2>&1; then
        echo "OK: the $1 key is stored and decrypts."
    else
        echo "Problem: the $1 key is missing or cannot be decrypted. Run: scripts/keys.sh add $1" >&2
        exit 1
    fi
}

case "${1:-}" in
    add)
        need_name "${2:-}"
        read -rsp "Paste the $2 key, then press Enter (it will not show): " key
        echo
        [[ -n "$key" ]] || { echo "No key entered; nothing stored." >&2; exit 1; }
        mkdir -p "$DIR"
        chmod 700 "$DIR"
        printf %s "$key" | systemd-creds --user encrypt --name="$2" - "$DIR/.$2.cred.new"
        unset key
        chmod 600 "$DIR/.$2.cred.new"
        mv "$DIR/.$2.cred.new" "$DIR/$2.cred"
        check "$2"
        ;;
    remove)
        need_name "${2:-}"
        [[ -f "$DIR/$2.cred" ]] || { echo "No $2 key is stored." >&2; exit 1; }
        rm -- "$DIR/$2.cred"
        echo "Removed the $2 key."
        ;;
    list)
        names=""
        [[ -d "$DIR" ]] && names=$(find "$DIR" -maxdepth 1 -name '*.cred' -printf '%f\n' | sed 's/\.cred$//' | sort)
        echo "${names:-No keys stored.}"
        ;;
    check)
        need_name "${2:-}"
        check "$2"
        ;;
    *)
        usage
        ;;
esac
